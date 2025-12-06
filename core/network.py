import json
import socket
from urllib.parse import urlencode

import requests
from loguru import logger


def compose_account(account: str, carrier: str) -> str:
    carrier = (carrier or "").strip().lower()
    if carrier in ("telecom", "cmcc", "unicom"):
        return f"{account}@{carrier}"
    return account


def _strip_jsonp(text: str) -> str:
    s = text.strip()
    i = s.find("(")
    j = s.rfind(")")
    if i != -1 and j != -1 and j > i:
        return s[i + 1 : j]
    return s


def parse_jsonp(text: str) -> dict:
    try:
        body = _strip_jsonp(text)
        return json.loads(body)
    except Exception:
        return {"result": 0, "msg": "parse error"}


def get_local_ip() -> str:
    ip = ""
    try:
        logger.debug("正在获取本地IP地址")
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("1.1.1.1", 80))
        ip = s.getsockname()[0]
        logger.debug(f"获取到本地IP: {ip}")
    except Exception as e:
        logger.error(f"获取本地IP失败: {str(e)}")
        pass
    try:
        s.close()
    except Exception:
        pass
    return ip


def login(base: str, account: str, password: str, carrier: str, callback: str = "dr1003", timeout: float = 5.0) -> dict:
    user = compose_account(account, carrier)
    url = f"{base.rstrip('/')}/eportal/portal/login"
    params = {
        "callback": callback,
        "login_method": "1",
        "user_account": user,
        "user_password": password,
    }
    
    # 记录日志，脱敏密码
    log_params = params.copy()
    if log_params.get("user_password"):
        log_params["user_password"] = "****"
    logger.info(f"登录请求: URL={url}, 参数={log_params}, 超时={timeout}")
    
    try:
        resp = requests.get(url, params=params, timeout=timeout)
        logger.debug(f"登录响应: 状态码={resp.status_code}, 内容长度={len(resp.text)} 字节")
        
        data = parse_jsonp(resp.text)
        logger.info(f"登录解析结果: result={data.get('result')}, msg={data.get('msg')}")
        
        ok = int(data.get("result", 0)) == 1
        if ok:
            logger.info("登录成功")
        else:
            logger.warning(f"登录失败: {data.get('msg', '未知错误')}")
        
        return {"ok": ok, "msg": data.get("msg", "success" if ok else "failed"), "data": data}
    except Exception as e:
        logger.error(f"登录异常: {str(e)}")
        return {"ok": False, "msg": str(e), "data": {}}


def logout(base: str, ip: str = "", callback: str = "dr1004", timeout: float = 5.0) -> dict:
    url = f"{base.rstrip('/')}/eportal/portal/logout"
    if not ip:
        ip = get_local_ip()
        logger.debug(f"自动获取本地IP: {ip}")
    
    params = {
        "callback": callback,
        "login_method": "1",
        "user_account": "drcom",
        "user_password": "123",
        "ac_logout": "0",
        "register_mode": "1",
        "wlan_user_ip": ip,
    }
    
    logger.info(f"登出请求: URL={url}, IP={ip}, 参数={params}, 超时={timeout}")
    
    try:
        resp = requests.get(url, params=params, timeout=timeout)
        logger.debug(f"登出响应: 状态码={resp.status_code}, 内容长度={len(resp.text)} 字节")
        
        data = parse_jsonp(resp.text)
        logger.info(f"登出解析结果: result={data.get('result')}, msg={data.get('msg')}")
        
        ok = int(data.get("result", 0)) == 1
        if ok:
            logger.info("登出成功")
        else:
            logger.warning(f"登出失败: {data.get('msg', '未知错误')}")
        
        return {"ok": ok, "msg": data.get("msg", "success" if ok else "failed"), "data": data}
    except Exception as e:
        logger.error(f"登出异常: {str(e)}")
        return {"ok": False, "msg": str(e), "data": {}}