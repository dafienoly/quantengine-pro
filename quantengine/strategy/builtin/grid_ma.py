"""
Grid + MA Composite Strategy
==============================
Combines a moving average trend filter with grid trading.

Logic:
- Use MA to determine trend direction (above MA = bullish bias)
- Place buy grid levels below current price, sell grid levels above
- Each grid level triggers at its price, with auto take-profit at next level
- Position sizing adjusts based on trend strength
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


class GridMAStrategy(BaseStrategy):
    """
    Grid trading strategy with moving average trend filter.

    Parameters:
        ma_period (int): Moving average period for trend filter (default 50)
        grid_levels (int): Number of grid levels (default 10)
        grid_spacing (float): Price spacing between levels as fraction (default 0.01)
        base_position_pct (float): Base position size as fraction of capital (default 0.5)
    """

    def __init__(self, params: Optional[dict] = None):
        super().__init__(params)
        self.ma_period = self.params.get("ma_period", 50)
        self.grid_levels = self.params.get("grid_levels", 10)
        self.grid_spacing = self.params.get("grid_spacing", 0.01)
        self.base_position_pct = self.params.get("base_position_pct", 0.5)

        # Track grid state
        self._grid_center = None
        self._filled_levels = set()

    def on_bar(self, bar: pd.Series, context: StrategyContext) -> Optional[Signal]:
        """Generate grid trading signals with MA filter."""
        history = context.history
        if history.empty or len(history) < self.ma_period + 1:
            return None

        close_vals = history["close"].values
        current_price = bar["close"]
        timestamp = bar["timestamp"] if "timestamp" in bar else pd.Timestamp.now()

        # MA trend filter
        ma = np.mean(close_vals[-self.ma_period:])
        trend_bias = "bullish" if current_price > ma else "bearish"
        trend_strength = abs(current_price - ma) / ma

        # Initialize grid center
        if self._grid_center is None:
            self._grid_center = ma

        # Shift grid center if price drifts too far (>5 grid levels away)
        if abs(current_price - self._grid_center) > self._grid_center * self.grid_spacing * 5:
            self._grid_center = ma
            self._filled_levels.clear()

        # Calculate grid levels
        pos_check = any(
            p.get("quantity", 0) > 0 for p in context.positions.values()
        )

        for level in range(1, self.grid_levels + 1):
            # Buy grid (below center)
            buy_price = self._grid_center * (1 - self.grid_spacing * level)
            # Sell grid (above center)
            sell_price = self._grid_center * (1 + self.grid_spacing * level)

            level_key_buy = f"buy_{level}"
            level_key_sell = f"sell_{level}"

            # Buy signal: price drops to buy level (only in bullish bias or neutral)
            if (current_price <= buy_price and not pos_check
                    and level_key_buy not in self._filled_levels
                    and trend_bias == "bullish"):
                self._filled_levels.add(level_key_buy)
                return self._record_signal(Signal(
                    timestamp=timestamp,
                    symbol=context.symbol,
                    type=SignalType.BUY,
                    price=current_price,
                    stop_loss=buy_price * 0.99,  # 1% below buy level
                    take_profit=self._grid_center,  # Target center
                    confidence=0.65 + 0.05 * trend_strength * 100,
                    metadata={
                        "mode": "grid_buy",
                        "grid_level": level,
                        "ma": ma,
                        "trend_bias": trend_bias,
                    },
                ))

            # Sell signal: price rises to sell level (exit existing long)
            if current_price >= sell_price and pos_check:
                return self._record_signal(Signal(
                    timestamp=timestamp,
                    symbol=context.symbol,
                    type=SignalType.SELL,
                    price=current_price,
                    confidence=0.7,
                    metadata={"mode": "grid_sell", "grid_level": level},
                ))

        return None
