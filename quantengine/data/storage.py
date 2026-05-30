"""
QuantEngine Pro - Parquet Storage Manager
==========================================
Cold storage layer using Apache Parquet format.

Features:
- Partitioned storage by symbol/freq for efficient queries
- Automatic directory structure: {base_path}/{symbol}/{freq}/{key}.parquet
- Compression: snappy (fast) or gzip (smaller)
- Append mode for incremental data updates
"""

import os
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from loguru import logger


class ParquetStorage:
    """
    Parquet-based persistent storage for market data.

    Organizes data in a partitioned directory structure for efficient
    filtering and retrieval.

    Directory layout:
        {base_path}/
            {symbol}/
                {freq}/
                    {key}.parquet

    Usage:
        ParquetStorage.save(df, "./data/parquet", "000001_1d_20200101_20231231")
        df = ParquetStorage.load("./data/parquet", "000001_1d_20200101_20231231")
    """

    # Default Parquet write options
    DEFAULT_COMPRESSION = "snappy"  # Fast read/write, good compression
    DEFAULT_ROW_GROUP_SIZE = 100000  # 100K rows per row group

    @staticmethod
    def _get_file_path(base_path: str, key: str) -> Path:
        """
        Build file path from base path and cache key.

        Creates partitioned directories to avoid too many files
        in a single directory.

        Args:
            base_path: Root storage directory
            key: Cache key (MD5 hash or descriptive key)

        Returns:
            Full Path object to the parquet file
        """
        # Use first 2 chars of key for subdirectory sharding
        subdir = key[:2]
        return Path(base_path) / subdir / f"{key}.parquet"

    @staticmethod
    def save(
        df: pd.DataFrame,
        base_path: str,
        key: str,
        compression: Optional[str] = None,
        append: bool = False,
    ) -> bool:
        """
        Save DataFrame to Parquet file.

        Args:
            df: DataFrame to save
            base_path: Root storage directory
            key: Unique key for this dataset
            compression: 'snappy', 'gzip', 'zstd', or None
            append: If True, append to existing data (load → concat → save)

        Returns:
            True if saved successfully, False on error
        """
        if df is None or df.empty:
            logger.debug(f"Skipping save for empty DataFrame: {key}")
            return False

        file_path = ParquetStorage._get_file_path(base_path, key)

        try:
            # Create parent directories
            file_path.parent.mkdir(parents=True, exist_ok=True)

            if append and file_path.exists():
                # Load existing, concat, deduplicate, save
                try:
                    existing = pd.read_parquet(file_path)
                    df = pd.concat([existing, df], ignore_index=True)
                    if "timestamp" in df.columns:
                        df = df.drop_duplicates(subset=["timestamp"], keep="last")
                        df = df.sort_values("timestamp").reset_index(drop=True)
                except Exception as e:
                    logger.warning(f"Failed to append to {file_path}: {e}, overwriting")

            # Write Parquet with schema preservation
            df.to_parquet(
                file_path,
                compression=compression or ParquetStorage.DEFAULT_COMPRESSION,
                index=False,
                engine="pyarrow",
                row_group_size=ParquetStorage.DEFAULT_ROW_GROUP_SIZE,
            )

            file_size = file_path.stat().st_size
            logger.info(
                f"Saved {len(df)} rows ({file_size / 1024:.1f} KB) → {file_path}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to save Parquet file {file_path}: {e}")
            return False

    @staticmethod
    def load(base_path: str, key: str) -> Optional[pd.DataFrame]:
        """
        Load DataFrame from Parquet file.

        Args:
            base_path: Root storage directory
            key: Cache key

        Returns:
            DataFrame or None if file not found
        """
        file_path = ParquetStorage._get_file_path(base_path, key)

        if not file_path.exists():
            return None

        try:
            df = pd.read_parquet(file_path, engine="pyarrow")
            logger.debug(f"Loaded {len(df)} rows from {file_path}")
            return df

        except Exception as e:
            logger.error(f"Failed to load Parquet file {file_path}: {e}")
            return None

    @staticmethod
    def load_range(
        base_path: str,
        keys: List[str],
    ) -> Dict[str, pd.DataFrame]:
        """
        Load multiple Parquet files at once.

        Args:
            base_path: Root storage directory
            keys: List of cache keys

        Returns:
            Dict mapping key → DataFrame (missing keys omitted)
        """
        result = {}
        for key in keys:
            df = ParquetStorage.load(base_path, key)
            if df is not None:
                result[key] = df
        return result

    @staticmethod
    def delete(base_path: str, key: str) -> bool:
        """
        Delete a Parquet file.

        Args:
            base_path: Root storage directory
            key: Cache key

        Returns:
            True if deleted, False if file didn't exist or error
        """
        file_path = ParquetStorage._get_file_path(base_path, key)

        if not file_path.exists():
            return False

        try:
            file_path.unlink()
            logger.info(f"Deleted: {file_path}")

            # Clean up empty parent directory
            parent = file_path.parent
            if not any(parent.iterdir()):
                parent.rmdir()

            return True

        except Exception as e:
            logger.error(f"Failed to delete {file_path}: {e}")
            return False

    @staticmethod
    def list_keys(base_path: str, prefix: str = "") -> List[str]:
        """
        List all cache keys in storage.

        Args:
            base_path: Root storage directory
            prefix: Filter keys starting with this prefix

        Returns:
            List of cache key strings
        """
        base = Path(base_path)
        if not base.exists():
            return []

        keys = []
        for parquet_file in base.rglob("*.parquet"):
            key = parquet_file.stem  # filename without .parquet
            if key.startswith(prefix):
                keys.append(key)

        return sorted(keys)

    @staticmethod
    def get_stats(base_path: str) -> Dict:
        """
        Get storage statistics.

        Args:
            base_path: Root storage directory

        Returns:
            Dict with total files, total size, date range
        """
        base = Path(base_path)
        if not base.exists():
            return {"total_files": 0, "total_size_bytes": 0}

        files = list(base.rglob("*.parquet"))
        total_size = sum(f.stat().st_size for f in files)

        return {
            "total_files": len(files),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "base_path": str(base.absolute()),
        }
