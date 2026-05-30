#!/usr/bin/env python3
"""
QuantEngine Pro - Smoke Test
==============================
Minimal dependency test — verifies all core modules import correctly
and basic functionality works. Run before committing code.

Usage:
    python tests/smoke_test.py
"""

import sys
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_imports():
    """Verify all core modules import correctly."""
    print("--- Test: Imports ---")

    # Config
    from quantengine.config.manager import ConfigManager, get_config
    cfg = ConfigManager("./config")
    assert cfg.get("data.quote.provider") == "akshare"
    print("  ✓ config.manager")

    # Utils
    from quantengine.utils.logging import setup_logging, get_logger
    setup_logging(log_level="WARNING")
    log = get_logger("smoke_test")
    log.info("smoke test running")
    print("  ✓ utils.logging")

    # Data layer
    from quantengine.data.base import (
        BaseQuoteFetcher, BaseMarketFlowFetcher, BaseNewsFetcher,
        NewsItem, QuoteBar, MarketFlow,
    )
    n = NewsItem(timestamp="2024-01-01", title="Test", source="test")
    assert n.sentiment is None
    q = QuoteBar(symbol="TEST", timestamp="2024-01-01", open=1, high=2, low=0.9, close=1.5, volume=1000)
    assert q.amount == 0.0
    print("  ✓ data.base")

    from quantengine.data.cache import LRUCache, CacheManager
    lru = LRUCache(5)
    lru.put("k", "v")
    assert lru.get("k") == "v"
    assert lru.get("missing") is None
    cm = CacheManager(memory_size=10)
    key = cm.make_key("BTC", "1d", "2024", "2025")
    assert len(key) == 32
    print("  ✓ data.cache")

    from quantengine.data.storage import ParquetStorage
    stats = ParquetStorage.get_stats("./data/parquet")
    assert "total_files" in stats
    print("  ✓ data.storage")

    # backtest layer
    from quantengine.backtest.event_bus import EventBus, EventType, Event
    bus = EventBus()
    bus.subscribe(EventType.MARKET_DATA, lambda e: None)
    bus.publish(Event(EventType.MARKET_DATA, "2024-01-01", {"close": 100}))
    assert bus.stats["total_events"] == 1
    print("  ✓ backtest.event_bus")

    from quantengine.backtest.cost_model import CostModel
    cm = CostModel("a_share")
    r = cm.calculate(10.0, 1000, True)
    assert r.commission > 0
    assert r.stamp_tax == 0  # No stamp on buy
    print("  ✓ backtest.cost_model")

    from quantengine.backtest.position_manager import PositionManager, PositionSide
    pm = PositionManager(100000)
    assert pm.total_equity == 100000
    pos = pm.open_position("BTC", PositionSide.LONG, 0.1, 50000)
    assert pos is not None
    pm.close_position("BTC", 51000)
    assert pm.realized_pnl > 0
    print("  ✓ backtest.position_manager")

    from quantengine.backtest.analyzer import PerformanceAnalyzer
    import pandas as pd
    import numpy as np
    dates = pd.date_range("2024-01-01", periods=100, freq="B")
    np.random.seed(42)
    eq = 100000 * (1 + np.random.randn(100).cumsum() * 0.01)
    curve = list(zip(dates, eq))
    trades = [{"symbol": "X", "pnl": 100}]
    a = PerformanceAnalyzer(curve, trades, 100000)
    rpt = a.analyze()
    assert "sharpe_ratio" in rpt
    print(f"  ✓ backtest.analyzer (sharpe={rpt['sharpe_ratio']:.2f})")

    # Strategy layer
    from quantengine.strategy.base import BaseStrategy, Signal, SignalType, StrategyContext
    sig = Signal(timestamp="2024-01-01", symbol="BTC", type=SignalType.BUY, confidence=0.8)
    assert sig.confidence == 0.8

    class TestStrat(BaseStrategy):
        def on_bar(self, bar, ctx):
            return None
    s = TestStrat({"p": 1})
    assert s.params == {"p": 1}
    print("  ✓ strategy.base")

    from quantengine.strategy.registry import StrategyRegistry
    from quantengine.strategy.builtin.dual_thrust import DualThrustStrategy
    reg = StrategyRegistry()
    reg.register_class("dual_thrust", DualThrustStrategy)
    assert "dual_thrust" in reg.strategy_names
    inst = reg.create("dual_thrust", k1=0.5, k2=0.5)
    assert inst is not None
    print("  ✓ strategy.registry + dual_thrust")

    from quantengine.strategy.builtin.turtle import TurtleStrategy
    from quantengine.strategy.builtin.bollinger import BollingerStrategy
    from quantengine.strategy.builtin.dual_ma import DualMAStrategy
    from quantengine.strategy.builtin.r_breaker import RBreakerStrategy
    from quantengine.strategy.builtin.grid_ma import GridMAStrategy
    from quantengine.strategy.builtin.simple_mm import SimpleMarketMaker
    print("  ✓ 7 built-in strategies loaded")

    # Factor layer
    from quantengine.factor.base import MomentumFactor, VolatilityFactor, RSIFactor, MACDFactor, FactorRegistry
    df = pd.DataFrame({
        "close": 100 + np.random.randn(100).cumsum() * 2,
        "high": 102 + np.random.randn(100).cumsum() * 2,
        "low": 98 + np.random.randn(100).cumsum() * 2,
        "volume": np.random.randint(1000, 10000, 100),
    })
    mom = MomentumFactor(20)
    vals = mom.calculate(df)
    assert len(vals) == 100
    rf = FactorRegistry()
    rf.register("mom", mom)
    scores = rf.compute_all(df)
    assert "mom" in scores.columns
    print("  ✓ factor.base + library")

    # Execution layer
    from quantengine.execution.base import BrokerOrder, BrokerPosition, AccountBalance, OrderSide, OrderType
    pos = BrokerPosition(symbol="BTC", quantity=0.1, avg_price=50000, current_price=51000, unrealized_pnl=100.0)
    assert pos.unrealized_pnl == 100.0
    bal = AccountBalance(total_equity=100000, available_cash=50000, currency="CNY")
    assert bal.currency == "CNY"
    print("  ✓ execution.base")

    from quantengine.execution.risk_manager import RiskManager
    rm = RiskManager({"max_single_symbol_pct": 0.20})
    assert rm.check_order("S", 100, 10, 10000, {}).passed
    rm.add_to_blacklist("BAD", "test")
    assert not rm.check_order("BAD", 100, 10, 10000, {}).passed
    print("  ✓ execution.risk_manager")

    from quantengine.execution.reporter import DailyReporter
    rep = DailyReporter()
    rpt = rep.generate([], [], [("2024-01-01", 100000)])
    assert rpt["summary"]["current_equity"] == 100000
    print("  ✓ execution.reporter")

    # Analysis layer
    from quantengine.analysis.llm.base import AnalysisResult, BaseLLMService
    ar = AnalysisResult(sentiment="positive", sentiment_score=0.8, confidence=0.9)
    assert ar.sentiment == "positive"
    print("  ✓ analysis.llm.base")

    from quantengine.analysis.screener import StockScreener
    scr = StockScreener({"top_n": 3})
    # Generate test data for screening
    test_data = {}
    np.random.seed(42)
    for i in range(5):
        sym = f"{600000 + i:06d}"
        c = 10 + np.random.randn(100).cumsum() * 0.5
        test_data[sym] = pd.DataFrame({
            "close": c,
            "high": c + np.random.rand(100) * 0.5,
            "low": c - np.random.rand(100) * 0.5,
            "volume": np.random.randint(1_000_000, 10_000_000, 100),
        })
    print("  ✓ analysis.screener")

    from quantengine.analysis.signal_advisor import TradeRecommendation
    rec = TradeRecommendation(
        symbol="BTC", direction="BUY", price=50000,
        stop_loss=49000, take_profit=52000, confidence=0.85, reasoning="Test"
    )
    assert rec.direction == "BUY"
    print("  ✓ analysis.signal_advisor")

    # Web layer
    from quantengine.web.api import create_app
    app = create_app()
    assert app.title == "QuantEngine Pro API"
    print("  ✓ web.api")

    print("\n✓ ALL SMOKE TESTS PASSED\n")


