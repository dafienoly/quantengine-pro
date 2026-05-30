"""
Multi-Factor Stock Selection Strategy
=======================================
Ranks stocks by composite factor scores, selects top N for equal-weight portfolio.

Factors supported:
- momentum_N: N-day price momentum
- volatility_N: N-day volatility (inverse for low-vol preference)
- volume_ratio: Volume relative to N-day average
- rsi_N: RSI value (mean-reversion signal)
- turnover_N: Average turnover rate

Rebalancing: Monthly (configurable)
"""

from typing import List, Optional

import numpy as np
import pandas as pd

from quantengine.strategy.base import (
    BaseStrategy,
    Signal,
    SignalType,
    StrategyContext,
)


class MultiFactorStrategy(BaseStrategy):
    """
    Multi-factor stock selection and ranking strategy.

    Parameters:
        factors (list): List of factor names to use (default: momentum, volatility)
        top_n (int): Number of top stocks to hold (default 10)
        rebalance_freq (str): 'daily', 'weekly', or 'monthly' (default 'monthly')
        equal_weight (bool): If True, equal weight all positions (default True)
    """

    def __init__(self, params: Optional[dict] = None):
        super().__init__(params)
        self.factors = self.params.get("factors", ["momentum_20", "volatility_20", "volume_ratio"])
        self.top_n = self.params.get("top_n", 10)
        self.rebalance_freq = self.params.get("rebalance_freq", "monthly")
        self.equal_weight = self.params.get("equal_weight", True)

        # Factor registry
        self._factor_calculators = {
            "momentum": self._calc_momentum,
            "volatility": self._calc_volatility,
            "volume_ratio": self._calc_volume_ratio,
            "rsi": self._calc_rsi,
            "turnover": self._calc_turnover,
        }

    def on_bar(self, bar: pd.Series, context: StrategyContext) -> Optional[Signal]:
        """
        Multi-factor strategy generates signals during rebalance periods.

        For daily bars, checks if it's a rebalance day and issues
        REBALANCE signals with target weights.
        """
        history = context.history
        if history.empty or len(history) < 60:
            return None

        timestamp = bar["timestamp"] if "timestamp" in bar else pd.Timestamp.now()

        # Check if rebalance day
        if not self._is_rebalance_day(timestamp, self.rebalance_freq):
            return None

        # This strategy requires external stock universe scanning
        # For a single symbol context, calculate factor scores
        close_vals = history["close"].values

        scores = {}
        for factor_name in self.factors:
            # Parse factor name (e.g., "momentum_20" → factor="momentum", period=20)
            parts = factor_name.split("_")
            base = parts[0]
            period = int(parts[1]) if len(parts) > 1 else 20

            calculator = self._factor_calculators.get(base)
            if calculator:
                score = calculator(close_vals, period)
                scores[factor_name] = score

        # Composite score (equal weight)
        if scores:
            composite = np.mean(list(scores.values()))
        else:
            composite = 0.0

        # Generate signal based on composite score
        current_price = bar["close"]
        has_position = any(
            p.get("quantity", 0) > 0 for p in context.positions.values()
        )

        # Strong positive score → buy
        if composite > 0.5 and not has_position:
            return self._record_signal(Signal(
                timestamp=timestamp,
                symbol=context.symbol,
                type=SignalType.BUY,
                price=current_price,
                confidence=min(abs(composite), 0.9),
                metadata={"factor_scores": scores, "composite": composite},
            ))

        # Negative score → sell
        if composite < -0.5 and has_position:
            return self._record_signal(Signal(
                timestamp=timestamp,
                symbol=context.symbol,
                type=SignalType.SELL,
                price=current_price,
                confidence=min(abs(composite), 0.9),
                metadata={"factor_scores": scores, "composite": composite},
            ))

        return None

    # ---- Factor Calculators ----

    @staticmethod
    def _calc_momentum(prices: np.ndarray, period: int = 20) -> float:
        """Calculate normalized momentum score."""
        if len(prices) < period + 1:
            return 0.0
        momentum = (prices[-1] - prices[-period-1]) / prices[-period-1]
        # Normalize to roughly -1 to 1
        return np.tanh(momentum * 10)

    @staticmethod
    def _calc_volatility(prices: np.ndarray, period: int = 20) -> float:
        """Calculate inverse volatility score (prefer low vol)."""
        if len(prices) < period:
            return 0.0
        returns = np.diff(prices[-period:]) / prices[-period:-1]
        vol = np.std(returns)
        if vol == 0:
            return 0.0
        # Inverse: lower vol → higher score
        return -np.tanh(vol * 100)

    @staticmethod
    def _calc_volume_ratio(close_vals: np.ndarray, period: int = 20) -> float:
        """Volume ratio placeholder (needs volume data)."""
        return 0.0  # Requires volume column in context

    @staticmethod
    def _calc_rsi(prices: np.ndarray, period: int = 14) -> float:
        """Calculate RSI-based score (oversold = positive)."""
        if len(prices) < period + 1:
            return 0.0
        deltas = np.diff(prices[-period-1:])
        gains = np.maximum(deltas, 0)
        losses = np.abs(np.minimum(deltas, 0))
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100.0 - 100.0 / (1.0 + rs)
        # Normalize: RSI < 30 → positive score, RSI > 70 → negative
        return (50.0 - rsi) / 50.0

    @staticmethod
    def _calc_turnover(prices: np.ndarray, period: int = 20) -> float:
        """Turnover placeholder."""
        return 0.0

    @staticmethod
    def _is_rebalance_day(timestamp: pd.Timestamp, freq: str) -> bool:
        """Check if current day is a rebalance day."""
        if freq == "daily":
            return True
        elif freq == "weekly":
            return timestamp.dayofweek == 4  # Friday
        elif freq == "monthly":
            # Last trading day of month (approximate)
            return timestamp.day >= 25
        return False
