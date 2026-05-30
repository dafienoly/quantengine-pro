"""
QuantEngine Pro - Signal Advisor
==================================
Combines strategy signals, technical patterns, and LLM analysis
to generate actionable buy/sell recommendations.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from loguru import logger


@dataclass
class TradeRecommendation:
    """A trading recommendation with stop-loss and take-profit."""
    symbol: str
    direction: str          # BUY / SELL / HOLD
    price: float
    stop_loss: float
    take_profit: float
    confidence: float       # 0.0 - 1.0
    reasoning: str
    strategy_source: str = ""
    technical_signals: List[str] = field(default_factory=list)
    llm_interpretation: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


class SignalAdvisor:
    """
    Buy/sell signal advisor combining strategy signals, technical patterns,
    and optional LLM market interpretation.
    """

    def __init__(self, llm_service=None):
        self.llm_service = llm_service

    async def analyze(
        self,
        symbol: str,
        strategy_signals: List,
        market_data: pd.DataFrame,
        news_context: Optional[str] = None,
    ) -> Optional[TradeRecommendation]:
        """
        Generate trade recommendation for a symbol.

        Args:
            symbol: Trading symbol
            strategy_signals: Recent signals from active strategies
            market_data: OHLCV DataFrame
            news_context: Optional news for LLM interpretation
        """
        if market_data.empty:
            return None

        close = market_data["close"].values
        high = market_data["high"].values if "high" in market_data.columns else close
        low = market_data["low"].values if "low" in market_data.columns else close
        current_price = float(close[-1])

        technical_signals = []
        reasoning = []
        strategy_direction = None
        strategy_confidence = 0.0
        strategy_name = ""

        # 1. Strategy signals
        if strategy_signals:
            buys = [s for s in strategy_signals if hasattr(s, 'type') and s.type.value == "BUY"]
            sells = [s for s in strategy_signals if hasattr(s, 'type') and s.type.value in ("SELL", "CLOSE")]
            if buys:
                strategy_direction = "BUY"
                strategy_confidence = float(np.mean([s.confidence if hasattr(s, 'confidence') else 0.6 for s in buys]))
                strategy_name = ", ".join(s.metadata.get("strategy_name", "") for s in buys if hasattr(s, 'metadata'))
                reasoning.append(f"Strategy: {len(buys)} buy signals")
            elif sells:
                strategy_direction = "SELL"
                strategy_confidence = float(np.mean([s.confidence if hasattr(s, 'confidence') else 0.6 for s in sells]))
                reasoning.append(f"Strategy: {len(sells)} sell signals")

        # 2. Technical patterns
        if len(close) >= 60:
            # RSI divergence
            rsi = self._calc_rsi(close, 14)
            prev_rsi = self._calc_rsi(close[:-1], 14)
            if close[-1] < close[-6] and rsi > prev_rsi:
                technical_signals.append("RSI底背离"); reasoning.append("RSI bullish divergence")
            if close[-1] > close[-6] and rsi < prev_rsi:
                technical_signals.append("RSI顶背离"); reasoning.append("RSI bearish divergence")

            # MA cross
            ma5, ma20 = np.mean(close[-5:]), np.mean(close[-20:])
            prev_ma5, prev_ma20 = np.mean(close[-6:-1]), np.mean(close[-21:-1])
            if prev_ma5 <= prev_ma20 and ma5 > ma20:
                technical_signals.append("MA金叉"); reasoning.append("Golden cross MA5/20")
                strategy_direction = strategy_direction or "BUY"
            elif prev_ma5 >= prev_ma20 and ma5 < ma20:
                technical_signals.append("MA死叉"); reasoning.append("Death cross MA5/20")
                strategy_direction = strategy_direction or "SELL"

        # 3. Stop-loss / Take-profit (ATR-based)
        if len(close) >= 20:
            atr = self._calc_atr(high, low, close, 14)
            if strategy_direction == "BUY":
                stop_loss = current_price - 2 * atr
                take_profit = current_price + 3 * atr
            elif strategy_direction == "SELL":
                stop_loss = current_price + 2 * atr
                take_profit = current_price - 3 * atr
            else:
                stop_loss = current_price * 0.95
                take_profit = current_price * 1.05
        else:
            stop_loss, take_profit = current_price * 0.95, current_price * 1.05

        # 4. LLM interpretation
        llm_text = ""
        if self.llm_service and news_context:
            try:
                prompt = f"Briefly analyze impact of '{news_context[:200]}' on {symbol} at price {current_price}."
                # Simple: use analyze_news interface
                llm_result = await self.llm_service.analyze_news(f"{symbol}: {news_context[:500]}")
                llm_text = llm_result.summary[:100] if llm_result.summary else ""
                if llm_text: reasoning.append(f"AI: {llm_text[:80]}")
            except Exception as e:
                logger.warning(f"LLM interpretation failed: {e}")

        if strategy_direction is None and not technical_signals:
            direction, confidence = "HOLD", 0.3
        else:
            direction = strategy_direction or ("BUY" if len(technical_signals) > 1 else "HOLD")
            confidence = strategy_confidence * 0.6 + min(len(technical_signals) / 5, 1.0) * 0.4

        return TradeRecommendation(
            symbol=symbol, direction=direction, price=current_price,
            stop_loss=round(stop_loss, 2), take_profit=round(take_profit, 2),
            confidence=round(min(confidence, 0.95), 2),
            reasoning="; ".join(reasoning) if reasoning else "No clear signal",
            strategy_source=strategy_name, technical_signals=technical_signals,
            llm_interpretation=llm_text,
        )

    @staticmethod
    def _calc_rsi(prices: np.ndarray, period: int = 14) -> float:
        if len(prices) < period + 1: return 50.0
        deltas = np.diff(prices[-period-1:])
        gains, losses = np.maximum(deltas, 0), np.abs(np.minimum(deltas, 0))
        avg_gain, avg_loss = np.mean(gains), np.mean(losses)
        return 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)

    @staticmethod
    def _calc_atr(high, low, close, period: int = 14) -> float:
        if len(close) < 2: return 0.0
        prev_close = np.roll(close, 1); prev_close[0] = close[0]
        tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
        return float(np.mean(tr[-period:]))
