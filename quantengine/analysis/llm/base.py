"""
QuantEngine Pro - LLM Service Abstraction
===========================================
Abstract interface for LLM services (DeepSeek, OpenAI, Anthropic).
Switch providers by changing config — no code changes needed.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class AnalysisResult:
    """Structured LLM analysis result, standardized across all providers."""
    sentiment: str = "neutral"        # positive, negative, neutral
    sentiment_score: float = 0.0      # -1.0 (negative) to 1.0 (positive)
    confidence: float = 0.0           # LLM confidence in analysis
    summary: str = ""                 # Brief Chinese summary
    key_points: List[str] = field(default_factory=list)
    mentioned_symbols: List[str] = field(default_factory=list)
    relevance_score: float = 0.0      # Trading relevance (0-1)
    price_impact: str = "neutral"     # expected price impact
    urgency: str = "low"              # low, medium, high
    raw_response: str = ""            # Original LLM response
    tokens_used: int = 0              # For cost tracking
    model: str = ""                   # Which model was used


class BaseLLMService(ABC):
    """
    Abstract LLM service interface.

    All LLM providers (DeepSeek, OpenAI, Claude) implement this.
    """

    def __init__(self, config: Dict):
        self.config = config
        self.model = config.get("model", "default")
        self.max_tokens = config.get("max_tokens", 1024)
        self.temperature = config.get("temperature", 0.3)

    @abstractmethod
    async def analyze_news(self, news_text: str) -> AnalysisResult:
        """
        Analyze a single news article.

        Returns:
            AnalysisResult with sentiment, key_points, mentioned_symbols
        """
        ...

    @abstractmethod
    async def generate_market_summary(self, news_list: List[str]) -> str:
        """
        Generate daily market summary from multiple news articles.

        Returns:
            Markdown-formatted market summary
        """
        ...

    @abstractmethod
    async def analyze_symbol(
        self,
        symbol: str,
        technical_data: str,
        news_context: str = "",
    ) -> AnalysisResult:
        """
        Analyze a specific trading symbol combining technical and news data.

        Returns:
            AnalysisResult with trading recommendations
        """
        ...

    async def batch_analyze_news(
        self, news_texts: List[str], max_concurrent: int = 5
    ) -> List[AnalysisResult]:
        """Analyze multiple articles with concurrency control."""
        import asyncio
        from loguru import logger

        semaphore = asyncio.Semaphore(max_concurrent)

        async def _with_limit(text: str) -> AnalysisResult:
            async with semaphore:
                try:
                    return await self.analyze_news(text)
                except Exception as e:
                    logger.error(f"LLM analysis failed: {e}")
                    return AnalysisResult(summary=f"Error: {e}")

        return await asyncio.gather(*[_with_limit(t) for t in news_texts])

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the LLM provider."""
        ...
