"""
QuantEngine Pro - Signal Advisor
==================================
Combines strategy signals, technical patterns, and LLM analysis
to generate actionable buy/sell recommendations.

Each recommendation includes:
- Symbol, direction, price, stop-loss, take-profit
- Confidence score from signal strength + LLM reinforcement
- Explanation of the reasoning behind the recommendation
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from loguru import logger


class RecType(str, Enum):
    """Recommendation type."""
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"


@dataclass
class TradeRecommendation:
    """A trading recommendation with full reasoning."""
    timestamp: datetime
    symbol: str
    type: RecType
    price: float
    stop_loss: float
    take_profit: float
    confidence: float  # 0.0 to 1.0
    source: str        # Which component generated this
    reasons: List[str] = field(default_factory=list)
    risk_level: str = "medium"
    metadata: Dict = field(default_factory=dict)


class SignalAdvisor:
    """
    Trading signal advisor combining multiple analysis sources.

    Integrates:
    1. Strategy signals (from backtest/live strategies)
    2. Technical pattern recognition
    3. LLM analysis and explanation

    Usage:
        advisor = SignalAdvisor(llm_service)
        rec = await advisor.evaluate(signal, market_data, news_context)
    """

    def __init__(self, llm_service=None):
        """
        Initialize signal advisor.

        Args:
            llm_service: Optional LLM service for generating explanations
        """
        self.llm_service = llm_service

        # Technical patterns to detect
        self.patterns = [
            "golden_cross",      # Fast MA crosses above slow MA
            "death_cross",       # Fast MA crosses below slow MA
            "rsi_divergence",    # Price vs RSI divergence
            "double_bottom",     # W-shaped reversal pattern
            "double_top",        # M-shaped reversal pattern
            "support_bounce",    # Price bouncing off support
            "resistance_break",  # Price breaking resistance
        ]

    async def evaluate(
        self,
        signal,
        market_data: Dict,
        news_context: str = "",
    ) -> TradeRecommendation:
        """
        Evaluate a trading signal and generate a recommendation.

        Args:
            signal: Strategy signal object
            market_data: Recent market data for the symbol
            news_context: Related news for LLM analysis

        Returns:
            TradeRecommendation with type, price levels, confidence, reasons
        """
        symbol = signal.symbol
        current_price = signal.price or market_data.get("close", 0)
        timestamp = signal.timestamp if hasattr(signal, "timestamp") else datetime.now()

        # 1. Base recommendation from signal
        rec_type = self._signal_to_rec_type(signal)
        base_confidence = signal.confidence if hasattr(signal, "confidence") else 0.6

        # 2. Technical pattern detection
        patterns_found = []
        pattern_confidence = 0.0

        if isinstance(market_data, dict) and "history" in market_data:
            patterns_found = self._detect_patterns(market_data["history"])
            if patterns_found:
                pattern_confidence = 0.2 * len(patterns_found)

        # 3. LLM analysis (if available)
        llm_boost = 0.0
        reasons = []

        if self.llm_service and news_context:
            try:
                analysis = await self.llm_service.analyze_symbol(
                    symbol=symbol,
                    technical_data=self._format_technical_data(market_data),
                    news_context=news_context,
                )

                if analysis.sentiment == "bullish" and rec_type in (RecType.BUY, RecType.STRONG_BUY):
                    llm_boost = 0.1
                elif analysis.sentiment == "bearish" and rec_type in (RecType.SELL, RecType.STRONG_SELL):
                    llm_boost = 0.1
                elif analysis.sentiment != "neutral":
                    llm_boost = -0.1  # LLM disagrees with signal

                if analysis.summary:
                    reasons.append(f"LLM: {analysis.summary}")

            except Exception as e:
                logger.error(f"LLM analysis failed for {symbol}: {e}")

        # Add pattern-based reasons
        for pattern in patterns_found:
            reasons.append(f"Pattern: {pattern}")

        # 4. Calculate final confidence
        final_confidence = min(
            base_confidence + pattern_confidence + llm_boost,
            0.95,
        )

        # 5. Calculate stop-loss and take-profit
        stop_loss, take_profit = self._calculate_levels(
            current_price, rec_type, market_data
        )

        # 6. Build recommendation
        return TradeRecommendation(
            timestamp=timestamp,
            symbol=symbol,
            type=rec_type,
            price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            confidence=final_confidence,
            source="signal_advisor",
            reasons=reasons,
            risk_level=self._assess_risk(final_confidence, market_data),
            metadata={
                "signal_type": str(signal.type) if hasattr(signal, "type") else "",
                "patterns": patterns_found,
                "confidence_breakdown": {
                    "signal": base_confidence,
                    "patterns": pattern_confidence,
                    "llm": llm_boost,
                    "final": final_confidence,
                },
            },
        )

    def _signal_to_rec_type(self, signal) -> RecType:
        """Map signal type to recommendation type."""
        from quantengine.strategy.base import SignalType

        sig_type = signal.type if hasattr(signal, "type") else None
        confidence = signal.confidence if hasattr(signal, "confidence") else 0.5

        if sig_type == SignalType.BUY:
            return RecType.STRONG_BUY if confidence > 0.8 else RecType.BUY
        elif sig_type in (SignalType.SELL, SignalType.CLOSE):
            return RecType.STRONG_SELL if confidence > 0.8 else RecType.SELL
        return RecType.HOLD

    def _detect_patterns(self, history) -> List[str]:
        """
        Detect technical patterns in historical data.

        Args:
            history: DataFrame with OHLCV data

        Returns:
            List of detected pattern names
        """
        found = []

        try:
            import numpy as np
            close = history["close"].values if hasattr(history, "values") else history

            if len(close) < 20:
                return found

            # Golden cross: MA5 crosses above MA20
            ma5 = np.mean(close[-5:])
            ma20 = np.mean(close[-20:])
            prev_ma5 = np.mean(close[-6:-1])
            prev_ma20 = np.mean(close[-21:-1])

            if prev_ma5 <= prev_ma20 and ma5 > ma20:
                found.append("golden_cross")
            elif prev_ma5 >= prev_ma20 and ma5 < ma20:
                found.append("death_cross")

            # Support bounce: price near N-day low and bouncing
            period_low = np.min(close[-20:])
            if close[-1] <= period_low * 1.02 and close[-1] > close[-2]:
                found.append("support_bounce")

            # Resistance break: price breaking above N-day high
            period_high = np.max(close[-21:-1])
            if close[-1] >= period_high:
                found.append("resistance_break")

        except Exception as e:
            logger.debug(f"Pattern detection failed: {e}")

        return found

    def _calculate_levels(
        self,
        price: float,
        rec_type: RecType,
        market_data: Dict,
    ) -> tuple:
        """
        Calculate stop-loss and take-profit levels.

        Uses ATR-based levels with 2:1 reward-to-risk ratio.

        Returns:
            Tuple of (stop_loss, take_profit)
        """
        # Default: 2% stop, 4% target for long positions
        if rec_type in (RecType.BUY, RecType.STRONG_BUY):
            stop_loss = price * 0.98
            take_profit = price * 1.04
        elif rec_type in (RecType.SELL, RecType.STRONG_SELL):
            stop_loss = price * 1.02
            take_profit = price * 0.96
        else:
            stop_loss = price * 0.98
            take_profit = price * 1.02

        # Try to use ATR if available
        try:
            if isinstance(market_data, dict) and "history" in market_data:
                hist = market_data["history"]
                if hasattr(hist, "high") and len(hist) > 20:
                    import numpy as np
                    high = hist["high"].values[-20:]
                    low = hist["low"].values[-20:]
                    close = hist["close"].values[-20:]
                    tr = np.maximum(
                        high - low,
                        np.maximum(
                            np.abs(high - np.roll(close, 1)),
                            np.abs(low - np.roll(close, 1)),
                        ),
                    )
                    atr = np.mean(tr[-14:]) if len(tr) > 14 else np.mean(tr)

                    if rec_type in (RecType.BUY, RecType.STRONG_BUY):
                        stop_loss = price - 2 * atr
                        take_profit = price + 4 * atr
                    elif rec_type in (RecType.SELL, RecType.STRONG_SELL):
                        stop_loss = price + 2 * atr
                        take_profit = price - 4 * atr
        except Exception:
            pass

        return (round(stop_loss, 2), round(take_profit, 2))

    def _assess_risk(self, confidence: float, market_data: Dict) -> str:
        """Assess risk level based on confidence and market conditions."""
        if confidence > 0.8:
            return "low"
        elif confidence > 0.6:
            return "medium"
        else:
            return "high"

    @staticmethod
    def _format_technical_data(market_data: Dict) -> str:
        """Format market data for LLM consumption."""
        try:
            hist = market_data.get("history")
            if hist is None or len(hist) < 5:
                return "Insufficient data"

            import numpy as np
            close = hist["close"].values if hasattr(hist, "close") else hist
            returns = np.diff(close[-20:]) / close[-21:-1] if len(close) > 20 else []

            return (
                f"Recent price: {close[-1]:.2f}\n"
                f"5-day return: {(close[-1]/close[-5]-1)*100:.1f}%\n" if len(close) >= 5 else "" +
                f"20-day return: {(close[-1]/close[-20]-1)*100:.1f}%\n" if len(close) >= 20 else "" +
                f"Volatility (20d): {np.std(returns)*100:.1f}%\n" if len(returns) > 0 else "" +
                f"MA20: {np.mean(close[-20:]):.2f}\n" if len(close) >= 20 else ""
            )
        except Exception:
            return "Data formatting error"
