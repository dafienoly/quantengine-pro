"""
QuantEngine Pro - CCXT Quote Fetcher
=====================================
Cryptocurrency market data fetcher using CCXT (CryptoCurrency eXchange Trading Library).
Supports 100+ exchanges (Binance, OKX, Bybit, etc.) with unified API.

Free: CCXT is MIT-licensed and exchanges provide free market data.
Upgrade path: Exchange-specific WebSocket feeds or paid data services.
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
from loguru import logger

from quantengine.data.base import BaseQuoteFetcher


class CCXTQuoteFetcher(BaseQuoteFetcher):
    """
    Cryptocurrency market data fetcher using CCXT unified API.

    Supports all major exchanges with consistent interface.
    Rate-limited to respect exchange API constraints.

    Usage:
        fetcher = CCXTQuoteFetcher({"exchange": "binance", "testnet": True})
        df = await fetcher.fetch_kline("BTC/USDT", "1h", limit=500)
    """

    def __init__(self, config: Dict):
        """
        Initialize CCXT fetcher.

        Args:
            config: Dict with keys:
                - exchange: Exchange name (binance, okx, bybit, etc.)
                - testnet: Use testnet/sandbox (default False)
                - rate_limit_ms: Min ms between requests (default 200)
        """
        super().__init__(config)
        self.exchange_name = config.get("exchange", "binance")
        self.is_testnet = config.get("testnet", False)
        self.rate_limit_ms = config.get("rate_limit_ms", 200)

        # Lazy initialization - create exchange on first use
        self._exchange = None
        logger.info(
            f"CCXTQuoteFetcher initialized: exchange={self.exchange_name}, "
            f"testnet={self.is_testnet}"
        )

    def _get_exchange(self):
        """
        Lazy-load the CCXT exchange instance.

        Returns:
            ccxt.Exchange: Configured exchange instance
        """
        if self._exchange is None:
            import ccxt

            # Dynamically get exchange class
            exchange_class = getattr(ccxt, self.exchange_name)
            config = {
                "enableRateLimit": True,  # CCXT built-in rate limiting
                "options": {"defaultType": "spot"},
            }

            if self.is_testnet:
                # Configure testnet/sandbox URLs if available
                if self.exchange_name == "binance":
                    config["urls"] = {"api": "https://testnet.binance.vision"}
                elif self.exchange_name == "okx":
                    config["urls"] = {"api": "https://www.okx.com/api/v5/public"}
                    config["options"]["sandbox"] = True

            self._exchange = exchange_class(config)
            logger.debug(f"CCXT exchange {self.exchange_name} created")

        return self._exchange

    async def fetch_kline(
        self,
        symbol: str,
        freq: str = "1d",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 1000,
    ) -> pd.DataFrame:
        """
        Fetch OHLCV candlestick data from crypto exchange.

        Args:
            symbol: Trading pair (e.g., 'BTC/USDT', 'ETH/USDT')
            freq: Bar frequency - supported: '1m','5m','15m','30m','1h','4h','1d','1w','1M'
            start_date: Start datetime string 'YYYY-MM-DD HH:MM:SS' or 'YYYY-MM-DD'
            end_date: End datetime string
            limit: Max bars (exchange-limited, typically 500-1500)

        Returns:
            DataFrame columns: timestamp, open, high, low, close, volume
        """
        exchange = self._get_exchange()

        # Normalize frequency format for CCXT
        # CCXT uses: '1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w', '1M'
        valid_freqs = {"1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1M"}
        if freq not in valid_freqs:
            logger.warning(f"Frequency '{freq}' may not be supported by CCXT, using '1d'")
            freq = "1d"

        # Parse start date to timestamp (ms)
        since = None
        if start_date:
            try:
                # Support multiple date formats
                for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y%m%d"]:
                    try:
                        dt = datetime.strptime(start_date, fmt)
                        since = int(dt.timestamp() * 1000)
                        break
                    except ValueError:
                        continue
            except Exception as e:
                logger.error(f"Failed to parse start_date '{start_date}': {e}")

        logger.debug(f"Fetching {symbol} {freq} kline, since={since}, limit={limit}")

        try:
            # Run synchronous CCXT call in thread pool
            loop = asyncio.get_event_loop()
            ohlcv = await loop.run_in_executor(
                None,
                lambda: exchange.fetch_ohlcv(
                    symbol, timeframe=freq, since=since, limit=limit
                )
            )

            if not ohlcv:
                logger.warning(f"No data returned for {symbol} {freq}")
                return pd.DataFrame()

            # Convert to DataFrame
            df = pd.DataFrame(
                ohlcv,
                columns=["timestamp", "open", "high", "low", "close", "volume"]
            )
            # Convert ms timestamp to datetime
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df["amount"] = df["close"] * df["volume"]  # Quote volume approximation

            logger.info(f"Fetched {len(df)} bars for {symbol} {freq}")
            return df

        except Exception as e:
            logger.error(f"CCXT fetch_kline failed for {symbol}: {e}")
            return pd.DataFrame()

    async def fetch_realtime_quote(self, symbol: str) -> Dict:
        """
        Fetch real-time ticker data for a symbol.

        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')

        Returns:
            Dict with bid, ask, last price, volume, change percentage
        """
        exchange = self._get_exchange()

        try:
            loop = asyncio.get_event_loop()
            ticker = await loop.run_in_executor(
                None, lambda: exchange.fetch_ticker(symbol)
            )

            return {
                "symbol": symbol,
                "price": ticker.get("last", 0),
                "bid": ticker.get("bid", 0),
                "ask": ticker.get("ask", 0),
                "volume": ticker.get("baseVolume", 0),
                "change_pct": ticker.get("percentage", 0),
                "high_24h": ticker.get("high", 0),
                "low_24h": ticker.get("low", 0),
                "timestamp": datetime.now(),
            }
        except Exception as e:
            logger.error(f"Failed to fetch ticker for {symbol}: {e}")
            return {"symbol": symbol, "error": str(e)}

    async def get_all_symbols(self, market: str = "crypto") -> List[str]:
        """
        Get all available trading pairs from the exchange.

        Args:
            market: Market filter (ignored for crypto, always returns all)

        Returns:
            List of trading pair strings
        """
        exchange = self._get_exchange()

        try:
            loop = asyncio.get_event_loop()
            markets = await loop.run_in_executor(
                None, lambda: exchange.load_markets()
            )

            # Filter to USDT spot pairs by default for relevance
            symbols = [
                sym for sym, info in markets.items()
                if info.get("active", False) and info.get("spot", False)
            ]

            logger.info(f"Loaded {len(symbols)} active spot symbols from {self.exchange_name}")
            return sorted(symbols)

        except Exception as e:
            logger.error(f"Failed to load markets from {self.exchange_name}: {e}")
            return []

    async def fetch_order_book(self, symbol: str, depth: int = 20) -> Dict:
        """
        Fetch current order book for a symbol.

        Args:
            symbol: Trading pair
            depth: Number of price levels (default 20)

        Returns:
            Dict with 'bids' and 'asks' lists of [price, quantity]
        """
        exchange = self._get_exchange()

        try:
            loop = asyncio.get_event_loop()
            orderbook = await loop.run_in_executor(
                None, lambda: exchange.fetch_order_book(symbol, limit=depth)
            )
            return {
                "symbol": symbol,
                "bids": orderbook.get("bids", []),
                "asks": orderbook.get("asks", []),
                "timestamp": datetime.now(),
            }
        except Exception as e:
            logger.error(f"Failed to fetch order book for {symbol}: {e}")
            return {"symbol": symbol, "bids": [], "asks": [], "error": str(e)}
