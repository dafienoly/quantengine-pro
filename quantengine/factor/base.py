"""
QuantEngine Pro - Factor System
=================================
Base factor class and technical factor library.

Each factor is an independent calculation that takes a DataFrame
and returns a Series of factor values. Factors are composable
and can be combined for multi-factor strategies.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Union

import numpy as np
import pandas as pd
from loguru import logger


class BaseFactor(ABC):
    """
    Abstract base class for all factors.

    Each factor must implement:
        calculate(data: DataFrame) -> Series

    Factors are named and can have parameters for customization.
    """

    def __init__(self, name: str, params: Optional[Dict] = None):
        """
        Initialize factor.

        Args:
            name: Factor name (used for column naming)
            params: Factor parameters
        """
        self.name = name
        self.params = params or {}

    @abstractmethod
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """
        Calculate factor values from market data.

        Args:
            data: DataFrame with columns: open, high, low, close, volume

        Returns:
            Series of factor values indexed by timestamp
        """
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.name})"


# =============================================================================
# Technical Factors
# =============================================================================

class MomentumFactor(BaseFactor):
    """N-period price momentum factor."""

    def __init__(self, period: int = 20):
        super().__init__(name=f"momentum_{period}", params={"period": period})
        self.period = period

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        close = data["close"]
        momentum = close.pct_change(self.period)
        # Normalize to z-score
        return (momentum - momentum.mean()) / momentum.std()


class VolatilityFactor(BaseFactor):
    """N-period historical volatility factor (inverse)."""

    def __init__(self, period: int = 20):
        super().__init__(name=f"volatility_{period}", params={"period": period})
        self.period = period

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        returns = data["close"].pct_change()
        vol = returns.rolling(self.period).std()
        # Inverse: prefer low volatility
        return -vol / vol.mean()


class VolumeFactor(BaseFactor):
    """Volume ratio factor (current vol / average vol)."""

    def __init__(self, short_period: int = 5, long_period: int = 20):
        super().__init__(
            name=f"volume_ratio_{short_period}_{long_period}",
            params={"short_period": short_period, "long_period": long_period},
        )
        self.short_period = short_period
        self.long_period = long_period

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        if "volume" not in data.columns:
            return pd.Series(0, index=data.index)
        short_avg = data["volume"].rolling(self.short_period).mean()
        long_avg = data["volume"].rolling(self.long_period).mean()
        return (short_avg / long_avg - 1).fillna(0)


class RSIFactor(BaseFactor):
    """RSI-based factor (mean-reversion signal)."""

    def __init__(self, period: int = 14):
        super().__init__(name=f"rsi_{period}", params={"period": period})
        self.period = period

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        close = data["close"]
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.rolling(self.period).mean()
        avg_loss = loss.rolling(self.period).mean()
        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))
        # Normalize: values far from 50 → stronger signal
        return -(rsi - 50) / 50


class MACDFactor(BaseFactor):
    """MACD histogram factor (trend strength and direction)."""

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        super().__init__(
            name=f"macd_{fast}_{slow}_{signal}",
            params={"fast": fast, "slow": slow, "signal": signal},
        )
        self.fast = fast
        self.slow = slow
        self.signal = signal

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        close = data["close"]
        ema_fast = close.ewm(span=self.fast, adjust=False).mean()
        ema_slow = close.ewm(span=self.slow, adjust=False).mean()
        macd = ema_fast - ema_slow
        signal_line = macd.ewm(span=self.signal, adjust=False).mean()
        histogram = macd - signal_line
        # Normalize by price
        return histogram / close


class TurnoverFactor(BaseFactor):
    """Turnover rate factor (liquidity proxy)."""

    def __init__(self, period: int = 20):
        super().__init__(name=f"turnover_{period}", params={"period": period})
        self.period = period

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        if "turnover_rate" not in data.columns and "amount" not in data.columns:
            return pd.Series(0, index=data.index)
        # Use amount as proxy if turnover_rate not available
        col = "turnover_rate" if "turnover_rate" in data.columns else "amount"
        return data[col].rolling(self.period).mean()


# =============================================================================
# Factor Registry
# =============================================================================

class FactorRegistry:
    """
    Registry for creating and combining factors.

    Usage:
        registry = FactorRegistry()
        registry.register("momentum_20", MomentumFactor(20))
        scores = registry.compute_all(data)
        composite = registry.composite_score(scores)
    """

    def __init__(self):
        self._factors: Dict[str, BaseFactor] = {}
        self._weights: Dict[str, float] = {}

    def register(self, name: str, factor: BaseFactor, weight: float = 1.0) -> None:
        """Register a factor with optional weight."""
        self._factors[name] = factor
        self._weights[name] = weight
        logger.debug(f"Factor registered: {name} (weight={weight})")

    def compute_all(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Compute all registered factors.

        Args:
            data: Market data DataFrame

        Returns:
            DataFrame with factor values as columns
        """
        results = {}
        for name, factor in self._factors.items():
            try:
                results[name] = factor.calculate(data)
            except Exception as e:
                logger.error(f"Factor {name} calculation failed: {e}")
                results[name] = pd.Series(0, index=data.index)

        return pd.DataFrame(results)

    def composite_score(self, factor_df: pd.DataFrame) -> pd.Series:
        """
        Calculate weighted composite factor score.

        Args:
            factor_df: DataFrame with factor columns

        Returns:
            Series of composite scores
        """
        if factor_df.empty:
            return pd.Series()

        # Normalize each factor (z-score)
        normalized = (factor_df - factor_df.mean()) / factor_df.std()

        # Weighted sum
        composite = pd.Series(0, index=normalized.index)
        for col in normalized.columns:
            weight = self._weights.get(col, 1.0)
            composite += normalized[col].fillna(0) * weight

        return composite

    @property
    def factor_names(self) -> List[str]:
        return list(self._factors.keys())
