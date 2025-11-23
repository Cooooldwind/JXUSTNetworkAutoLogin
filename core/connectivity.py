import requests
from loguru import logger


TARGETS = [
    ("https://www.baidu.com", None),
    ("https://www.qq.com", None),
    ("http://www.msftncsi.com/ncsi.txt", "Microsoft NCSI"),
]


def is_online(timeout: float = 2.5) -> bool:
    logger.debug(f"开始网络连接检查，超时设置: {timeout}秒")
    for url, must_contain in TARGETS:
        try:
            logger.debug(f"检查目标连接: {url}")
            r = requests.head(url, timeout=timeout, allow_redirects=True)
            logger.debug(f"目标 {url} HEAD响应状态码: {r.status_code}")
            if 200 <= r.status_code < 400:
                logger.info(f"网络连接检查通过: {url} HEAD请求成功")
                return True
        except Exception as e:
            logger.warning(f"目标 {url} HEAD请求失败: {str(e)}")
        try:
            logger.debug(f"尝试GET请求: {url}")
            r = requests.get(url, timeout=timeout, allow_redirects=True)
            logger.debug(f"目标 {url} GET响应状态码: {r.status_code}")
            if 200 <= r.status_code < 400:
                if must_contain is None:
                    logger.info(f"网络连接检查通过: {url} GET请求成功")
                    return True
                if must_contain in r.text:
                    logger.info(f"网络连接检查通过: {url} 包含指定内容 '{must_contain}'")
                    return True
        except Exception as e:
            logger.warning(f"目标 {url} GET请求失败: {str(e)}")
    logger.error("所有目标连接检查失败，网络可能未连接")
    return False