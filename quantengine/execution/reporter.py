"""
QuantEngine Pro - Daily Report Generator
==========================================
Generates daily trading summary reports with:
- Trade list with P&L
- Position summary
- Equity curve
- Strategy performance breakdown
- Risk metrics

Reports can be pushed via adapters (log, email, DingTalk, WeChat).
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger


class DailyReporter:
    """
    Generate and distribute daily trading reports.

    Usage:
        reporter = DailyReporter(config)
        report = reporter.generate(trades, positions, equity, strategies)
        reporter.send(report)
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize reporter.

        Args:
            config: Dict with:
                - language: 'zh' or 'en' (default 'zh')
                - include_charts: Include chart data (default True)
                - notifications: List of channel configs
        """
        self.config = config or {}
        self.language = self.config.get("language", "zh")
        self.include_charts = self.config.get("include_charts", True)
        self.notification_channels = self.config.get("notifications", [{"type": "log"}])

        # Channel adapters
        self._adapters = {
            "log": self._send_log,
            "email": self._send_email,
            "dingtalk": self._send_dingtalk,
            "wechat": self._send_wechat,
        }

        logger.info(f"DailyReporter initialized: lang={self.language}")

    def generate(
        self,
        trades: List[Dict],
        positions: List[Dict],
        equity_curve: List[tuple],
        strategy_stats: Optional[Dict] = None,
    ) -> Dict:
        """
        Generate daily report from trading data.

        Args:
            trades: List of trade dicts
            positions: Current positions
            equity_curve: (timestamp, equity) tuples
            strategy_stats: Optional per-strategy performance

        Returns:
            Report dict ready for distribution
        """
        # Calculate daily stats
        today_trades = [
            t for t in trades
            if isinstance(t.get("timestamp"), datetime)
            and t["timestamp"].date() == datetime.now().date()
        ]

        total_pnl = sum(t.get("pnl", 0) for t in today_trades)
        winning_trades = [t for t in today_trades if t.get("pnl", 0) > 0]
        losing_trades = [t for t in today_trades if t.get("pnl", 0) <= 0]

        # Current equity
        current_equity = equity_curve[-1][1] if equity_curve else 0

        # Daily return
        if len(equity_curve) >= 2:
            prev_equity = equity_curve[-2][1]
            daily_return = (current_equity - prev_equity) / prev_equity if prev_equity > 0 else 0
        else:
            daily_return = 0

        report = {
            "report_type": "daily",
            "generated_at": datetime.now().isoformat(),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "language": self.language,

            # Summary
            "summary": {
                "current_equity": round(current_equity, 2),
                "daily_pnl": round(total_pnl, 2),
                "daily_return_pct": round(daily_return * 100, 2),
                "total_trades_today": len(today_trades),
                "winning_trades": len(winning_trades),
                "losing_trades": len(losing_trades),
                "win_rate": len(winning_trades) / max(len(today_trades), 1),
                "avg_win": round(sum(t.get("pnl", 0) for t in winning_trades) / max(len(winning_trades), 1), 2),
                "avg_loss": round(abs(sum(t.get("pnl", 0) for t in losing_trades)) / max(len(losing_trades), 1), 2),
                "open_positions": len(positions),
            },

            # Trade details
            "trades": [
                {
                    "symbol": t.get("symbol"),
                    "side": t.get("side"),
                    "quantity": t.get("quantity"),
                    "entry": t.get("entry_price"),
                    "exit": t.get("exit_price"),
                    "pnl": round(t.get("pnl", 0), 2),
                    "strategy": t.get("strategy"),
                }
                for t in today_trades[-20:]  # Last 20 trades
            ],

            # Positions
            "positions": [
                {
                    "symbol": p.get("symbol"),
                    "quantity": p.get("quantity"),
                    "avg_price": p.get("avg_price"),
                    "current_price": p.get("current_price"),
                    "unrealized_pnl": round(p.get("unrealized_pnl", 0), 2),
                }
                for p in positions
            ],

            # Strategy performance
            "strategies": strategy_stats or {},

            # Risk metrics
            "risk": {
                "drawdown_warning": daily_return < -0.03,  # -3% daily
            },
        }

        logger.info(
            f"Daily report generated: PnL={total_pnl:,.2f}, "
            f"trades={len(today_trades)}, return={daily_return:.2%}"
        )
        return report

    async def send(self, report: Dict) -> Dict[str, bool]:
        """
        Send report through all configured notification channels.

        Args:
            report: Report dict from generate()

        Returns:
            Dict mapping channel type → success
        """
        results = {}

        for channel in self.notification_channels:
            channel_type = channel.get("type", "log")
            adapter = self._adapters.get(channel_type, self._send_log)

            try:
                success = await adapter(report, channel)
                results[channel_type] = success
            except Exception as e:
                logger.error(f"Failed to send report via {channel_type}: {e}")
                results[channel_type] = False

        return results

    # ---- Channel Adapters ----

    async def _send_log(self, report: Dict, config: Dict) -> bool:
        """Log report to file/system log."""
        s = report["summary"]
        logger.info(
            f"\n{'='*50}\n"
            f"  Daily Report - {report['date']}\n"
            f"  Equity: {s['current_equity']:,.2f} | "
            f"PnL: {s['daily_pnl']:+,.2f} ({s['daily_return_pct']:+.2f}%)\n"
            f"  Trades: {s['total_trades_today']} | "
            f"Win Rate: {s['win_rate']:.0%} | "
            f"Open Positions: {s['open_positions']}\n"
            f"{'='*50}"
        )
        return True

    async def _send_email(self, report: Dict, config: Dict) -> bool:
        """Send report via email. Requires smtp configuration."""
        logger.info("Email notification not yet implemented")
        return False

    async def _send_dingtalk(self, report: Dict, config: Dict) -> bool:
        """
        Send report to DingTalk via webhook.

        Args:
            report: Report dict
            config: DingTalk config with webhook_url
        """
        webhook_url = config.get("webhook_url", "")
        if not webhook_url:
            logger.warning("DingTalk webhook URL not configured")
            return False

        try:
            import aiohttp

            s = report["summary"]
            markdown_text = (
                f"## 📊 QuantEngine Pro 日报\n\n"
                f"**日期**: {report['date']}\n\n"
                f"**当前权益**: {s['current_equity']:,.2f}\n\n"
                f"**当日盈亏**: {s['daily_pnl']:+,.2f} ({s['daily_return_pct']:+.2f}%)\n\n"
                f"**交易笔数**: {s['total_trades_today']} | "
                f"**胜率**: {s['win_rate']:.0%}\n\n"
                f"**持仓数**: {s['open_positions']}\n\n"
                f"---\n*Generated by QuantEngine Pro*"
            )

            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "title": f"QuantEngine Daily Report - {report['date']}",
                    "text": markdown_text,
                },
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload) as resp:
                    if resp.status == 200:
                        logger.info("DingTalk report sent successfully")
                        return True
                    else:
                        logger.error(f"DingTalk send failed: {resp.status}")
                        return False

        except Exception as e:
            logger.error(f"DingTalk notification failed: {e}")
            return False

    async def _send_wechat(self, report: Dict, config: Dict) -> bool:
        """Send report to WeChat Work via webhook."""
        webhook_url = config.get("webhook_url", "")
        if not webhook_url:
            logger.warning("WeChat webhook URL not configured")
            return False

        try:
            import aiohttp

            s = report["summary"]
            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "content": (
                        f"## QuantEngine Pro 日报\n"
                        f"> 日期: {report['date']}\n"
                        f"> 权益: **{s['current_equity']:,.2f}**\n"
                        f"> 当日盈亏: **{s['daily_pnl']:+,.2f}** ({s['daily_return_pct']:+.2f}%)\n"
                        f"> 交易: {s['total_trades_today']}笔 | 胜率: {s['win_rate']:.0%}\n"
                    ),
                },
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload) as resp:
                    return resp.status == 200

        except Exception as e:
            logger.error(f"WeChat notification failed: {e}")
            return False
