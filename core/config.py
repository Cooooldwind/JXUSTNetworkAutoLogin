import os
import json
from dataclasses import dataclass, asdict
from pathlib import Path
import yaml
import base64
import logging

try:
    import keyring
except Exception:
    keyring = None

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 应用目录配置
APP_DIR = os.path.join(os.getenv("APPDATA", str(Path.home())), "jxust_network_login")
CONFIG_PATH = os.path.join(APP_DIR, "config.yaml")
# 添加密码文件作为后备方案
PASSWORDS_FILE = os.path.join(APP_DIR, "passwords.json")
SERVICE = "jxust_network_login"


def ensure_dir():
    Path(APP_DIR).mkdir(parents=True, exist_ok=True)


def default_config() -> dict:
    return {
        "account": "",
        "carrier": "none",
        "auto_start": {
            "registry": False,
            "task_scheduler": False,
            "service": False
        },
        "auto_reconnect": True,
        "check_interval": 15,
        "endpoint_base": "http://10.17.8.18:801",
        "callback_login": "dr1003",
        "callback_logout": "dr1004",
    }


def load_config() -> dict:
    ensure_dir()
    if not os.path.exists(CONFIG_PATH):
        return default_config()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            base = default_config()
            
            # 迁移旧配置：将单个布尔值 auto_start 转换为字典格式
            if isinstance(data.get("auto_start"), bool):
                old_auto_start = data.pop("auto_start")
                data["auto_start"] = {
                    "registry": old_auto_start,
                    "task_scheduler": False,
                    "service": False
                }
            
            base.update(data)
            return base
    except Exception:
        return default_config()


def save_config(data: dict):
    ensure_dir()
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def _load_passwords_file() -> dict:
    """从文件加载密码（后备方案）"""
    if not os.path.exists(PASSWORDS_FILE):
        return {}
    try:
        with open(PASSWORDS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"加载密码文件失败: {e}")
        return {}

def _save_passwords_file(passwords: dict) -> bool:
    """保存密码到文件（后备方案）"""
    try:
        with open(PASSWORDS_FILE, 'w', encoding='utf-8') as f:
            json.dump(passwords, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"保存密码文件失败: {e}")
        return False

def set_password(username: str, password: str) -> bool:
    """设置密码，优先使用keyring，失败则使用文件存储"""
    # 优先尝试keyring
    if keyring:
        try:
            keyring.set_password(SERVICE, username, password)
            logger.info(f"使用keyring成功保存用户 {username} 的密码")
            return True
        except Exception as e:
            logger.warning(f"keyring保存密码失败: {e}，尝试使用文件存储")
    
    # 后备方案：使用文件存储
    try:
        passwords = _load_passwords_file()
        # 简单的base64编码（仅作基本混淆，不是安全加密）
        passwords[username] = base64.b64encode(password.encode('utf-8')).decode('utf-8')
        success = _save_passwords_file(passwords)
        if success:
            logger.info(f"使用文件成功保存用户 {username} 的密码")
        return success
    except Exception as e:
        logger.error(f"文件存储密码失败: {e}")
        return False


def get_password(username: str) -> str:
    """获取密码，优先使用keyring，失败则从文件读取"""
    # 优先尝试keyring
    if keyring:
        try:
            password = keyring.get_password(SERVICE, username)
            if password:
                logger.info(f"使用keyring成功获取用户 {username} 的密码")
                return password
        except Exception as e:
            logger.warning(f"keyring获取密码失败: {e}，尝试从文件读取")
    
    # 后备方案：从文件读取
    try:
        passwords = _load_passwords_file()
        if username in passwords:
            # 解码base64
            encoded = passwords[username]
            password = base64.b64decode(encoded).decode('utf-8')
            logger.info(f"使用文件成功获取用户 {username} 的密码")
            return password
    except Exception as e:
        logger.error(f"文件读取密码失败: {e}")
    
    logger.warning(f"无法获取用户 {username} 的密码")
    return ""