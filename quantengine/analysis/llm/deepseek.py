"""
QuantEngine Pro - DeepSeek LLM Adapter
========================================
LLM service implementation using DeepSeek's OpenAI-compatible API.

DeepSeek offers:
- Free tier with generous limits
- OpenAI-compatible API (just change base_url)
- DeepSeek-v4-flash: Fast and cost-effective
- DeepSeek-v4-pro: Higher quality for complex analysis

Upgrade path: Change provider to 'openai' in config → use GPT-4.
"""

import json
import re
from typing import Dict, List

from loguru import logger
from openai import AsyncOpenAI

from quantengine.analysis.llm.base import AnalysisResult, BaseLLMService


# System prompts for different analysis tasks
NEWS_ANALYSIS_PROMPT = """You are a financial news analyst. Analyze the following news article and output a JSON object with this exact structure:
{
    "sentiment": "positive" | "negative" | "neutral",
    "sentiment_score": <float between -1.0 and 1.0>,
    "confidence": <float between 0.0 and 1.0>,
    "summary": "<one-sentence summary in Chinese>",
    "key_points": ["<point1>", "<point2>"],
    "mentioned_symbols": ["<stock/crypto symbol>"],
    "relevance_score": <float 0-1, how relevant for trading>,
    "price_impact": "positive" | "negative" | "neutral",
    "urgency": "low" | "medium" | "high"
}

News article:
"""

MARKET_SUMMARY_PROMPT = """You are a senior market analyst. Based on the following news headlines, write a concise daily market summary in Chinese. Include:
1. Overall market sentiment (1 sentence)
2. Key events driving the market (2-3 points)
3. Sectors/coins to watch
4. Risk factors to monitor

News headlines:
"""

SYMBOL_ANALYSIS_PROMPT = """You are a quantitative trading analyst. Analyze the following trading symbol data and provide a structured assessment. Output JSON:
{
    "sentiment": "bullish" | "bearish" | "neutral",
    "sentiment_score": <float -1.0 to 1.0>,
    "confidence": <float 0.0 to 1.0>,
    "summary": "<analysis summary in Chinese>",
    "key_points": ["<key observation>"],
    "recommendation": "buy" | "sell" | "hold",
    "risk_level": "low" | "medium" | "high",
    "target_price": <float or null>,
    "stop_loss": <float or null>
}

Data:
"""


