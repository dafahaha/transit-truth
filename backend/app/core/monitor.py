"""Continuous monitoring and alerting for AI API relays.

Monitors configured relays at regular intervals and sends alerts
when trust score drops below threshold or anomalies are detected.

Usage:
    transit-truth monitor --config monitor-config.json
    transit-truth monitor --api-key sk-xxx --model gpt-4o --interval 3600

Alert channels:
- Console (default)
- Email (SMTP)
- Telegram bot
- Webhook (Slack, Discord, etc.)
"""
import asyncio
import json
import smtplib
import time
from dataclasses import dataclass, field
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

import httpx

from .auditor import AuditEngine
from ..models import AuditRequest, AuditMode


@dataclass
class MonitorConfig:
    """Configuration for a monitoring task."""
    name: str
    api_key: str
    base_url: str
    model: str
    interval_seconds: int = 3600  # default: 1 hour
    alert_threshold: float = 60.0  # alert if score drops below this
    score_drop_threshold: float = 10.0  # alert if score drops by this much
    mode: AuditMode = AuditMode.QUICK
    probe_count: int = 5
    # Alert channels
    alert_channels: list[str] = field(default_factory=lambda: ["console"])
    # Email config
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    email_from: Optional[str] = None
    email_to: list[str] = field(default_factory=list)
    # Telegram config
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    # Webhook config
    webhook_url: Optional[str] = None


@dataclass
class MonitorRecord:
    """A single monitoring record."""
    timestamp: str
    score: float
    trust_level: str
    token_discrepancy: Optional[float]
    latency_ms: Optional[float]
    alerts: list[str] = field(default_factory=list)


