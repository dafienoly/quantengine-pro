"""
R Breaker Strategy
===================
Classic intraday breakout strategy based on yesterday's price levels.

Logic:
- Calculate 6 key levels from yesterday's high/low/close
- BBreak (long entry) and SSetup (short entry) for trend
- BEnter (long reversal) and SEnter (short reversal) for reversal
- Uses f1/f2/f3 parameters to adjust levels
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


class RBreakerStrategy(BaseStrategy):
    """
    R Breaker intraday strategy.

    Parameters:
        f1 (float): Range multiplier for breakout levels (default 0.35)
        f2 (float): Range multiplier for reversal levels (default 0.07)
        f3 (float): Range multiplier for reference (default 0.25)
    """

    def __init__(self, params: Optional[dict] = None):
        super().__init__(params)
        self.f1 = self.params.get("f1", 0.35)
        self.f2 = self.params.get("f2", 0.07)
        self.f3 = self.params.get("f3", 0.25)

        # Store yesterday's levels
        self._yesterday_levels = None

    def on_bar(self, bar: pd.Series, context: StrategyContext) -> Optional[Signal]:
        """Generate signals based on R Breaker logic."""
        history = context.history
        if history.empty or len(history) < 2:
            return None

        # Calculate yesterday's levels (once per day)
        prev_bar = history.iloc[-2]
        prev_high = prev_bar["high"]
        prev_low = prev_bar["low"]
        prev_close = prev_bar["close"]

        # 6 Key Levels
        pivot = (prev_high + prev_close + prev_low) / 3
        b_break = prev_high + self.f1 * (prev_close - prev_low)  # Long entry (breakout)
        s_setup = prev_low - self.f1 * (prev_high - prev_close)  # Short entry (breakout)
        b_enter = pivot + self.f2 * (prev_high - prev_low)       # Long entry (reversal)
        s_enter = pivot - self.f2 * (prev_high - prev_low)       # Short entry (reversal)

        current_price = bar["close"]
        timestamp = bar["timestamp"] if "timestamp" in bar else pd.Timestamp.now()

        # Position check
        has_long = any(
            p.get("quantity", 0) > 0 for p in context.positions.values()
        )

        # Trend-following long: price breaks above BBreak
        if current_price > b_break and not has_long:
            return self._record_signal(Signal(
                timestamp=timestamp,
                symbol=context.symbol,
                type=SignalType.BUY,
                price=current_price,
                stop_loss=b_enter,
                take_profit=current_price + (b_break - pivot),
                confidence=0.8,
                metadata={
                    "pivot": pivot, "b_break": b_break, "b_enter": b_enter,
                    "s_setup": s_setup, "s_enter": s_enter, "mode": "breakout",
                },
            ))

        # Reversal long: price drops below SSetup then rebounds above BEnter
        prev_low_price = history["low"].iloc[-1]
        if prev_low_price < s_setup and current_price > b_enter and not has_long:
            return self._record_signal(Signal(
                timestamp=timestamp,
                symbol=context.symbol,
                type=SignalType.BUY,
                price=current_price,
                stop_loss=s_enter,
                take_profit=pivot,
                confidence=0.7,
                metadata={
                    "pivot": pivot, "s_setup": s_setup, "b_enter": b_enter,
                    "mode": "reversal",
                },
            ))

        # Exit long
        if has_long and (current_price < s_enter or current_price < pivot):
            return self._record_signal(Signal(
                timestamp=timestamp,
                symbol=context.symbol,
                type=SignalType.SELL,
                price=current_price,
                confidence=0.7,
                metadata={"reason": "r_breaker_exit"},
            ))

        return None
