"""
Turtle Trading Strategy
========================
Classic trend-following strategy based on Richard Dennis's Turtle system.

Logic:
- Entry: Price breaks above/below Donchian channel (N-day high/low)
- Exit: Price crosses opposite Donchian channel (shorter period)
- Stop: ATR-based trailing stop
- Position sizing: Risk-based using ATR (1% risk per trade + 2×ATR stop)
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


class TurtleStrategy(BaseStrategy):
    """
    Turtle Trading strategy implementation.

    Parameters:
        entry_period (int): Donchian channel period for entry (default 20)
        exit_period (int): Donchian channel period for exit (default 10)
        atr_period (int): ATR calculation period (default 20)
        atr_multiplier (float): Stop distance in ATR multiples (default 2.0)
        risk_per_trade (float): Fraction of portfolio at risk (default 0.02)
    """

    def __init__(self, params: Optional[dict] = None):
        super().__init__(params)
        self.entry_period = self.params.get("entry_period", 20)
        self.exit_period = self.params.get("exit_period", 10)
        self.atr_period = self.params.get("atr_period", 20)
        self.atr_multiplier = self.params.get("atr_multiplier", 2.0)
        self.risk_per_trade = self.params.get("risk_per_trade", 0.02)

    def on_bar(self, bar: pd.Series, context: StrategyContext) -> Optional[Signal]:
        """Generate trading signals using Turtle rules."""
        history = context.history
        min_bars = max(self.entry_period, self.atr_period) + 1
        if history.empty or len(history) < min_bars:
            return None

        close = history["close"].values
        high = history["high"].values
        low = history["low"].values

        current_price = bar["close"]
        timestamp = bar["timestamp"] if "timestamp" in bar else pd.Timestamp.now()

        # Donchian channels
        entry_high = np.max(high[-self.entry_period:])
        entry_low = np.min(low[-self.entry_period:])
        exit_high = np.max(high[-self.exit_period:])
        exit_low = np.min(low[-self.exit_period:])

        # ATR (Average True Range)
        atr = self._calc_atr(high, low, close, self.atr_period)

        # Position check
        has_long = any(
            p.get("quantity", 0) > 0 for p in context.positions.values()
        )

        # Entry: Break above entry_high with no existing position
        if current_price > entry_high and not has_long:
            stop_price = current_price - self.atr_multiplier * atr
            return self._record_signal(Signal(
                timestamp=timestamp,
                symbol=context.symbol,
                type=SignalType.BUY,
                price=current_price,
                stop_loss=stop_price,
                take_profit=current_price + self.atr_multiplier * 3 * atr,
                confidence=0.8,
                metadata={
                    "entry_high": entry_high,
                    "atr": atr,
                    "strategy": "turtle",
                },
            ))

        # Exit: Cross below exit_low
        if current_price < exit_low and has_long:
            return self._record_signal(Signal(
                timestamp=timestamp,
                symbol=context.symbol,
                type=SignalType.SELL,
                price=current_price,
                confidence=0.9,
                metadata={"exit_low": exit_low, "strategy": "turtle"},
            ))

        # Trailing stop check (for existing positions)
        if has_long:
            for sym, pos in context.positions.items():
                pos_qty = pos.get("quantity", 0)
                avg_price = pos.get("avg_price", 0)
                if pos_qty > 0:
                    # ATR trailing stop
                    trail_stop = current_price - self.atr_multiplier * atr
                    if current_price < trail_stop:
                        return self._record_signal(Signal(
                            timestamp=timestamp,
                            symbol=context.symbol,
                            type=SignalType.SELL,
                            price=current_price,
                            confidence=0.85,
                            metadata={"trail_stop": trail_stop, "reason": "trailing_stop"},
                        ))

        return None

    @staticmethod
    def _calc_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> float:
        """Calculate Average True Range."""
        if len(close) < 2:
            return 0.0

        prev_close = np.roll(close, 1)
        prev_close[0] = close[0]

        tr = np.maximum(
            high - low,
            np.maximum(
                np.abs(high - prev_close),
                np.abs(low - prev_close),
            ),
        )
        return float(np.mean(tr[-period:]))
