"""
Dual Thrust Strategy
=====================
Classic breakout strategy using the previous N-day range.

Logic:
- Range = Max(HH - LC, HC - LL) where HH/LL are N-day highest/lowest close
- Buy line = Open + K1 × Range
- Sell line = Open - K2 × Range
- Long above Buy line, Short below Sell line
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


class DualThrustStrategy(BaseStrategy):
    """
    Dual Thrust breakout strategy.

    Parameters:
        k1 (float): Upper breakout multiplier (default 0.7)
        k2 (float): Lower breakout multiplier (default 0.7)
        period (int): Lookback period for range calculation (default 20)
    """

    def __init__(self, params: Optional[dict] = None):
        super().__init__(params)
        self.k1 = self.params.get("k1", 0.7)
        self.k2 = self.params.get("k2", 0.7)
        self.period = self.params.get("period", 20)

    def on_bar(self, bar: pd.Series, context: StrategyContext) -> Optional[Signal]:
        """Generate signals based on Dual Thrust breakout logic."""
        history = context.history
        if history.empty or len(history) < self.period + 1:
            return None

        close = history["close"].values
        high = history["high"].values
        low = history["low"].values

        # Calculate range
        hh = np.max(close[-self.period:])  # N-day highest close
        lc = np.min(close[-self.period:])  # N-day lowest close
        hc = np.max(close[-self.period:])  # Same as hh for close
        ll = np.min(close[-self.period:])  # Same as lc for close

        # Range = Max(HH - LC, HC - LL)
        rng = max(hh - lc, hc - ll)

        # Open price
        open_price = bar["open"] if "open" in bar else bar["close"]

        # Buy/Sell lines
        buy_line = open_price + self.k1 * rng
        sell_line = open_price - self.k2 * rng

        current_price = bar["close"]
        timestamp = bar["timestamp"] if "timestamp" in bar else pd.Timestamp.now()

        # Check existing positions
        positions = context.positions
        has_long = any(
            p.get("quantity", 0) > 0 for p in positions.values()
        )

        # Breakout signals
        if current_price > buy_line and not has_long:
            return self._record_signal(Signal(
                timestamp=timestamp,
                symbol=context.symbol,
                type=SignalType.BUY,
                price=current_price,
                stop_loss=sell_line,
                take_profit=current_price + 2 * rng,
                confidence=min(abs(current_price - buy_line) / buy_line * 10, 0.95),
                metadata={"buy_line": buy_line, "sell_line": sell_line, "range": rng},
            ))

        elif current_price < sell_line and has_long:
            return self._record_signal(Signal(
                timestamp=timestamp,
                symbol=context.symbol,
                type=SignalType.SELL,
                price=current_price,
                confidence=min(abs(sell_line - current_price) / sell_line * 10, 0.95),
                metadata={"buy_line": buy_line, "sell_line": sell_line},
            ))

        return None
