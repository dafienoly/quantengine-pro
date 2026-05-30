"""
QuantEngine Pro - Auto Stock Screener
=======================================
Multi-condition stock screening with factor scoring and LLM news filtering.
"""

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from loguru import logger


class StockScreener:
    """
    Multi-condition stock screener with composite factor scoring.

    Supports: MA alignment, volume surge, momentum, low volatility, breakout.

    Usage:
        screener = StockScreener({'top_n': 10})
        picks = await screener.screen(symbols, market_data)
    """

    def __init__(self, config: Optional[Dict] = None):
        config = config or {}
        self.top_n = config.get("top_n", 10)
        self.conditions = config.get("conditions", [
            "ma_bullish", "volume_surge", "momentum_top"
        ])
        self.min_score = config.get("min_score", 0.6)
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
        """Screen stocks and rank by composite score."""
        results = []

        for symbol in universe:
            df = market_data.get(symbol)
            if df is None or df.empty or len(df) < 60:
                continue

            scores = {}; signals = []
            for condition in self.conditions:
                fn = self._screeners.get(condition)
                if fn:
                    passed, score = fn(df)
                    scores[condition] = score
                    if passed: signals.append(condition)

            composite = np.mean(list(scores.values())) if scores else 0.0

            # LLM news filtering
            llm_adj = 0.0
            if llm_service and news_data:
                sym_news = news_data.get(symbol, [])
                if sym_news:
                    try:
                        analysis = await llm_service.analyze_news(" ".join(sym_news[:3]))
                        if analysis.sentiment == "negative": llm_adj = -0.3
                        elif analysis.sentiment == "positive": llm_adj = 0.1
                        signals.append(f"llm:{analysis.sentiment}")
                    except Exception: pass

            composite += llm_adj
            if composite >= self.min_score:
                results.append({
                    "symbol": symbol, "composite_score": round(composite, 3),
                    "signals": signals, "individual_scores": scores,
                    "llm_adjustment": llm_adj,
                })

        results.sort(key=lambda x: x["composite_score"], reverse=True)
        logger.info(f"Screener: {len(universe)}→{len(results)} passed→top {len(results[:self.top_n])}")
        return pd.DataFrame(results[:self.top_n])

    @staticmethod
    def _check_ma_bullish(df: pd.DataFrame) -> Tuple[bool, float]:
        close = df["close"].values
        if len(close) < 60: return (False, 0.0)
        ma20 = np.mean(close[-20:]); ma60 = np.mean(close[-60:])
        score = min((close[-1] - ma20) / ma20 * 10 + 0.5, 1.0)
        return (close[-1] > ma20 > ma60, max(score, 0.0))

    @staticmethod
    def _check_volume_surge(df: pd.DataFrame) -> Tuple[bool, float]:
        if "volume" not in df.columns or len(df) < 20: return (False, 0.0)
        vol = df["volume"].values
        ratio = vol[-1] / np.mean(vol[-20:-1]) if np.mean(vol[-20:-1]) > 0 else 0
        return (ratio > 1.5, min(ratio / 3.0, 1.0))

    @staticmethod
    def _check_momentum(df: pd.DataFrame) -> Tuple[bool, float]:
        close = df["close"].values
        if len(close) < 21: return (False, 0.0)
        mom = (close[-1] - close[-21]) / close[-21]
        score = min(mom * 10 + 0.5, 1.0)
        return (mom > 0.02, max(score, 0.0))

    @staticmethod
    def _check_low_volatility(df: pd.DataFrame) -> Tuple[bool, float]:
        close = df["close"].values
        if len(close) < 20: return (False, 0.0)
        rets = np.diff(close[-20:]) / close[-20:-1]
        vol = np.std(rets)
        return (vol < 0.03, 1.0 - min(vol * 100, 1.0))

    @staticmethod
    def _check_breakout(df: pd.DataFrame) -> Tuple[bool, float]:
        close = df["close"].values
        high = df["high"].values if "high" in df.columns else close
        if len(high) < 20: return (False, 0.0)
        period_high = np.max(high[-21:-1])
        pct = (close[-1] - period_high) / period_high if period_high > 0 else 0
        return (close[-1] >= period_high, min(pct * 50 + 0.5, 1.0))
