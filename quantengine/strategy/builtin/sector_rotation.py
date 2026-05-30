"""
Sector Rotation Strategy
==========================
Invests in top-performing sector ETFs based on momentum.

Logic:
- Calculate N-day momentum for each sector/ETF
- Rank sectors by momentum
- Allocate capital to top K sectors
- Monthly rebalancing
"""

from typing import List, Optional

import numpy as np
import pandas as pd

from quantengine.strategy.base import (
    BaseStrategy,
    Signal,
    SignalType,
    StrategyContext,
)


class SectorRotationStrategy(BaseStrategy):
    """
    Sector/ETF rotation strategy based on momentum ranking.

    Parameters:
        momentum_period (int): Lookback period for momentum (default 60)
        top_sectors (int): Number of top sectors to hold (default 3)
        etf_only (bool): If True, only trade ETFs (default True)
        min_momentum (float): Minimum momentum threshold (default 0.0)
    """

    def __init__(self, params: Optional[dict] = None):
        super().__init__(params)
        self.momentum_period = self.params.get("momentum_period", 60)
        self.top_sectors = self.params.get("top_sectors", 3)
        self.etf_only = self.params.get("etf_only", True)
        self.min_momentum = self.params.get("min_momentum", 0.0)

        # Track sector momentum scores
        self._momentum_scores = {}
        self._current_holdings = set()

    def on_bar(self, bar: pd.Series, context: StrategyContext) -> Optional[Signal]:
        """
        Check momentum and generate rotation signals.

        On rebalance days: sell underperformers, buy top performers.
        """
        history = context.history
        if history.empty or len(history) < self.momentum_period + 1:
            return None

        timestamp = bar["timestamp"] if "timestamp" in bar else pd.Timestamp.now()
        current_price = bar["close"]
        close_vals = history["close"].values

        # Check rebalance day (monthly)
        if not self._is_month_end(timestamp):
            return None

        # Calculate momentum for this symbol
        momentum = (close_vals[-1] - close_vals[-(self.momentum_period+1)]) / close_vals[-(self.momentum_period+1)]
        self._momentum_scores[context.symbol] = momentum

        # Rank sectors
        ranked = sorted(
            self._momentum_scores.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        top_symbols = {
            sym for sym, score in ranked[:self.top_sectors]
            if score > self.min_momentum
        }

        has_position = any(
            p.get("quantity", 0) > 0 for p in context.positions.values()
        )

        # Buy if in top sectors and no position
        if context.symbol in top_symbols and not has_position:
            return self._record_signal(Signal(
                timestamp=timestamp,
                symbol=context.symbol,
                type=SignalType.BUY,
                price=current_price,
                confidence=min(abs(momentum) * 5, 0.85),
                metadata={
                    "momentum": momentum,
                    "rank": ranked.index((context.symbol, momentum)) + 1,
                    "top_symbols": list(top_symbols),
                },
            ))

        # Sell if not in top sectors and have position
        if context.symbol not in top_symbols and has_position:
            return self._record_signal(Signal(
                timestamp=timestamp,
                symbol=context.symbol,
                type=SignalType.SELL,
                price=current_price,
                confidence=0.8,
                metadata={"reason": "sector_rotation_exit"},
            ))

        return None

    @staticmethod
    def _is_month_end(timestamp: pd.Timestamp) -> bool:
        """Check if date is near month end (rebalance trigger)."""
        return timestamp.day >= 25
