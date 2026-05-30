"""
QuantEngine Pro - DeepSeek LLM Adapter
========================================
LLM service using DeepSeek's OpenAI-compatible API.

DeepSeek offers free tier with OpenAI-compatible format:
- deepseek-v4-flash: Fast and cost-effective for news analysis
- deepseek-v4-pro: Higher quality for complex reasoning

Upgrade: Change provider to 'openai' in config → use GPT-4.
"""

import json
import re
from typing import Dict, List

from loguru import logger
from openai import AsyncOpenAI

from quantengine.analysis.llm.base import AnalysisResult, BaseLLMService

# Prompts optimized for financial analysis in Chinese
NEWS_PROMPT = """Analyze this financial news and output JSON:
{
    "sentiment": "positive" | "negative" | "neutral",
    "sentiment_score": <float -1.0 to 1.0>,
    "confidence": <float 0.0 to 1.0>,
    "summary": "<one-sentence Chinese summary>",
    "key_points": ["<point>", ...],
    "mentioned_symbols": ["<symbol>", ...],
    "relevance_score": <float 0-1>,
    "price_impact": "positive" | "negative" | "neutral",
    "urgency": "low" | "medium" | "high"
}

News: """

SYMBOL_PROMPT = """Analyze this trading symbol. Output JSON:
{
    "sentiment": "bullish" | "bearish" | "neutral",
    "sentiment_score": <float -1.0 to 1.0>,
    "confidence": <float 0.0 to 1.0>,
    "summary": "<Chinese analysis>",
    "key_points": ["<observation>", ...],
    "recommendation": "buy" | "sell" | "hold",
    "risk_level": "low" | "medium" | "high"
}

Data: """

MARKET_PROMPT = """You are a senior market analyst. Based on these headlines, write a Chinese daily market summary with:
1. Overall sentiment (1 sentence)
2. Key events (2-3 bullet points)
3. Sectors/coins to watch
4. Risk factors

Headlines:
"""


class DeepSeekService(BaseLLMService):
    """
    DeepSeek LLM service using OpenAI-compatible API.

    Usage:
        svc = DeepSeekService({"api_key": "sk-xxx", "model": "deepseek-v4-flash"})
        result = await svc.analyze_news("Market rallied today...")
    """

    def __init__(self, config: Dict):
        super().__init__(config)
        api_key = config.get("api_key", "")
        base_url = config.get("base_url", "https://api.deepseek.com")
        self.request_timeout = config.get("request_timeout", 30)
        self.max_retries = config.get("max_retries", 3)

        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=self.request_timeout,
            max_retries=self.max_retries,
        )
        logger.info(f"DeepSeekService init: model={self.model}")

    async def analyze_news(self, news_text: str) -> AnalysisResult:
        """Analyze a single news article."""
        if not news_text.strip():
            return AnalysisResult()

        try:
            resp = await self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": NEWS_PROMPT},
                    {"role": "user", "content": news_text[:3000]},
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                response_format={"type": "json_object"},
            )

            content = resp.choices[0].message.content
            tokens = resp.usage.total_tokens if resp.usage else 0
            data = self._parse_json(content)

            return AnalysisResult(
                sentiment=data.get("sentiment", "neutral"),
                sentiment_score=float(data.get("sentiment_score", 0)),
                confidence=float(data.get("confidence", 0.7)),
                summary=data.get("summary", ""),
                key_points=data.get("key_points", []),
                mentioned_symbols=data.get("mentioned_symbols", []),
                relevance_score=float(data.get("relevance_score", 0)),
                price_impact=data.get("price_impact", "neutral"),
                urgency=data.get("urgency", "low"),
                raw_response=content or "",
                tokens_used=tokens,
                model=self.model,
            )
        except Exception as e:
            logger.error(f"DeepSeek analyze_news failed: {e}")
            return AnalysisResult(summary=f"Error: {e}")

    async def generate_market_summary(self, news_list: List[str]) -> str:
        """Generate daily market summary."""
        if not news_list:
            return "No news available."

        combined = "\n---\n".join(news_list[:20])[:6000]
        try:
            resp = await self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": MARKET_PROMPT},
                    {"role": "user", "content": combined},
                ],
                max_tokens=min(self.max_tokens, 1500),
                temperature=0.5,
            )
            return resp.choices[0].message.content or "Summary unavailable."
        except Exception as e:
            logger.error(f"Market summary failed: {e}")
            return f"Summary generation failed: {e}"

    async def analyze_symbol(
        self, symbol: str, technical_data: str, news_context: str = ""
    ) -> AnalysisResult:
        """Analyze a trading symbol."""
        combined = f"Symbol: {symbol}\n\nTechnical:\n{technical_data}"
        if news_context:
            combined += f"\n\nNews:\n{news_context}"

        try:
            resp = await self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYMBOL_PROMPT},
                    {"role": "user", "content": combined[:4000]},
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                response_format={"type": "json_object"},
            )
            content = resp.choices[0].message.content
            tokens = resp.usage.total_tokens if resp.usage else 0
            data = self._parse_json(content)

            return AnalysisResult(
                sentiment=data.get("sentiment", "neutral"),
                sentiment_score=float(data.get("sentiment_score", 0)),
                confidence=float(data.get("confidence", 0.7)),
                summary=data.get("summary", ""),
                key_points=data.get("key_points", []),
                mentioned_symbols=[symbol],
                raw_response=content or "",
                tokens_used=tokens,
                model=self.model,
            )
        except Exception as e:
            logger.error(f"Symbol analysis failed for {symbol}: {e}")
            return AnalysisResult(summary=f"Error: {e}")

    @property
    def provider_name(self) -> str:
        return "deepseek"

    @staticmethod
    def _parse_json(content: str) -> Dict:
        """Parse LLM JSON, handling markdown code blocks."""
        if not content:
            return {}
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', content, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(1))
                except json.JSONDecodeError:
                    pass
            logger.warning(f"JSON parse failed: {content[:200]}...")
            return {}
