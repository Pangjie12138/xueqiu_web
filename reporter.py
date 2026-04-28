"""
HTML 报告生成（Web 服务版）
为每个用户生成个性化的调仓报告邮件
"""
from datetime import datetime


def build_email_report(
    cube_symbol: str,
    cube_name: str,
    rebalancings: list,
    period_start: str,
    period_end: str,
    unsubscribe_url: str,
) -> str:
    """为单个组合生成 HTML 邮件报告"""
    report_date = datetime.now().strftime("%Y-%m-%d")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8">
<style>
  body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         max-width: 700px; margin: 0 auto; padding: 20px; color: #333; background: #f5f5f5; }}
  .header {{ background: linear-gradient(135deg, #1a73e8, #0d47a1); color: white;
             padding: 24px; border-radius: 12px; margin-bottom: 20px; }}
  .header h1 {{ margin: 0 0 6px 0; font-size: 20px; }}
  .header p {{ margin: 0; opacity: 0.85; font-size: 13px; }}
  .card {{ background: white; border-radius: 10px; padding: 18px;
           margin-bottom: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
  .rb-time {{ font-size: 13px; color: #666; margin-bottom: 8px; }}
  .rb-comment {{ font-size: 14px; background: #fff3e0; padding: 8px 12px;
                 border-radius: 6px; margin-bottom: 10px; border-left: 3px solid #ff9800; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ background: #e8f0fe; padding: 8px; text-align: left; }}
  td {{ padding: 7px 8px; border-bottom: 1px solid #eee; }}
  .buy {{ color: #d32f2f; font-weight: bold; }}
  .sell {{ color: #388e3c; font-weight: bold; }}
  .footer {{ text-align: center; color: #999; font-size: 12px; margin-top: 24px; padding: 16px; }}
  .footer a {{ color: #999; }}
  .empty {{ text-align: center; color: #888; padding: 30px; }}
</style>
</head>
<body>
<div class="header">
  <h1>📊 {cube_name}（{cube_symbol}）调仓通知</h1>
  <p>监控周期：{period_start} ~ {period_end}</p>
</div>
"""

    if not rebalancings:
        html += '<div class="card empty"><p>✅ 监控周期内无调仓操作</p></div>\n'
    else:
        for rb in rebalancings:
            html += f'<div class="card">\n'
            html += f'  <div class="rb-time">⏰ 调仓时间：{rb["created_at_str"]}</div>\n'
            if rb.get("comment"):
                html += f'  <div class="rb-comment">💬 {rb["comment"]}</div>\n'

            stocks = rb.get("stocks_changed", [])
            if stocks:
                html += '  <table><tr><th>股票</th><th>代码</th><th>操作</th><th>调整前</th><th>调整后</th><th>变动</th></tr>\n'
                for s in stocks:
                    diff = s["weight_diff"]
                    action = "买入" if diff > 0 else ("卖出" if diff < 0 else "调整")
                    cls = "buy" if diff > 0 else ("sell" if diff < 0 else "")
                    html += (
                        f'  <tr><td>{s["stock_name"]}</td><td>{s["stock_symbol"]}</td>'
                        f'<td class="{cls}">{action}</td>'
                        f'<td>{s["prev_weight"]}%</td><td>{s["target_weight"]}%</td>'
                        f'<td class="{cls}">{diff:+.1f}%</td></tr>\n'
                    )
                html += '  </table>\n'
            html += '</div>\n'

    html += f"""
<div class="footer">
  由雪球调仓监控服务自动生成 · {report_date}<br>
  数据来源：xueqiu.com<br>
  <a href="{unsubscribe_url}">取消订阅</a>
</div>
</body></html>"""

    return html
