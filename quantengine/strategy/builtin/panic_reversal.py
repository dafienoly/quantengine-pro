"""
Panic Reversal Strategy (恐慌反转策略)
=========================================
Detects panic selling events and trades the subsequent reversal.

Logic:
- Monitor for large price drops (>threshold%) with volume surge
- Wait for stabilization (reduced volatility + price consolidation)
- Enter long when price shows reversal signal (higher low, RSI recovery)
- Exit on target recovery % or trailing stop

This strategy capitalizes on the behavioral finance principle that
markets tend to overreact to bad news, creating mean-reversion opportunities.
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


class PanicReversalStrategy(BaseStrategy):
    """
    恐慌反转策略 - Trades reversals after panic selling events.

    Parameters:
        panic_threshold (float): Minimum drop % to trigger panic watch (default -5%)
        volume_multiplier (float): Volume must exceed N× average (default 2.0)
        stabilization_bars (int): Bars to wait for stabilization (default 5)
        rsi_recovery_threshold (int): RSI must recover above this to enter (default 40)
        target_recovery_pct (float): Take profit at this recovery % (default 3%)
        stop_loss_pct (float): Stop loss below entry (default 2%)
        lookback_bars (int): Bars to calculate averages (default 50)
    """

    def __init__(self, params: Optional[dict] = None):
        super().__init__(params)
        self.panic_threshold = self.params.get("panic_threshold", -0.05)  # -5%
        self.volume_multiplier = self.params.get("volume_multiplier", 2.0)
        self.stabilization_bars = self.params.get("stabilization_bars", 5)
        self.rsi_recovery_threshold = self.params.get("rsi_recovery_threshold", 40)
        self.target_recovery_pct = self.params.get("target_recovery_pct", 0.03)  # 3%
        self.stop_loss_pct = self.params.get("stop_loss_pct", 0.02)  # 2%
        self.lookback_bars = self.params.get("lookback_bars", 50)

        # State machine for panic detection
        self._panic_detected = False
        self._panic_low_price = None
        self._panic_bar_index = -1
        self._bars_since_panic = 0

    def on_bar(self, bar: pd.Series, context: StrategyContext) -> Optional[Signal]:
        """
        Detect panic and generate reversal signals.

        State flow:
            NORMAL → (big drop + vol surge) → PANIC_DETECTED
            PANIC_DETECTED → (stabilization) → WAITING_REVERSAL
            WAITING_REVERSAL → (RSI recovery + higher low) → BUY
        """
        history = context.history
        if history.empty or len(history) < self.lookback_bars:
            return None

        close_vals = history["close"].values
        high_vals = history["high"].values if "high" in history.columns else close_vals
        low_vals = history["low"].values if "low" in history.columns else close_vals
        vol_vals = history["volume"].values if "volume" in history.columns else np.ones_like(close_vals)

        current_price = bar["close"]
        current_vol = bar.get("volume", 0)
        timestamp = bar["timestamp"] if "timestamp" in bar else pd.Timestamp.now()

        # Check existing positions
        has_long = any(
            p.get("quantity", 0) > 0 for p in context.positions.values()
        )

        # ---- Already in position: manage exit ----
        if has_long:
            for sym, pos in context.positions.items():
                if pos.get("quantity", 0) > 0:
                    avg_price = pos.get("avg_price", current_price)
                    pnl_pct = (current_price - avg_price) / avg_price

                    # Take profit
                    if pnl_pct >= self.target_recovery_pct:
                        return self._record_signal(Signal(
                            timestamp=timestamp,
                            symbol=context.symbol,
                            type=SignalType.SELL,
                            price=current_price,
                            confidence=0.9,
                            metadata={"reason": "target_reached", "pnl_pct": pnl_pct},
                        ))

                    # Update trailing stop (highest price since entry)
                    trail_stop = avg_price * (1 - self.stop_loss_pct)
                    if current_price < trail_stop:
                        return self._record_signal(Signal(
                            timestamp=timestamp,
                            symbol=context.symbol,
                            type=SignalType.SELL,
                            price=current_price,
                            confidence=0.95,
                            metadata={"reason": "stop_loss", "pnl_pct": pnl_pct},
                        ))

        # ---- Detect panic event ----
        if not self._panic_detected and not has_long:
            # Calculate metrics
            avg_vol = np.mean(vol_vals[-self.lookback_bars:])
            day_return = (close_vals[-1] - close_vals[-2]) / close_vals[-2]
            vol_ratio = current_vol / avg_vol if avg_vol > 0 else 1.0

            # Panic = large drop + volume surge
            if day_return <= self.panic_threshold and vol_ratio >= self.volume_multiplier:
                self._panic_detected = True
                self._panic_low_price = current_price
                self._panic_bar_index = len(close_vals)
                self._bars_since_panic = 0

        # ---- Wait for stabilization after panic ----
        if self._panic_detected and not has_long:
            self._bars_since_panic += 1

            # Track the lowest price during panic
            if current_price < self._panic_low_price:
                self._panic_low_price = current_price

            # Wait for stabilization period
            if self._bars_since_panic < self.stabilization_bars:
                return None

            # ---- Check reversal conditions ----
            # 1. Price is above panic low (higher low)
            recovery_from_low = (current_price - self._panic_low_price) / self._panic_low_price
            if recovery_from_low < 0.01:  # Need at least 1% above panic low
                return None

            # 2. RSI is recovering
            rsi = self._calc_rsi(close_vals, 14)

            if rsi >= self.rsi_recovery_threshold:
                # 3. Reduced volatility (stabilization)
                recent_returns = np.diff(close_vals[-self.stabilization_bars:]) / close_vals[-(self.stabilization_bars+1):-1]
                recent_vol = np.std(recent_returns)
                long_term_vol = np.std(
                    np.diff(close_vals[-self.lookback_bars:]) / close_vals[-(self.lookback_bars+1):-1]
                )

                if recent_vol < long_term_vol:  # Volatility contracting
                    # Reset state machine
                    self._panic_detected = False
                    self._panic_low_price = None

                    return self._record_signal(Signal(
                        timestamp=timestamp,
                        symbol=context.symbol,
                        type=SignalType.BUY,
                        price=current_price,
                        stop_loss=current_price * (1 - self.stop_loss_pct),
                        take_profit=current_price * (1 + self.target_recovery_pct),
                        confidence=0.7,
                        metadata={
                            "panic_drop_pct": round(day_return * 100, 1) if 'day_return' in dir() else "N/A",
                            "recovery_from_low_pct": round(recovery_from_low * 100, 1),
                            "rsi": round(rsi, 1),
                            "strategy": "panic_reversal",
                        },
                    ))

            # Timeout: if panic was too long ago without reversal, reset
            if self._bars_since_panic > self.lookback_bars:
                self._panic_detected = False
                self._panic_low_price = None

        return None

    @staticmethod
    def _calc_rsi(prices: np.ndarray, period: int = 14) -> float:
        """Calculate RSI."""
        if len(prices) < period + 1:
            return 50.0
        deltas = np.diff(prices[-period-1:])
        gains = np.maximum(deltas, 0)
        losses = np.abs(np.minimum(deltas, 0))
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        if avg_loss == 0:
            return 100.0
        return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
