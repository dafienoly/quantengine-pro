"""
QuantEngine Pro - News Fetchers
================================
Multiple free news source implementations:
- CailianNewsFetcher: 财联社电报 RSS feed
- SinaStockNewsFetcher: 新浪财经个股新闻
- CryptoPanicNewsFetcher: Cryptocurrency news (free tier)

All return standardized NewsItem objects via the BaseNewsFetcher interface.
"""

import asyncio
import hashlib
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from xml.etree import ElementTree

import aiohttp
import requests
from bs4 import BeautifulSoup
from loguru import logger

from quantengine.data.base import BaseNewsFetcher, NewsItem


class CailianNewsFetcher(BaseNewsFetcher):
    """
    财联社 (Cailian Press) news fetcher.

    Cailian is a leading Chinese financial news service. This fetcher
    parses their RSS/API feeds for breaking financial news.

    Sources:
    - RSS feed: https://www.cls.cn/telegraph (电报 - flash news)
    - API: https://www.cls.cn/api (requires parsing)

    Free: No API key needed for basic RSS access.
    """

    # Cailian API endpoints (reverse-engineered from web client)
    TELEGRAPH_API = "https://www.cls.cn/api/sw?app=CailianpressWeb&os=web&sv=8.4.6"

    def __init__(self, config: Dict):
        """
        Initialize Cailian news fetcher.

        Args:
            config: Dict with optional keys:
                - limit_per_request: Max items per fetch (default 50)
                - timeout: Request timeout (default 15)
        """
        super().__init__(config)
        self.limit_per_request = config.get("limit_per_request", 50)
        self.timeout = config.get("timeout", 15)
        self._session: Optional[aiohttp.ClientSession] = None
        logger.info("CailianNewsFetcher initialized")

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://www.cls.cn/",
            })
        return self._session

    def _extract_symbols(self, text: str) -> List[str]:
        """
        Extract stock symbols mentioned in news text.

        Uses regex patterns for:
        - 6-digit A-share codes
        - Common stock name patterns

        Args:
            text: News text content

        Returns:
            List of extracted symbol strings
        """
        symbols = []
        # Match 6-digit stock codes
        code_pattern = re.findall(r'\b(\d{6})\b', text)
        symbols.extend(code_pattern)
        return list(set(symbols))

    async def fetch_news(
        self,
        symbols: Optional[List[str]] = None,
        date: Optional[str] = None,
        limit: int = 50,
    ) -> List[NewsItem]:
        """
        Fetch Cailian telegraph (电报) news.

        Args:
            symbols: Filter by stock codes (optional)
            date: Date filter 'YYYYMMDD' (optional)
            limit: Max items

        Returns:
            List of NewsItem objects
        """
        session = await self._get_session()

        try:
            # Cailian telegraph list API
            url = f"{self.TELEGRAPH_API}/v1/roll/list"
            params = {
                "app": "CailianpressWeb",
                "os": "web",
                "sv": "8.4.6",
                "limit": min(limit, self.limit_per_request),
            }

            async with session.get(
                url, params=params, timeout=self.timeout
            ) as response:
                if response.status != 200:
                    logger.error(f"Cailian API returned status {response.status}")
                    return []

                data = await response.json()
                if not data or "data" not in data:
                    return []

                items = data["data"].get("roll_data", [])
                news_list = []

                for item in items:
                    title = item.get("title", "")
                    content = item.get("content", "") or item.get("brief", "")

                    news_item = NewsItem(
                        timestamp=datetime.fromtimestamp(
                            item.get("ctime", 0)
                        ),
                        title=title,
                        content=content,
                        source="cailian",
                        url=f"https://www.cls.cn/detail/{item.get('id', '')}",
                        symbols=self._extract_symbols(f"{title} {content}"),
                        category="financial",
                    )
                    news_list.append(news_item)

                logger.info(f"Fetched {len(news_list)} Cailian news items")
                return news_list

        except asyncio.TimeoutError:
            logger.error("Cailian API request timed out")
            return []
        except Exception as e:
            logger.error(f"Failed to fetch Cailian news: {e}")
            return []


