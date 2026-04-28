"""
雪球组合调仓监控 — Web 服务
Flask 主应用
"""
import os
import uuid
from flask import Flask, request, jsonify, render_template, redirect, url_for
from apscheduler.schedulers.background import BackgroundScheduler

import db
import xueqiu_api
import scheduler as job_scheduler

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "xueqiu-monitor-dev-key")

# 初始化数据库
db.init_db()


# ── 页面路由 ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """首页 — 订阅表单"""
    stats = db.get_stats()
    return render_template("index.html", stats=stats)


@app.route("/unsubscribe/<token>")
def unsubscribe_page(token):
    """取消订阅页面"""
    ok = db.remove_subscription(token)
    return render_template("unsubscribe.html", success=ok)


# ── API 路由 ──────────────────────────────────────────────────────────────────

@app.route("/api/validate", methods=["POST"])
def api_validate():
    """验证组合编号是否存在"""
    data = request.get_json(silent=True) or {}
    symbol = data.get("cube_symbol", "").strip().upper()
    if not symbol:
        return jsonify({"valid": False, "error": "请输入组合编号"}), 400

    result = xueqiu_api.validate_symbol(symbol)
    return jsonify(result)


@app.route("/api/subscribe", methods=["POST"])
def api_subscribe():
    """创建订阅"""
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip().lower()
    symbol = data.get("cube_symbol", "").strip().upper()

    if not email or "@" not in email:
        return jsonify({"ok": False, "error": "请输入有效的邮箱地址"}), 400
    if not symbol or not symbol.startswith("ZH"):
        return jsonify({"ok": False, "error": "组合编号格式错误，应以 ZH 开头"}), 400

    # 验证组合是否存在
    info = xueqiu_api.validate_symbol(symbol)
    if not info.get("valid"):
        return jsonify({"ok": False, "error": f"组合 {symbol} 不存在或已关闭"}), 400

    # 限制每个邮箱最多订阅 10 个组合
    existing = db.get_subscriptions_by_email(email)
    if len(existing) >= 10:
        return jsonify({"ok": False, "error": "每个邮箱最多订阅 10 个组合"}), 400

    token = uuid.uuid4().hex
    result = db.add_subscription(
        email=email,
        cube_symbol=symbol,
        cube_name=info.get("name", ""),
        token=token,
    )

    return jsonify({
        "ok": True,
        "cube_name": info.get("name", ""),
        "owner": info.get("owner", ""),
        "message": "订阅成功！有调仓时会发邮件通知你。",
    })


@app.route("/api/my-subscriptions", methods=["POST"])
def api_my_subscriptions():
    """查询我的订阅"""
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip().lower()
    if not email:
        return jsonify({"ok": False, "error": "请输入邮箱"}), 400

    subs = db.get_subscriptions_by_email(email)
    return jsonify({"ok": True, "subscriptions": subs})


@app.route("/api/stats")
def api_stats():
    """公开统计信息"""
    return jsonify(db.get_stats())


# ── 手动触发（管理用）────────────────────────────────────────────────────────

@app.route("/api/trigger", methods=["POST"])
def api_trigger():
    """手动触发一次监控任务（需要 admin key）"""
    data = request.get_json(silent=True) or {}
    admin_key = os.environ.get("ADMIN_KEY", "")
    if admin_key and data.get("key") != admin_key:
        return jsonify({"ok": False, "error": "unauthorized"}), 403
    if not admin_key:
        return jsonify({"ok": False, "error": "ADMIN_KEY not set"}), 500

    import threading
    threading.Thread(target=job_scheduler.run_monitor_job, daemon=True).start()
    return jsonify({"ok": True, "message": "监控任务已触发，后台执行中"})


# ── 定时任务 ──────────────────────────────────────────────────────────────────

def start_scheduler():
    """启动定时任务"""
    sched = BackgroundScheduler()
    hour = int(os.environ.get("MONITOR_HOUR", "18"))
    minute = int(os.environ.get("MONITOR_MINUTE", "0"))
    sched.add_job(
        job_scheduler.run_monitor_job,
        "cron",
        hour=hour,
        minute=minute,
        id="daily_monitor",
    )
    sched.start()
    print(f"✅ 定时任务已启动：每天 {hour:02d}:{minute:02d} 执行调仓监控")


# gunicorn --preload 模式下启动定时任务（只在主进程执行一次）
start_scheduler()


# ── 本地开发 ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
