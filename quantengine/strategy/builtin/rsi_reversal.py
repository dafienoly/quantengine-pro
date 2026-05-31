"""
RSI Reversal Strategy (RSI反转策略)
=========================================
Standalone RSI-based mean reversion strategy.
Buys when RSI is oversold (< threshold), sells when overbought (> threshold).

Logic:
- RSI = 100 - (100 / (1 + RS)) where RS = avg_gain / avg_loss over N periods
- Long entry: RSI < oversold_threshold (default 30)
- Long exit: RSI > neutral_threshold (default 50)
- Short entry: RSI > overbought_threshold (default 70)
- Short exit: RSI < neutral_threshold (default 50)
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


class RSIReversalStrategy(BaseStrategy):
    """
    RSI mean reversion strategy.

    Parameters:
        rsi_period (int): RSI lookback period (default 14)
        oversold (int): Oversold threshold (default 30)
        overbought (int): Overbought threshold (default 70)
        neutral (int): Exit threshold for reversal (default 50)
        atr_mult_sl (float): ATR multiplier for stop loss (default 1.5)
    """

    def __init__(self, params: Optional[dict] = None):
        super().__init__(params)
        self.rsi_period = self.params.get("rsi_period", 14)
        self.oversold = self.params.get("oversold", 30)
        self.overbought = self.params.get("overbought", 70)
        self.neutral = self.params.get("neutral", 50)
        self.atr_mult_sl = self.params.get("atr_mult_sl", 1.5)

    def _calc_rsi(self, close: np.ndarray, period: int) -> float:
        deltas = np.diff(close)
        gains = np.maximum(deltas, 0)
        losses = np.maximum(-deltas, 0)
        avg_gain = np.mean(gains[-period:]) if len(gains) >= period else np.mean(gains)
        avg_loss = np.mean(losses[-period:]) if len(losses) >= period else np.mean(losses)
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def _calc_atr(self, history: pd.DataFrame, period: int = 14) -> float:
        high_low = history["high"].values - history["low"].values
        return float(np.mean(high_low[-period:])) if len(high_low) >= period else float(np.mean(high_low))

    def on_bar(self, bar: pd.Series, context: StrategyContext) -> Optional[Signal]:
        history = context.history
        if history.empty or len(history) < self.rsi_period + 2:
            return None

        close = history["close"].values
        rsi = self._calc_rsi(close, self.rsi_period)
        atr = self._calc_atr(history)

        current_price = bar["close"]
        timestamp = bar["timestamp"] if "timestamp" in bar else pd.Timestamp.now()
        positions = context.positions
        has_long = any(p.get("quantity", 0) > 0 for p in positions.values())

        # Long: RSI oversold
        if rsi < self.oversold and not has_long:
            return self._record_signal(Signal(
                timestamp=timestamp, symbol=context.symbol,
                type=SignalType.BUY, price=current_price,
                stop_loss=current_price - self.atr_mult_sl * atr,
                take_profit=current_price + 3 * self.atr_mult_sl * atr,
                confidence=max(0, min((self.oversold - rsi) / self.oversold, 0.9)),
                metadata={"rsi": rsi, "atr": atr},
            ))

        # Exit long: RSI back to neutral
        if rsi >= self.neutral and has_long:
            return self._record_signal(Signal(
                timestamp=timestamp, symbol=context.symbol,
                type=SignalType.SELL, price=current_price,
                confidence=0.8,
                metadata={"rsi": rsi, "reason": "rsi_neutral"},
            ))

        return None
