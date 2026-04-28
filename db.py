"""
数据库管理 — 订阅表
支持两种模式：
  1. Turso 云数据库（Vercel 部署用，设置 TURSO_URL + TURSO_TOKEN 环境变量）
  2. 本地 SQLite（本地开发用，不设环境变量时自动 fallback）
"""
import os
import json
import sqlite3
import requests
from datetime import datetime
from pathlib import Path

TURSO_URL = os.environ.get("TURSO_URL", "")  # e.g. https://xxx.turso.io
TURSO_TOKEN = os.environ.get("TURSO_TOKEN", "")
DB_PATH = os.environ.get("DB_PATH", str(Path(__file__).parent / "data" / "subscriptions.db"))

USE_TURSO = bool(TURSO_URL and TURSO_TOKEN)


# ── Turso HTTP API ────────────────────────────────────────────────────────────

def _turso_execute(sql: str, args: list = None) -> list:
    """通过 Turso HTTP API 执行 SQL"""
    url = f"{TURSO_URL}/v2/pipeline"
    headers = {"Authorization": f"Bearer {TURSO_TOKEN}", "Content-Type": "application/json"}

    stmt = {"type": "execute", "stmt": {"sql": sql}}
    if args:
        stmt["stmt"]["args"] = [{"type": "text", "value": str(a)} if isinstance(a, str)
                                 else {"type": "integer", "value": str(a)}
                                 for a in args]

    payload = {"requests": [stmt, {"type": "close"}]}
    resp = requests.post(url, json=payload, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    result = data.get("results", [{}])[0].get("response", {}).get("result", {})
    cols = [c["name"] for c in result.get("cols", [])]
    rows = []
    for row in result.get("rows", []):
        rows.append({cols[i]: (v.get("value") if v.get("type") != "null" else None) for i, v in enumerate(row)})
    return rows


def _turso_execute_write(sql: str, args: list = None) -> int:
    """执行写操作，返回 affected_rows"""
    url = f"{TURSO_URL}/v2/pipeline"
    headers = {"Authorization": f"Bearer {TURSO_TOKEN}", "Content-Type": "application/json"}

    stmt = {"type": "execute", "stmt": {"sql": sql}}
    if args:
        stmt["stmt"]["args"] = [{"type": "text", "value": str(a)} if isinstance(a, str)
                                 else {"type": "integer", "value": str(a)}
                                 for a in args]

    payload = {"requests": [stmt, {"type": "close"}]}
    resp = requests.post(url, json=payload, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return data.get("results", [{}])[0].get("response", {}).get("result", {}).get("affected_row_count", 0)


# ── 本地 SQLite ──────────────────────────────────────────────────────────────

def _local_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── 初始化 ────────────────────────────────────────────────────────────────────

CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL,
        cube_symbol TEXT NOT NULL,
        cube_name TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        is_active INTEGER DEFAULT 1,
        unsubscribe_token TEXT NOT NULL,
        UNIQUE(email, cube_symbol)
    )
"""


def init_db():
    if USE_TURSO:
        _turso_execute(CREATE_TABLE_SQL)
        print("✅ Turso 云数据库已连接")
    else:
        Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
        conn = _local_conn()
        conn.execute(CREATE_TABLE_SQL)
        conn.commit()
        conn.close()
        print("✅ 本地 SQLite 数据库已初始化")


# ── CRUD 操作 ─────────────────────────────────────────────────────────────────

def add_subscription(email: str, cube_symbol: str, cube_name: str, token: str) -> dict:
    symbol = cube_symbol.upper()
    now = datetime.now().isoformat()

    if USE_TURSO:
        try:
            _turso_execute_write(
                "INSERT INTO subscriptions (email, cube_symbol, cube_name, created_at, unsubscribe_token) VALUES (?, ?, ?, ?, ?)",
                [email, symbol, cube_name, now, token],
            )
            return {"ok": True}
        except Exception as e:
            if "UNIQUE" in str(e) or "constraint" in str(e).lower():
                _turso_execute_write(
                    "UPDATE subscriptions SET is_active = 1, cube_name = ? WHERE email = ? AND cube_symbol = ?",
                    [cube_name, email, symbol],
                )
                return {"ok": True, "reactivated": True}
            raise
    else:
        conn = _local_conn()
        try:
            conn.execute(
                "INSERT INTO subscriptions (email, cube_symbol, cube_name, created_at, unsubscribe_token) VALUES (?, ?, ?, ?, ?)",
                (email, symbol, cube_name, now, token),
            )
            conn.commit()
            return {"ok": True}
        except sqlite3.IntegrityError:
            conn.execute(
                "UPDATE subscriptions SET is_active = 1, cube_name = ? WHERE email = ? AND cube_symbol = ?",
                (cube_name, email, symbol),
            )
            conn.commit()
            return {"ok": True, "reactivated": True}
        finally:
            conn.close()


def remove_subscription(token: str) -> bool:
    if USE_TURSO:
        affected = _turso_execute_write(
            "UPDATE subscriptions SET is_active = 0 WHERE unsubscribe_token = ? AND is_active = 1",
            [token],
        )
        return affected > 0
    else:
        conn = _local_conn()
        cursor = conn.execute(
            "UPDATE subscriptions SET is_active = 0 WHERE unsubscribe_token = ? AND is_active = 1",
            (token,),
        )
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        return affected > 0


def get_all_active_subscriptions() -> list:
    if USE_TURSO:
        return _turso_execute("SELECT * FROM subscriptions WHERE is_active = 1 ORDER BY cube_symbol")
    else:
        conn = _local_conn()
        rows = conn.execute("SELECT * FROM subscriptions WHERE is_active = 1 ORDER BY cube_symbol").fetchall()
        conn.close()
        return [dict(r) for r in rows]


def get_subscriptions_by_email(email: str) -> list:
    if USE_TURSO:
        return _turso_execute("SELECT * FROM subscriptions WHERE email = ? AND is_active = 1", [email])
    else:
        conn = _local_conn()
        rows = conn.execute("SELECT * FROM subscriptions WHERE email = ? AND is_active = 1", (email,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]


def get_unique_symbols() -> list:
    if USE_TURSO:
        rows = _turso_execute("SELECT DISTINCT cube_symbol FROM subscriptions WHERE is_active = 1")
        return [r["cube_symbol"] for r in rows]
    else:
        conn = _local_conn()
        rows = conn.execute("SELECT DISTINCT cube_symbol FROM subscriptions WHERE is_active = 1").fetchall()
        conn.close()
        return [r["cube_symbol"] for r in rows]


def get_subscribers_for_symbol(cube_symbol: str) -> list:
    if USE_TURSO:
        return _turso_execute(
            "SELECT email, unsubscribe_token FROM subscriptions WHERE cube_symbol = ? AND is_active = 1",
            [cube_symbol],
        )
    else:
        conn = _local_conn()
        rows = conn.execute(
            "SELECT email, unsubscribe_token FROM subscriptions WHERE cube_symbol = ? AND is_active = 1",
            (cube_symbol,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


def get_stats() -> dict:
    if USE_TURSO:
        r1 = _turso_execute("SELECT COUNT(*) as c FROM subscriptions WHERE is_active = 1")
        r2 = _turso_execute("SELECT COUNT(DISTINCT email) as c FROM subscriptions WHERE is_active = 1")
        r3 = _turso_execute("SELECT COUNT(DISTINCT cube_symbol) as c FROM subscriptions WHERE is_active = 1")
        return {
            "total_subscriptions": int(r1[0]["c"]) if r1 else 0,
            "total_users": int(r2[0]["c"]) if r2 else 0,
            "total_symbols": int(r3[0]["c"]) if r3 else 0,
        }
    else:
        conn = _local_conn()
        total_subs = conn.execute("SELECT COUNT(*) FROM subscriptions WHERE is_active = 1").fetchone()[0]
        total_users = conn.execute("SELECT COUNT(DISTINCT email) FROM subscriptions WHERE is_active = 1").fetchone()[0]
        total_symbols = conn.execute("SELECT COUNT(DISTINCT cube_symbol) FROM subscriptions WHERE is_active = 1").fetchone()[0]
        conn.close()
        return {"total_subscriptions": total_subs, "total_users": total_users, "total_symbols": total_symbols}
