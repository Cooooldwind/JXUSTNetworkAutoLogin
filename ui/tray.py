from PySide6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor
from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtCore import Qt
import os, sys
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_global_tray = None


def get_tray():
    return _global_tray


class AppTray(QSystemTrayIcon):
    def __init__(self, main_window):
        super().__init__()
        global _global_tray
        _global_tray = self
        self.main = main_window
        self.setToolTip("JXUST 网络登录")
        
        # 检查系统托盘是否可用
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.error("系统托盘功能不可用")
            return
        logger.info("系统托盘功能可用")
        
        def _find_resource(candidates):
            dirs = []
            try: 
                dirs.append(os.getcwd())
                logger.debug(f"添加当前目录: {os.getcwd()}")
            except Exception as e:
                logger.warning(f"获取当前目录失败: {e}")
            
            # 检查PyInstaller或Nuitka的临时目录
            if hasattr(sys, "_MEIPASS"):
                meipass = getattr(sys, "_MEIPASS")
                dirs.append(meipass)
                logger.debug(f"添加_MEIPASS: {meipass}")
                
            # 检查Nuitka特定的环境变量
            for k in ("NUITKA_ONEFILE_PARENT", "NUITKA_ONEFILE_TEMP_DIR"):
                v = os.environ.get(k)
                if v:
                    dirs.append(v)
                    logger.debug(f"添加环境变量 {k}: {v}")
                    
            # 检查可执行文件目录
            try:
                exe_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
                dirs.append(exe_dir)
                logger.debug(f"添加可执行文件目录: {exe_dir}")
            except Exception as e:
                logger.warning(f"获取可执行文件目录失败: {e}")
                
            # 检查脚本文件目录
            try:
                script_dir = os.path.dirname(os.path.abspath(__file__))
                dirs.append(script_dir)
                logger.debug(f"添加脚本目录: {script_dir}")
            except Exception as e:
                logger.warning(f"获取脚本目录失败: {e}")
                
            # 去重
            seen = set(); uniq = []
            for d in dirs:
                if d and d not in seen:
                    uniq.append(d); seen.add(d)
            
            # 搜索图标文件
            for name in candidates:
                for d in uniq:
                    p = os.path.join(d, name)
                    logger.debug(f"尝试图标路径: {p}")
                    if os.path.exists(p):
                        logger.info(f"找到图标: {p}")
                        return p
            
            logger.warning(f"未找到图标文件，候选路径: {candidates}")
            return None
        
        # 扩展图标搜索路径，增加更多可能的位置
        icon_candidates = [
            "logo.ico", 
            "./logo.ico",
            "assets/app.ico", 
            "assets/logo.ico",
            "ui/assets/logo.ico"
        ]
        
        # 尝试加载图标文件
        icon_path = _find_resource(icon_candidates)
        icon = None
        
        # 尝试从路径加载图标
        if icon_path and os.path.exists(icon_path):
            try:
                icon = QIcon(icon_path)
                logger.info(f"成功加载托盘图标: {icon_path}")
                if icon.isNull():
                    logger.warning(f"图标加载但为空: {icon_path}")
            except Exception as e:
                logger.warning(f"无法从路径加载图标 {icon_path}: {e}")
        else:
            logger.warning(f"图标路径不存在或未找到: {icon_path}")
        
        # 如果图标加载失败，创建一个简单的占位图标
        if not icon or icon.isNull():
            try:
                logger.info("创建默认占位图标")
                # 创建一个简单的红色方形图标作为占位符
                pixmap = QPixmap(32, 32)
                pixmap.fill(QColor(255, 0, 0))  # 红色背景
                painter = QPainter(pixmap)
                painter.setPen(QColor(255, 255, 255))  # 白色文字
                painter.drawText(pixmap.rect(), Qt.AlignCenter, "网")
                painter.end()
                icon = QIcon(pixmap)
                logger.info("占位图标创建成功")
            except Exception as e:
                logger.error(f"无法创建占位图标: {e}")
        
        # 设置图标
        try:
            self.setIcon(icon if icon and not icon.isNull() else QIcon())
            logger.info("托盘图标已设置")
        except Exception as e:
            logger.error(f"设置托盘图标失败: {e}")
        menu = QMenu()
        openAct = QAction("打开")
        loginAct = QAction("登录")
        logoutAct = QAction("注销")
        autoStartAct = QAction("自启动", checkable=True)
        autoReconnectAct = QAction("自动重连", checkable=True)
        exitAct = QAction("退出")
        autoStartAct.setChecked(bool(self.main.config.get("auto_start", False)))
        autoReconnectAct.setChecked(bool(self.main.config.get("auto_reconnect", True)))
        menu.addAction(openAct)
        menu.addSeparator()
        menu.addAction(loginAct)
        menu.addAction(logoutAct)
        menu.addSeparator()
        menu.addAction(autoStartAct)
        menu.addAction(autoReconnectAct)
        menu.addSeparator()
        menu.addAction(exitAct)
        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)
        openAct.triggered.connect(self._open)
        loginAct.triggered.connect(self.main.login)
        logoutAct.triggered.connect(self.main.logout)
        autoStartAct.triggered.connect(self._toggle_autostart)
        autoReconnectAct.triggered.connect(self._toggle_autoreconnect)
        exitAct.triggered.connect(self._exit)
        # 显示托盘图标
        try:
            self.show()
            logger.info("托盘图标已显示")
        except Exception as e:
            logger.error(f"显示托盘图标失败: {e}")
            # 作为后备，尝试在Windows下使用一些常见的修复方法
            if sys.platform == 'win32':
                try:
                    # 尝试直接设置图标
                    self.setVisible(True)
                    logger.info("尝试通过setVisible(True)显示托盘图标")
                except Exception as e2:
                    logger.error(f"后备显示方法也失败: {e2}")

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self._open()

    def _open(self):
        self.main.show()
        self.main.raise_()
        self.main.activateWindow()

    def _toggle_autostart(self):
        self.main._toggle_autostart()

    def _toggle_autoreconnect(self):
        self.main._toggle_autoreconnect()

    def _exit(self):
        self.hide()
        self.main.close()

    def show_message(self, title: str, text: str, duration_ms: int = 3000):
        self.showMessage(title, text, self.icon(), duration_ms)
