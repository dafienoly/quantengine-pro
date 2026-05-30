"""
QuantEngine Pro - LLM Service Abstraction
===========================================
Abstract interface for LLM services (DeepSeek, OpenAI, Anthropic, etc.).

Supports:
- News sentiment analysis
- Market summary generation
- Stock/coin analysis
- Trading signal explanation
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AnalysisResult:
    """
    Structured LLM analysis result.

    Standardized output format across all LLM providers.
    """
    # Sentiment
    sentiment: str = "neutral"       # positive, negative, neutral
    sentiment_score: float = 0.0     # -1.0 (negative) to 1.0 (positive)
    confidence: float = 0.0          # LLM confidence in analysis

    # Content
    summary: str = ""                # Brief summary
    key_points: List[str] = field(default_factory=list)  # Key takeaways
    mentioned_symbols: List[str] = field(default_factory=list)  # Referenced symbols

    # Trading relevance
    relevance_score: float = 0.0     # How relevant for trading (0-1)
    price_impact: str = "neutral"    # expected, positive, negative, neutral
    urgency: str = "low"             # low, medium, high

    # Raw
    raw_response: str = ""           # Original LLM response
    tokens_used: int = 0             # Token count for cost tracking
    model: str = ""                  # Which model was used


class BaseLLMService(ABC):
    """
    Abstract LLM service interface.

    All LLM providers (DeepSeek, OpenAI, Claude, etc.) implement this.
    Switch providers by changing config — no code changes needed.
    """

    def __init__(self, config: Dict):
        """
        Initialize LLM service.

        Args:
            config: Provider-specific configuration
        """
        self.config = config
        self.model = config.get("model", "default")
        self.max_tokens = config.get("max_tokens", 1024)
        self.temperature = config.get("temperature", 0.3)

    @abstractmethod
    async def analyze_news(self, news_text: str) -> AnalysisResult:
        """
        Analyze a single news article.

        Extracts:
        - Sentiment (positive/negative/neutral) with score
        - Key points and mentioned symbols
        - Trading relevance

        Args:
            news_text: News article text (title + content)

        Returns:
            AnalysisResult with structured analysis
        """
        ...

    @abstractmethod
    async def generate_market_summary(self, news_list: List[str]) -> str:
        """
        Generate a daily market summary from multiple news articles.

        Args:
            news_list: List of news article texts

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
        Analyze a specific trading symbol with LLM.

        Args:
            symbol: Trading symbol
            technical_data: Technical indicators and price data summary
            news_context: Recent news about this symbol

        Returns:
            AnalysisResult with trading recommendations
        """
        ...

    async def batch_analyze_news(
        self,
        news_texts: List[str],
        max_concurrent: int = 5,
    ) -> List[AnalysisResult]:
        """
        Analyze multiple news articles with concurrency control.

        Args:
            news_texts: List of news texts
            max_concurrent: Max concurrent API calls

        Returns:
            List of AnalysisResult objects
        """
        import asyncio

        semaphore = asyncio.Semaphore(max_concurrent)

        async def _analyze_with_limit(text: str) -> AnalysisResult:
            async with semaphore:
                try:
                    return await self.analyze_news(text)
                except Exception as e:
                    from loguru import logger
                    logger.error(f"LLM analysis failed: {e}")
                    return AnalysisResult(summary=f"Error: {e}")

        tasks = [_analyze_with_limit(t) for t in news_texts]
        return await asyncio.gather(*tasks)

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the LLM provider (deepseek, openai, etc.)."""
        ...