class DeepSeekService(BaseLLMService):
    """
    DeepSeek LLM service implementation.

    Uses OpenAI-compatible API format — same client library,
    different base_url and api_key.

    Usage:
        service = DeepSeekService({
            "api_key": "sk-xxx",
            "model": "deepseek-v4-flash",
            "base_url": "https://api.deepseek.com",
        })
        result = await service.analyze_news("Market rallied today...")
    """

    def __init__(self, config: Dict):
        """
        Initialize DeepSeek service.

        Args:
            config: Dict with keys:
                - api_key: DeepSeek API key
                - base_url: API endpoint (default: https://api.deepseek.com)
                - model: Model name (default: deepseek-v4-flash)
                - max_tokens: Max response tokens (default: 1024)
                - temperature: Sampling temperature (default: 0.3)
                - request_timeout: API timeout seconds (default: 30)
                - max_retries: Retry attempts (default: 3)
        """
        super().__init__(config)

        api_key = config.get("api_key", "")
        base_url = config.get("base_url", "https://api.deepseek.com")
        self.request_timeout = config.get("request_timeout", 30)
        self.max_retries = config.get("max_retries", 3)

        # Initialize OpenAI-compatible client
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=self.request_timeout,
            max_retries=self.max_retries,
        )

        logger.info(
            f"DeepSeekService initialized: model={self.model}, "
            f"base_url={base_url}"
        )

    async def analyze_news(self, news_text: str) -> AnalysisResult:
        """
        Analyze a single news article for sentiment and trading relevance.

        Args:
            news_text: News article text

        Returns:
            AnalysisResult with sentiment, key points, mentioned symbols
        """
        if not news_text.strip():
            return AnalysisResult()

        # Truncate very long texts
        text = news_text[:3000]

        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": NEWS_ANALYSIS_PROMPT},
                    {"role": "user", "content": text},
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            tokens = response.usage.total_tokens if response.usage else 0

            # Parse JSON response
            result = self._parse_json_response(content)

            return AnalysisResult(
                sentiment=result.get("sentiment", "neutral"),
                sentiment_score=float(result.get("sentiment_score", 0)),
                confidence=float(result.get("confidence", 0.7)),
                summary=result.get("summary", ""),
                key_points=result.get("key_points", []),
                mentioned_symbols=result.get("mentioned_symbols", []),
                relevance_score=float(result.get("relevance_score", 0)),
                price_impact=result.get("price_impact", "neutral"),
                urgency=result.get("urgency", "low"),
                raw_response=content or "",
                tokens_used=tokens,
                model=self.model,
            )

        except Exception as e:
            logger.error(f"DeepSeek news analysis failed: {e}")
            return AnalysisResult(summary=f"Analysis error: {e}")

    async def generate_market_summary(self, news_list: List[str]) -> str:
        """
        Generate daily market summary from news headlines.

        Args:
            news_list: List of news article texts

        Returns:
            Markdown-formatted Chinese market summary
        """
        if not news_list:
            return "No news available for summary."

        # Combine headlines (limit total length)
        combined = "\n---\n".join(news_list[:20])
        combined = combined[:6000]  # Limit input tokens

        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": MARKET_SUMMARY_PROMPT},
                    {"role": "user", "content": combined},
                ],
                max_tokens=min(self.max_tokens, 1500),
                temperature=0.5,
            )

            return response.choices[0].message.content or "Summary unavailable."

        except Exception as e:
            logger.error(f"DeepSeek market summary failed: {e}")
            return f"Market summary generation failed: {e}"

    async def analyze_symbol(
        self,
        symbol: str,
        technical_data: str,
        news_context: str = "",
    ) -> AnalysisResult:
        """
        Analyze a trading symbol combining technical and news data.

        Args:
            symbol: Trading symbol
            technical_data: Technical analysis summary
            news_context: Related news

        Returns:
            AnalysisResult with trading recommendations
        """
        combined = f"Symbol: {symbol}\n\nTechnical Data:\n{technical_data}"
        if news_context:
            combined += f"\n\nRecent News:\n{news_context}"

        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYMBOL_ANALYSIS_PROMPT},
                    {"role": "user", "content": combined[:4000]},
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            tokens = response.usage.total_tokens if response.usage else 0
            result = self._parse_json_response(content)

            return AnalysisResult(
                sentiment=result.get("sentiment", "neutral"),
                sentiment_score=float(result.get("sentiment_score", 0)),
                confidence=float(result.get("confidence", 0.7)),
                summary=result.get("summary", ""),
                key_points=result.get("key_points", []),
                mentioned_symbols=[symbol],
                raw_response=content or "",
                tokens_used=tokens,
                model=self.model,
            )

        except Exception as e:
            logger.error(f"DeepSeek symbol analysis failed for {symbol}: {e}")
            return AnalysisResult(summary=f"Analysis error: {e}")

    @property
    def provider_name(self) -> str:
        return "deepseek"

    @staticmethod
    def _parse_json_response(content: str) -> Dict:
        """
        Parse LLM JSON response, handling markdown code blocks.

        Args:
            content: Raw LLM response text

        Returns:
            Parsed dict (empty dict on failure)
        """
        if not content:
            return {}

        try:
            # Try direct parse
            return json.loads(content)
        except json.JSONDecodeError:
            # Try extracting from markdown code block
            match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', content, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass

            logger.warning(f"Failed to parse LLM JSON response: {content[:200]}...")
            return {}
