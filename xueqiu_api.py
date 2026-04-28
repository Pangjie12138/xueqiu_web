"""
雪球 API 封装（Web 服务版）
Cookie 从环境变量或 data/session.json 读取
"""
import os
import json
import time
import requests
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent


def load_cookie() -> str:
    """
    加载雪球 Cookie，优先环境变量，其次 session.json
    环境变量格式：XUEQIU_COOKIE="xq_a_token=xxx; u=xxx"
    """
    cookie_env = os.environ.get("XUEQIU_COOKIE", "")
    if cookie_env:
        return cookie_env

    session_path = BASE_DIR / "data" / "session.json"
    if session_path.exists():
        with open(session_path, encoding="utf-8") as f:
            session = json.load(f)
        parts = [f"{c['name']}={c['value']}" for c in session.get("cookies", [])]
        return "; ".join(parts)

    return ""


def build_headers() -> dict:
    cookie = load_cookie()
    return {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Cookie": cookie,
        "Referer": "https://xueqiu.com/",
        "Accept": "application/json, text/plain, */*",
    }


_anon_session = None

def _get_anon_session() -> requests.Session:
    """获取一个带匿名 token 的 session（缓存复用）"""
    global _anon_session
    if _anon_session is None:
        _anon_session = requests.Session()
        _anon_session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": "https://xueqiu.com/",
            "Accept": "application/json, text/plain, */*",
        })
        _anon_session.get("https://xueqiu.com/", timeout=10)
        _anon_session.get("https://xueqiu.com/hq", timeout=10)
    return _anon_session


def validate_symbol(cube_symbol: str) -> dict:
    """
    验证组合编号是否存在，返回组合基本信息
    用匿名 session（先访问首页拿 token）
    """
    symbol = cube_symbol.strip().upper()
    try:
        s = _get_anon_session()
        resp = s.get(
            f"https://xueqiu.com/cubes/quote.json?code={symbol}",
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            info = data.get(symbol, {})
            if info and info.get("name"):
                return {
                    "valid": True,
                    "symbol": symbol,
                    "name": info.get("name", ""),
                    "owner": info.get("owner", {}).get("screen_name", "") if isinstance(info.get("owner"), dict) else "",
                    "net_value": info.get("net_value", ""),
                    "total_gain": info.get("total_gain", ""),
                }
        # token 可能过期，清空重试一次
        global _anon_session
        _anon_session = None
        s = _get_anon_session()
        resp = s.get(f"https://xueqiu.com/cubes/quote.json?code={symbol}", timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            info = data.get(symbol, {})
            if info and info.get("name"):
                return {
                    "valid": True,
                    "symbol": symbol,
                    "name": info.get("name", ""),
                    "owner": info.get("owner", {}).get("screen_name", "") if isinstance(info.get("owner"), dict) else "",
                    "net_value": info.get("net_value", ""),
                    "total_gain": info.get("total_gain", ""),
                }
        return {"valid": False, "error": "组合不存在或已关闭"}
    except Exception as e:
        _anon_session = None
        return {"valid": False, "error": str(e)}


def get_rebalancing_history(cube_symbol: str, count: int = 20) -> list:
    """拉取组合调仓历史（需要登录 Cookie）"""
    headers = build_headers()
    if not headers.get("Cookie"):
        return []

    try:
        resp = requests.get(
            "https://xueqiu.com/cubes/rebalancing/history.json",
            headers=headers,
            params={"cube_symbol": cube_symbol, "count": count, "page": 1},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("list", [])
    except Exception as e:
        print(f"[ERROR] get_rebalancing_history({cube_symbol}): {e}")
        return []


def filter_recent(items: list, since_ts_ms: int) -> list:
    """过滤出指定时间戳之后的调仓"""
    return [item for item in items if item.get("created_at", 0) >= since_ts_ms]


def parse_rebalancing(item: dict) -> dict:
    """解析单条调仓记录"""
    stocks = []
    for r in item.get("rebalancing_histories", []):
        prev = r.get("prev_weight", 0) or 0
        target = r.get("target_weight", 0) or 0
        stocks.append({
            "stock_symbol": r.get("stock_symbol", ""),
            "stock_name": r.get("stock_name", ""),
            "prev_weight": prev,
            "target_weight": target,
            "weight_diff": round(target - prev, 2),
            "price": r.get("price", 0),
        })

    created_at = item.get("created_at", 0)
    return {
        "id": item.get("id"),
        "created_at": created_at,
        "created_at_str": datetime.fromtimestamp(created_at / 1000).strftime("%Y-%m-%d %H:%M") if created_at else "",
        "comment": item.get("comment", ""),
        "stocks_changed": stocks,
    }
