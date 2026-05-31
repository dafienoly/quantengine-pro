"""
Pivot Point Strategy (枢轴点支撑阻力系统)
============================================
Classic floor-trader pivot point system using previous day's
High, Low, and Close to calculate support/resistance levels.

Logic:
- Pivot Point (PP) = (High + Low + Close) / 3
- R1 = 2 × PP - Low, R2 = PP + (High - Low), R3 = High + 2 × (PP - Low)
- S1 = 2 × PP - High, S2 = PP - (High - Low), S3 = Low - 2 × (High - PP)
- Buy at S1/S2 with stop below, Sell at R1/R2 with stop above
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


class PivotPointStrategy(BaseStrategy):
    """
    Pivot Point support/resistance strategy.

    Parameters:
        sensitivity (str): Level aggressiveness 'conservative' | 'moderate' | 'aggressive' (default 'moderate')
        use_close (bool): Use close price for pivot calculation (default True, else use (H+L+C)/3)
    """

    def __init__(self, params: Optional[dict] = None):
        super().__init__(params)
        self.sensitivity = self.params.get("sensitivity", "moderate")
        self.use_close = self.params.get("use_close", True)

    def on_bar(self, bar: pd.Series, context: StrategyContext) -> Optional[Signal]:
        history = context.history
        if history.empty or len(history) < 2:
            return None

        # Get previous day's data
        prev = history.iloc[-2]
        prev_high = prev["high"]
        prev_low = prev["low"]
        if self.use_close:
            prev_close = prev["close"]
        else:
            prev_close = (prev["high"] + prev["low"] + prev["close"]) / 3

        # Calculate pivot levels
        pp = (prev_high + prev_low + prev_close) / 3
        r1 = 2 * pp - prev_low
        s1 = 2 * pp - prev_high
        r2 = pp + (prev_high - prev_low)
        s2 = pp - (prev_high - prev_low)
        r3 = prev_high + 2 * (pp - prev_low)
        s3 = prev_low - 2 * (prev_high - pp)

        current_price = bar["close"]
        timestamp = bar["timestamp"] if "timestamp" in bar else pd.Timestamp.now()
        positions = context.positions
        has_long = any(p.get("quantity", 0) > 0 for p in positions.values())

        # Select entry level based on sensitivity
        if self.sensitivity == "conservative":
            buy_level, sell_level = s2, r2
            sl_offset = (pp - s2) * 0.5
        elif self.sensitivity == "aggressive":
            buy_level, sell_level = s1, r1
            sl_offset = (pp - s1) * 0.3
        else:  # moderate
            buy_level, sell_level = (s1 + s2) / 2, (r1 + r2) / 2
            sl_offset = (pp - s1) * 0.4

        # Long: price near support
        if current_price <= buy_level * 1.01 and not has_long:
            stop_loss = buy_level - sl_offset
            take_profit = pp
            confidence = min(abs(buy_level - current_price) / current_price * 100, 0.85)
            return self._record_signal(Signal(
                timestamp=timestamp, symbol=context.symbol,
                type=SignalType.BUY, price=current_price,
                stop_loss=stop_loss, take_profit=take_profit,
                confidence=confidence,
                metadata={"pp": pp, "r1": r1, "s1": s1, "level": "support"},
            ))

        # Exit long at pivot or resistance
        if current_price >= pp and has_long:
            return self._record_signal(Signal(
                timestamp=timestamp, symbol=context.symbol,
                type=SignalType.SELL, price=current_price,
                confidence=0.7,
                metadata={"pp": pp, "reason": "pivot_reached"},
            ))

        return None
