"""
菲阿里四价策略 (Four-Price Breakout)
========================================
Based on yesterday's four key prices: High, Low, Open, Close.
Long when price breaks above yesterday's High, short when below yesterday's Low.
Reverse at yesterday's Open and Close for mean reversion.

Logic:
- Long entry: current price > max(prev_high, prev_close)
- Short entry: current price < min(prev_low, prev_open)
- Exit long: current price < min(prev_open, prev_close)
- Exit short: current price > max(prev_open, prev_close)
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


class FeiAliStrategy(BaseStrategy):
    """
    菲阿里四价 breakout strategy.

    Parameters:
        atr_mult_sl (float): ATR multiplier for stop loss (default 1.5)
        atr_mult_tp (float): ATR multiplier for take profit (default 3.0)
    """

    def __init__(self, params: Optional[dict] = None):
        super().__init__(params)
        self.atr_mult_sl = self.params.get("atr_mult_sl", 1.5)
        self.atr_mult_tp = self.params.get("atr_mult_tp", 3.0)

    def on_bar(self, bar: pd.Series, context: StrategyContext) -> Optional[Signal]:
        history = context.history
        if history.empty or len(history) < 3:
            return None

        prev = history.iloc[-2]
        prev_high = prev["high"]
        prev_low = prev["low"]
        prev_open = prev["open"]
        prev_close = prev["close"]

        # Calculate ATR for volatility-based stops
        high_low = history["high"].values - history["low"].values
        atr = np.mean(high_low[-14:]) if len(high_low) >= 14 else np.mean(high_low)

        current_price = bar["close"]
        timestamp = bar["timestamp"] if "timestamp" in bar else pd.Timestamp.now()
        positions = context.positions
        has_long = any(p.get("quantity", 0) > 0 for p in positions.values())

        # Entry conditions
        buy_trigger = max(prev_high, prev_close)
        sell_trigger = min(prev_low, prev_open)

        # Long: break above max(prev_high, prev_close)
        if current_price > buy_trigger and not has_long:
            return self._record_signal(Signal(
                timestamp=timestamp, symbol=context.symbol,
                type=SignalType.BUY, price=current_price,
                stop_loss=current_price - self.atr_mult_sl * atr,
                take_profit=current_price + self.atr_mult_tp * atr,
                confidence=min((current_price - buy_trigger) / buy_trigger * 50, 0.9),
                metadata={"buy_trigger": buy_trigger, "atr": atr},
            ))

        # Exit long below min(prev_open, prev_close)
        exit_long = min(prev_open, prev_close)
        if current_price < exit_long and has_long:
            return self._record_signal(Signal(
                timestamp=timestamp, symbol=context.symbol,
                type=SignalType.SELL, price=current_price,
                confidence=0.8,
                metadata={"exit_long": exit_long, "reason": "below_exit"},
            ))

        return None
