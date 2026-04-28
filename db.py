"""
SQLite 数据库管理 — 订阅表
"""
import sqlite3
import os
from datetime import datetime
from pathlib import Path

DB_PATH = os.environ.get("DB_PATH", str(Path(__file__).parent / "data" / "subscriptions.db"))


def get_conn():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_conn()
    conn.execute("""
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
    """)
    conn.commit()
    conn.close()
    print("✅ 数据库已初始化")


def add_subscription(email: str, cube_symbol: str, cube_name: str, token: str) -> dict:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO subscriptions (email, cube_symbol, cube_name, created_at, unsubscribe_token) VALUES (?, ?, ?, ?, ?)",
            (email, cube_symbol.upper(), cube_name, datetime.now().isoformat(), token),
        )
        conn.commit()
        return {"ok": True}
    except sqlite3.IntegrityError:
        conn.execute(
            "UPDATE subscriptions SET is_active = 1, cube_name = ? WHERE email = ? AND cube_symbol = ?",
            (cube_name, email, cube_symbol.upper()),
        )
        conn.commit()
        return {"ok": True, "reactivated": True}
    finally:
        conn.close()


def remove_subscription(token: str) -> bool:
    conn = get_conn()
    cursor = conn.execute(
        "UPDATE subscriptions SET is_active = 0 WHERE unsubscribe_token = ? AND is_active = 1",
        (token,),
    )
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0


def get_all_active_subscriptions() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM subscriptions WHERE is_active = 1 ORDER BY cube_symbol").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_subscriptions_by_email(email: str) -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM subscriptions WHERE email = ? AND is_active = 1", (email,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_unique_symbols() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT DISTINCT cube_symbol FROM subscriptions WHERE is_active = 1").fetchall()
    conn.close()
    return [r["cube_symbol"] for r in rows]


def get_subscribers_for_symbol(cube_symbol: str) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT email, unsubscribe_token FROM subscriptions WHERE cube_symbol = ? AND is_active = 1",
        (cube_symbol,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stats() -> dict:
    conn = get_conn()
    total_subs = conn.execute("SELECT COUNT(*) FROM subscriptions WHERE is_active = 1").fetchone()[0]
    total_users = conn.execute("SELECT COUNT(DISTINCT email) FROM subscriptions WHERE is_active = 1").fetchone()[0]
    total_symbols = conn.execute("SELECT COUNT(DISTINCT cube_symbol) FROM subscriptions WHERE is_active = 1").fetchone()[0]
    conn.close()
    return {"total_subscriptions": total_subs, "total_users": total_users, "total_symbols": total_symbols}
