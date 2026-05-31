"""
Aberration Strategy (波动率自适应通道突破)
============================================
A mean-reversion strategy using volatility-adaptive channels.
Uses Bollinger Bands with standard deviation to detect overextended
price moves. Entry when price touches the outer band, exit at the middle.

Logic:
- Upper band = SMA(period) + num_std × StdDev(period)
- Lower band = SMA(period) - num_std × StdDev(period)
- Middle band = SMA(period)
- Long entry when price < Lower band, exit when price ≥ Middle
- Short entry when price > Upper band, exit when price ≤ Middle
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


class AberrationStrategy(BaseStrategy):
    """
    Aberration volatility-adaptive channel strategy.

    Parameters:
        period (int): Lookback period for SMA and StdDev (default 20)
        num_std (float): Number of standard deviations for bands (default 2.0)
        risk_per_trade (float): Risk per trade as fraction of capital (default 0.02)
    """

    def __init__(self, params: Optional[dict] = None):
        super().__init__(params)
        self.period = self.params.get("period", 20)
        self.num_std = self.params.get("num_std", 2.0)
        self.risk_per_trade = self.params.get("risk_per_trade", 0.02)

    def on_bar(self, bar: pd.Series, context: StrategyContext) -> Optional[Signal]:
        history = context.history
        if history.empty or len(history) < self.period + 1:
            return None

        close = history["close"].values

        # Calculate Bollinger Bands
        sma = np.mean(close[-self.period:])
        std = np.std(close[-self.period:], ddof=1)
        upper = sma + self.num_std * std
        lower = sma - self.num_std * std

        current_price = bar["close"]
        timestamp = bar["timestamp"] if "timestamp" in bar else pd.Timestamp.now()
        positions = context.positions
        has_long = any(p.get("quantity", 0) > 0 for p in positions.values())

        # Long: price below lower band → mean reversion buy
        if current_price < lower and not has_long:
            atr = np.mean(np.abs(np.diff(close[-self.period:])))
            stop_loss = current_price - 2 * atr
            take_profit = sma  # Target middle band
            confidence = min((lower - current_price) / current_price * 50, 0.9)
            return self._record_signal(Signal(
                timestamp=timestamp, symbol=context.symbol,
                type=SignalType.BUY, price=current_price,
                stop_loss=stop_loss, take_profit=take_profit,
                confidence=confidence,
                metadata={"sma": sma, "upper": upper, "lower": lower, "atr": atr},
            ))

        # Exit long when price reaches middle band
        if current_price >= sma and has_long:
            return self._record_signal(Signal(
                timestamp=timestamp, symbol=context.symbol,
                type=SignalType.SELL, price=current_price,
                confidence=0.8,
                metadata={"sma": sma, "reason": "middle_band_reached"},
            ))

        return None
