"""HTML report generator for audit results."""
import html
from datetime import datetime
from typing import Optional

from ..models import AuditResult, CheckResult, CheckType


def _trust_color(level: str) -> str:
    return {
        "high": "#16a34a",
        "medium": "#d97706",
        "low": "#dc2626",
        "critical": "#991b1b",
        "unknown": "#64748b",
    }.get(level, "#64748b")


def _trust_label(level: str) -> str:
    return {
        "high": "高信任度",
        "medium": "中等信任",
        "low": "低信任度",
        "critical": "危险",
        "unknown": "未知",
    }.get(level, level)


def _check_icon(passed: bool) -> str:
    return "✅" if passed else "❌"


def _check_type_label(check_type: CheckType) -> str:
    return {
        CheckType.TOKEN_COUNT: "Token 计数验证",
        CheckType.MODEL_FINGERPRINT: "模型指纹检测",
        CheckType.RESPONSE_LATENCY: "延迟与可用性",
        CheckType.PROTOCOL_COMPLIANCE: "协议合规性",
        CheckType.CAPABILITY_TEST: "能力测试",
    }.get(check_type, check_type.value)


def _score_bar(score: float, passed: bool) -> str:
    color = "#16a34a" if passed else "#dc2626"
    width = min(max(score, 0), 100)
    return f'''<div style="background:#e2e8f0;border-radius:4px;height:8px;width:100%;margin:4px 0;">
        <div style="background:{color};height:100%;width:{width}%;border-radius:4px;"></div>
    </div>'''


def _evidence_table(evidence: dict) -> str:
    if not evidence:
        return ""
    rows = []
    for key, value in evidence.items():
        if isinstance(value, dict):
            value = html.escape(str(value)[:200])
        elif isinstance(value, list):
            value = html.escape(str(value)[:200])
        else:
            value = html.escape(str(value)[:200])
        rows.append(f"<tr><td style='padding:4px 8px;font-weight:600;'>{html.escape(str(key))}</td>"
                    f"<td style='padding:4px 8px;'>{value}</td></tr>")
    return f"<table style='width:100%;font-size:0.8rem;border-collapse:collapse;'>{''.join(rows)}</table>"


