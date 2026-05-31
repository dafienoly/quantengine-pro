"""
QuantEngine Pro - Data Fetcher Abstract Base Classes
=====================================================
Defines the abstract interfaces that all data providers must implement.
This ensures pluggability: swap providers by changing config, not code.

Three core abstractions:
    BaseQuoteFetcher      - Market data (K-line, tick, real-time quotes)
    BaseMarketFlowFetcher - Market breadth, fund flow, index valuation
    BaseNewsFetcher       - News and sentiment feeds
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd


# =============================================================================
# Data Transfer Objects
# =============================================================================

@dataclass
class NewsItem:
    """Standardized news item across all providers."""
    timestamp: datetime
    title: str
    content: str = ""
    source: str = ""
    url: str = ""
    symbols: List[str] = field(default_factory=list)  # Related symbols
    sentiment: Optional[float] = None  # -1.0 to 1.0, set by LLM analysis
    category: str = ""  # macro, company, sector, crypto, etc.


@dataclass
class QuoteBar:
    """Standardized OHLCV bar for a single period."""
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float = 0.0  # Trading amount (quote currency volume)
    freq: str = "1d"     # Bar frequency: 1m, 5m, 15m, 1h, 1d, 1w, etc.


@dataclass
class MarketFlow:
    """Market-wide fund flow data."""
    timestamp: datetime
    main_net_inflow: float      # Main force net inflow (yuan)
    retail_net_inflow: float    # Retail net inflow
    total_turnover: float       # Total market turnover
    up_count: int = 0           # Number of rising stocks
    down_count: int = 0         # Number of falling stocks
    limit_up_count: int = 0     # Number hitting limit-up
    limit_down_count: int = 0   # Number hitting limit-down


# =============================================================================
# Abstract Base Classes
# =============================================================================

class BaseQuoteFetcher(ABC):
    """
    Abstract base class for market data fetchers.

    All implementations must support fetching K-line data, real-time quotes,
    and provide a list of available symbols.
    """

    def __init__(self, config: Dict):
        """
        Initialize the fetcher.

        Args:
            config: Provider-specific configuration dict
        """
        self.config = config
        self.name = self.__class__.__name__

    @abstractmethod
    async def fetch_kline(
        self,
        symbol: str,
        freq: str = "1d",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 1000,
    ) -> pd.DataFrame:
        """
        Fetch historical K-line data.

        Args:
            symbol: Trading symbol (e.g., '000001' for A-share, 'BTC/USDT' for crypto)
            freq: Bar frequency ('1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w', '1M')
            start_date: Start date string 'YYYYMMDD' or 'YYYY-MM-DD'
            end_date: End date string
            limit: Maximum number of bars to return

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume, amount
        """
        ...

    @abstractmethod
    async def fetch_realtime_quote(self, symbol: str) -> Dict:
        """
        Fetch real-time quote for a single symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Dict with keys: symbol, price, volume, bid, ask, timestamp, change_pct
        """
        ...

    @abstractmethod
    async def get_all_symbols(self, market: str = "all") -> List[str]:
        """
        Get list of all available symbols.

        Args:
            market: Market filter ('a_share', 'crypto', 'all')

        Returns:
            List of symbol strings
        """
        ...

    @abstractmethod
    async def fetch_tick(
        self,
        symbol: str,
        date: Optional[str] = None,
        limit: int = 1000,
    ) -> pd.DataFrame:
        """
        Fetch tick-level trade data.

        Args:
            symbol: Trading symbol
            date: Date string 'YYYYMMDD', defaults to today
            limit: Maximum number of ticks

        Returns:
            DataFrame with columns: timestamp, price, volume, direction
        """
        ...

    async def fetch_batch_kline(
        self,
        symbols: List[str],
        freq: str = "1d",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch K-line data for multiple symbols.

        Default implementation loops over symbols; subclasses may override
        for batch-optimized fetching.

        Args:
            symbols: List of trading symbols
            freq: Bar frequency
            start_date: Start date
            end_date: End date

        Returns:
            Dict mapping symbol -> DataFrame
        """
        import asyncio

        tasks = [
            self.fetch_kline(sym, freq, start_date, end_date)
            for sym in symbols
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        result_dict = {}
        for sym, res in zip(symbols, results):
            if isinstance(res, Exception):
                from loguru import logger
                logger.error(f"Failed to fetch {sym}: {res}")
                result_dict[sym] = pd.DataFrame()
            else:
                result_dict[sym] = res

        return result_dict


class BaseMarketFlowFetcher(ABC):
    """
    Abstract base class for market breadth and fund flow data.
    """

    def __init__(self, config: Dict):
        self.config = config

    @abstractmethod
    async def fetch_market_breadth(self, date: Optional[str] = None) -> pd.DataFrame:
        """
        Fetch market breadth data (advancing/declining issues, limits).

        Args:
            date: Date string 'YYYYMMDD', defaults to today

        Returns:
            DataFrame with market breadth indicators
        """
        ...

    @abstractmethod
    async def fetch_sector_flow(self, date: Optional[str] = None) -> pd.DataFrame:
        """
        Fetch sector-level fund flow data.

        Args:
            date: Date string

        Returns:
            DataFrame with sector fund flow data
        """
        ...

    @abstractmethod
    async def fetch_index_valuation(self, index_code: str = "000300") -> Dict:
        """
        Fetch index valuation data (PE, PB, dividend yield percentiles).

        Args:
            index_code: Index code (000300=CSI300, 000016=SSE50, etc.)

        Returns:
            Dict with valuation metrics
        """
        ...


class BaseNewsFetcher(ABC):
    """
    Abstract base class for news/sentiment data fetchers.
    """

    def __init__(self, config: Dict):
        self.config = config

    @abstractmethod
    async def fetch_news(
        self,
        symbols: Optional[List[str]] = None,
        date: Optional[str] = None,
        limit: int = 50,
    ) -> List[NewsItem]:
        """
        Fetch news items.

        Args:
            symbols: Filter by related symbols (None = all)
            date: Date filter
            limit: Maximum number of news items

        Returns:
            List of NewsItem objects
        """
        ...

    async def fetch_all_news(
        self,
        symbols: Optional[List[str]] = None,
        days: int = 1,
        limit: int = 100,
    ) -> List[NewsItem]:
        """
        Fetch news for multiple days.

        Args:
            symbols: Symbol filter
            days: Number of days to look back
            limit: Max items per day

        Returns:
            Combined list of NewsItem objects
        """
        from datetime import datetime, timedelta

        all_news = []
        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
            items = await self.fetch_news(symbols, date, limit)
            all_news.extend(items)

        # Deduplicate by title
        seen = set()
        deduped = []
        for item in all_news:
            if item.title not in seen:
                seen.add(item.title)
                deduped.append(item)

        return deduped[:limit]
