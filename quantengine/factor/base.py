"""
QuantEngine Pro - Factor System
=================================
Base factor class and technical factor library.

Each factor is an independent calculation that takes a DataFrame
and returns a Series of factor values. Factors are composable
and can be combined for multi-factor strategies.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from loguru import logger


class BaseFactor(ABC):
    """
    Abstract base class for all factors.

    Each factor must implement calculate(data: DataFrame) -> Series.
    """

    def __init__(self, name: str, params: Optional[Dict] = None):
        self.name = name
        self.params = params or {}

    @abstractmethod
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """Calculate factor values from OHLCV data."""
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.name})"


class MomentumFactor(BaseFactor):
    """N-period price momentum factor (z-score normalized)."""

    def __init__(self, period: int = 20):
        super().__init__(name=f"momentum_{period}", params={"period": period})
        self.period = period

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        close = data["close"]
        momentum = close.pct_change(self.period)
        return (momentum - momentum.mean()) / momentum.std()


class VolatilityFactor(BaseFactor):
    """N-period historical volatility factor (inverse: prefer low vol)."""

    def __init__(self, period: int = 20):
        super().__init__(name=f"volatility_{period}", params={"period": period})
        self.period = period

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        returns = data["close"].pct_change()
        vol = returns.rolling(self.period).std()
        return -vol / vol.mean()


class VolumeFactor(BaseFactor):
    """Volume ratio factor: short_avg / long_avg."""

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
    """RSI-based factor: values far from 50 → stronger signal."""

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
        return -(rsi - 50) / 50


class MACDFactor(BaseFactor):
    """MACD histogram factor normalized by price."""

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
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=self.signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return histogram / close


class FactorRegistry:
    """
    Registry for creating and combining factors.

    Usage:
        reg = FactorRegistry()
        reg.register("momentum_20", MomentumFactor(20))
        scores = reg.compute_all(data)
        composite = reg.composite_score(scores)
    """

    def __init__(self):
        self._factors: Dict[str, BaseFactor] = {}
        self._weights: Dict[str, float] = {}

    def register(self, name: str, factor: BaseFactor, weight: float = 1.0) -> None:
        """Register a factor with optional weight."""
        self._factors[name] = factor
        self._weights[name] = weight

    def compute_all(self, data: pd.DataFrame) -> pd.DataFrame:
        """Compute all registered factors."""
        results = {}
        for name, factor in self._factors.items():
            try:
                results[name] = factor.calculate(data)
            except Exception as e:
                logger.error(f"Factor {name} failed: {e}")
                results[name] = pd.Series(0, index=data.index)
        return pd.DataFrame(results)

    def composite_score(self, factor_df: pd.DataFrame) -> pd.Series:
        """Weighted composite factor score with z-score normalization."""
        if factor_df.empty:
            return pd.Series()
        normalized = (factor_df - factor_df.mean()) / factor_df.std()
        composite = pd.Series(0.0, index=normalized.index)
        for col in normalized.columns:
            weight = self._weights.get(col, 1.0)
            composite += normalized[col].fillna(0) * weight
        return composite

    @property
    def factor_names(self) -> List[str]:
        return list(self._factors.keys())