def generate_html_report(result: AuditResult) -> str:
    """Generate a standalone HTML report from an audit result."""
    trust_color = _trust_color(result.trust_level)
    trust_label = _trust_label(result.trust_level)
    duration = ""
    if result.completed_at and result.started_at:
        duration = f"{(result.completed_at - result.started_at).total_seconds():.1f}s"

    # Checks HTML
    checks_html = ""
    for check in result.checks:
        checks_html += f'''
        <div style="background:#f8fafc;border-radius:8px;padding:16px;margin-bottom:12px;border-left:4px solid {'#16a34a' if check.passed else '#dc2626'};">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                <span style="font-weight:600;font-size:1rem;">{_check_icon(check.passed)} {html.escape(check.name)}</span>
                <span style="font-size:1.2rem;font-weight:700;color:{'#16a34a' if check.passed else '#dc2626'};">{check.score:.0f}/100</span>
            </div>
            {_score_bar(check.score, check.passed)}
            <p style="margin:8px 0 0;font-size:0.85rem;color:#475569;">{html.escape(check.details)}</p>
            <details style="margin-top:8px;">
                <summary style="cursor:pointer;font-size:0.8rem;color:#64748b;">查看证据</summary>
                <div style="margin-top:8px;">{_evidence_table(check.evidence)}</div>
            </details>
        </div>'''

    # Token comparison
    token_html = ""
    if result.token_comparison:
        tc = result.token_comparison
        token_html = f'''
        <div style="background:#f8fafc;border-radius:8px;padding:16px;margin-bottom:12px;">
            <h3 style="margin:0 0 12px;font-size:1rem;">📊 Token 计数对比</h3>
            <table style="width:100%;font-size:0.85rem;border-collapse:collapse;">
                <tr><td style="padding:6px 8px;font-weight:600;">报告的 Prompt Tokens</td><td style="padding:6px 8px;">{tc.prompt_tokens_reported}</td></tr>
                <tr><td style="padding:6px 8px;font-weight:600;">预期 Prompt Tokens</td><td style="padding:6px 8px;">{tc.prompt_tokens_expected or 'N/A'}</td></tr>
                <tr><td style="padding:6px 8px;font-weight:600;">报告的 Completion Tokens</td><td style="padding:6px 8px;">{tc.completion_tokens_reported}</td></tr>
                <tr><td style="padding:6px 8px;font-weight:600;">预期 Completion Tokens</td><td style="padding:6px 8px;">{tc.completion_tokens_expected or 'N/A'}</td></tr>
                <tr><td style="padding:6px 8px;font-weight:600;">总 Tokens</td><td style="padding:6px 8px;font-weight:700;">{tc.total_tokens_reported}</td></tr>
                <tr><td style="padding:6px 8px;font-weight:600;">Prompt 差异率</td><td style="padding:6px 8px;color:{'#dc2626' if (tc.prompt_inflation_pct or 0) > 10 else '#16a34a'};">{tc.prompt_inflation_pct:+.1f}%</td></tr>
                <tr><td style="padding:6px 8px;font-weight:600;">Completion 差异率</td><td style="padding:6px 8px;color:{'#dc2626' if (tc.completion_inflation_pct or 0) > 10 else '#16a34a'};">{tc.completion_inflation_pct:+.1f}%</td></tr>
                <tr><td style="padding:6px 8px;font-weight:600;">Chat Template 估算</td><td style="padding:6px 8px;">{tc.chat_template_overhead} tokens</td></tr>
                <tr><td style="padding:6px 8px;font-weight:600;">可疑</td><td style="padding:6px 8px;font-weight:700;color:{'#dc2626' if tc.suspicious else '#16a34a'};">{'⚠ 是（已扣除chat template）' if tc.suspicious else '否'}</td></tr>
            </table>
            {'<p style="margin-top:8px;font-size:0.75rem;color:#64748b;">💡 ' + html.escape(tc.discrepancy_note) + '</p>' if tc.discrepancy_note else ''}
        </div>'''

    # Fingerprint
    fp_html = ""
    if result.fingerprint:
        fp = result.fingerprint
        fp_html = f'''
        <div style="background:#f8fafc;border-radius:8px;padding:16px;margin-bottom:12px;">
            <h3 style="margin:0 0 12px;font-size:1rem;">🔍 模型指纹分析</h3>
            <table style="width:100%;font-size:0.85rem;border-collapse:collapse;">
                <tr><td style="padding:6px 8px;font-weight:600;">声称模型</td><td style="padding:6px 8px;">{html.escape(fp.claimed_model)}</td></tr>
                <tr><td style="padding:6px 8px;font-weight:600;">检测到的家族</td><td style="padding:6px 8px;">{html.escape(fp.detected_family or 'N/A')}</td></tr>
                <tr><td style="padding:6px 8px;font-weight:600;">家族匹配</td><td style="padding:6px 8px;color:{'#16a34a' if fp.family_match else '#dc2626'};">{'✅ 匹配' if fp.family_match else '❌ 不匹配'}</td></tr>
                <tr><td style="padding:6px 8px;font-weight:600;">置信度</td><td style="padding:6px 8px;">{fp.confidence:.0%}</td></tr>
                <tr><td style="padding:6px 8px;font-weight:600;">可疑</td><td style="padding:6px 8px;font-weight:700;color:{'#dc2626' if fp.suspicious else '#16a34a'};">{'⚠ 是' if fp.suspicious else '否'}</td></tr>
            </table>
        </div>'''

    # Recommendations
    recs_html = ""
    if result.recommendations:
        recs_items = "".join(f"<li style='margin-bottom:6px;'>{html.escape(rec)}</li>" for rec in result.recommendations)
        recs_html = f'''
        <div style="background:#fef3c7;border-radius:8px;padding:16px;margin-bottom:12px;">
            <h3 style="margin:0 0 12px;font-size:1rem;color:#92400e;">💡 建议</h3>
            <ul style="margin:0;padding-left:20px;font-size:0.9rem;color:#78350f;">{recs_items}</ul>
        </div>'''

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TransitTruth 审计报告 - {html.escape(result.model)}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f1f5f9; margin: 0; padding: 20px; color: #1e293b; }}
        .container {{ max-width: 800px; margin: 0 auto; }}
        .header {{ background: linear-gradient(135deg, #1e40af, #3b82f6); color: white; border-radius: 12px; padding: 24px; margin-bottom: 20px; }}
        .header h1 {{ margin: 0 0 8px; font-size: 1.5rem; }}
        .header .meta {{ font-size: 0.85rem; opacity: 0.9; }}
        .score-section {{ background: white; border-radius: 12px; padding: 24px; margin-bottom: 20px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .score-number {{ font-size: 3.5rem; font-weight: 800; line-height: 1; }}
        .score-label {{ font-size: 1.2rem; font-weight: 600; margin-top: 4px; }}
        .footer {{ text-align: center; font-size: 0.75rem; color: #94a3b8; margin-top: 20px; padding: 20px; }}
        details summary {{ cursor: pointer; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🛡️ TransitTruth 审计报告</h1>
            <div class="meta">
                审计 ID: {html.escape(result.audit_id)} | 
                模型: {html.escape(result.model)} | 
                URL: {html.escape(result.base_url)}<br>
                时间: {result.started_at.strftime("%Y-%m-%d %H:%M:%S")} | 
                耗时: {duration}
            </div>
        </div>

        <div class="score-section">
            <div class="score-number" style="color:{trust_color};">{result.overall_score:.0f}<span style="font-size:1.5rem;color:#94a3b8;">/100</span></div>
            <div class="score-label" style="color:{trust_color};">{trust_label}</div>
        </div>

        {token_html}
        {fp_html}

        <h2 style="font-size:1.2rem;margin:20px 0 12px;">检测项目详情</h2>
        {checks_html}

        {recs_html}

        <div class="footer">
            <p>由 TransitTruth v0.1.0 生成 | 开源 AI API 中转站验真器</p>
            <p>本报告基于有限样本，不构成对任何服务的最终评价 | API Key 未被存储</p>
        </div>
    </div>
</body>
</html>'''
