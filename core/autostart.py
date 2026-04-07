import os
import sys
import winreg


APP_NAME = "JXUSTNetLogin"


# 注册表自启动相关函数 - 使用HKEY_LOCAL_MACHINE
def _run_key():
    return winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_ALL_ACCESS)


def _launch_command() -> str:
    if getattr(sys, "frozen", False):
        exe = sys.executable
    else:
        exe = sys.executable
        script = os.path.abspath(sys.argv[0])
        return f'"{exe}" "{script}" --silent'
    return f'"{exe}" --silent'


def enable_autostart() -> bool:
    try:
        with _run_key() as k:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, _launch_command())
        return True
    except Exception:
        return False


def disable_autostart() -> bool:
    try:
        with _run_key() as k:
            winreg.DeleteValue(k, APP_NAME)
        return True
    except FileNotFoundError:
        return True
    except Exception:
        return False


def is_autostart_enabled() -> bool:
    try:
        with _run_key() as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except Exception:
        return False