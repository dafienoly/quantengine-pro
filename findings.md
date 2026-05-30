# QuantEngine Pro - Findings & Research

## Architecture Decisions
- Python 3.10+ as primary language
- Poetry for dependency management
- YAML for all configuration
- asyncio for async operations
- plotly + dash for visualization
- openai library for DeepSeek LLM (OpenAI-compatible API)

## Data Source Notes
- akshare: free A-share data, rate-limited
- CCXT: crypto exchange unified API, free
- EastMoney: free web API, needs parsing
- Cailian: RSS feed for financial news
- DeepSeek: free tier available, OpenAI-compatible

## Key Design Patterns
- Abstract base classes for all pluggable components
- Factory pattern for strategy/fetcher creation
- Observer pattern via EventBus
- Strategy pattern for trading algorithms
- Adapter pattern for broker/LLM integration
