#!/usr/bin/env python3
"""
QuantEngine Pro - Data Download Script
=======================================
One-click historical data download for A-share and cryptocurrency markets.

Usage:
    python scripts/download_data.py --market a_share --freq 1d
    python scripts/download_data.py --market crypto --symbols BTC/USDT,ETH/USDT --freq 5m
    python scripts/download_data.py --market all --start 20200101
"""

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from quantengine.config.manager import get_config
from quantengine.data.akshare_fetcher import AkshareQuoteFetcher
from quantengine.data.cache import CacheManager
from quantengine.data.ccxt_fetcher import CCXTQuoteFetcher
from quantengine.data.storage import ParquetStorage
from loguru import logger


async def download_a_share(
    freq: str = "1d",
    start_date: str = "20200101",
    end_date: str = None,
    symbols: list = None,
    max_symbols: int = None,
):
    """
    Download A-share historical K-line data.

    Args:
        freq: Bar frequency ('1d', '1w', '1M')
        start_date: Start date YYYYMMDD
        end_date: End date YYYYMMDD
        symbols: Specific symbols to download (None = all)
        max_symbols: Limit number of symbols (for testing)
    """
    if end_date is None:
        end_date = datetime.now().strftime("%Y%m%d")

    logger.info(f"Starting A-share {freq} download: {start_date} → {end_date}")

    config = get_config()
    storage_path = config.get("data_source.data.storage.parquet_path", "./data/parquet")
    fetcher = AkshareQuoteFetcher({"rate_limit": 0.3})

    # Get symbol list
    if symbols is None:
        symbols = await fetcher.get_all_symbols()
        logger.info(f"Downloading {len(symbols)} A-share stocks")

    if max_symbols:
        symbols = symbols[:max_symbols]
        logger.info(f"Limited to {max_symbols} symbols")

    success_count = 0
    fail_count = 0

    for i, symbol in enumerate(symbols):
        try:
            df = await fetcher.fetch_kline(
                symbol=symbol,
                freq=freq,
                start_date=start_date,
                end_date=end_date,
            )

            if df is not None and not df.empty:
                key = f"{symbol}_{freq}_{start_date}_{end_date}"
                ParquetStorage.save(df, storage_path, key)
                success_count += 1
            else:
                fail_count += 1

            # Progress reporting
            if (i + 1) % 100 == 0:
                logger.info(
                    f"Progress: {i+1}/{len(symbols)} "
                    f"({success_count} OK, {fail_count} FAIL)"
                )

        except Exception as e:
            logger.error(f"Failed to download {symbol}: {e}")
            fail_count += 1

    logger.info(
        f"A-share download complete: {success_count} success, {fail_count} failed"
    )


async def download_crypto(
    freq: str = "1d",
    symbols: list = None,
    start_date: str = "20220101",
    exchange: str = "binance",
):
    """
    Download cryptocurrency historical OHLCV data.

    Args:
        freq: Bar frequency
        symbols: Trading pairs (default: BTC/USDT, ETH/USDT)
        start_date: Start date
        exchange: Exchange name for CCXT
    """
    if symbols is None:
        symbols = ["BTC/USDT", "ETH/USDT"]

    logger.info(f"Starting crypto {freq} download from {exchange}: {symbols}")

    fetcher = CCXTQuoteFetcher({
        "exchange": exchange,
        "rate_limit_ms": 500,
    })

    config = get_config()
    storage_path = config.get("data_source.data.storage.parquet_path", "./data/parquet")

    for symbol in symbols:
        logger.info(f"Downloading {symbol} {freq}...")
        df = await fetcher.fetch_kline(
            symbol=symbol,
            freq=freq,
            start_date=start_date,
            limit=1500,
        )

        if df is not None and not df.empty:
            key = f"{symbol.replace('/', '_')}_{freq}_{start_date}"
            ParquetStorage.save(df, storage_path, key)
            logger.info(f"Saved {len(df)} bars for {symbol}")
        else:
            logger.warning(f"No data for {symbol}")

    logger.info("Crypto download complete")


async def main():
    """Main entry point for data download script."""
    parser = argparse.ArgumentParser(
        description="QuantEngine Pro - Historical Data Downloader"
    )
    parser.add_argument(
        "--market",
        choices=["a_share", "crypto", "all"],
        default="all",
        help="Market to download",
    )
    parser.add_argument(
        "--freq",
        default="1d",
        help="Bar frequency (1d, 1w, 1M, 1h, 5m, 15m, etc.)",
    )
    parser.add_argument(
        "--symbols",
        default=None,
        help="Comma-separated symbol list (default: all for A-share, BTC/ETH for crypto)",
    )
    parser.add_argument(
        "--start",
        default="20200101",
        help="Start date YYYYMMDD",
    )
    parser.add_argument(
        "--end",
        default=None,
        help="End date YYYYMMDD (default: today)",
    )
    parser.add_argument(
        "--max-symbols",
        type=int,
        default=None,
        help="Max number of symbols (for testing)",
    )
    parser.add_argument(
        "--exchange",
        default="binance",
        help="Crypto exchange for CCXT",
    )

    args = parser.parse_args()

    # Parse symbols
    symbols = None
    if args.symbols:
        symbols = args.symbols.split(",")

    if args.market in ("a_share", "all"):
        await download_a_share(
            freq=args.freq,
            start_date=args.start,
            end_date=args.end,
            symbols=symbols,
            max_symbols=args.max_symbols,
        )

    if args.market in ("crypto", "all"):
        await download_crypto(
            freq=args.freq,
            symbols=symbols if args.market == "crypto" else None,
            start_date=args.start,
            exchange=args.exchange,
        )

    # Print storage stats
    config = get_config()
    storage_path = config.get("data_source.data.storage.parquet_path", "./data/parquet")
    stats = ParquetStorage.get_stats(storage_path)
    logger.info(f"Storage stats: {stats}")


if __name__ == "__main__":
    asyncio.run(main())
