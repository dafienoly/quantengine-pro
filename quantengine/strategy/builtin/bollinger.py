"""
Bollinger Bands Mean Reversion Strategy
=========================================
Uses Bollinger Bands with RSI confirmation for mean-reversion trades.

Logic:
- Long: Price touches/crosses lower band AND RSI < oversold threshold
- Short/Exit: Price touches/crosses upper band AND RSI > overbought threshold
- Stop: Opposite band
"""

from typing import Optional

import numpy as np
import pandas as pd

from quantengine.strategy.base import (
    BaseStrategy,
    Signal,
    SignalType,
    StrategyContext,
)


class BollingerStrategy(BaseStrategy):
    """
    Bollinger Bands mean reversion strategy.

    Parameters:
        period (int): MA and standard deviation period (default 20)
        num_std (float): Number of standard deviations for bands (default 2.0)
        rsi_period (int): RSI calculation period (default 14)
        rsi_oversold (float): RSI threshold for oversold (default 30)
        rsi_overbought (float): RSI threshold for overbought (default 70)
    """

    def __init__(self, params: Optional[dict] = None):
        super().__init__(params)
        self.period = self.params.get("period", 20)
        self.num_std = self.params.get("num_std", 2.0)
        self.rsi_period = self.params.get("rsi_period", 14)
        self.rsi_oversold = self.params.get("rsi_oversold", 30)
        self.rsi_overbought = self.params.get("rsi_overbought", 70)

    def on_bar(self, bar: pd.Series, context: StrategyContext) -> Optional[Signal]:
        """Generate signals using Bollinger Bands mean reversion."""
        history = context.history
        min_bars = max(self.period, self.rsi_period) + 1
        if history.empty or len(history) < min_bars:
            return None

        close = history["close"].values
        current_price = bar["close"]
        timestamp = bar["timestamp"] if "timestamp" in bar else pd.Timestamp.now()

        # Bollinger Bands
        ma = np.mean(close[-self.period:])
        std = np.std(close[-self.period:], ddof=1)
        upper_band = ma + self.num_std * std
        lower_band = ma - self.num_std * std
        bandwidth = (upper_band - lower_band) / ma  # Normalized width

        # RSI
        rsi = self._calc_rsi(close, self.rsi_period)

        # Position check
        has_long = any(
            p.get("quantity", 0) > 0 for p in context.positions.values()
        )

        # Long signal: price at/below lower band + RSI oversold
        if current_price <= lower_band and rsi < self.rsi_oversold and not has_long:
            return self._record_signal(Signal(
                timestamp=timestamp,
                symbol=context.symbol,
                type=SignalType.BUY,
                price=current_price,
                stop_loss=lower_band * 0.98,  # 2% below lower band
                take_profit=ma,  # Target middle band
                confidence=min((self.rsi_oversold - rsi) / self.rsi_oversold, 0.95),
                metadata={
                    "ma": ma,
                    "upper": upper_band,
                    "lower": lower_band,
                    "rsi": rsi,
                    "bandwidth": bandwidth,
                },
            ))

        # Exit long: price at/above upper band + RSI overbought
        if current_price >= upper_band and rsi > self.rsi_overbought and has_long:
            return self._record_signal(Signal(
                timestamp=timestamp,
                symbol=context.symbol,
                type=SignalType.SELL,
                price=current_price,
                confidence=min((rsi - self.rsi_overbought) / (100 - self.rsi_overbought), 0.95),
                metadata={"ma": ma, "upper": upper_band, "rsi": rsi},
            ))

        return None

    @staticmethod
    def _calc_rsi(prices: np.ndarray, period: int) -> float:
        """Calculate Relative Strength Index."""
        if len(prices) < period + 1:
            return 50.0

        deltas = np.diff(prices[-period-1:])
        gains = np.maximum(deltas, 0)
        losses = np.abs(np.minimum(deltas, 0))

        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)

        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))
