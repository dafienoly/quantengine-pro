"""
Dynamic Breakout II Strategy (动态突破II)
============================================
Evolution of classic breakout with volatility-adjusted lookback.
Uses ATR to dynamically adjust the N-day range calculation period.
When volatility rises, the lookback shortens to react faster.

Logic:
- Base period = parameter N (default 20)
- Volatility ratio = ATR(current) / ATR(N-day median)
- Dynamic period = max(min_period, min(max_period, base_period / vol_ratio))
- Uses Dual Thrust style range with dynamic lookback
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


class DynamicBreakoutIIStrategy(BaseStrategy):
    """
    Dynamic Breakout II with volatility-adjusted period.

    Parameters:
        base_period (int): Base lookback period (default 20)
        min_period (int): Minimum lookback when volatile (default 10)
        max_period (int): Maximum lookback when calm (default 40)
        k1 (float): Upper breakout multiplier (default 0.5)
        k2 (float): Lower breakout multiplier (default 0.5)
        atr_period (int): ATR calculation period (default 14)
    """

    def __init__(self, params: Optional[dict] = None):
        super().__init__(params)
        self.base_period = self.params.get("base_period", 20)
        self.min_period = self.params.get("min_period", 10)
        self.max_period = self.params.get("max_period", 40)
        self.k1 = self.params.get("k1", 0.5)
        self.k2 = self.params.get("k2", 0.5)
        self.atr_period = self.params.get("atr_period", 14)

    def _calc_atr(self, history: pd.DataFrame, period: int) -> float:
        high_low = history["high"].values - history["low"].values
        return float(np.mean(high_low[-period:])) if len(high_low) >= period else float(np.mean(high_low))

    def on_bar(self, bar: pd.Series, context: StrategyContext) -> Optional[Signal]:
        history = context.history
        if history.empty or len(history) < self.max_period:
            return None

        # Calculate ATR and dynamic period
        atr_current = self._calc_atr(history, self.atr_period)
        atr_median = self._calc_atr(history, min(len(history), self.base_period))

        vol_ratio = atr_current / atr_median if atr_median > 0 else 1.0
        dynamic_period = int(np.clip(
            self.base_period / max(vol_ratio, 0.3),
            self.min_period, self.max_period,
        ))

        close = history["close"].values
        high = history["high"].values
        low = history["low"].values

        # Calculate dynamic range
        hh = np.max(close[-dynamic_period:])
        ll = np.min(close[-dynamic_period:])
        hc = np.max(high[-dynamic_period:])
        lc = np.min(low[-dynamic_period:])
        rng = max(hh - lc, hc - ll)

        open_price = bar["open"] if "open" in bar else bar["close"]
        buy_line = open_price + self.k1 * rng
        sell_line = open_price - self.k2 * rng

        current_price = bar["close"]
        timestamp = bar["timestamp"] if "timestamp" in bar else pd.Timestamp.now()
        positions = context.positions
        has_long = any(p.get("quantity", 0) > 0 for p in positions.values())

        if current_price > buy_line and not has_long:
            return self._record_signal(Signal(
                timestamp=timestamp, symbol=context.symbol,
                type=SignalType.BUY, price=current_price,
                stop_loss=current_price - 2 * atr_current,
                take_profit=current_price + 3 * atr_current,
                confidence=min(abs(current_price - buy_line) / buy_line * 10, 0.95),
                metadata={"dynamic_period": dynamic_period, "vol_ratio": vol_ratio, "atr": atr_current},
            ))

        if current_price < sell_line and has_long:
            return self._record_signal(Signal(
                timestamp=timestamp, symbol=context.symbol,
                type=SignalType.SELL, price=current_price,
                confidence=0.8,
                metadata={"dynamic_period": dynamic_period, "reason": "sell_line_break"},
            ))

        return None
