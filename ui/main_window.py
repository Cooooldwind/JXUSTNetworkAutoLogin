from PySide6.QtCore import Qt, QSize, QTimer, Signal, QObject, QRect, QPoint, QEvent
from PySide6.QtGui import QPixmap, QAction, QColor, QPainter, QPainterPath, QIcon
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QComboBox, QPushButton, QCheckBox, QFrame, QStackedLayout
from loguru import logger


class NotifyBridge(QObject):
    login_done = Signal(bool, str)
    logout_done = Signal(bool, str)
    online_state = Signal(bool)


def _load_qf():
    try:
        import qfluentwidgets as qf
        return qf
    except Exception:
        return None


class MainWindow(QWidget):
    def __init__(self, config: dict):
        print('[ui] MainWindow __init__ begin', flush=True)
        super().__init__()
        print('[ui] MainWindow super done', flush=True)
        self.setWindowTitle("校园网登录")
        self.resize(980, 580)
        try:
            self.setWindowIcon(QIcon('logo.ico'))
        except Exception:
            pass
        self.config = config
        self.logging = False
        self.timer = QTimer(self)
        self.timer.setSingleShot(False)
        self.timer.setInterval(int(self.config.get("check_interval", 15)) * 1000)
        self.retry_interval = int(self.config.get("check_interval", 15))
        self.bridge = NotifyBridge()
        self.bridge.login_done.connect(self._on_login_done)
        self.bridge.logout_done.connect(self._on_logout_done)
        self.bridge.online_state.connect(self._apply_online_state)
        
        # 监听系统事件，用于检测睡眠唤醒
        self.installEventFilter(self)
        
        print('[ui] build ui', flush=True)
        self._build_ui()

    def _build_ui(self):
        print('[ui] _build_ui enter', flush=True)
        qf = _load_qf()
        print(f'[ui] qfluentwidgets loaded={bool(qf)}', flush=True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.bgLayer = _BackgroundLayer(self)
        self.bgLayer.lower()
        root = QHBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        leftWrap = _GlassPanel(self)
        form = QVBoxLayout(leftWrap)
        form.setContentsMargins(28, 28, 28, 28)
        rightCard = _ImagePanel(self)
        rightCard.setFixedWidth(440)
        title = QLabel("JXUST 网络登录")
        if qf:
            print('[ui] using qfluent style', flush=True)
            title.setStyleSheet("font-size:22px;font-weight:600;")
            from qfluentwidgets import LineEdit, PasswordLineEdit, ComboBox, PrimaryPushButton, PushButton, InfoBar, InfoBarPosition, CheckBox
            self.accountEdit = LineEdit()
            self.accountEdit.setPlaceholderText("学号")
            self.passwordEdit = PasswordLineEdit()
            self.passwordEdit.setPlaceholderText("密码")
            self.carrierBox = ComboBox()
            self.autoStartBox = CheckBox("自启动")
            self.autoReconnectBox = CheckBox("自动重连")
            self.loginBtn = PrimaryPushButton("登录")
            self.logoutBtn = PushButton("注销")
            self.infobar_class = InfoBar
            self.infobar_pos = InfoBarPosition
        else:
            from PySide6.QtWidgets import QLineEdit
            self.accountEdit = QLineEdit()
            self.passwordEdit = QLineEdit()
            self.passwordEdit.setEchoMode(QLineEdit.Password)
            self.carrierBox = QComboBox()
            self.autoStartBox = QCheckBox("自启动")
            self.autoReconnectBox = QCheckBox("自动重连")
            self.loginBtn = QPushButton("登录")
            self.logoutBtn = QPushButton("注销")
            self.infobar_class = None
            self.infobar_pos = None
        self.carrierBox.addItems(["none", "telecom", "cmcc", "unicom"])
        self.accountEdit.setText(self.config.get("account", ""))
        try:
            from core.network import compose_account
            from core import config as cfg
            acc = self.config.get("account", "")
            car = self.config.get("carrier", "none")
            user_full = compose_account(acc, car)
            pwd_saved = cfg.get_password(user_full)
            if pwd_saved:
                self.passwordEdit.setText(pwd_saved)
        except Exception:
            self.passwordEdit.setText("")
        idx = max(0, self.carrierBox.findText(self.config.get("carrier", "none")))
        self.carrierBox.setCurrentIndex(idx)
        if isinstance(self.autoStartBox, QCheckBox):
            self.autoStartBox.setChecked(bool(self.config.get("auto_start", False)))
        else:
            self.autoStartBox.setChecked(bool(self.config.get("auto_start", False)))
        if isinstance(self.autoReconnectBox, QCheckBox):
            self.autoReconnectBox.setChecked(bool(self.config.get("auto_reconnect", True)))
        else:
            self.autoReconnectBox.setChecked(bool(self.config.get("auto_reconnect", True)))
        form.addWidget(title)
        form.addSpacing(12)
        form.addWidget(QLabel("账户"))
        form.addWidget(self.accountEdit)
        form.addWidget(QLabel("密码"))
        form.addWidget(self.passwordEdit)
        form.addWidget(QLabel("运营商"))
        form.addWidget(self.carrierBox)
        form.addSpacing(8)
        form.addWidget(self.autoStartBox)
        form.addWidget(self.autoReconnectBox)
        form.addSpacing(16)
        btnRow = QHBoxLayout()
        btnRow.addWidget(self.loginBtn)
        btnRow.addWidget(self.logoutBtn)
        rowWidget = QWidget()
        rowWidget.setLayout(btnRow)
        form.addWidget(rowWidget)
        root.addWidget(leftWrap, 0)
        root.addSpacing(24)
        leftWrap.setFixedWidth(480)
        root.addWidget(rightCard, 0)
        self.loginBtn.clicked.connect(self.login)
        self.logoutBtn.clicked.connect(self.logout)
        if isinstance(self.autoStartBox, QCheckBox):
            self.autoStartBox.stateChanged.connect(self._toggle_autostart)
        else:
            self.autoStartBox.checkedChanged.connect(self._toggle_autostart)
        if isinstance(self.autoReconnectBox, QCheckBox):
            self.autoReconnectBox.stateChanged.connect(self._toggle_autoreconnect)
        else:
            self.autoReconnectBox.checkedChanged.connect(self._toggle_autoreconnect)
        self._apply_qss()
        self._init_connectivity_state()

    def _apply_qss(self):
        is_dark = False
        try:
            import darkdetect
            is_dark = darkdetect.isDark()
        except Exception:
            pass
        text = "#eaeaea" if is_dark else "#202020"
        self.setStyleSheet(f"color:{text}; background: transparent;")
        try:
            # 让输入框更 Fluent，但尽量少覆盖 qfluentwidgets 默认
            for w in (self.accountEdit, self.passwordEdit, self.carrierBox):
                w.setClearButtonEnabled(True) if hasattr(w, 'setClearButtonEnabled') else None
        except Exception:
            pass
        self.loginBtn.setStyleSheet("padding:12px 14px;border-radius:12px;background:#1677ff;color:white; font-weight:600;")
        self.logoutBtn.setStyleSheet(f"padding:12px 14px;border-radius:12px;background: rgba(0,0,0,0.08); color:{text};")

    def show_info(self, text: str, success: bool = True):
        if self.infobar_class:
            bar = self.infobar_class.success if success else self.infobar_class.error
            bar(title="提示", content=text, orient=Qt.Horizontal, isClosable=True, position=self.infobar_pos.TOP_RIGHT, duration=3000, parent=self)
        else:
            try:
                from PySide6.QtWidgets import QMessageBox
                m = QMessageBox.information if success else QMessageBox.warning
                m(self, "提示", text)
            except Exception:
                pass

    def _save_inputs(self):
        from core import config as cfg
        self.config["account"] = self.accountEdit.text().strip()
        self.config["carrier"] = self.carrierBox.currentText()
        cfg.save_config(self.config)

    def _toggle_autostart(self):
        from core import autostart
        enabled = self.autoStartBox.isChecked() if isinstance(self.autoStartBox, QCheckBox) else self.autoStartBox.isChecked()
        ok = autostart.enable_autostart() if enabled else autostart.disable_autostart()
        self.config["auto_start"] = enabled and ok
        self.show_info("自启动已开启" if self.config["auto_start"] else "自启动已关闭", ok)
        from core import config as cfg
        cfg.save_config(self.config)

    def _toggle_autoreconnect(self):
        val = self.autoReconnectBox.isChecked() if isinstance(self.autoReconnectBox, QCheckBox) else self.autoReconnectBox.isChecked()
        self.config["auto_reconnect"] = bool(val)
        from core import config as cfg
        cfg.save_config(self.config)

    def login(self):
        if self.logging:
            return
        
        # 检查账户和密码是否填写
        account = self.accountEdit.text().strip()
        password = self.passwordEdit.text()
        
        if not account:
            self.show_info("请输入学号", False)
            return
        
        if not password:
            self.show_info("请输入密码", False)
            return
        
        self.logging = True
        self.loginBtn.setEnabled(False)
        self.logoutBtn.setEnabled(False)
        
        # 保存输入信息
        self._save_inputs()
        
        from core.network import login as do_login, compose_account
        from core import config as cfg
        import threading
        import os
        from datetime import datetime
        
        # 配置loguru日志输出到文件
        try:
            # 创建logs目录
            log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
            os.makedirs(log_dir, exist_ok=True)
            
            # 生成日志文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = os.path.join(log_dir, f"login_{timestamp}.log")
            
            # 配置loguru日志，确保日志格式详细且包含所有信息
            logger.remove()  # 移除默认的控制台处理器
            logger.add(
                log_file,
                level="DEBUG",
                format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
                rotation=None,  # 不进行轮转，每个登录会话一个文件
                retention=None,
                encoding="utf-8",
                backtrace=True,
                diagnose=True
            )
            
            # 同时添加控制台输出
            logger.add(
                sink=lambda msg: print(msg, end=""),
                level="INFO",
                format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> - <level>{message}</level>"
            )
            
            logger.info(f"日志文件已创建: {log_file}")
        except Exception as e:
            # 如果日志配置失败，记录错误
            print(f"无法配置日志文件: {e}")
        
        username = compose_account(account, self.config.get("carrier", "none"))
        
        # 优先使用输入的密码
        pwd = password
        
        # 尝试保存密码到存储
        if pwd:
            success = cfg.set_password(username, pwd)
            logger.info(f"密码保存{'成功' if success else '失败'}")
        
        base = self.config.get("endpoint_base")
        cb = self.config.get("callback_login", "dr1003")
        
        def work():
            try:
                # 记录登录尝试
                logger.info(f"尝试登录，用户名: {username}, 基础URL: {base}")
                
                # 执行登录
                r = do_login(base, account, pwd, self.config.get("carrier", "none"), cb)
                
                # 处理登录结果
                ok = bool(r.get("ok"))
                msg = r.get("msg", "")
                
                if not ok:
                    # 登录失败时提供更详细的错误信息
                    if not msg:
                        msg = "无法连接到服务器或服务器返回异常"
                    if "密码" in msg or "password" in msg.lower():
                        msg = f"密码错误或无效: {msg}"
                    if "用户" in msg or "user" in msg.lower():
                        msg = f"用户不存在或无效: {msg}"
                
                logger.info(f"登录{'成功' if ok else '失败'}: {msg}")
                
                self.bridge.login_done.emit(ok, msg)
            except Exception as e:
                # 捕获所有异常并提供友好提示
                error_msg = f"登录过程发生错误: {str(e)}"
                logger.error(f"登录异常: {e}", exc_info=True)
                self.bridge.login_done.emit(False, error_msg)
        
        threading.Thread(target=work, daemon=True).start()

    def _on_login_done(self, ok: bool, msg: str):
        self.logging = False
        self.loginBtn.setEnabled(True)
        self.logoutBtn.setEnabled(True)
        
        # 登录失败时添加日志文件位置信息
        if not ok:
            try:
                # 获取日志文件位置（适用于loguru）
                import os
                import re
                
                # 通过日志目录查找最新的日志文件
                log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
                if os.path.exists(log_dir):
                    # 获取所有以login_开头的日志文件
                    log_files = [f for f in os.listdir(log_dir) if f.startswith('login_') and f.endswith('.log')]
                    if log_files:
                        # 按时间戳排序，获取最新的文件
                        log_files.sort(reverse=True)
                        log_file = os.path.join(log_dir, log_files[0])
                    else:
                        log_file = os.path.join(log_dir, "(暂未找到日志文件)")
                else:
                    log_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs', "(logs目录尚未创建)")
                
                # 修改提示信息，包含日志位置
                msg = f"{msg}\n\n详细错误信息已记录至日志文件：\n{log_file}"
            except Exception as e:
                # 如果获取日志位置失败，继续使用原消息
                pass
        
        self.show_info("登录成功" if ok else f"登录失败：{msg}", ok)
        try:
            if ok:
                from loguru import logger as _lg
                _lg.info("login success")
            else:
                from loguru import logger as _lg
                _lg.warning(f"login failed: {msg}")
        except Exception:
            pass
        try:
            from ui.tray import get_tray
            t = get_tray()
            if t:
                # 托盘消息保持简洁
                tray_msg = "成功" if ok else ("失败：" + (msg.splitlines()[0] if isinstance(msg, str) and msg else ""))
                t.show_message("登录", tray_msg)
        except Exception:
            pass
        
        # 添加toast通知
        try:
            import os
            import sys
            script_path = os.path.abspath(__file__)
            app_path = os.path.dirname(os.path.dirname(script_path))
            sys.path.append(app_path)
            from eportal_client import show_toast
            
            # 为toast创建启动命令
            if getattr(sys, "frozen", False):
                launch_cmd = sys.executable
            else:
                launch_cmd = f"{sys.executable} {os.path.join(app_path, 'app.py')}"
            
            if ok:
                show_toast("登录成功", "校园网络已登录成功", launch_cmd=launch_cmd)
            else:
                show_toast("登录失败", f"登录失败：{msg.splitlines()[0]}", launch_cmd=launch_cmd)
        except Exception as e:
            from loguru import logger
            logger.warning(f"无法显示toast通知: {e}")
        if ok:
            self.retry_interval = int(self.config.get("check_interval", 15))
            if self.timer.isActive():
                self.timer.setInterval(self.retry_interval * 1000)

    def logout(self):
        from core.network import logout as do_logout
        from core.network import get_local_ip
        import threading
        base = self.config.get("endpoint_base")
        cb = self.config.get("callback_logout", "dr1004")
        ip = get_local_ip()
        def work():
            r = do_logout(base, ip, cb)
            self.bridge.logout_done.emit(bool(r.get("ok")), r.get("msg", ""))
        threading.Thread(target=work, daemon=True).start()

    def _on_logout_done(self, ok: bool, msg: str):
        self.show_info("注销成功" if ok else f"注销失败：{msg}", ok)
        try:
            self._set_controls_enabled(True)
        except Exception:
            pass
        try:
            if ok:
                from loguru import logger as _lg
                _lg.info("logout success")
            else:
                from loguru import logger as _lg
                _lg.warning(f"logout failed: {msg}")
        except Exception:
            pass
        try:
            from ui.tray import get_tray
            t = get_tray()
            if t:
                t.show_message("注销", "成功" if ok else f"失败：{msg}")
        except Exception:
            pass

    def start_connectivity_timer(self):
        self.timer.timeout.connect(self._on_timer)
        self.timer.start()

    def _on_timer(self):
        from core.connectivity import is_online
        if is_online():
            self._set_controls_enabled(False)
            self.retry_interval = int(self.config.get("check_interval", 15))
            if self.timer.interval() != self.retry_interval * 1000:
                self.timer.setInterval(self.retry_interval * 1000)
            return
        self._set_controls_enabled(True)
        if not self.config.get("auto_reconnect", True):
            return
        if self.logging:
            return
        self.try_login_silent()
        self.retry_interval = min(self.retry_interval * 2, 60)
        self.timer.setInterval(self.retry_interval * 1000)

    def try_login_silent(self):
        self.login()

    def _init_connectivity_state(self):
        import threading
        from core.connectivity import is_online
        def work():
            online = is_online()
            self.bridge.online_state.emit(online)
        threading.Thread(target=work, daemon=True).start()

    def _set_controls_enabled(self, enabled: bool):
        for w in (self.accountEdit, self.passwordEdit, self.carrierBox, self.loginBtn):
            try:
                w.setEnabled(enabled)
            except Exception:
                pass

    def _apply_online_state(self, online: bool):
        self._set_controls_enabled(not online)
        if online:
            self.show_info("当前已联网，已禁用登录", True)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, "bgLayer") and self.bgLayer:
            self.bgLayer.setGeometry(self.rect())
    
    def closeEvent(self, event):
        # 阻止窗口关闭，而是隐藏窗口
        event.ignore()
        self.hide()

    def eventFilter(self, obj, event):
        """事件过滤器，用于检测系统唤醒事件"""
        # 检测WindowActivate事件，这通常在系统从睡眠中唤醒或解锁屏幕时触发
        if event.type() == QEvent.WindowActivate:
            # 当窗口被激活时，立即检查网络状态
            self._check_network_on_wake()
        return super().eventFilter(obj, event)
    
    def _check_network_on_wake(self):
        """系统唤醒时检查网络状态"""
        import threading
        from loguru import logger
        
        logger.info("检测到系统唤醒或窗口激活，立即检查网络状态")
        
        # 重置轮询间隔到默认值
        default_interval = int(self.config.get("check_interval", 15))
        self.retry_interval = default_interval
        if self.timer.isActive() and self.timer.interval() != default_interval * 1000:
            self.timer.setInterval(default_interval * 1000)
            logger.info(f"已将网络检测间隔重置为默认值: {default_interval}秒")
        
        # 异步检查网络状态
        def check_network():
            from core.connectivity import is_online
            try:
                online = is_online()
                # 通过信号更新UI状态
                self.bridge.online_state.emit(online)
                
                # 如果网络离线且启用了自动重连，尝试立即登录
                if not online and self.config.get("auto_reconnect", True) and not self.logging:
                    logger.info("系统唤醒后发现网络离线，尝试自动重连")
                    # 使用QTimer确保在主线程调用
                    QTimer.singleShot(0, self.try_login_silent)
            except Exception as e:
                logger.error(f"系统唤醒时检查网络状态出错: {str(e)}")
        
        threading.Thread(target=check_network, daemon=True).start()