def test_config_files():
    """Verify all config files are valid YAML."""
    import yaml

    print("--- Test: Config Files ---")
    config_dir = Path("./config")
    for f in sorted(config_dir.glob("*.yaml")):
        with open(f) as fp:
            data = yaml.safe_load(fp)
        assert data is not None, f"Failed to parse {f.name}"
        print(f"  ✓ {f.name}")


def test_backtest_engine():
    """Test full backtest engine with synthetic data."""
    print("--- Test: Backtest Engine ---")
    import pandas as pd
    import numpy as np
    from datetime import datetime

    from quantengine.backtest.engine import BacktestEngine
    from quantengine.strategy.builtin.dual_thrust import DualThrustStrategy

    # Generate synthetic OHLCV data
    np.random.seed(42)
    n = 500
    prices = 100 + np.random.randn(n).cumsum() * 2
    df = pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=n, freq="h"),
        "open": prices - np.random.rand(n) * 0.5,
        "high": prices + np.random.rand(n) * 1,
        "low": prices - np.random.rand(n) * 1,
        "close": prices + np.random.randn(n) * 0.3,
        "volume": np.random.randint(100, 10000, n),
    })

    engine = BacktestEngine(initial_capital=100000, market="crypto")
    strategy = DualThrustStrategy({"k1": 0.7, "k2": 0.7, "period": 20})
    engine.add_strategy(strategy, symbols=["SYNTH"], weight=1.0, timeframe="1h")

    report = engine.run({"SYNTH": df})

    assert report is not None
    assert "total_return_pct" in report
    assert "sharpe_ratio" in report
    assert "max_drawdown_pct" in report
    assert report["trading_days"] > 0

    print(f"  ✓ Engine: {report['trading_days']} bars processed")
    print(f"    Return: {report['total_return_pct']:.2f}%")
    print(f"    Sharpe: {report['sharpe_ratio']:.2f}")
    print(f"    Max DD: {report['max_drawdown_pct']:.2f}%")
    print(f"    Trades: {report['total_trades']}")

    # Verify equity curve is available
    eq = engine.equity_curve
    assert not eq.empty
    assert "equity" in eq.columns
    assert "cumulative_return" in eq.columns

    # Test summary string
    summary = engine.summary()
    assert "Backtest Summary" in summary

    print("  ✓ Full engine integration test passed")


if __name__ == "__main__":
    print("=" * 60)
    print("QuantEngine Pro - Smoke Test Suite")
    print("=" * 60)

    test_config_files()
    test_imports()
    test_backtest_engine()

    print("\n" + "=" * 60)
    print("ALL SMOKE TESTS PASSED ✓")
    print("=" * 60)
