"""
QuantEngine Pro - Event-Driven Backtest Engine
================================================
Core backtest engine that simulates strategy execution over historical data.

Process (per bar):
    1. Publish MARKET_DATA event with new bar
    2. Strategy.on_bar() generates Signals
    3. Broker validates and fills orders
    4. PositionManager updates portfolio state
    5. Record equity curve

Supports:
- Single and multi-strategy backtests
- Full transaction cost simulation
- Multi-strategy capital competition
- Stop-loss / take-profit / forced liquidation
- Daily settlement and equity recording
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from loguru import logger

from quantengine.backtest.broker import Broker
from quantengine.backtest.cost_model import CostModel
from quantengine.backtest.event_bus import Event, EventBus, EventType
from quantengine.backtest.position_manager import PositionManager
from quantengine.strategy.base import (
    BaseStrategy,
    Signal,
    SignalType,
    StrategyContext,
)
from quantengine.strategy.registry import StrategyRegistry


class BacktestEngine:
    """
    Event-driven backtest engine.

    Orchestrates the full backtest cycle: data → strategy → order → fill → update.

    Usage:
        engine = BacktestEngine(initial_capital=100000)
        engine.add_strategy(strategy_instance, symbols=["BTC/USDT"], weight=1.0)
        report = engine.run(data_dict)
    """

    def __init__(
        self,
        initial_capital: float = 100000.0,
        market: str = "crypto",
        cost_config: Optional[Dict] = None,
        risk_config: Optional[Dict] = None,
    ):
        """
        Initialize backtest engine.

        Args:
            initial_capital: Starting portfolio value
            market: 'a_share' or 'crypto'
            cost_config: Override default cost parameters
            risk_config: Override default risk parameters
        """
        self.initial_capital = initial_capital
        self.market = market

        # Core components
        self.event_bus = EventBus()
        self.cost_model = CostModel(market, cost_config)
        self.position_manager = PositionManager(
            initial_capital=initial_capital,
            **(risk_config or {})
        )
        self.broker = Broker(
            self.position_manager,
            self.cost_model,
        )

        # Strategy tracking
        self._strategies: Dict[str, BaseStrategy] = {}
        self._strategy_configs: Dict[str, Dict] = {}

        # State
        self._is_running = False
        self._current_time: Optional[datetime] = None
        self._bar_count = 0

        # Results
        self._equity_curve: List[Tuple[datetime, float]] = []
        self._daily_returns: List[Tuple[datetime, float]] = []
        self._signals_generated: List[Signal] = []
        self._report: Optional[Dict] = None

        # Register internal event handlers
        self._register_handlers()

        logger.info(
            f"BacktestEngine initialized: market={market}, "
            f"capital={initial_capital:,.0f}"
        )

    def _register_handlers(self) -> None:
        """Register internal event handlers for the backtest lifecycle."""

        def on_risk_violation(event: Event) -> None:
            data = event.data or {}
            logger.warning(
                f"Risk violation: {data.get('type')} on {data.get('symbol')}"
            )

        def on_margin_call(event: Event) -> None:
            data = event.data or {}
            logger.error(
                f"Margin call: {data.get('symbol')} "
                f"margin_ratio={data.get('margin_ratio', 0):.2%}"
            )
            # Force close position
            symbol = data.get("symbol")
            strategy = data.get("strategy", "default")
            if symbol:
                self.position_manager.close_position(
                    symbol=symbol,
                    price=data.get("position", None).current_price if data.get("position") else 0,
                    strategy_name=strategy,
                )

        self.event_bus.subscribe(EventType.RISK_VIOLATION, on_risk_violation)
        self.event_bus.subscribe(EventType.MARGIN_CALL, on_margin_call)

    # ---- Strategy Management ----

    def add_strategy(
        self,
        strategy: BaseStrategy,
        symbols: List[str],
        weight: float = 1.0,
        timeframe: str = "1d",
    ) -> None:
        """
        Add a strategy to the backtest.

        Args:
            strategy: Strategy instance
            symbols: Trading symbols for this strategy
            weight: Capital allocation weight
            timeframe: Bar frequency
        """
        name = getattr(strategy, "name", strategy.__class__.__name__)
        self._strategies[name] = strategy
        self._strategy_configs[name] = {
            "symbols": symbols,
            "weight": weight,
            "timeframe": timeframe,
        }
        self.position_manager.set_strategy_weight(name, weight)
        strategy.on_start()
        logger.info(f"Strategy added: {name} on {symbols} (weight={weight})")

    def add_strategies_from_registry(
        self,
        registry: StrategyRegistry,
    ) -> None:
        """
        Add all active strategies from a StrategyRegistry.

        Args:
            registry: Configured strategy registry
        """
        for name, strategy in registry.get_all().items():
            config = registry.get_config(name)
            if config:
                self.add_strategy(
                    strategy=strategy,
                    symbols=config.get("symbols", []),
                    weight=config.get("weight", 1.0),
                    timeframe=config.get("timeframe", "1d"),
                )

    # ---- Main Backtest Loop ----

    def run(
        self,
        data: Dict[str, pd.DataFrame],
        progress_callback: Optional[callable] = None,
    ) -> Dict:
        """
        Run backtest over historical data.

        Args:
            data: Dict mapping symbol → DataFrame with OHLCV data
                  DataFrames must have columns: timestamp, open, high, low, close, volume
            progress_callback: Optional callback(current_step, total_steps) for progress

        Returns:
            Dict with backtest report (equity curve, trades, performance metrics)
        """
        self._is_running = True
        start_time = datetime.now()

        # Publish start event
        self.event_bus.publish(Event(
            type=EventType.BACKTEST_START,
            timestamp=datetime.now(),
            data={"initial_capital": self.initial_capital},
            source="engine",
        ))

        # Align and sort all timestamps
        all_timestamps = self._align_timestamps(data)
        total_steps = len(all_timestamps)
        logger.info(f"Backtest starting: {total_steps} bars to process")

        for step, timestamp in enumerate(all_timestamps):
            self._current_time = timestamp
            self._bar_count = step

            # Collect current bar data for all symbols
            bar_data = {}
            for symbol, df in data.items():
                bar_rows = df[df["timestamp"] == timestamp]
                if not bar_rows.empty:
                    bar_data[symbol] = bar_rows.iloc[0]

            if not bar_data:
                continue

            # Step 1: Publish market data event
            self.event_bus.publish(Event(
                type=EventType.MARKET_DATA,
                timestamp=timestamp,
                data=bar_data,
                source="engine",
            ))

            # Step 2: Generate signals from all strategies
            all_signals = self._generate_signals(bar_data, data)

            # Step 3: Submit and fill orders
            if all_signals:
                # Submit all signals (use first symbol's price as reference)
                any_price = list(bar_data.values())[0].get("close", 0)
                orders = self.broker.submit_signals(all_signals, any_price, timestamp)

                # Fill orders
                filled = self.broker.fill_orders(orders, bar_data, timestamp)

                # Publish fill events
                for order in filled:
                    self.event_bus.publish(Event(
                        type=EventType.ORDER_FILLED,
                        timestamp=timestamp,
                        data=order,
                        source="broker",
                    ))

            # Step 4: Update position prices and check risk
            for symbol, bar in bar_data.items():
                self.position_manager.update_price(symbol, bar.get("close", 0))

            # Check risk events
            risk_events = self.position_manager.check_risk_events()
            for re in risk_events:
                if re["type"] in ("margin_call", "force_liquidate"):
                    self.event_bus.publish(Event(
                        type=EventType.MARGIN_CALL,
                        timestamp=timestamp,
                        data=re,
                        source="position_manager",
                    ))
                elif re["type"] in ("stop_loss", "take_profit"):
                    # Auto-close on stop-loss/take-profit
                    pos = re["position"]
                    self.position_manager.close_position(
                        symbol=re["symbol"],
                        price=pos.current_price,
                        strategy_name=re["strategy"],
                    )

            # Step 5: Record equity
            self.position_manager.record_equity(timestamp)
            self._equity_curve.append((timestamp, self.position_manager.total_equity))

            # Daily settlement
            self.event_bus.publish(Event(
                type=EventType.BAR_CLOSE,
                timestamp=timestamp,
                data={"equity": self.position_manager.total_equity},
                source="engine",
            ))

            # Progress
            if progress_callback and step % 100 == 0:
                progress_callback(step, total_steps)

        # Publish end event
        self.event_bus.publish(Event(
            type=EventType.BACKTEST_END,
            timestamp=datetime.now(),
            data={"final_equity": self.position_manager.total_equity},
            source="engine",
        ))

        # Generate report
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"Backtest completed in {elapsed:.1f}s: {total_steps} bars processed")

        self._is_running = False
        self._report = self._generate_report()
        return self._report

    def _generate_signals(
        self,
        bar_data: Dict[str, pd.Series],
        full_data: Dict[str, pd.DataFrame],
    ) -> List[Signal]:
        """
        Generate trading signals from all strategies for current bar.

        Args:
            bar_data: Current bar for each symbol
            full_data: Full historical data for context

        Returns:
            List of trading signals
        """
        all_signals = []

        for strategy_name, strategy in self._strategies.items():
            config = self._strategy_configs.get(strategy_name, {})
            strategy_symbols = config.get("symbols", [])

            for symbol in strategy_symbols:
                if symbol not in bar_data:
                    continue

                bar = bar_data[symbol]
                history = full_data.get(symbol, pd.DataFrame())

                # Build strategy context
                context = StrategyContext(
                    symbol=symbol,
                    timeframe=config.get("timeframe", "1d"),
                    current_bar=bar,
                    history=history[history["timestamp"] <= self._current_time],
                    positions={
                        sym: {
                            "quantity": pos.quantity,
                            "avg_price": pos.avg_price,
                            "pnl": pos.unrealized_pnl,
                        }
                        for sym, pos in self.position_manager.get_strategy_positions(
                            strategy_name
                        ).items()
                    },
                    portfolio_value=self.position_manager.total_equity,
                    cash=self.position_manager.cash,
                    metadata={"strategy_name": strategy_name},
                )

                try:
                    signal = strategy.on_bar(bar, context)
                    if signal is not None:
                        # Enrich signal with strategy info
                        signal.metadata["strategy_name"] = strategy_name
                        all_signals.append(signal)
                        self._signals_generated.append(signal)
                except Exception as e:
                    logger.error(
                        f"Strategy {strategy_name} error on {symbol}: {e}"
                    )

        return all_signals

    def _align_timestamps(self, data: Dict[str, pd.DataFrame]) -> List[datetime]:
        """
        Align timestamps across all data series.

        Returns sorted unique timestamps present in any series.

        Args:
            data: Symbol → DataFrame mapping

        Returns:
            Sorted list of datetime objects
        """
        all_ts = set()
        for df in data.values():
            if "timestamp" in df.columns:
                all_ts.update(df["timestamp"].dropna().tolist())
        return sorted(all_ts)

    def _generate_report(self) -> Dict:
        """Generate comprehensive backtest report."""
        from quantengine.backtest.analyzer import PerformanceAnalyzer

        analyzer = PerformanceAnalyzer(
            equity_curve=self._equity_curve,
            trades=self.position_manager.get_trades(),
            initial_capital=self.initial_capital,
            signals=self._signals_generated,
        )

        return analyzer.analyze()

    # ---- Accessors ----

    @property
    def equity_curve(self) -> pd.DataFrame:
        """Get equity curve as DataFrame."""
        if not self._equity_curve:
            return pd.DataFrame()
        df = pd.DataFrame(self._equity_curve, columns=["timestamp", "equity"])
        df["return"] = df["equity"].pct_change()
        df["cumulative_return"] = df["equity"] / self.initial_capital - 1
        return df

    @property
    def trades(self) -> pd.DataFrame:
        """Get all trades as DataFrame."""
        trades = self.position_manager.get_trades()
        if not trades:
            return pd.DataFrame()
        return pd.DataFrame(trades)

    @property
    def report(self) -> Optional[Dict]:
        """Get the latest backtest report."""
        return self._report

    def summary(self) -> str:
        """Get a human-readable summary of the backtest."""
        if not self._report:
            return "No backtest report available. Run engine.run() first."

        r = self._report
        return (
            f"===== Backtest Summary =====\n"
            f"Period: {r.get('start_date', 'N/A')} → {r.get('end_date', 'N/A')}\n"
            f"Initial Capital: {self.initial_capital:,.2f}\n"
            f"Final Equity: {r.get('final_equity', 0):,.2f}\n"
            f"Total Return: {r.get('total_return_pct', 0):.2f}%\n"
            f"Annual Return: {r.get('annual_return_pct', 0):.2f}%\n"
            f"Sharpe Ratio: {r.get('sharpe_ratio', 0):.2f}\n"
            f"Max Drawdown: {r.get('max_drawdown_pct', 0):.2f}%\n"
            f"Win Rate: {r.get('win_rate_pct', 0):.2f}%\n"
            f"Total Trades: {r.get('total_trades', 0)}\n"
            f"Profit Factor: {r.get('profit_factor', 0):.2f}\n"
            f"Total Costs: {r.get('total_costs', 0):,.2f}\n"
            f"==========================="
        )
