"""
QuantEngine Pro - FastAPI REST + WebSocket Backend
====================================================
Provides endpoints: /api/health, /api/equity, /api/positions,
/api/trades, /api/performance, /api/strategies, /api/market/overview,
/api/llm/analysis/{symbol}, /api/backtest/run
WebSocket: /ws for real-time updates
"""

import asyncio
import json
from datetime import datetime
from typing import Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

# Global references set by main app
backtest_engine = None
live_executor = None
market_overview = None
llm_service = None
strategy_registry = None


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="QuantEngine Pro API",
        description="Quantitative Trading System API",
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"], allow_credentials=True,
        allow_methods=["*"], allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "timestamp": datetime.now().isoformat(), "version": "0.1.0"}

    @app.get("/api/equity")
    async def get_equity():
        if backtest_engine and hasattr(backtest_engine, "equity_curve"):
            df = backtest_engine.equity_curve
            if not df.empty:
                return {"data": json.loads(df.to_json(orient="records", date_format="iso"))}
        return {"data": []}

    @app.get("/api/positions")
    async def get_positions():
        if backtest_engine and hasattr(backtest_engine, "position_manager"):
            positions = backtest_engine.position_manager.get_all_positions()
            return {"positions": [
                {"symbol": p.symbol, "quantity": p.quantity, "avg_price": p.avg_price,
                 "current_price": p.current_price, "unrealized_pnl": p.unrealized_pnl,
                 "side": p.side.value} for p in positions
            ]}
        return {"positions": []}

    @app.get("/api/trades")
    async def get_trades(limit: int = 100):
        if backtest_engine:
            trades = backtest_engine.position_manager.get_trades()
            return {"trades": trades[-limit:]}
        return {"trades": []}

    @app.get("/api/performance")
    async def get_performance():
        if backtest_engine and backtest_engine.report:
            return {"report": backtest_engine.report}
        return {"report": {}}

    @app.get("/api/strategies")
    async def get_strategies():
        if strategy_registry:
            strategies = []
            for name, strat in strategy_registry.get_all().items():
                cfg = strategy_registry.get_config(name) or {}
                strategies.append({
                    "name": name, "class": strat.__class__.__name__,
                    "symbols": cfg.get("symbols", []),
                    "timeframe": cfg.get("timeframe", "1d"),
                    "weight": cfg.get("weight", 1.0),
                    "signals": strat.signal_count,
                })
            return {"strategies": strategies}
        return {"strategies": []}

    @app.get("/api/market/overview")
    async def get_market():
        if market_overview:
            return await market_overview.get_dashboard()
        return {"available": False}

    @app.post("/api/backtest/run")
    async def run_backtest(config: Dict):
        return {"status": "not_implemented", "message": "Use CLI: python scripts/run_backtest.py"}

    @app.get("/api/llm/analysis/{symbol}")
    async def get_llm(symbol: str):
        if llm_service:
            try:
                result = await llm_service.analyze_symbol(symbol=symbol, technical_data="Recent data")
                return {"symbol": symbol, "sentiment": result.sentiment,
                        "summary": result.summary, "confidence": result.confidence}
            except Exception as e:
                return {"error": str(e)}
        return {"available": False}

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket):
        await websocket.accept()
        logger.info("WebSocket connected")
        try:
            while True:
                update = {"timestamp": datetime.now().isoformat(), "equity": 0, "positions": []}
                if backtest_engine:
                    update["equity"] = backtest_engine.position_manager.total_equity
                if live_executor:
                    update["stats"] = live_executor.stats
                await websocket.send_json(update)
                await asyncio.sleep(1)
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")

    return app