class RelayMonitor:
    """Continuously monitor an AI API relay and send alerts."""

    def __init__(self, config: MonitorConfig):
        self.config = config
        self.engine = AuditEngine()
        self.history: list[MonitorRecord] = []
        self.baseline_score: Optional[float] = None

    async def run_once(self) -> MonitorRecord:
        """Run a single audit and check for alerts."""
        print(f"[{datetime.now().isoformat()}] Auditing {self.config.name} ({self.config.model})...")

        request = AuditRequest(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            model=self.config.model,
            mode=self.config.mode,
            probe_count=self.config.probe_count,
        )

        try:
            result = await self.engine.run_audit(request)
        except Exception as e:
            record = MonitorRecord(
                timestamp=datetime.now().isoformat(),
                score=0,
                trust_level="error",
                token_discrepancy=None,
                latency_ms=None,
                alerts=[f"Audit failed: {str(e)}"],
            )
            self._send_alerts(record)
            self.history.append(record)
            return record

        score = result.overall_score
        alerts = []

        # Check 1: Absolute score below threshold
        if score < self.config.alert_threshold:
            alerts.append(
                f"⚠️ Trust score {score}/100 below threshold {self.config.alert_threshold}"
            )

        # Check 2: Score drop from baseline
        if self.baseline_score is not None:
            drop = self.baseline_score - score
            if drop > self.config.score_drop_threshold:
                alerts.append(
                    f"📉 Trust score dropped by {drop:.1f} points "
                    f"(baseline: {self.baseline_score:.1f}, current: {score:.1f})"
                )

        # Check 3: Token discrepancy spike
        token_disc = None
        if result.token_comparison and result.token_comparison.prompt_inflation_pct is not None:
            token_disc = result.token_comparison.prompt_inflation_pct
            if abs(token_disc) > 50:
                alerts.append(f"🔢 Token discrepancy {token_disc:+.1f}% exceeds 50% threshold")

        # Check 4: High latency
        latency = None
        if result.latency_protocol and result.latency_protocol.avg_latency_ms:
            latency = result.latency_protocol.avg_latency_ms
            if latency > 10000:
                alerts.append(f"🐢 High latency: {latency:.0f}ms (>10s)")

        # Set baseline on first successful run
        if self.baseline_score is None and score > 0:
            self.baseline_score = score

        record = MonitorRecord(
            timestamp=datetime.now().isoformat(),
            score=score,
            trust_level=result.trust_level,
            token_discrepancy=token_disc,
            latency_ms=latency,
            alerts=alerts,
        )

        self.history.append(record)

        # Print summary
        status_icon = "✅" if not alerts else "🚨"
        print(f"  {status_icon} Score: {score}/100 ({result.trust_level})"
              f" | Token: {token_disc:+.1f}%" if token_disc is not None else "")
        if alerts:
            for alert in alerts:
                print(f"  {alert}")
            self._send_alerts(record)

        # Save history to file
        self._save_history()

        return record

    async def run_continuous(self):
        """Run continuous monitoring loop."""
        print(f"Starting continuous monitoring for '{self.config.name}'")
        print(f"  Interval: {self.config.interval_seconds}s ({self.config.interval_seconds/3600:.1f}h)")
        print(f"  Alert threshold: {self.config.alert_threshold}")
        print(f"  Press Ctrl+C to stop")
        print("=" * 60)

        try:
            while True:
                await self.run_once()
                print(f"  Next audit in {self.config.interval_seconds}s...\n")
                await asyncio.sleep(self.config.interval_seconds)
        except KeyboardInterrupt:
            print("\nMonitoring stopped by user.")
            print(f"Total records: {len(self.history)}")

    def _send_alerts(self, record: MonitorRecord):
        """Send alerts through configured channels."""
        if not record.alerts:
            return

        message = self._format_alert_message(record)

        for channel in self.config.alert_channels:
            try:
                if channel == "console":
                    self._alert_console(message)
                elif channel == "email" and self.config.smtp_host:
                    self._alert_email(message)
                elif channel == "telegram" and self.config.telegram_bot_token:
                    asyncio.create_task(self._alert_telegram(message))
                elif channel == "webhook" and self.config.webhook_url:
                    asyncio.create_task(self._alert_webhook(message, record))
            except Exception as e:
                print(f"  Failed to send alert via {channel}: {e}")

    def _format_alert_message(self, record: MonitorRecord) -> str:
        """Format alert message."""
        lines = [
            f"🚨 TransitTruth Alert: {self.config.name}",
            f"",
            f"Time: {record.timestamp}",
            f"Model: {self.config.model}",
            f"Trust Score: {record.score}/100 ({record.trust_level})",
        ]
        if record.token_discrepancy is not None:
            lines.append(f"Token Discrepancy: {record.token_discrepancy:+.1f}%")
        if record.latency_ms is not None:
            lines.append(f"Latency: {record.latency_ms:.0f}ms")
        lines.append("")
        lines.append("Alerts:")
        for alert in record.alerts:
            lines.append(f"  - {alert}")
        return "\n".join(lines)

    def _alert_console(self, message: str):
        """Print alert to console."""
        print("\n" + "=" * 60)
        print(message)
        print("=" * 60 + "\n")

    def _alert_email(self, message: str):
        """Send alert via email."""
        if not self.config.email_to:
            return

        msg = MIMEText(message, "plain", "utf-8")
        msg["Subject"] = f"[TransitTruth] Alert: {self.config.name}"
        msg["From"] = self.config.email_from or self.config.smtp_user
        msg["To"] = ", ".join(self.config.email_to)

        with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
            server.starttls()
            if self.config.smtp_user:
                server.login(self.config.smtp_user, self.config.smtp_password or "")
            server.send_message(msg)

    async def _alert_telegram(self, message: str):
        """Send alert via Telegram bot."""
        url = f"https://api.telegram.org/bot{self.config.telegram_bot_token}/sendMessage"
        async with httpx.AsyncClient() as client:
            await client.post(url, json={
                "chat_id": self.config.telegram_chat_id,
                "text": message,
            })

    async def _alert_webhook(self, message: str, record: MonitorRecord):
        """Send alert via webhook (Slack/Discord compatible)."""
        payload = {
            "text": message,
            "record": {
                "timestamp": record.timestamp,
                "score": record.score,
                "trust_level": record.trust_level,
                "alerts": record.alerts,
            },
        }
        async with httpx.AsyncClient() as client:
            await client.post(self.config.webhook_url, json=payload)

    def _save_history(self):
        """Save monitoring history to JSON file."""
        history_dir = Path("monitor_history")
        history_dir.mkdir(exist_ok=True)

        safe_name = self.config.name.replace(" ", "_").replace("/", "_")
        history_file = history_dir / f"{safe_name}.json"

        data = {
            "config": {
                "name": self.config.name,
                "model": self.config.model,
                "base_url": self.config.base_url,
                "interval_seconds": self.config.interval_seconds,
                "alert_threshold": self.config.alert_threshold,
            },
            "baseline_score": self.baseline_score,
            "records": [
                {
                    "timestamp": r.timestamp,
                    "score": r.score,
                    "trust_level": r.trust_level,
                    "token_discrepancy": r.token_discrepancy,
                    "latency_ms": r.latency_ms,
                    "alerts": r.alerts,
                }
                for r in self.history
            ],
        }

        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


# ─── Convenience functions ────────────────────────────────────

def load_monitor_config(config_path: str) -> MonitorConfig:
    """Load monitor configuration from JSON file."""
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return MonitorConfig(
        name=data.get("name", "unnamed"),
        api_key=data["api_key"],
        base_url=data["base_url"],
        model=data["model"],
        interval_seconds=data.get("interval_seconds", 3600),
        alert_threshold=data.get("alert_threshold", 60.0),
        score_drop_threshold=data.get("score_drop_threshold", 10.0),
        mode=AuditMode(data.get("mode", "quick")),
        probe_count=data.get("probe_count", 5),
        alert_channels=data.get("alert_channels", ["console"]),
        smtp_host=data.get("smtp_host"),
        smtp_port=data.get("smtp_port", 587),
        smtp_user=data.get("smtp_user"),
        smtp_password=data.get("smtp_password"),
        email_from=data.get("email_from"),
        email_to=data.get("email_to", []),
        telegram_bot_token=data.get("telegram_bot_token"),
        telegram_chat_id=data.get("telegram_chat_id"),
        webhook_url=data.get("webhook_url"),
    )


async def run_monitor(config_path: str):
    """Run continuous monitoring from config file."""
    config = load_monitor_config(config_path)
    monitor = RelayMonitor(config)
    await monitor.run_continuous()
