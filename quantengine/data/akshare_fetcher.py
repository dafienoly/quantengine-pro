"""
QuantEngine Pro - Akshare Quote Fetcher
=========================================
Implements the ``BaseQuoteFetcher`` abstract class using the **akshare**
library for free A-share market data sourced from East Money (东方财富).

Key capabilities:
    - Historical K-line (daily / weekly / monthly) for individual stocks
      and major market indices.
    - Real-time spot quotes for all A-share stocks.
    - Full A-share symbol listing.

Dependencies (runtime):
    - akshare >= 1.13.0
    - pandas
    - loguru

Usage::

    from quantengine.data.akshare_fetcher import AkshareQuoteFetcher

    fetcher = AkshareQuoteFetcher({"rate_limit": 0.5})
    df = await fetcher.fetch_kline("000001", freq="1d")
    quote = await fetcher.fetch_realtime_quote("600519")
    symbols = await fetcher.get_all_symbols()
"""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
from loguru import logger

from quantengine.data.base import BaseQuoteFetcher

# ==============================================================================
# Public Interface
# ==============================================================================


class AkshareQuoteFetcher(BaseQuoteFetcher):
    """
    A-share market data fetcher powered by the akshare library.

    Provides free access to Chinese A-share stock data including historical
    K-line (with forward-adjusted prices), real-time spot quotes, and a
    complete symbol listing.

    **Symbol conventions**

    ============ ========================== =====================
    Type         Example                    Notes
    ============ ========================== =====================
    Stock        000001                     6-digit A-share code
    Index        sh000300                   ``sh`` + 6-digit code
    Index        sz399001                   ``sz`` + 6-digit code
    ============ ========================== =====================

    **Frequency mapping**

    ============ ===================== ===========================
    ``freq``     stock_zh_a_hist       index (client-side resample)
    ============ ===================== ===========================
    ``'1d'``     ``period='daily'``    native daily
    ``'1w'``     ``period='weekly'``   resample from daily
    ``'1M'``     ``period='monthly'``  resample from daily
    ============ ===================== ===========================

    **Configuration**

    ================= ======= ==========================================
    Key               Default Description
    ================= ======= ==========================================
    ``rate_limit``    0.3     Minimum seconds between API requests.
    ``max_workers``   4       Thread-pool size for blocking akshare calls.
    ``adjust``        'qfq'   Price adjustment: ``'qfq'`` (forward),
                              ``'hfq'`` (backward), ``None`` (unadjusted).
    ``default_limit`` 1000    Default bars when no date range is given.
    ================= ======= ==========================================

    .. warning::
       All akshare functions are synchronous. This wrapper offloads them to a
       thread-pool executor and enforces rate limiting to avoid being
       throttled by the upstream data source.
    """

    # ------------------------------------------------------------------
    # Column mappings: akshare naming  ->  standard QuantEngine naming
    # ------------------------------------------------------------------

    # stock_zh_a_hist uses Chinese column names
    _KLINE_COLUMN_MAP: Dict[str, str] = {
        "日期": "timestamp",
        "开盘": "open",
        "最高": "high",
        "最低": "low",
        "收盘": "close",
        "成交量": "volume",
        "成交额": "amount",
    }

    # stock_zh_index_daily uses English column names
    _INDEX_KLINE_COLUMN_MAP: Dict[str, str] = {
        "date": "timestamp",
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "volume": "volume",
    }

    # stock_zh_a_spot_em Chinese -> English
    _SPOT_COLUMN_MAP: Dict[str, str] = {
        "代码": "symbol",
        "名称": "name",
        "最新价": "price",
        "涨跌幅": "change_pct",
        "涨跌额": "change",
        "成交量": "volume",
        "成交额": "amount",
        "今开": "open",
        "最高价": "high",
        "最低价": "low",
        "昨收": "pre_close",
        "换手率": "turnover",
        "市盈率-动态": "pe",
        "市净率": "pb",
    }

    # Freq -> stock_zh_a_hist period parameter
    _FREQ_PERIOD_MAP: Dict[str, str] = {
        "1d": "daily",
        "1w": "weekly",
        "1M": "monthly",
    }

    # Default request interval (seconds)
    _DEFAULT_RATE_LIMIT: float = 0.3

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialise the Akshare quote fetcher.

        Args:
            config: Optional dictionary of configuration overrides.
                    See class docstring for supported keys.
        """
        config = config or {}
        super().__init__(config)

        # Rate limiting state
        self._rate_limit: float = config.get("rate_limit", self._DEFAULT_RATE_LIMIT)
        self._last_request_time: float = 0.0

        # Thread pool for offloading blocking akshare calls
        self._executor = ThreadPoolExecutor(
            max_workers=config.get("max_workers", 4),
            thread_name_prefix="akshare",
        )

        # Price adjustment mode for individual stocks
        self._adjust: Optional[str] = config.get("adjust", "qfq")

        # Default bar limit when no date range is provided
        self._default_limit: int = config.get("default_limit", 1000)

        logger.info(
            f"AkshareQuoteFetcher initialized | "
            f"rate_limit={self._rate_limit}s | adjust={self._adjust} | "
            f"max_workers={self._executor._max_workers}"
        )

    # ==================================================================
    # Public API  —  BaseQuoteFetcher contract
    # ==================================================================

    async def fetch_kline(
        self,
        symbol: str,
        freq: str = "1d",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 1000,
    ) -> pd.DataFrame:
        """
        Fetch historical K-line (OHLCV) data.

        Dispatches to the appropriate akshare function based on symbol prefix:

        * **Stock** (e.g. ``'000001'``)   → ``akshare.stock_zh_a_hist``
        * **Index** (e.g. ``'sh000300'``) → ``akshare.stock_zh_index_daily``

        Index data is daily only; when ``freq`` is ``'1w'`` or ``'1M'`` the
        daily series is resampled client-side via pandas.

        Args:
            symbol: 6-digit stock code (e.g. ``'000001'``) or index code
                    with prefix (e.g. ``'sh000300'``, ``'sz399001'``).
            freq: Bar frequency — ``'1d'``, ``'1w'``, or ``'1M'``.
            start_date: Start date in ``'YYYYMMDD'`` or ``'YYYY-MM-DD'``
                        format. When omitted the latest **limit** bars are
                        returned.
            end_date: End date in the same formats. Defaults to today.
            limit: Maximum number of bars. Only used when **start_date** is
                   omitted (otherwise all bars in the range are returned).

        Returns:
            DataFrame with columns:

            ``timestamp``, ``open``, ``high``, ``low``, ``close``,
            ``volume``, ``amount``

            ``amount`` is set to 0 for index data (not provided by akshare).

        Raises:
            ValueError: If ``freq`` is unsupported or ``symbol`` is empty.
            RuntimeError: If the underlying akshare call fails.
        """
        symbol = symbol.strip()
        if not symbol:
            raise ValueError("Symbol must not be empty")

        # --- validate frequency -------------------------------------------
        if freq not in self._FREQ_PERIOD_MAP:
            raise ValueError(
                f"Unsupported frequency {freq!r}. "
                f"Supported: {list(self._FREQ_PERIOD_MAP.keys())}"
            )

        logger.debug(
            f"fetch_kline: symbol={symbol} freq={freq} "
            f"start={start_date} end={end_date} limit={limit}"
        )

        # --- dispatch -----------------------------------------------------
        try:
            if symbol.lower().startswith(("sh", "sz")):
                df = await self._fetch_index_kline(symbol, freq, start_date, end_date)
            else:
                df = await self._fetch_stock_kline(
                    symbol, freq, start_date, end_date, limit
                )
        except ValueError:
            raise
        except Exception as exc:
            msg = f"K-line fetch failed for {symbol} ({freq}): {exc}"
            logger.error(msg)
            raise RuntimeError(msg) from exc

        if df.empty:
            logger.warning(f"No K-line data returned for {symbol} ({freq})")
            return df

        # --- standardise --------------------------------------------------
        df = self._standardise_kline_columns(df, freq)
        df = self._sort_and_dedup(df)

        # When the caller supplied a date range akshare already honours it;
        # when they only gave *limit* we trim here for completeness.
        if start_date is None and limit is not None and len(df) > limit:
            df = df.tail(limit).reset_index(drop=True)

        logger.info(f"Fetched {len(df)} bars for {symbol} ({freq})")
        return df

    async def fetch_realtime_quote(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch a real-time snapshot quote for a single A-share stock.

        The full-market spot table (``akshare.stock_zh_a_spot_em``) is
        fetched and filtered to the requested symbol.

        Args:
            symbol: 6-digit stock code, e.g. ``'000001'`` or ``'600519'``.

        Returns:
            Dictionary with the following keys:

            =============  ======  ==================================
            Key            Type    Description
            =============  ======  ==================================
            ``symbol``     str     6-digit stock code
            ``name``       str     Stock short name (e.g. 平安银行)
            ``price``      float   Latest trade price
            ``change``     float   Price change vs previous close
            ``change_pct`` float   Percentage change
            ``volume``     float   Total volume (shares)
            ``amount``     float   Total turnover (yuan)
            ``open``       float   Today's open price
            ``high``       float   Today's high
            ``low``        float   Today's low
            ``pre_close``  float   Previous close
            ``turnover``   float   Turnover rate (%)
            ``pe``         float   Dynamic P/E ratio
            ``pb``         float   P/B ratio
            ``timestamp``  str     ISO-format time of the snapshot
            =============  ======  ==================================

        Raises:
            ValueError: If ``symbol`` is not found in the market.
            RuntimeError: If the akshare call fails.
        """
        symbol = symbol.strip()
        logger.debug(f"fetch_realtime_quote: symbol={symbol}")

        try:
            spot_df = await self._run_akshare("stock_zh_a_spot_em")
        except Exception as exc:
            msg = f"Failed to fetch real-time spot data: {exc}"
            logger.error(msg)
            raise RuntimeError(msg) from exc

        if spot_df.empty:
            raise RuntimeError("Empty spot-data table returned by akshare")

        # Filter by the 6-digit code column
        match = spot_df.loc[spot_df["代码"] == symbol]

        if match.empty:
            raise ValueError(
                f"Symbol {symbol!r} not found in A-share market. "
                "Ensure it is a valid 6-digit stock code."
            )

        row = match.iloc[0]
        quote = self._build_quote_dict(row)

        logger.debug(f"Realtime quote for {symbol}: price={quote.get('price')}")
        return quote

    async def get_all_symbols(self, market: str = "a_share") -> List[str]:
        """
        Retrieve the full list of A-share stock codes.

        Args:
            market: Filter — only ``'a_share'`` and ``'all'`` are
                    recognised; anything else returns an empty list.

        Returns:
            Sorted list of 6-digit stock code strings, e.g.
            ``['000001', '000002', ..., '688981']``.

        Raises:
            RuntimeError: If the akshare call fails.
        """
        if market.lower() not in ("a_share", "all"):
            logger.warning(
                f"Market {market!r} is not supported by "
                f"{self.__class__.__name__}; returning empty list."
            )
            return []

        logger.debug(f"get_all_symbols: market={market}")

        try:
            spot_df = await self._run_akshare("stock_zh_a_spot_em")
        except Exception as exc:
            msg = f"Failed to fetch symbol list: {exc}"
            logger.error(msg)
            raise RuntimeError(msg) from exc

        if spot_df.empty:
            logger.warning("Empty symbol list returned by akshare")
            return []

        symbols = sorted(spot_df["代码"].unique().tolist())
        logger.info(f"Retrieved {len(symbols)} A-share symbols")
        return symbols

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """
        Shut down the internal thread pool executor.

        Call this when the fetcher is no longer needed to release
        OS-level threads.
        """
        if hasattr(self, "_executor") and not self._executor._shutdown:
            self._executor.shutdown(wait=False)
            logger.debug("AkshareQuoteFetcher thread pool shut down")

    def __del__(self) -> None:
        self.close()

    # ==================================================================
    # Internal helpers
    # ==================================================================

    # ---- K-line dispatch -----------------------------------------------

    async def _fetch_stock_kline(
        self,
        symbol: str,
        freq: str,
        start_date: Optional[str],
        end_date: Optional[str],
        limit: int,
    ) -> pd.DataFrame:
        """
        Fetch K-line data for an individual stock via
        ``akshare.stock_zh_a_hist``.

        This function supports forward / backward price adjustment and
        three built-in periods (daily, weekly, monthly).
        """
        period = self._FREQ_PERIOD_MAP[freq]
        start = self._normalise_date(start_date) if start_date else None
        end = self._normalise_date(end_date) if end_date else None

        logger.debug(
            f"_fetch_stock_kline: symbol={symbol} period={period} "
            f"start={start} end={end} adjust={self._adjust}"
        )

        return await self._run_akshare(
            "stock_zh_a_hist",
            symbol=symbol,
            period=period,
            start_date=start,
            end_date=end,
            adjust=self._adjust,
        )

    async def _fetch_index_kline(
        self,
        symbol: str,
        freq: str,
        start_date: Optional[str],
        end_date: Optional[str],
    ) -> pd.DataFrame:
        """
        Fetch daily K-line data for an index via
        ``akshare.stock_zh_index_daily``.

        akshare's index endpoint is daily-only. When the caller requests
        ``freq='1w'`` or ``freq='1M'`` the daily series is resampled
        client-side using standard OHLC aggregation.
        """
        logger.debug(f"_fetch_index_kline: symbol={symbol}")

        df = await self._run_akshare("stock_zh_index_daily", symbol=symbol)

        if df.empty:
            return df

        # Ensure 'date' column is datetime for filtering / resampling
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
        else:
            logger.warning("Index data has no 'date' column; returning as-is")
            return df

        # Date-range filter
        if start_date:
            start_dt = pd.Timestamp(self._normalise_date(start_date))
            df = df[df["date"] >= start_dt]
        if end_date:
            end_dt = pd.Timestamp(self._normalise_date(end_date))
            df = df[df["date"] <= end_dt]

        # Resample to weekly / monthly when requested
        if freq in ("1w", "1M") and not df.empty:
            rule = "W" if freq == "1w" else "ME"
            df = (
                df.set_index("date")
                .resample(rule)
                .agg({
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                })
                .dropna()
                .reset_index()
            )

        return df

    # ---- Thread-pool / rate-limiting -----------------------------------

    async def _run_akshare(self, func_name: str, *args: Any, **kwargs: Any) -> pd.DataFrame:
        """
        Execute a blocking akshare function in the thread-pool executor.

        Rate-limiting is enforced **before** each call: the method sleeps
        if less than ``self._rate_limit`` seconds have elapsed since the
        previous akshare invocation.

        Args:
            func_name: Name of the akshare top-level function, e.g.
                       ``'stock_zh_a_hist'``.
            *args: Forwarded to the akshare function.
            **kwargs: Forwarded to the akshare function.

        Returns:
            DataFrame returned by akshare (empty DataFrame on failure).

        Raises:
            ImportError: If akshare is not installed.
            ValueError: If ``func_name`` does not exist in the akshare module.
        """
        await self._throttle()

        try:
            import akshare as ak  # noqa: F811 — runtime dependency
        except ImportError as err:
            logger.error(
                "akshare is not installed. Install with: pip install akshare"
            )
            raise ImportError(
                "akshare is required for AkshareQuoteFetcher. "
                "Install with: pip install akshare"
            ) from err

        func = getattr(ak, func_name, None)
        if func is None:
            raise ValueError(
                f"akshare has no function named {func_name!r}"
            )

        loop = asyncio.get_running_loop()

        try:
            result = await loop.run_in_executor(
                self._executor,
                lambda: func(*args, **kwargs),
            )
        except Exception:
            logger.exception(f"akshare.{func_name} raised an exception")
            raise

        if result is None or not isinstance(result, pd.DataFrame):
            logger.warning(
                f"akshare.{func_name} returned {type(result).__name__}; "
                f"expected DataFrame. Returning empty."
            )
            return pd.DataFrame()

        return result

    async def _throttle(self) -> None:
        """
        Enforce the configured rate limit.

        Sleeps for ``(rate_limit - elapsed)`` seconds when the time since
        the last request is shorter than ``rate_limit``.
        """
        now = time.monotonic()
        elapsed = now - self._last_request_time

        if elapsed < self._rate_limit:
            wait = self._rate_limit - elapsed
            logger.debug(f"Rate-limit sleep: {wait:.2f}s")
            await asyncio.sleep(wait)

        self._last_request_time = time.monotonic()

    # ---- DataFrame standardisation -------------------------------------

    @staticmethod
    def _standardise_kline_columns(df: pd.DataFrame, freq: str) -> pd.DataFrame:
        """
        Rename columns to the standard QuantEngine schema and keep only
        the expected columns.

        Handles both:

        * Chinese-column DataFrames (``stock_zh_a_hist``)
        * English-column DataFrames (``stock_zh_index_daily``)

        The returned DataFrame always contains:
        ``timestamp``, ``open``, ``high``, ``low``, ``close``, ``volume``,
        ``amount`` (filled with 0 if absent).
        """
        if df.empty:
            return df

        # Detect column style
        if "日期" in df.columns:
            col_map: Dict[str, str] = AkshareQuoteFetcher._KLINE_COLUMN_MAP
        elif "date" in df.columns:
            col_map = AkshareQuoteFetcher._INDEX_KLINE_COLUMN_MAP
        else:
            logger.warning(
                f"K-line column format not recognised. "
                f"Columns: {list(df.columns)}"
            )
            return df

        rename = {k: v for k, v in col_map.items() if k in df.columns}
        df = df.rename(columns=rename)

        # Keep only the standard columns (amount may be absent for indices)
        out_cols = ["timestamp", "open", "high", "low", "close", "volume", "amount"]
        df = df[[c for c in out_cols if c in df.columns]]

        # Ensure timestamp is datetime
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"])

        # Coerce numeric columns
        for col in ["open", "high", "low", "close", "volume", "amount"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # Fill missing amount with 0 (index data doesn't carry it)
        if "amount" not in df.columns:
            df["amount"] = 0.0

        return df

    @staticmethod
    def _sort_and_dedup(df: pd.DataFrame) -> pd.DataFrame:
        """
        Sort by ``timestamp`` ascending and remove duplicate rows.

        When two rows share the same timestamp the **last** occurrence
        is kept (``keep='last'``), which helps when appending intraday
        updates.
        """
        if df.empty or "timestamp" not in df.columns:
            return df

        return (
            df.sort_values("timestamp")
            .drop_duplicates(subset=["timestamp"], keep="last")
            .reset_index(drop=True)
        )

    # ---- Misc helpers --------------------------------------------------

    @staticmethod
    def _normalise_date(date_str: str) -> str:
        """
        Convert a date string to ``'YYYYMMDD'`` format.

        Accepts:
            * ``'YYYYMMDD'``  — kept as-is
            * ``'YYYY-MM-DD'`` — dashes removed
            * ``'YYYY/MM/DD'`` — slashes removed
            * ISO-8601 strings parsed by ``pd.Timestamp``
        """
        cleaned = date_str.replace("-", "").replace("/", "").strip()
        if len(cleaned) == 8 and cleaned.isdigit():
            return cleaned

        # Fall back to pandas parsing
        try:
            return pd.Timestamp(date_str).strftime("%Y%m%d")
        except (ValueError, TypeError):
            logger.warning(f"Could not parse date {date_str!r}; using as-is")
            return date_str

    async def fetch_tick(
        self,
        symbol: str,
        date: Optional[str] = None,
        limit: int = 1000,
    ) -> pd.DataFrame:
        """
        Fetch tick-level trade data for A-share stocks.

        Uses akshare ``stock_zh_a_tick_tx`` for intraday tick data.

        Args:
            symbol: A-share stock code (e.g., '000001')
            date: Date string 'YYYYMMDD'
            limit: Max ticks (unused, API returns all ticks for the day)

        Returns:
            DataFrame with columns: timestamp, price, volume, direction
        """
        logger.info(f"Fetching tick data for {symbol} on {date or 'today'}")
        try:
            date_str = date or datetime.now().strftime("%Y-%m-%d")
            df = await self._run_akshare("stock_zh_a_tick_tx", symbol, date_str)
            if df.empty:
                return pd.DataFrame(columns=["timestamp", "price", "volume", "direction"])
            df = df.rename(columns={
                "成交时间": "timestamp", "成交价": "price",
                "成交量": "volume", "买卖方向": "direction",
            })
            return df.head(limit)
        except Exception as e:
            logger.warning(f"fetch_tick failed for {symbol}: {e}")
            return pd.DataFrame(columns=["timestamp", "price", "volume", "direction"])

    @staticmethod
    def _build_quote_dict(row: pd.Series) -> Dict[str, Any]:
        """
        Build a standardised quote dictionary from a raw spot-data row.

        Args:
            row: A single row from the ``stock_zh_a_spot_em`` DataFrame.

        Returns:
            Dictionary with all keys documented in :meth:`fetch_realtime_quote`.
        """
        return {
            "symbol": str(row.get("代码", "")),
            "name": str(row.get("名称", "")),
            "price": float(row.get("最新价", 0.0) or 0.0),
            "change": float(row.get("涨跌额", 0.0) or 0.0),
            "change_pct": float(row.get("涨跌幅", 0.0) or 0.0),
            "volume": float(row.get("成交量", 0.0) or 0.0),
            "amount": float(row.get("成交额", 0.0) or 0.0),
            "open": float(row.get("今开", row.get("开盘价", 0.0)) or 0.0),
            "high": float(row.get("最高价", 0.0) or 0.0),
            "low": float(row.get("最低价", 0.0) or 0.0),
            "pre_close": float(row.get("昨收", 0.0) or 0.0),
            "turnover": float(row.get("换手率", 0.0) or 0.0),
            "pe": float(row.get("市盈率-动态", 0.0) or 0.0),
            "pb": float(row.get("市净率", 0.0) or 0.0),
            "timestamp": datetime.now().isoformat(),
        }
