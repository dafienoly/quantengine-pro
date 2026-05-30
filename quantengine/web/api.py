"""
QuantEngine Pro - FastAPI REST + WebSocket Backend
====================================================
Provides API endpoints for the dashboard:
- REST: /api/equity, /api/positions, /api/trades, /api/strategies
- WebSocket: /ws for real-time updates
- Backtest: /api/backtest/run, /api/backtest/status
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

# Global state references (set by main app)
backtest_engine = None
live_executor = None
market_overview = None
llm_service = None
strategy_registry = None


def create_app() -> FastAPI:
    """
    Create and configure FastAPI application.

    Returns:
        Configured FastAPI app instance
    """
    app = FastAPI(
        title="QuantEngine Pro API",
        description="Quantitative Trading System API",
        version="0.1.0",
    )

    # CORS for dashboard access
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---- REST Endpoints ----

    @app.get("/api/health")
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "version": "0.1.0",
        }

    @app.get("/api/equity")
    async def get_equity_curve():
        """Get equity curve data."""
        if backtest_engine and hasattr(backtest_engine, "equity_curve"):
            df = backtest_engine.equity_curve
            if not df.empty:
                return {
                    "data": json.loads(df.to_json(orient="records", date_format="iso")),
                }
        return {"data": []}

    @app.get("/api/positions")
    async def get_positions():
        """Get current positions."""
        if backtest_engine and hasattr(backtest_engine, "position_manager"):
            positions = backtest_engine.position_manager.get_all_positions()
            return {
                "positions": [
                    {
                        "symbol": p.symbol,
                        "quantity": p.quantity,
                        "avg_price": p.avg_price,
                        "current_price": p.current_price,
                        "unrealized_pnl": p.unrealized_pnl,
                        "side": p.side.value,
                    }
                    for p in positions
                ],
            }
        return {"positions": []}

    @app.get("/api/trades")
    async def get_trades(limit: int = 100):
        """Get trade history."""
        if backtest_engine:
            trades = backtest_engine.position_manager.get_trades()
            return {"trades": trades[-limit:]}
        return {"trades": []}

    @app.get("/api/performance")
    async def get_performance():
        """Get performance metrics."""
        if backtest_engine and backtest_engine.report:
            return {"report": backtest_engine.report}
        return {"report": {}}

    @app.get("/api/strategies")
    async def get_strategies():
        """Get active strategies."""
        if strategy_registry:
            strategies = []
            for name, strategy in strategy_registry.get_all().items():
                config = strategy_registry.get_config(name) or {}
                strategies.append({
                    "name": name,
                    "class": strategy.__class__.__name__,
                    "symbols": config.get("symbols", []),
                    "timeframe": config.get("timeframe", "1d"),
                    "weight": config.get("weight", 1.0),
                    "signals_generated": strategy.signal_count,
                })
            return {"strategies": strategies}
        return {"strategies": []}

    @app.get("/api/market/overview")
    async def get_market_overview():
        """Get market overview dashboard data."""
        if market_overview:
            return await market_overview.get_dashboard()
        return {"available": False}

    @app.post("/api/backtest/run")
    async def run_backtest(config: Dict):
        """Start a backtest with given configuration."""
        return {"status": "not_implemented", "message": "Use CLI for backtesting"}

    @app.get("/api/llm/analysis/{symbol}")
    async def get_llm_analysis(symbol: str):
        """Get LLM analysis for a symbol."""
        if llm_service:
            try:
                result = await llm_service.analyze_symbol(
                    symbol=symbol,
                    technical_data="Recent data placeholder",
                )
                return {
                    "symbol": symbol,
                    "sentiment": result.sentiment,
                    "summary": result.summary,
                    "confidence": result.confidence,
                }
            except Exception as e:
                return {"error": str(e)}
        return {"available": False}

    # ---- WebSocket ----

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket endpoint for real-time data streaming."""
        await websocket.accept()
        logger.info("WebSocket client connected")

        try:
            while True:
                # Build real-time update
                update = {
                    "timestamp": datetime.now().isoformat(),
                    "equity": 0,
                    "positions": [],
                }

                if backtest_engine:
                    update["equity"] = backtest_engine.position_manager.total_equity

                if live_executor:
                    update["stats"] = live_executor.stats

                await websocket.send_json(update)
                await asyncio.sleep(1)  # 1 second update interval

        except WebSocketDisconnect:
            logger.info("WebSocket client disconnected")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")

    return app
