"""
Dual Moving Average + Grid Strategy
=====================================
Combines golden/death cross signals with grid trading for range-bound markets.

Logic:
- Fast MA crosses above Slow MA → Long (golden cross)
- Fast MA crosses below Slow MA → Exit (death cross)
- During ranging periods, places grid orders around current price
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


class DualMAStrategy(BaseStrategy):
    """
    Dual Moving Average crossover strategy with grid overlay.

    Parameters:
        fast_period (int): Fast MA period (default 20)
        slow_period (int): Slow MA period (default 60)
        grid_spacing (float): Grid level spacing as fraction (default 0.02 = 2%)
        grid_levels (int): Number of grid levels each side (default 5)
    """

    def __init__(self, params: Optional[dict] = None):
        super().__init__(params)
        self.fast_period = self.params.get("fast_period", 20)
        self.slow_period = self.params.get("slow_period", 60)
        self.grid_spacing = self.params.get("grid_spacing", 0.02)
        self.grid_levels = self.params.get("grid_levels", 5)

    def on_bar(self, bar: pd.Series, context: StrategyContext) -> Optional[Signal]:
        """Generate signals based on MA crossover and grid logic."""
        history = context.history
        min_bars = self.slow_period + 2
        if history.empty or len(history) < min_bars:
            return None

        close_vals = history["close"].values
        current_price = bar["close"]
        timestamp = bar["timestamp"] if "timestamp" in bar else pd.Timestamp.now()

        # Calculate MAs
        fast_ma = np.mean(close_vals[-self.fast_period:])
        slow_ma = np.mean(close_vals[-self.slow_period:])
        prev_fast_ma = np.mean(close_vals[-(self.fast_period+1):-1])
        prev_slow_ma = np.mean(close_vals[-(self.slow_period+1):-1])

        # Crossover detection
        golden_cross = prev_fast_ma <= prev_slow_ma and fast_ma > slow_ma
        death_cross = prev_fast_ma >= prev_slow_ma and fast_ma < slow_ma

        # Trend strength (MA separation)
        trend_strength = abs(fast_ma - slow_ma) / slow_ma

        has_long = any(
            p.get("quantity", 0) > 0 for p in context.positions.values()
        )

        # Golden cross: Buy
        if golden_cross and not has_long:
            return self._record_signal(Signal(
                timestamp=timestamp,
                symbol=context.symbol,
                type=SignalType.BUY,
                price=current_price,
                stop_loss=current_price * (1 - self.grid_spacing * self.grid_levels),
                take_profit=current_price * (1 + self.grid_spacing * self.grid_levels),
                confidence=min(trend_strength * 20, 0.9),
                metadata={
                    "fast_ma": fast_ma, "slow_ma": slow_ma,
                    "trend_strength": trend_strength, "signal": "golden_cross",
                },
            ))

        # Death cross: Sell
        if death_cross and has_long:
            return self._record_signal(Signal(
                timestamp=timestamp,
                symbol=context.symbol,
                type=SignalType.SELL,
                price=current_price,
                confidence=min(trend_strength * 20, 0.9),
                metadata={
                    "fast_ma": fast_ma, "slow_ma": slow_ma,
                    "signal": "death_cross",
                },
            ))

        # Grid trading: no strong trend → place grid levels
        if not golden_cross and not death_cross and trend_strength < 0.01:
            # Check if price is at a grid level
            base_price = slow_ma
            for level in range(1, self.grid_levels + 1):
                buy_level = base_price * (1 - self.grid_spacing * level)
                sell_level = base_price * (1 + self.grid_spacing * level)

                # Buy at grid support
                if current_price <= buy_level * 1.002 and not has_long:
                    return self._record_signal(Signal(
                        timestamp=timestamp,
                        symbol=context.symbol,
                        type=SignalType.BUY,
                        price=current_price,
                        stop_loss=buy_level * 0.99,
                        take_profit=base_price * (1 + self.grid_spacing * (level - 0.5)),
                        confidence=0.6,
                        metadata={"mode": "grid_buy", "level": level},
                    ))

        return None
