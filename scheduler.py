"""
定时任务：遍历所有订阅，拉取调仓数据，发送邮件
"""
import time
import os
from datetime import datetime, timedelta

import db
import xueqiu_api
import reporter
import mailer

LOOKBACK_HOURS = int(os.environ.get("LOOKBACK_HOURS", "24"))
BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000")


def run_monitor_job():
    """执行一次完整的监控任务"""
    print(f"\n{'='*60}")
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始执行调仓监控任务")
    print(f"{'='*60}")

    symbols = db.get_unique_symbols()
    if not symbols:
        print("[INFO] 当前没有任何订阅，跳过")
        return

    print(f"[INFO] 共 {len(symbols)} 个组合需要监控")

    now = datetime.now()
    since_dt = now - timedelta(hours=LOOKBACK_HOURS)
    since_ts_ms = int(since_dt.timestamp() * 1000)
    period_start = since_dt.strftime("%Y-%m-%d %H:%M")
    period_end = now.strftime("%Y-%m-%d %H:%M")

    # 按组合拉取调仓数据
    results = {}
    for symbol in symbols:
        print(f"  [{symbol}] 拉取调仓数据...")
        raw = xueqiu_api.get_rebalancing_history(symbol, count=20)
        recent = xueqiu_api.filter_recent(raw, since_ts_ms)
        parsed = [xueqiu_api.parse_rebalancing(item) for item in recent]
        results[symbol] = parsed
        print(f"    → {len(parsed)} 条调仓记录")
        time.sleep(1)  # 避免请求过快

    # 按组合给订阅者发邮件
    sent_count = 0
    for symbol, rebalancings in results.items():
        if not rebalancings:
            continue  # 无调仓不发邮件

        subscribers = db.get_subscribers_for_symbol(symbol)
        if not subscribers:
            continue

        # 获取组合名称
        info = xueqiu_api.validate_symbol(symbol)
        cube_name = info.get("name", symbol) if info.get("valid") else symbol

        print(f"  [{symbol}] {cube_name}: {len(rebalancings)} 条调仓，通知 {len(subscribers)} 人")

        for sub in subscribers:
            unsubscribe_url = f"{BASE_URL}/unsubscribe/{sub['unsubscribe_token']}"
            html = reporter.build_email_report(
                cube_symbol=symbol,
                cube_name=cube_name,
                rebalancings=rebalancings,
                period_start=period_start,
                period_end=period_end,
                unsubscribe_url=unsubscribe_url,
            )
            subject = f"📊 {cube_name} 调仓通知 ({now.strftime('%m-%d')})"
            ok = mailer.send_email(to=sub["email"], subject=subject, body=html)
            if ok:
                sent_count += 1
            time.sleep(0.5)  # 邮件发送间隔

    print(f"\n✅ 监控任务完成，共发送 {sent_count} 封邮件")