class _BackgroundLayer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        mode_dark = False
        try:
            import darkdetect
            mode_dark = darkdetect.isDark()
        except Exception:
            pass
        self.overlay = QColor(0, 0, 0, 90) if mode_dark else QColor(255, 255, 255, 90)
        self.pix = None
        rp = _find_resource(["pic.jpg", "assets/side.png"]) or "pic.jpg"
        q = QPixmap(rp)
        if not q.isNull():
            self.pix = q
        # 用于取样（未加模糊的位图）
        self.scale = 1.0
        self.tw = self.th = 0
        self.ox = self.oy = 0
        self.scaled_pix = None
        # 背景显示（加模糊）：使用 QLabel + QGraphicsBlurEffect
        from PySide6.QtWidgets import QLabel, QGraphicsBlurEffect
        self.lbl = QLabel(self)
        self.lbl.setScaledContents(True)
        self.blur = QGraphicsBlurEffect(self)
        self.blur.setBlurRadius(24)
        self.lbl.setGraphicsEffect(self.blur)
        # 遮罩
        self.mask = QWidget(self)
        self.mask.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        try:
            self._fetch_remote_background()
        except Exception:
            from loguru import logger as _lg
            _lg.exception("fetch remote background init error")

    def resizeEvent(self, e):
        super().resizeEvent(e)
        r = self.rect()
        if not self.pix:
            return
        pw, ph = self.pix.width(), self.pix.height()
        rw, rh = r.width(), r.height()
        if pw <= 0 or ph <= 0 or rw <= 0 or rh <= 0:
            return
        self.scale = max(rw / pw, rh / ph)
        self.tw, self.th = int(pw * self.scale), int(ph * self.scale)
        self.ox = (rw - self.tw) // 2
        self.oy = (rh - self.th) // 2
        self.scaled_pix = self.pix.scaled(self.tw, self.th, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        # 设置到 label（模糊显示）
        self.lbl.setGeometry(r)
        if self.scaled_pix:
            self.lbl.setPixmap(self.scaled_pix)
        self.mask.setGeometry(r)
        self.mask.setStyleSheet(f"background-color: rgba({self.overlay.red()},{self.overlay.green()},{self.overlay.blue()},{self.overlay.alpha()});")

    def _apply_pix(self, pix: QPixmap):
        try:
            if not pix or pix.isNull():
                return
            self.pix = pix
            self.resizeEvent(None)
            self.update()
        except Exception:
            from loguru import logger as _lg
            _lg.exception("apply pix error")

    def _fetch_remote_background(self):
        import threading
        from PySide6.QtCore import QTimer as _QTimer
        url = "http://10.17.8.18:801/eportal/extern/6MbEyk1729738317/U5b7jU1729738336/6cb18cf347707cfac05c2b79ac275440.jpg"
        def work():
            try:
                import requests
                resp = requests.get(url, timeout=5)
                resp.raise_for_status()
                data = resp.content
                pix = QPixmap()
                ok = pix.loadFromData(data)
                if ok:
                    _QTimer.singleShot(0, lambda: self._apply_pix(pix))
                else:
                    from loguru import logger as _lg
                    _lg.warning("remote background loadFromData failed")
            except Exception:
                from loguru import logger as _lg
                _lg.exception("remote background fetch failed")
        threading.Thread(target=work, daemon=True).start()


class _GlassPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = self.rect()
        path = QPainterPath()
        path.addRoundedRect(r.adjusted(0, 0, -1, -1), 18, 18)
        is_dark = False
        try:
            import darkdetect
            is_dark = darkdetect.isDark()
        except Exception:
            pass
        color = QColor(28, 28, 28, 170) if is_dark else QColor(255, 255, 255, 200)
        p.fillPath(path, color)


class _ImagePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.radius = 26
        self.pix = None  # 直接从背景层采样

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = self.rect().adjusted(0, 0, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(r, self.radius, self.radius)
        p.setClipPath(path)
        win = self.window()
        bg = getattr(win, 'bgLayer', None)
        if bg and bg.scaled_pix:
            top_left_in_win = self.mapTo(win, QPoint(0, 0))
            bg_in_win = bg.mapTo(win, QPoint(0, 0))
            wx = top_left_in_win.x() - bg_in_win.x()
            wy = top_left_in_win.y() - bg_in_win.y()
            sx = wx - bg.ox
            sy = wy - bg.oy
            # 防护：拷贝范围不得越界
            sx = max(0, min(bg.scaled_pix.width() - 1, sx))
            sy = max(0, min(bg.scaled_pix.height() - 1, sy))
            sw = min(r.width(), bg.scaled_pix.width() - sx)
            sh = min(r.height(), bg.scaled_pix.height() - sy)
            if sw > 0 and sh > 0:
                src = bg.scaled_pix.copy(sx, sy, sw, sh)
                p.drawPixmap(0, 0, src.scaled(r.width(), r.height(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
        # inner border
        is_dark = False
        try:
            import darkdetect
            is_dark = darkdetect.isDark()
        except Exception:
            pass
        border = QColor(255, 255, 255, 28) if not is_dark else QColor(255, 255, 255, 18)
        p.setClipping(False)
        p.setPen(border)
        p.drawPath(path)


class _Switch(QCheckBox):
    def __init__(self, text='', parent=None):
        super().__init__(text, parent)
        self._apply_style()

    def _apply_style(self):
        is_dark = False
        try:
            import darkdetect
            is_dark = darkdetect.isDark()
        except Exception:
            pass
        track_on = "#1677ff"
        track_off = "rgba(0,0,0,0.25)" if not is_dark else "rgba(255,255,255,0.25)"
        self.setStyleSheet(f'''
            QCheckBox::indicator {{ width: 44px; height: 24px; border-radius: 12px; }}
            QCheckBox::indicator:unchecked {{ background: {track_off}; }}
            QCheckBox::indicator:unchecked:pressed {{ background: rgba(0,0,0,0.35); }}
            QCheckBox::indicator:checked {{ background: {track_on}; }}
            QCheckBox::indicator:checked:pressed {{ background: #2a7dff; }}
            QCheckBox {{ spacing: 10px; }}
        ''')
def _find_resource(candidates):
    import os, sys
    dirs = []
    # 详细日志记录（用于调试）
    log_msg = []
    
    # Nuitka Onefile 模式下的关键路径处理
    # 1. 尝试获取Nuitka临时目录（Onefile模式）
    nuitka_temp = os.environ.get("NUITKA_ONEFILE_TEMP_DIR")
    if nuitka_temp:
        dirs.append(nuitka_temp)
        log_msg.append(f"Nuitka temp: {nuitka_temp}")
    
    # 2. 可执行文件所在目录（适用于复制后的exe）
    try:
        exe_path = os.path.abspath(sys.argv[0])
        exe_dir = os.path.dirname(exe_path)
        dirs.append(exe_dir)
        log_msg.append(f"Exe dir: {exe_dir}")
        # 添加可能的子目录
        if os.path.exists(os.path.join(exe_dir, "assets")):
            dirs.append(os.path.join(exe_dir, "assets"))
    except Exception as e:
        log_msg.append(f"Error getting exe path: {e}")
    
    # 3. 当前工作目录
    try:
        cwd = os.getcwd()
        dirs.append(cwd)
        log_msg.append(f"CWD: {cwd}")
    except Exception:
        log_msg.append("Error getting CWD")
    
    # 4. PyInstaller 路径支持（保持兼容性）
    if hasattr(sys, "_MEIPASS"):
        meipass = getattr(sys, "_MEIPASS")
        dirs.append(meipass)
        log_msg.append(f"MEIPASS: {meipass}")
    
    # 5. 其他Nuitka相关路径
    for k in ("NUITKA_ONEFILE_PARENT", "NUITKA_APP_DIR"):
        v = os.environ.get(k)
        if v:
            dirs.append(v)
            log_msg.append(f"{k}: {v}")
    
    # 6. 模块所在目录（开发模式）
    try:
        module_dir = os.path.dirname(os.path.abspath(__file__))
        dirs.append(module_dir)
        log_msg.append(f"Module dir: {module_dir}")
        # 添加可能的资源目录
        dirs.append(os.path.join(module_dir, "assets"))
        dirs.append(os.path.join(os.path.dirname(module_dir), "assets"))
    except Exception:
        log_msg.append("Error getting module path")
    
    # 7. 添加上级目录和其他可能的位置
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        dirs.append(base_dir)
        log_msg.append(f"Base dir: {base_dir}")
    except Exception:
        pass
    
    # 去重
    seen = set()
    uniq_dirs = []
    for d in dirs:
        if d and d not in seen:
            uniq_dirs.append(d)
            seen.add(d)
    
    # 尝试查找资源文件
    for name in candidates:
        # 构建多种可能的路径变体
        variants = [name]
        # 为主要图片资源添加更多可能的变体
        if name in ["pic.jpg", "side.png"]:
            variants.extend([
                f"assets/{name}",
                f"ui/assets/{name}",
                f"{os.path.basename(name)}"
            ])
        
        # 尝试所有变体
        for variant in variants:
            # 直接尝试变体路径
            if os.path.exists(variant):
                try:
                    from loguru import logger
                    logger.debug(f"Found resource at direct path: {variant}")
                except Exception:
                    pass
                return variant
            
            # 尝试在所有可能的目录中查找变体
            for d in uniq_dirs:
                p = os.path.join(d, variant)
                if os.path.exists(p):
                    try:
                        from loguru import logger
                        logger.debug(f"Found resource at: {p}")
                    except Exception:
                        pass
                    return p
    
    # 如果找不到，尝试记录查找过程（仅在开发模式）
    try:
        if not nuitka_temp:  # 仅在非打包模式记录日志
            print(f"[Resource Search] Candidates: {candidates}")
            print(f"[Resource Search] Searched in: {uniq_dirs}")
    except Exception:
        pass
    
    # 作为最后的回退，如果是pic.jpg，尝试创建一个简单的占位图像
    if "pic.jpg" in candidates:
        try:
            from PySide6.QtGui import QPixmap, QPainter, QColor
            from PySide6.QtCore import Qt
            
            # 创建一个简单的占位图像
            placeholder = QPixmap(800, 600)
            placeholder.fill(QColor(240, 240, 240))
            painter = QPainter(placeholder)
            painter.setPen(QColor(100, 100, 100))
            painter.drawText(placeholder.rect(), Qt.AlignCenter, "背景图片")
            painter.end()
            
            # 保存到临时位置
            temp_path = os.path.join(exe_dir or os.getcwd(), "temp_pic.jpg")
            placeholder.save(temp_path)
            return temp_path
        except Exception:
            pass
    
    return None
