"""
QuantEngine Pro - Auto Stock Screener
=======================================
Multi-condition stock screening and ranking system.

Supports:
- Technical screen (MA alignment, breakouts, volume)
- Fundamental screen (PE/PB percentile)
- Factor-based ranking (momentum, low vol, quality)
- LLM-based news filtering
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from loguru import logger


class StockScreener:
    """
    Multi-condition stock screener with factor scoring.

    Usage:
        screener = StockScreener(config)
        picks = await screener.screen(universe, market_data)
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize screener.

        Args:
            config: Dict with:
                - top_n: Number of top picks (default 10)
                - conditions: List of screen conditions
                - min_score: Minimum composite score (default 0.6)
        """
        self.config = config or {}
        self.top_n = self.config.get("top_n", 10)
        self.conditions = self.config.get("conditions", [
            "ma_bullish", "volume_surge", "momentum_top"
        ])
        self.min_score = self.config.get("min_score", 0.6)

        # Screening functions registry
        self._screeners = {
            "ma_bullish": self._check_ma_bullish,
            "volume_surge": self._check_volume_surge,
            "momentum_top": self._check_momentum,
            "low_volatility": self._check_low_volatility,
            "breakout": self._check_breakout,
        }

    async def screen(
        self,
        universe: List[str],
        market_data: Dict[str, pd.DataFrame],
        llm_service=None,
        news_data: Optional[Dict[str, List]] = None,
    ) -> pd.DataFrame:
        """
        Screen stocks and rank by composite score.

        Args:
            universe: List of stock symbols
            market_data: Dict mapping symbol → OHLCV DataFrame
            llm_service: Optional LLM service for news filtering
            news_data: Optional news data per symbol for LLM analysis

        Returns:
            DataFrame with ranked results: symbol, score, signals, recommendation
        """
        results = []

        for symbol in universe:
            df = market_data.get(symbol)
            if df is None or df.empty or len(df) < 60:
                continue

            scores = {}
            signals = []

            # Run each screen condition
            for condition in self.conditions:
                screener_fn = self._screeners.get(condition)
                if screener_fn:
                    passed, score = screener_fn(df)
                    scores[condition] = score
                    if passed:
                        signals.append(condition)

            # Composite score (average of all conditions)
            if scores:
                composite = np.mean(list(scores.values()))
            else:
                composite = 0.0

            # LLM news filtering
            llm_penalty = 0.0
            if llm_service and news_data:
                symbol_news = news_data.get(symbol, [])
                if symbol_news:
                    try:
                        # Analyze recent news sentiment
                        recent = " ".join(symbol_news[:3])
                        analysis = await llm_service.analyze_news(recent)
                        if analysis.sentiment == "negative":
                            llm_penalty = -0.3
                        elif analysis.sentiment == "positive":
                            llm_penalty = 0.1
                        signals.append(f"llm:{analysis.sentiment}")
                    except Exception:
                        pass

            composite += llm_penalty

            # Filter by minimum score
            if composite >= self.min_score:
                results.append({
                    "symbol": symbol,
                    "composite_score": round(composite, 3),
                    "signals": signals,
                    "individual_scores": scores,
                    "llm_adjustment": llm_penalty,
                })

        # Sort by score descending
        results.sort(key=lambda x: x["composite_score"], reverse=True)
        top_picks = results[:self.top_n]

        logger.info(
            f"Screened {len(universe)} stocks → {len(results)} passed → "
            f"top {len(top_picks)} selected"
        )
        return pd.DataFrame(top_picks)

    # ---- Screening Functions ----

    @staticmethod
    def _check_ma_bullish(df: pd.DataFrame) -> Tuple[bool, float]:
        """Check if price is above key MAs (bullish alignment)."""
        close = df["close"].values
        if len(close) < 60:
            return (False, 0.0)

        ma20 = np.mean(close[-20:])
        ma60 = np.mean(close[-60:])
        current = close[-1]

        # Score: how far above MAs
        score = min((current - ma20) / ma20 * 10 + 0.5, 1.0)
        passed = current > ma20 > ma60
        return (passed, max(score, 0.0))

    @staticmethod
    def _check_volume_surge(df: pd.DataFrame) -> Tuple[bool, float]:
        """Check for volume surge (volume > 1.5x average)."""
        if "volume" not in df.columns or len(df) < 20:
            return (False, 0.0)

        volume = df["volume"].values
        avg_vol = np.mean(volume[-20:-1])
        current_vol = volume[-1]
        ratio = current_vol / avg_vol if avg_vol > 0 else 0

        # Score: normalized volume ratio
        score = min(ratio / 3.0, 1.0)
        passed = ratio > 1.5
        return (passed, score)

    @staticmethod
    def _check_momentum(df: pd.DataFrame) -> Tuple[bool, float]:
        """Check price momentum (20-day return)."""
        close = df["close"].values
        if len(close) < 21:
            return (False, 0.0)

        momentum = (close[-1] - close[-21]) / close[-21]
        score = min(momentum * 10 + 0.5, 1.0)
        passed = momentum > 0.02  # 2% over 20 days
        return (passed, max(score, 0.0))

    @staticmethod
    def _check_low_volatility(df: pd.DataFrame) -> Tuple[bool, float]:
        """Check for low volatility (prefer stable stocks)."""
        close = df["close"].values
        if len(close) < 20:
            return (False, 0.0)

        returns = np.diff(close[-20:]) / close[-20:-1]
        vol = np.std(returns)

        # Score: lower vol → higher score
        score = 1.0 - min(vol * 100, 1.0)
        passed = vol < 0.03  # Daily vol < 3%
        return (passed, score)

    @staticmethod
    def _check_breakout(df: pd.DataFrame) -> Tuple[bool, float]:
        """Check for price breakout (new N-day high)."""
        close = df["close"].values
        high = df["high"].values if "high" in df.columns else close
        if len(high) < 20:
            return (False, 0.0)

        period_high = np.max(high[-21:-1])
        current = close[-1]
        breakout_pct = (current - period_high) / period_high if period_high > 0 else 0

        score = min(breakout_pct * 50 + 0.5, 1.0)
        passed = current >= period_high
        return (passed, max(score, 0.0))
