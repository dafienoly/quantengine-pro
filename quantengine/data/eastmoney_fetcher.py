"""
QuantEngine Pro - EastMoney Market Flow Fetcher
================================================
Free market breadth and fund flow data from EastMoney (东方财富) web API.
Parses the public HTTP endpoints used by EastMoney's web client.

Data available:
- Market breadth (advancing/declining issues, limit up/down counts)
- Sector/industry fund flow (主力资金净流入)
- North-bound (北向资金) flow
- Index valuation (PE/PB percentiles)

All data is free and publicly available via EastMoney's web interface.
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd
import requests
from loguru import logger

from quantengine.data.base import BaseMarketFlowFetcher


class EastMoneyFlowFetcher(BaseMarketFlowFetcher):
    """
    EastMoney (东方财富) market data fetcher.

    Parses EastMoney's public HTTP API for market breadth, fund flow,
    sector rotation, and index valuation data. All free, no API key needed.

    Rate limit: ~1 request/second to avoid being blocked.
    """

    # EastMoney API endpoints
    BASE_URL = "https://push2.eastmoney.com/api/qt"

    def __init__(self, config: Dict):
        """
        Initialize EastMoney fetcher.

        Args:
            config: Dict with optional keys:
                - request_delay: Seconds between requests (default 0.5)
                - timeout: Request timeout seconds (default 10)
        """
        super().__init__(config)
        self.request_delay = config.get("request_delay", 0.5)
        self.timeout = config.get("timeout", 10)
        self._session: Optional[requests.Session] = None
        logger.info("EastMoneyFlowFetcher initialized")

    def _get_session(self) -> requests.Session:
        """Get or create HTTP session with browser-like headers."""
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Referer": "https://data.eastmoney.com/",
                "Accept": "application/json, text/plain, */*",
            })
        return self._session

    async def _async_get(self, url: str, params: Dict = None) -> Dict:
        """
        Async wrapper for HTTP GET with rate limiting.

        Args:
            url: Request URL
            params: Query parameters

        Returns:
            Parsed JSON response dict
        """
        session = self._get_session()

        # Rate limiting
        await asyncio.sleep(self.request_delay)

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: session.get(url, params=params, timeout=self.timeout)
            )
            response.raise_for_status()

            # EastMoney responses are wrapped in JSONP-like format sometimes
            text = response.text
            # Handle JSONP: jQuery_xxx({...})
            if text.startswith("jQuery") or text.startswith("callback"):
                start = text.find("(") + 1
                end = text.rfind(")")
                text = text[start:end]

            return json.loads(text)
        except Exception as e:
            logger.error(f"EastMoney API request failed: {e}")
            return {}

    async def fetch_market_breadth(self, date: Optional[str] = None) -> pd.DataFrame:
        """
        Fetch market breadth indicators.

        Gets advancing/declining/limit-up/limit-down counts for major indices.

        Args:
            date: Date string 'YYYYMMDD', defaults to latest trading day

        Returns:
            DataFrame with columns: index_name, up_count, down_count,
            limit_up, limit_down, total_volume, total_amount
        """
        # EastMoney market overview API
        # fs=m:0+t:6+f:!2,m:0+t:13+f:!2 covers Shanghai + Shenzhen A shares
        url = f"{self.BASE_URL}/clist"
        params = {
            "pn": "1",
            "pz": "5000",
            "po": "1",
            "np": "1",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": "2",
            "invt": "2",
            "fid": "f3",
            "fs": "m:0+t:6+f:!2,m:0+t:13+f:!2",  # All A-shares
            "fields": "f2,f3,f4,f5,f6,f7,f8,f10,f12,f14,f15,f16,f17,f18",
        }

        data = await self._async_get(url, params)

        if not data or "data" not in data:
            logger.error("Failed to fetch market breadth data")
            return pd.DataFrame()

        try:
            records = data["data"].get("diff", [])
            if not records:
                return pd.DataFrame()

            df = pd.DataFrame(records)

            # Calculate breadth statistics
            up_count = len(df[df["f3"] > 0]) if "f3" in df.columns else 0
            down_count = len(df[df["f3"] < 0]) if "f3" in df.columns else 0
            limit_up = len(df[df["f3"] >= 9.9]) if "f3" in df.columns else 0
            limit_down = len(df[df["f3"] <= -9.9]) if "f3" in df.columns else 0

            result = pd.DataFrame([{
                "timestamp": datetime.now(),
                "total_stocks": len(df),
                "up_count": up_count,
                "down_count": down_count,
                "limit_up_count": limit_up,
                "limit_down_count": limit_down,
                "breadth_ratio": up_count / max(down_count, 1),
            }])

            logger.info(
                f"Market breadth: up={up_count}, down={down_count}, "
                f"limit_up={limit_up}, limit_down={limit_down}"
            )
            return result

        except Exception as e:
            logger.error(f"Failed to parse market breadth: {e}")
            return pd.DataFrame()

    async def fetch_sector_flow(self, date: Optional[str] = None) -> pd.DataFrame:
        """
        Fetch sector-level fund flow data.

        Gets net capital flow by industry sector.

        Args:
            date: Date string

        Returns:
            DataFrame with sectors ranked by net inflow
        """
        # EastMoney sector fund flow API
        url = f"{self.BASE_URL}/clist"
        params = {
            "pn": "1",
            "pz": "100",
            "po": "1",
            "np": "1",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": "2",
            "invt": "2",
            "fid": "f62",  # Sort by main force net inflow
            "fs": "m:90+t:2",  # Industry sectors
            "fields": "f2,f3,f4,f12,f14,f62,f66,f69,f72,f75,f78,f81,f84,f87",
        }

        data = await self._async_get(url, params)

        if not data or "data" not in data:
            logger.error("Failed to fetch sector flow data")
            return pd.DataFrame()

        try:
            records = data["data"].get("diff", [])
            df = pd.DataFrame(records)

            # Map columns to readable names
            if len(df.columns) >= 14:
                df = df.rename(columns={
                    "f14": "sector_name",
                    "f3": "change_pct",
                    "f62": "main_net_inflow",       # 主力净流入
                    "f66": "super_large_net_inflow", # 超大单净流入
                    "f72": "large_net_inflow",       # 大单净流入
                    "f78": "medium_net_inflow",      # 中单净流入
                    "f84": "small_net_inflow",       # 小单净流入
                })

            logger.info(f"Fetched sector flow for {len(df)} sectors")
            return df

        except Exception as e:
            logger.error(f"Failed to parse sector flow: {e}")
            return pd.DataFrame()

    async def fetch_index_valuation(self, index_code: str = "000300") -> Dict:
        """
        Fetch index valuation data including PE/PB percentiles.

        Args:
            index_code: Index code (000300=CSI300, 000016=SSE50, 000905=CSI500, 399006=ChiNext)

        Returns:
            Dict with PE, PB, dividend yield, and historical percentiles
        """
        # Map index codes to EastMoney security codes
        index_map = {
            "000300": "1.000300",   # CSI 300
            "000016": "1.000016",   # SSE 50
            "000905": "1.000905",   # CSI 500
            "399006": "0.399006",   # ChiNext
            "000001": "1.000001",   # SSE Composite
        }

        sec_id = index_map.get(index_code, f"1.{index_code}")

        # EastMoney index valuation API
        url = "https://datacenter.eastmoney.com/api/data/v1/get"
        params = {
            "sortColumns": "TRADE_DATE",
            "sortTypes": "-1",
            "pageSize": "1",
            "pageNumber": "1",
            "reportName": "RPT_INDEX_MARKETWEIGHT",
            "columns": "ALL",
            "filter": f'(INDEX_CODE="{index_code}")',
            "source": "WEB",
            "client": "WEB",
        }

        data = await self._async_get(url, params)

        if not data or "result" not in data:
            logger.error(f"Failed to fetch index valuation for {index_code}")
            return {}

        try:
            records = data["result"].get("data", [])
            if not records:
                return {}

            latest = records[0]
            return {
                "index_code": index_code,
                "pe_ttm": latest.get("PE_TTM"),
                "pb": latest.get("PB"),
                "dividend_yield": latest.get("DIVIDEND_YIELD"),
                "pe_percentile": latest.get("PE_TTM_QUANTILE"),  # PE历史分位
                "pb_percentile": latest.get("PB_QUANTILE"),       # PB历史分位
                "total_mv": latest.get("TOTAL_MV"),               # 总市值
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to parse index valuation: {e}")
            return {}

    async def fetch_north_bound_flow(self) -> pd.DataFrame:
        """
        Fetch North-bound (北向资金) flow data.

        Returns:
            DataFrame with daily north-bound net inflow
        """
        url = "https://datacenter.eastmoney.com/api/data/v1/get"
        params = {
            "sortColumns": "TRADE_DATE",
            "sortTypes": "-1",
            "pageSize": "30",
            "pageNumber": "1",
            "reportName": "RPT_MUTUAL_STOCK_NORTHBOUND",
            "columns": "ALL",
            "source": "WEB",
            "client": "WEB",
        }

        data = await self._async_get(url, params)

        if not data or "result" not in data:
            return pd.DataFrame()

        try:
            records = data["result"].get("data", [])
            df = pd.DataFrame(records)
            logger.info(f"Fetched {len(df)} days of north-bound flow data")
            return df
        except Exception as e:
            logger.error(f"Failed to parse north-bound flow: {e}")
            return pd.DataFrame()