class SinaStockNewsFetcher(BaseNewsFetcher):
    """
    新浪财经 (Sina Finance) stock news fetcher.

    Parses Sina Finance web pages for individual stock news.
    Free, no API key required.

    URL pattern: https://vip.stock.finance.sina.com.cn/corp/go.php/vCB_AllNewsStock/symbol/{code}.phtml
    """

    BASE_URL = "https://vip.stock.finance.sina.com.cn"

    def __init__(self, config: Dict):
        """
        Initialize Sina news fetcher.

        Args:
            config: Dict with optional keys:
                - timeout: Request timeout (default 15)
        """
        super().__init__(config)
        self.timeout = config.get("timeout", 15)
        logger.info("SinaStockNewsFetcher initialized")

    async def fetch_news(
        self,
        symbols: Optional[List[str]] = None,
        date: Optional[str] = None,
        limit: int = 50,
    ) -> List[NewsItem]:
        """
        Fetch Sina Finance stock news.

        If symbols are provided, fetches news for each symbol.
        Otherwise fetches general market news.

        Args:
            symbols: Stock codes to fetch news for
            date: Date filter
            limit: Max items

        Returns:
            List of NewsItem objects
        """
        if not symbols:
            # Fetch general market news from Sina Finance homepage
            symbols = ["000001"]  # Default: use SSE Composite related news

        all_news = []
        for symbol in symbols[:10]:  # Limit to 10 symbols to avoid rate issues
            try:
                symbol_news = await self._fetch_symbol_news(symbol, limit // len(symbols))
                all_news.extend(symbol_news)
            except Exception as e:
                logger.error(f"Failed to fetch news for {symbol}: {e}")

        logger.info(f"Fetched {len(all_news)} Sina news items across {len(symbols)} symbols")
        return all_news[:limit]

    async def _fetch_symbol_news(self, symbol: str, limit: int) -> List[NewsItem]:
        """
        Fetch news for a specific stock symbol from Sina.

        Args:
            symbol: 6-digit stock code
            limit: Max items for this symbol

        Returns:
            List of NewsItem objects
        """
        url = f"{self.BASE_URL}/corp/go.php/vCB_AllNewsStock/symbol/{symbol}.phtml"

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: requests.get(
                    url,
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=self.timeout,
                )
            )

            if response.status_code != 200:
                return []

            # Parse HTML with BeautifulSoup
            soup = BeautifulSoup(response.content, "html.parser", from_encoding="gb2312")
            news_items = []

            # Find news list items
            news_links = soup.find_all("a", href=re.compile(r"vCB_NewsDetail"))
            for link in news_links[:limit]:
                title = link.get_text(strip=True)
                href = link.get("href", "")
                # Extract date from nearby elements
                parent_row = link.find_parent("tr") or link.find_parent("div")
                date_text = ""
                if parent_row:
                    date_elem = parent_row.find(string=re.compile(r"\d{4}-\d{2}-\d{2}"))
                    if date_elem:
                        date_text = date_elem.strip()

                news_item = NewsItem(
                    timestamp=self._parse_date(date_text),
                    title=title,
                    content="",
                    source="sina",
                    url=f"{self.BASE_URL}{href}" if href.startswith("/") else href,
                    symbols=[symbol],
                    category="stock",
                )
                news_items.append(news_item)

            return news_items

        except Exception as e:
            logger.error(f"Failed to fetch Sina news for {symbol}: {e}")
            return []

    def _parse_date(self, date_text: str) -> datetime:
        """Parse date string, return current time on failure."""
        try:
            return datetime.strptime(date_text.strip(), "%Y-%m-%d %H:%M")
        except (ValueError, AttributeError):
            try:
                return datetime.strptime(date_text.strip(), "%Y-%m-%d")
            except (ValueError, AttributeError):
                return datetime.now()


