# eportal_client.py
# Windows only
import sys
import os
import time
import argparse
import json
import re
import tempfile
import socket
import threading
import logging
from urllib.parse import quote_plus

import requests

# Windows-specific
try:
    import winreg
    import win32crypt  # from pywin32
    from winotify import Notification, audio
except Exception as e:
    # If imports fail, we'll show friendly error later
    pass

APP_NAME = "eportal_client"
APP_FOLDER = os.path.join(os.getenv("APPDATA"), APP_NAME)
CONFIG_FILE = os.path.join(APP_FOLDER, "config.bin")
LOG_FILE = os.path.join(APP_FOLDER, "client.log")
LOGIN_CALLBACK = "dr1003"
LOGOUT_CALLBACK = "dr1004"

# login/logout url templates (use .format)
LOGIN_URL_TEMPLATE = ("http://10.17.8.18:801/eportal/portal/login?"
                      "callback={cb}&login_method=1&user_account={acct}&user_password={pwd}")
LOGOUT_URL_TEMPLATE = ("http://10.17.8.18:801/eportal/portal/logout?"
                       "callback={cb}&login_method=1&user_account=drcom&user_password=123&ac_logout=0&register_mode=1&wlan_user_ip={ip}")

# public connectivity check URL (simple, small)
CONNECT_CHECK_URL = "http://www.baidu.com/"  # china-friendly general site

# ensure app folder exists
os.makedirs(APP_FOLDER, exist_ok=True)

# logging
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(APP_NAME)
logger.info("Started")

# ---------- DPAPI helpers ----------
def dpapi_encrypt(data: bytes) -> bytes:
    """Encrypt bytes using Windows DPAPI (Current user scope)."""
    blob = win32crypt.CryptProtectData(data, None, None, None, None, 0)
    return blob

def dpapi_decrypt(blob: bytes) -> bytes:
    """Decrypt bytes encrypted by dpapi_encrypt."""
    descr, decrypted = win32crypt.CryptUnprotectData(blob, None, None, None, 0)
    return decrypted

def save_config_encrypted(cfg: dict):
    raw = json.dumps(cfg, ensure_ascii=False).encode("utf-8")
    enc = dpapi_encrypt(raw)
    with open(CONFIG_FILE, "wb") as f:
        f.write(enc)
    logger.info("Configuration saved (encrypted)")

def load_config_encrypted() -> dict:
    if not os.path.exists(CONFIG_FILE):
        return None
    with open(CONFIG_FILE, "rb") as f:
        blob = f.read()
    try:
        dec = dpapi_decrypt(blob)
        cfg = json.loads(dec.decode("utf-8"))
        return cfg
    except Exception as e:
        logger.exception("Failed to decrypt/load config")
        return None

# ---------- Windows autostart ----------
def register_run_key():
    """Add this exe to HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run"""
    try:
        exe_path = sys.executable if getattr(sys, "frozen", False) else os.path.abspath(sys.argv[0])
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{exe_path}" --run-from-startup')
        winreg.CloseKey(key)
        logger.info("Registered Run key for autostart")
    except Exception:
        logger.exception("Failed to register Run key")

# ---------- Toast helpers ----------
def show_toast(title: str, msg: str, launch_cmd: str = None, sound=True, duration="short"):
    """Show a toast; launch_cmd is a command-line string to pass when user clicks."""
    try:
        toast = Notification(app_id=APP_NAME, title=title, msg=msg, duration=duration)
        if sound:
            toast.set_audio(audio.Default, loop=False)
        if launch_cmd:
            # winotify expects a URI/command to launch. For simplicity, pass launch as-is.
            toast.add_actions(label="打开", launch=launch_cmd)
        toast.show()
        logger.info("Toast shown: %s - %s", title, msg)
    except Exception:
        logger.exception("Failed to show toast")

