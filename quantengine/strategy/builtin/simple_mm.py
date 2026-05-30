"""
Simple Market Maker Strategy
==============================
Places bid/ask limit orders around mid-price to capture spread.

Logic:
- Calculate mid-price and spread
- Place buy limit at mid - spread/2, sell limit at mid + spread/2
- Cancel and replace orders every N seconds
- Max position limit to avoid inventory risk
"""

from typing import Optional

import pandas as pd

from quantengine.strategy.base import (
    BaseStrategy,
    Signal,
    SignalType,
    StrategyContext,
)


class SimpleMarketMaker(BaseStrategy):
    """
    Simple market making strategy.

    Places two-sided limit orders around the mid-price.

    Parameters:
        spread_pct (float): Half-spread as fraction (default 0.001 = 0.1%)
        order_size (float): Size per order (default 0.01)
        max_position (float): Maximum absolute position (default 1.0)
        cancel_replace_seconds (int): Order refresh interval (default 30)
    """

    def __init__(self, params: Optional[dict] = None):
        super().__init__(params)
        self.spread_pct = self.params.get("spread_pct", 0.001)
        self.order_size = self.params.get("order_size", 0.01)
        self.max_position = self.params.get("max_position", 1.0)
        self.cancel_replace_seconds = self.params.get("cancel_replace_seconds", 30)

    def on_tick(self, tick: pd.Series, context: StrategyContext) -> Optional[Signal]:
        """Generate market making signals on each tick."""
        mid_price = tick.get("close", 0)
        if mid_price <= 0:
            return None

        # Current net position
        net_position = sum(
            p.get("quantity", 0) for p in context.positions.values()
        )

        bid_price = mid_price * (1 - self.spread_pct / 2)
        ask_price = mid_price * (1 + self.spread_pct / 2)

        # Place bid if under position limit
        if net_position < self.max_position:
            return self._record_signal(Signal(
                timestamp=tick["timestamp"] if "timestamp" in tick else pd.Timestamp.now(),
                symbol=context.symbol,
                type=SignalType.BUY,
                price=bid_price,
                quantity=self.order_size,
                confidence=0.6,
                metadata={"mode": "market_make", "side": "bid"},
            ))

        # Place ask if have inventory to sell
        if net_position > -self.max_position:
            return self._record_signal(Signal(
                timestamp=tick["timestamp"] if "timestamp" in tick else pd.Timestamp.now(),
                symbol=context.symbol,
                type=SignalType.SELL,
                price=ask_price,
                quantity=self.order_size,
                confidence=0.6,
                metadata={"mode": "market_make", "side": "ask"},
            ))

        return None

    def on_bar(self, bar: pd.Series, context: StrategyContext) -> Optional[Signal]:
        """Bar-based fallback: use close price as mid."""
        return self.on_tick(bar, context)
