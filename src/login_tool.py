# login_tool.py
import os
import subprocess
import time
import sys
import urllib.parse
import urllib3
import winreg
import shlex
import tkinter as tk
from tkinter import ttk, messagebox

TEMPLATE_BASE = "http://10.17.8.18:801/eportal/portal/login"
TEMPLATE_QUERY = "callback=dr1003&login_method=1&user_account={user_account}&user_password={user_password}"

OPERATOR_SUFFIX = {
    "无": "",
    "电信": "@telecom",
    "移动": "@cmcc",
    "联通": "@unicom",
}


def build_url(account: str, password: str, operator: str):
    """拼接并始终 URL encode 的登录 URL"""
    suffix = OPERATOR_SUFFIX.get(operator, "")
    full_account = account + suffix

    enc_account = urllib.parse.quote_plus(full_account, safe="")
    enc_password = urllib.parse.quote_plus(password, safe="")

    query = TEMPLATE_QUERY.format(user_account=enc_account, user_password=enc_password)
    return f"{TEMPLATE_BASE}?{query}"


def get_network_adapters():
    """获取本机所有网络适配器 (名称, 状态)"""
    try:
        result = subprocess.run(
            ["netsh", "interface", "show", "interface"],
            capture_output=True,
            text=True,
            check=True,
        )
        lines = result.stdout.splitlines()
        adapters = []
        for line in lines[3:]:
            parts = line.split()
            if len(parts) >= 4:
                state = parts[0]  # e.g. Connected/Disconnected
                name = " ".join(parts[3:])
                adapters.append((name, state))
        return adapters
    except Exception:
        return []


def get_default_adapter():
    """返回默认选中的网卡（优先已连接的以太网/有线）"""
    adapters = get_network_adapters()
    if not adapters:
        return "以太网"
    connected = [name for name, state in adapters if state.lower() == "connected"]
    if connected:
        for prefer in ["以太网", "Ethernet"]:
            for c in connected:
                if prefer in c:
                    return c
        return connected[0]
    return adapters[0][0]


def restart_network(adapter_name: str):
    """模块级的重启网卡函数（无 GUI 依赖）"""
    try:
        subprocess.run(
            ["netsh", "interface", "set", "interface", adapter_name, "admin=disable"],
            check=True, capture_output=True, text=True
        )
        time.sleep(2)
        subprocess.run(
            ["netsh", "interface", "set", "interface", adapter_name, "admin=enable"],
            check=True, capture_output=True, text=True
        )
        return True, f"已重启网卡：{adapter_name}"
    except Exception as e:
        return False, str(e)


def install_autostart(account: str, password: str, operator: str, exe_path: str = None):
    """在 HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run 写入 exe + 参数"""
    if exe_path is None:
        exe_path = os.path.abspath(sys.argv[0])
    # 把每个参数用双引号包起来，防止空格或特殊字符
    quoted = lambda s: f'"{s}"'
    cmd = f'{quoted(exe_path)} {quoted(account)} {quoted(password)} {quoted(operator)}'

    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, "CampusNetAutoLogin", 0, winreg.REG_SZ, cmd)
        winreg.CloseKey(key)
        return True, "已安装自启动（Run 注册表）。"
    except Exception as e:
        return False, str(e)


def uninstall_autostart():
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE
        )
        try:
            winreg.DeleteValue(key, "CampusNetAutoLogin")
        except FileNotFoundError:
            pass
        winreg.CloseKey(key)
        return True, "已移除自启动项。"
    except Exception as e:
        return False, str(e)


def is_autostart_installed():
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_READ
        )
        try:
            val, _ = winreg.QueryValueEx(key, "CampusNetAutoLogin")
            winreg.CloseKey(key)
            return True, val
        except FileNotFoundError:
            winreg.CloseKey(key)
            return False, None
    except Exception:
        return False, None


class URLGeneratorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("江理校园网登录工具")
        try:
            self.iconphoto(True, tk.PhotoImage(file="logo.png"))
        except Exception:
            pass
        self.resizable(False, False)
        self.http = urllib3.PoolManager()
        self.setup_widgets()

    def setup_widgets(self):
        pad = {"padx": 8, "pady": 6}

        frm = ttk.Frame(self)
        frm.grid(row=0, column=0, sticky="nsew", **pad)

        ttk.Label(frm, text="账号:").grid(row=0, column=0, sticky="e")
        self.account_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.account_var, width=30).grid(
            row=0, column=1, columnspan=2, sticky="w"
        )

        ttk.Label(frm, text="密码:").grid(row=1, column=0, sticky="e")
        self.password_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.password_var, show="*", width=30).grid(
            row=1, column=1, columnspan=2, sticky="w"
        )

        ttk.Label(frm, text="运营商:").grid(row=2, column=0, sticky="e")
        self.operator_var = tk.StringVar(value="无")
        op_combo = ttk.Combobox(
            frm, textvariable=self.operator_var, state="readonly", width=27
        )
        op_combo["values"] = list(OPERATOR_SUFFIX.keys())
        op_combo.grid(row=2, column=1, columnspan=2, sticky="w")

        ttk.Label(frm, text="网卡:").grid(row=3, column=0, sticky="e")
        self.adapter_var = tk.StringVar()
        adapters = [name for name, _ in get_network_adapters()]
        if not adapters:
            adapters = ["以太网"]
        adapter_combo = ttk.Combobox(
            frm, textvariable=self.adapter_var, values=adapters, state="readonly", width=27
        )
        adapter_combo.grid(row=3, column=1, columnspan=2, sticky="w")
        default_adapter = get_default_adapter()
        if default_adapter in adapters:
            self.adapter_var.set(default_adapter)
        else:
            self.adapter_var.set(adapters[0])

        btn_frame = ttk.Frame(frm)
        btn_frame.grid(row=4, column=0, columnspan=3, pady=(8, 0))

        ttk.Button(btn_frame, text="登录", command=self.do_login).grid(row=0, column=0, padx=6)
        ttk.Button(btn_frame, text="安装/卸载自启动", command=self.toggle_autostart).grid(row=0, column=1, padx=6)

        # 显示当前自启状态
        installed, val = is_autostart_installed()
        status_text = "已安装" if installed else "未安装"
        self.status_label = ttk.Label(frm, text=f"自启动: {status_text}")
        self.status_label.grid(row=5, column=0, columnspan=3, pady=(6, 0))

    def build_current_url(self):
        """根据当前输入生成 URL"""
        account = self.account_var.get().strip()
        password = self.password_var.get()
        operator = self.operator_var.get()

        if not account:
            messagebox.showwarning("输入错误", "请填写账号。")
            return None
        return build_url(account, password, operator)

    def do_login(self):
        url = self.build_current_url()
        if not url:
            return
        try:
            r = self.http.request("GET", url, timeout=5.0)
            messagebox.showinfo(
                "登录结果",
                f"状态码: {r.status}\n响应内容:\n{r.data.decode(errors='ignore')[:300]}...",
            )
        except Exception as e:
            if messagebox.askyesno(
                "网络错误", f"请求失败: {e}\n是否尝试重启网卡并重试？"
            ):
                ok, msg = restart_network(self.adapter_var.get())
                if ok:
                    time.sleep(5)
                    try:
                        r = self.http.request("GET", url, timeout=5.0)
                        messagebox.showinfo(
                            "登录结果",
                            f"状态码: {r.status}\n响应内容:\n{r.data.decode(errors='ignore')[:300]}...",
                        )
                    except Exception as e2:
                        messagebox.showerror("错误", f"重启网卡后仍然失败: {e2}")
                else:
                    messagebox.showerror("错误", f"重启网卡失败: {msg}")

    def toggle_autostart(self):
        account = self.account_var.get().strip()
        password = self.password_var.get()
        operator = self.operator_var.get()

        if not account:
            messagebox.showwarning("输入错误", "请填写账号后再安装自启动。")
            return

        installed, val = is_autostart_installed()
        if installed:
            ok, msg = uninstall_autostart()
            if ok:
                messagebox.showinfo("卸载成功", msg)
            else:
                messagebox.showerror("错误", msg)
        else:
            exe_path = os.path.abspath(sys.argv[0])
            ok, msg = install_autostart(account, password, operator, exe_path=exe_path)
            if ok:
                messagebox.showinfo("安装成功", msg)
            else:
                messagebox.showerror("错误", msg)

        # 更新状态标签
        installed2, _ = is_autostart_installed()
        self.status_label.config(text=f"自启动: {'已安装' if installed2 else '未安装'}")


def run_cli(account: str, password: str, operator: str):
    """命令行模式：尝试登录（失败时尝试重启默认网卡再重试一次），并把结果打印出来。"""
    url = build_url(account, password, operator)
    http = urllib3.PoolManager()
    try:
        r = http.request("GET", url, timeout=5.0)
        print(f"Login attempt: status={r.status}")
        # 若需更多响应内容可打印 r.data
        return 0
    except Exception as e:
        print(f"第一次请求失败: {e}", file=sys.stderr)
        adapter = get_default_adapter()
        ok, msg = restart_network(adapter)
        if ok:
            time.sleep(5)
            try:
                r = http.request("GET", url, timeout=5.0)
                print(f"Retry after restarting adapter: status={r.status}")
                return 0
            except Exception as e2:
                print(f"重试失败: {e2}", file=sys.stderr)
                return 2
        else:
            print(f"重启网卡失败: {msg}", file=sys.stderr)
            return 3


if __name__ == "__main__":
    # 命令行模式：三个参数 -> 静默执行一次登录（可用于注册表 Run）
    if len(sys.argv) == 4:
        acct, pwd, op = sys.argv[1:4]
        exit_code = run_cli(acct, pwd, op)
        sys.exit(exit_code)
    else:
        app = URLGeneratorApp()
        app.mainloop()