class CryptoPanicNewsFetcher(BaseNewsFetcher):
    """
    CryptoPanic news fetcher for cryptocurrency news.

    CryptoPanic aggregates crypto news from multiple sources.
    Free tier: Limited API calls, public RSS feeds available.

    API: https://cryptopanic.com/api/ (free tier available)
    RSS: https://cryptopanic.com/news/rss/
    """

    RSS_URL = "https://cryptopanic.com/news/rss/"
    API_URL = "https://cryptopanic.com/api/v1/posts/"

    def __init__(self, config: Dict):
        """
        Initialize CryptoPanic fetcher.

        Args:
            config: Dict with optional keys:
                - api_key: CryptoPanic API key (for API access)
                - use_rss: Use RSS instead of API (default True for free)
        """
        super().__init__(config)
        self.api_key = config.get("api_key", "")
        self.use_rss = config.get("use_rss", True)
        logger.info("CryptoPanicNewsFetcher initialized")

    async def fetch_news(
        self,
        symbols: Optional[List[str]] = None,
        date: Optional[str] = None,
        limit: int = 50,
    ) -> List[NewsItem]:
        """
        Fetch cryptocurrency news from CryptoPanic.

        Args:
            symbols: Cryptocurrency filter (list of currencies like ['BTC', 'ETH'])
            date: Date filter
            limit: Max items

        Returns:
            List of NewsItem objects
        """
        if self.use_rss or not self.api_key:
            return await self._fetch_rss(symbols, limit)
        else:
            return await self._fetch_api(symbols, limit)

    async def _fetch_rss(
        self, symbols: Optional[List[str]], limit: int
    ) -> List[NewsItem]:
        """
        Fetch news via RSS feed (no API key required).

        Args:
            symbols: Currency filter
            limit: Max items

        Returns:
            List of NewsItem objects
        """
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: requests.get(
                    self.RSS_URL,
                    headers={"User-Agent": "QuantEngine/1.0"},
                    timeout=15,
                )
            )

            if response.status_code != 200:
                return []

            # Parse RSS XML
            root = ElementTree.fromstring(response.content)
            news_items = []

            for item in root.iter("item"):
                title = item.find("title")
                link = item.find("link")
                pub_date = item.find("pubDate")
                description = item.find("description")

                title_text = title.text if title is not None else ""
                desc_text = description.text if description is not None else ""

                # Extract crypto symbols from title/description
                crypto_symbols = self._extract_crypto_symbols(f"{title_text} {desc_text}")

                # Filter by requested symbols
                if symbols:
                    symbol_set = {s.upper() for s in symbols}
                    if not symbol_set.intersection({s.upper() for s in crypto_symbols}):
                        continue

                # Parse date
                try:
                    dt = datetime.strptime(
                        pub_date.text, "%a, %d %b %Y %H:%M:%S %z"
                    ) if pub_date is not None else datetime.now()
                except (ValueError, TypeError):
                    dt = datetime.now()

                news_item = NewsItem(
                    timestamp=dt,
                    title=title_text,
                    content=desc_text,
                    source="cryptopanic",
                    url=link.text if link is not None else "",
                    symbols=crypto_symbols,
                    category="crypto",
                )
                news_items.append(news_item)

                if len(news_items) >= limit:
                    break

            logger.info(f"Fetched {len(news_items)} CryptoPanic RSS items")
            return news_items

        except Exception as e:
            logger.error(f"Failed to fetch CryptoPanic RSS: {e}")
            return []

    async def _fetch_api(
        self, symbols: Optional[List[str]], limit: int
    ) -> List[NewsItem]:
        """
        Fetch news via CryptoPanic API (requires API key).

        Args:
            symbols: Currency filter
            limit: Max items

        Returns:
            List of NewsItem objects
        """
        try:
            params = {
                "auth_token": self.api_key,
                "kind": "news",
                "limit": min(limit, 50),
            }
            if symbols:
                params["currencies"] = ",".join(symbols)

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: requests.get(self.API_URL, params=params, timeout=15)
            )

            if response.status_code != 200:
                return []

            data = response.json()
            news_items = []

            for post in data.get("results", []):
                currencies = [
                    c.get("code", "")
                    for c in post.get("currencies", [])
                ]
                news_item = NewsItem(
                    timestamp=datetime.fromisoformat(
                        post.get("published_at", "").replace("Z", "+00:00")
                    ),
                    title=post.get("title", ""),
                    content=post.get("body", ""),
                    source="cryptopanic",
                    url=post.get("url", ""),
                    symbols=currencies,
                    category="crypto",
                )
                news_items.append(news_item)

            logger.info(f"Fetched {len(news_items)} CryptoPanic API items")
            return news_items

        except Exception as e:
            logger.error(f"Failed to fetch CryptoPanic API: {e}")
            return []

    def _extract_crypto_symbols(self, text: str) -> List[str]:
        """
        Extract cryptocurrency symbols from text.

        Args:
            text: News text

        Returns:
            List of crypto symbols found
        """
        # Common crypto symbols to look for
        known_symbols = [
            "BTC", "ETH", "XRP", "SOL", "ADA", "DOGE", "AVAX",
            "DOT", "MATIC", "LINK", "UNI", "ATOM", "LTC", "FIL",
            "APT", "ARB", "OP", "SUI", "PEPE", "SHIB", "USDT", "USDC",
        ]

        found = []
        text_upper = text.upper()
        for sym in known_symbols:
            if sym in text_upper:
                found.append(sym)

        return found


class CompositeNewsFetcher(BaseNewsFetcher):
    """
    Composite news fetcher that aggregates multiple news sources.

    Merges results from all configured fetchers, deduplicates by title,
    and returns combined results sorted by timestamp.
    """

    def __init__(self, config: Dict, fetchers: List[BaseNewsFetcher]):
        """
        Initialize composite fetcher.

        Args:
            config: Configuration dict
            fetchers: List of BaseNewsFetcher instances to aggregate
        """
        super().__init__(config)
        self.fetchers = fetchers
        logger.info(f"CompositeNewsFetcher initialized with {len(fetchers)} sources")

    async def fetch_news(
        self,
        symbols: Optional[List[str]] = None,
        date: Optional[str] = None,
        limit: int = 100,
    ) -> List[NewsItem]:
        """
        Fetch and aggregate news from all configured sources.

        Args:
            symbols: Symbol filter
            date: Date filter
            limit: Total max items

        Returns:
            Combined, deduplicated, sorted list of NewsItem objects
        """
        all_news = []

        # Fetch from all sources concurrently
        tasks = [
            fetcher.fetch_news(symbols, date, limit // len(self.fetchers))
            for fetcher in self.fetchers
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Fetcher {self.fetchers[i].__class__.__name__} failed: {result}")
            else:
                all_news.extend(result)

        # Deduplicate by title hash
        seen_hashes = set()
        deduped = []
        for item in all_news:
            title_hash = hashlib.md5(item.title.encode()).hexdigest()
            if title_hash not in seen_hashes:
                seen_hashes.add(title_hash)
                deduped.append(item)

        # Sort by timestamp (newest first)
        deduped.sort(key=lambda x: x.timestamp, reverse=True)

        result = deduped[:limit]
        logger.info(
            f"Composite fetcher: {len(all_news)} raw → {len(deduped)} deduped → {len(result)} final"
        )
        return result
