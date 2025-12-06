import sys


def main():
    import argparse
    import os
    os.environ.setdefault("QT_API", "pyside6")
    os.environ.setdefault("QT_PREFERRED_BINDING", "PySide6")
    from loguru import logger
    try:
        from core import config as cfg
        log_dir = os.path.join(cfg.APP_DIR, "logs")
        os.makedirs(log_dir, exist_ok=True)
        logger.add(os.path.join(log_dir, "app.log"), encoding="utf-8", rotation="1 MB", retention="7 days", enqueue=True, backtrace=True, diagnose=False)
    except Exception:
        pass
    silent = False
    parser = argparse.ArgumentParser()
    parser.add_argument("--silent", action="store_true")
    args, _ = parser.parse_known_args()
    silent = args.silent
    print("[app] start", flush=True)
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    print("[app] qt imported", flush=True)
    app = QApplication(sys.argv)
    # 设置关闭最后一个窗口时不退出应用程序
    app.setQuitOnLastWindowClosed(False)
    print("[app] qapp created", flush=True)
    try:
        import qfluentwidgets as qf
        qf.setTheme(qf.Theme.AUTO)
        print("[app] qfluentwidgets theme set", flush=True)
    except Exception:
        print("[app] qfluentwidgets not available", flush=True)
    from core import config as cfg
    print("[app] load config", flush=True)
    c = cfg.load_config()
    print("[app] import ui", flush=True)
    from ui.tray import AppTray
    from ui.main_window import MainWindow
    print("[app] create main window", flush=True)
    w = MainWindow(c)
    print("[app] create tray", flush=True)
    tray = AppTray(w)
    if not silent:
        w.show()
        print("[app] show window", flush=True)
    else:
        tray.show_message("已启动", "后台运行，自动检测网络", 3000)
        print("[app] silent started", flush=True)
    def start_timer():
        w.start_connectivity_timer()
        if c.get("auto_reconnect", True):
            w.try_login_silent()
    QTimer.singleShot(0, start_timer)
    print("[app] enter event loop", flush=True)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
