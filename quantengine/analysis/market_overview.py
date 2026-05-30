"""
QuantEngine Pro - Market Overview Service
===========================================
Calculates market-wide indicators: breadth, fear & greed index, sector flow.
"""

from datetime import datetime
from typing import Any, Dict, Optional

from loguru import logger


class MarketOverview:
    """
    Market overview and breadth analysis service.

    Usage:
        overview = MarketOverview(flow_fetcher)
        dashboard = await overview.get_dashboard()
    """

    def __init__(self, flow_fetcher=None):
        self.flow_fetcher = flow_fetcher

    async def get_dashboard(self) -> Dict[str, Any]:
        """Get comprehensive market dashboard data."""
        dashboard = {
            "timestamp": datetime.now().isoformat(),
            "breadth": await self.get_market_breadth(),
            "fear_greed": await self.get_fear_greed_index(),
            "sector_flow": await self.get_sector_flow_summary(),
        }
        if self.flow_fetcher:
            try:
                val = await self.flow_fetcher.fetch_index_valuation("000300")
                dashboard["valuation"] = val
            except Exception:
                dashboard["valuation"] = {"available": False}
        return dashboard

    async def get_market_breadth(self) -> Dict:
        """Calculate market breadth indicators."""
        if self.flow_fetcher:
            try:
                df = await self.flow_fetcher.fetch_market_breadth()
                if not df.empty:
                    row = df.iloc[-1] if len(df) > 0 else df.iloc[0]
                    up = row.get("up_count", 0)
                    down = row.get("down_count", 0)
                    total = up + down
                    return {
                        "up_count": int(up), "down_count": int(down),
                        "breadth_ratio": round(up / max(down, 1), 2),
                        "net_advancing": int(up - down),
                        "advancing_pct": round(up / max(total, 1) * 100, 1),
                        "limit_up": int(row.get("limit_up_count", 0)),
                        "limit_down": int(row.get("limit_down_count", 0)),
                    }
            except Exception as e:
                logger.error(f"Market breadth failed: {e}")
        return {"up_count": 0, "down_count": 0, "breadth_ratio": 1.0,
                "net_advancing": 0, "advancing_pct": 50.0, "limit_up": 0, "limit_down": 0}

    async def get_fear_greed_index(self) -> Dict:
        """Calculate Fear & Greed Index approximation (0-100)."""
        score = 50.0
        if self.flow_fetcher:
            try:
                breadth = await self.get_market_breadth()
                score = 0.25 * breadth["advancing_pct"] + 0.75 * 50
            except Exception:
                pass

        if score <= 20: label = "极度恐惧"
        elif score <= 40: label = "恐惧"
        elif score <= 60: label = "中性"
        elif score <= 80: label = "贪婪"
        else: label = "极度贪婪"

        return {"value": round(score, 1), "label": label}

    async def get_sector_flow_summary(self) -> Dict:
        """Get top sector inflows and outflows."""
        if not self.flow_fetcher:
            return {"top_inflows": [], "top_outflows": []}
        try:
            df = await self.flow_fetcher.fetch_sector_flow()
            if df.empty or "main_net_inflow" not in df.columns:
                return {"top_inflows": [], "top_outflows": []}
            sorted_df = df.sort_values("main_net_inflow", ascending=False)
            top_in = sorted_df.head(5)[["sector_name", "main_net_inflow", "change_pct"]].to_dict("records") if "sector_name" in df.columns else []
            top_out = sorted_df.tail(5)[["sector_name", "main_net_inflow", "change_pct"]].to_dict("records") if "sector_name" in df.columns else []
            return {"top_inflows": top_in, "top_outflows": top_out}
        except Exception as e:
            logger.error(f"Sector flow failed: {e}")
            return {"top_inflows": [], "top_outflows": []}
