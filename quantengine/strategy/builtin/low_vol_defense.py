"""
Low Volatility Defense Strategy (低波防御策略)
===============================================
Defensive strategy that shifts capital to low-volatility assets
during market turbulence.

Logic:
- Monitor market-wide volatility (VIX-like metric from returns dispersion)
- When vol spikes above threshold: reduce position size / go to cash
- When vol normalizes: rotate into low-volatility assets
- Uses volatility-weighted position sizing: lower vol = larger position

This strategy aims to preserve capital during high-volatility regimes
while capturing returns during calm markets.
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


class LowVolDefenseStrategy(BaseStrategy):
    """
    低波防御策略 - Reduces exposure during high volatility, rotates to low-vol assets.

    Parameters:
        vol_lookback (int): Period for volatility calculation (default 20)
        vol_percentile_threshold (float): Vol above this percentile triggers defense (default 0.8)
        defense_position_pct (float): Reduce position to this % during defense (default 0.25)
        low_vol_rank_period (int): Ranking period for low-vol selection (default 60)
        rebalance_freq (int): Bars between rebalancing (default 20)
        min_position_pct (float): Minimum position size (default 0.10)
        max_position_pct (float): Maximum position size in normal mode (default 0.50)
    """

    def __init__(self, params: Optional[dict] = None):
        super().__init__(params)
        self.vol_lookback = self.params.get("vol_lookback", 20)
        self.vol_percentile_threshold = self.params.get("vol_percentile_threshold", 0.80)
        self.defense_position_pct = self.params.get("defense_position_pct", 0.25)
        self.low_vol_rank_period = self.params.get("low_vol_rank_period", 60)
        self.rebalance_freq = self.params.get("rebalance_freq", 20)
        self.min_position_pct = self.params.get("min_position_pct", 0.10)
        self.max_position_pct = self.params.get("max_position_pct", 0.50)

        # State tracking
        self._vol_history = []
        self._bars_since_rebalance = 0
        self._defense_mode = False
        self._vol_percentile_80 = None  # Calibrated threshold

    def on_bar(self, bar: pd.Series, context: StrategyContext) -> Optional[Signal]:
        """
        Monitor volatility and adjust position sizing defensively.

        Mode switching:
            NORMAL (low vol) → DEFENSE (high vol): reduce positions
            DEFENSE → NORMAL: restore positions, prefer low-vol assets
        """
        history = context.history
        if history.empty or len(history) < max(self.vol_lookback, self.low_vol_rank_period):
            return None

        close_vals = history["close"].values
        current_price = bar["close"]
        timestamp = bar["timestamp"] if "timestamp" in bar else pd.Timestamp.now()

        # ---- 1. Calculate current volatility ----
        returns = np.diff(close_vals[-self.vol_lookback:]) / close_vals[-(self.vol_lookback+1):-1]
        current_vol = np.std(returns) * np.sqrt(252)  # Annualized

        # Maintain rolling volatility history for percentile calculation
        self._vol_history.append(current_vol)
        if len(self._vol_history) > self.low_vol_rank_period:
            self._vol_history = self._vol_history[-self.low_vol_rank_period:]

        # Calibrate high-vol threshold (80th percentile of historical vol)
        if len(self._vol_history) >= self.low_vol_rank_period:
            self._vol_percentile_80 = np.percentile(
                self._vol_history, self.vol_percentile_threshold * 100
            )

        # ---- 2. Determine market regime ----
        is_high_vol = (
            self._vol_percentile_80 is not None
            and current_vol > self._vol_percentile_80
        )

        # ---- 3. Calculate long-term volatility for asset ranking ----
        long_term_returns = (
            np.diff(close_vals[-self.low_vol_rank_period:])
            / close_vals[-(self.low_vol_rank_period+1):-1]
        )
        long_term_vol = np.std(long_term_returns)
        trend = (close_vals[-1] - close_vals[-self.low_vol_rank_period]) / close_vals[-self.low_vol_rank_period]

        # Low vol score: inverse volatility + trend alignment
        vol_score = 1.0 / (long_term_vol * 100 + 0.01)  # Avoid div by zero
        vol_score = min(vol_score, 2.0)  # Cap

        # Position check
        has_position = any(
            p.get("quantity", 0) > 0 for p in context.positions.values()
        )

        # ---- 4. Rebalance logic ----
        self._bars_since_rebalance += 1

        if self._bars_since_rebalance < self.rebalance_freq:
            return None

        self._bars_since_rebalance = 0

        # ---- 5. Generate signals based on regime ----
        if is_high_vol and not self._defense_mode:
            # Enter defense mode
            self._defense_mode = True

            if has_position:
                # Reduce position: sell part of holdings
                return self._record_signal(Signal(
                    timestamp=timestamp,
                    symbol=context.symbol,
                    type=SignalType.SELL,
                    price=current_price,
                    quantity=0.5,  # Reduce by 50%
                    confidence=0.8,
                    metadata={
                        "regime": "defense",
                        "current_vol": round(current_vol * 100, 1),
                        "threshold": round(self._vol_percentile_80 * 100, 1) if self._vol_percentile_80 else "N/A",
                        "reason": "high_volatility_defense",
                    },
                ))
            # else: already in cash, stay defensive

        elif not is_high_vol and self._defense_mode:
            # Exit defense mode
            self._defense_mode = False

            # Only re-enter if volatility score is favorable
            if vol_score > 0.5 and not has_position:
                position_pct = min(
                    self.min_position_pct + vol_score * 0.3,
                    self.max_position_pct,
                )
                quantity = (context.portfolio_value * position_pct) / current_price

                return self._record_signal(Signal(
                    timestamp=timestamp,
                    symbol=context.symbol,
                    type=SignalType.BUY,
                    price=current_price,
                    quantity=quantity,
                    stop_loss=current_price * (1 - long_term_vol * 2),
                    take_profit=current_price * (1 + long_term_vol * 3),
                    confidence=min(0.6 + vol_score * 0.3, 0.9),
                    metadata={
                        "regime": "normal",
                        "vol_score": round(vol_score, 3),
                        "position_pct": round(position_pct * 100, 1),
                        "current_vol": round(current_vol * 100, 1),
                    },
                ))

        elif not is_high_vol and not self._defense_mode:
            # Normal mode: maintain or enter low-vol position
            if not has_position and vol_score > 0.7:
                position_pct = min(self.max_position_pct * vol_score, self.max_position_pct)
                quantity = (context.portfolio_value * position_pct) / current_price

                return self._record_signal(Signal(
                    timestamp=timestamp,
                    symbol=context.symbol,
                    type=SignalType.BUY,
                    price=current_price,
                    quantity=quantity,
                    stop_loss=current_price * (1 - long_term_vol * 2),
                    take_profit=current_price * (1 + long_term_vol * 3),
                    confidence=min(0.5 + vol_score * 0.3, 0.85),
                    metadata={
                        "regime": "normal",
                        "vol_score": round(vol_score, 3),
                        "position_pct": round(position_pct * 100, 1),
                    },
                ))

        return None

    @property
    def is_defense_mode(self) -> bool:
        """Check if strategy is currently in defensive mode."""
        return self._defense_mode