# ---------- Networking helpers ----------
def get_local_ip():
    """Get local LAN IP by opening UDP socket to an external address (doesn't send data)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        # fallback
        ip = socket.gethostbyname(socket.gethostname())
    finally:
        s.close()
    return ip

def is_connected(timeout=3):
    """Quick connectivity check to public site."""
    try:
        r = requests.get(CONNECT_CHECK_URL, timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False

def parse_callback_json(text: str):
    """
    Parse strings like: dr1003({...})
    Return Python dict or None.
    """
    m = re.search(r'^[^\(]*\((.*)\)\s*;*\s*$', text.strip(), re.S)
    if not m:
        # maybe already raw json
        try:
            return json.loads(text)
        except:
            return None
    inner = m.group(1)
    try:
        return json.loads(inner)
    except Exception:
        # sometimes it's JSONP with single quotes - try replace
        try:
            fixed = inner.replace("'", '"')
            return json.loads(fixed)
        except:
            return None

def attempt_login(username, password, operator):
    """Attempt to login and return (success_bool, parsed_response_text, parsed_json_or_none)."""
    acct = f"{username}@{operator}" if operator else username
    acct = quote_plus(acct)
    pwd = quote_plus(password)
    url = LOGIN_URL_TEMPLATE.format(cb=LOGIN_CALLBACK, acct=acct, pwd=pwd)
    logger.info("Attempting login to %s", url)
    try:
        r = requests.get(url, timeout=6)
        txt = r.text
        parsed = parse_callback_json(txt)
        ret_code = None
        if parsed and "ret_code" in parsed:
            ret_code = parsed.get("ret_code")
        # success when ret_code == 2 per your spec
        success = (ret_code == 2)
        return success, txt, parsed
    except Exception:
        logger.exception("Login attempt failed (exception)")
        return False, None, None

def attempt_logout():
    ip = get_local_ip()
    url = LOGOUT_URL_TEMPLATE.format(cb=LOGOUT_CALLBACK, ip=quote_plus(ip))
    logger.info("Attempting logout: %s", url)
    try:
        r = requests.get(url, timeout=6)
        return True, r.text
    except Exception:
        logger.exception("Logout attempt failed")
        return False, None

# ---------- Configuration mode ----------
def config_mode_interactive():
    print("=== EPortal 客户端配置模式 ===")
    username = input("用户名: ").strip()
    operator = input("运营商 (telecom/unicom/cmcc)（留空表示无）: ").strip()
    password = input("密码: ").strip()
    while True:
        try:
            interval = int(input("轮询间隔（秒，建议 >= 10）: ").strip())
            break
        except Exception:
            print("请输入一个整数秒数。")
    print("尝试登录……")
    ok, text, parsed = attempt_login(username, password, operator)
    if ok:
        # save
        cfg = {"username": username, "operator": operator, "password": password, "interval": interval}
        save_config_encrypted(cfg)
        register_run_key()
        print("登录成功，配置已保存并设置为开机自启（Run 注册表）。")
        logger.info("User configured successfully via interactive mode.")
    else:
        print("登录失败，请检查用户名/密码/运营商后重试。")
        logger.info("Interactive configuration login failed.")
    return ok

# ---------- Polling thread ----------
_stop_event = threading.Event()

def polling_loop(cfg):
    interval = max(5, int(cfg.get("interval", 60)))
    username = cfg.get("username")
    password = cfg.get("password")
    operator = cfg.get("operator", "")
    while not _stop_event.is_set():
        try:
            if is_connected():
                logger.info("Connectivity OK")
                # still try verifying campus portal by attempting a login check? The spec says "轮询检测是否正常连通网络，如果无法连通，则访问 login"
                # Here: if connected, we do nothing. If not connected, attempt login.
            else:
                logger.info("Connectivity DOWN - attempting login")
                ok, text, parsed = attempt_login(username, password, operator)
                if not parsed:
                    # failed parsing or no response, show toast to reconfigure
                    exe = sys.executable if getattr(sys, "frozen", False) else os.path.abspath(sys.argv[0])
                    launch = f'"{exe}" --config'
                    show_toast("登录异常", "无法登录校园网络，请点击重新配置。", launch_cmd=launch)
                else:
                    ret = parsed.get("ret_code")
                    if ret != 2:
                        exe = sys.executable if getattr(sys, "frozen", False) else os.path.abspath(sys.argv[0])
                        launch = f'"{exe}" --config'
                        show_toast("登录失败", f"登录返回 ret_code={ret}，请点击重新配置。", launch_cmd=launch)
                    else:
                        # success
                        # write response to temp file and set click to open it with notepad
                        tf = tempfile.NamedTemporaryFile(delete=False, suffix=".txt", prefix="eportal_", dir=APP_FOLDER)
                        tf.write(text.encode("utf-8"))
                        tf.close()
                        # launch command for toast: notepad "file"
                        launch = f'notepad.exe "{tf.name}"'
                        show_toast("登录成功", "校园网络已登录成功，点击查看详细返回。", launch_cmd=launch)
            # sleep
        except Exception:
            logger.exception("Exception in polling loop")
        # wait but allow stop
        for _ in range(int(interval)):
            if _stop_event.is_set():
                break
            time.sleep(1)

# ---------- CLI handling ----------
def main():
    parser = argparse.ArgumentParser(description="EPortal 自动登录客户端")
    parser.add_argument("interval", nargs="?", type=int, help="轮询间隔（秒）", default=None)
    parser.add_argument("username", nargs="?", help="用户名", default=None)
    parser.add_argument("password", nargs="?", help="密码", default=None)
    parser.add_argument("operator", nargs="?", help="运营商：空/telecom/unicom/cmcc", default=None)
    parser.add_argument("--config", action="store_true", help="进入配置模式（交互式）")
    parser.add_argument("--logout", action="store_true", help="登出网络（手动触发）")
    parser.add_argument("--run-from-startup", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    # ensure running on windows environment with necessary libs
    if os.name != "nt":
        print("此程序仅支持 Windows。")
        return

    # if config explicit
    if args.config:
        ok = config_mode_interactive()
        return

    # if logout explicit
    if args.logout:
        ok, txt = attempt_logout()
        if ok:
            print("登出请求已发送。")
            logger.info("Manual logout succeeded.")
        else:
            print("登出请求发送失败，请检查网络或重试。")
        return

    # If user provided parameters directly (positional)
    if args.username is not None and args.password is not None:
        # use provided args (interval may be in args.interval)
        interval = args.interval if args.interval is not None else 60
        username = args.username
        password = args.password
        operator = args.operator if args.operator is not None else ""
        # start polling with these values (do NOT save automatically unless user logs in via config)
        cfg = {"username": username, "password": password, "operator": operator, "interval": interval}
        # start polling loop in main thread (so process keeps running)
        print("启动轮询（按 Ctrl+C 停止）...")
        t = threading.Thread(target=polling_loop, args=(cfg,), daemon=True)
        t.start()
        try:
            while t.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            print("退出中...")
            _stop_event.set()
            t.join()
        return

    # If no args, try load saved config
    cfg = load_config_encrypted()
    if cfg:
        print(f"载入本地配置，周期 {cfg.get('interval')}s，用户名 {cfg.get('username')}")
        t = threading.Thread(target=polling_loop, args=(cfg,), daemon=True)
        t.start()
        try:
            while t.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            print("退出中...")
            _stop_event.set()
            t.join()
        return

    # otherwise nothing to do: show help
    parser.print_help()
    print("\n提示：使用 --config 交互式配置并保存，或直接以参数形式启动：\n"
          "e.g. eportal_client.py 60 username password telecom\n")

if __name__ == "__main__":
    main()
