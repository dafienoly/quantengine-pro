"""
QuantEngine Pro - Live Executor
=================================
Main execution loop that bridges strategy signals to broker orders.

Process:
    1. Scan strategy symbols at configurable interval
    2. Fetch latest market data
    3. Call strategy.on_bar() to generate signals
    4. Pass signals through risk manager
    5. Place orders via broker client
    6. Monitor fills and positions
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional

from loguru import logger

from quantengine.execution.base import (
    BaseBrokerClient,
    OrderSide,
    OrderType,
)
from quantengine.execution.risk_manager import RiskManager
from quantengine.strategy.base import BaseStrategy, Signal, SignalType


class LiveExecutor:
    """
    Real-time trading executor.

    Orchestrates the scan → signal → risk → order → monitor loop.

    Usage:
        executor = LiveExecutor(broker_client, risk_manager)
        executor.add_strategy(strategy, symbols=["BTC/USDT"], timeframe="5m")
        await executor.start()
    """

    def __init__(
        self,
        broker_client: BaseBrokerClient,
        risk_manager: Optional[RiskManager] = None,
        scan_interval: float = 10.0,
        order_timeout: float = 30.0,
        max_retries: int = 3,
    ):
        """
        Initialize live executor.

        Args:
            broker_client: Connected broker client instance
            risk_manager: Risk manager instance (created if None)
            scan_interval: Seconds between strategy scans (default 10s)
            order_timeout: Seconds before cancelling unfilled order (default 30s)
            max_retries: Max order retry attempts (default 3)
        """
        self.broker = broker_client
        self.risk_manager = risk_manager or RiskManager()
        self.scan_interval = scan_interval
        self.order_timeout = order_timeout
        self.max_retries = max_retries

        # Strategy tracking
        self._strategies: Dict[str, BaseStrategy] = {}
        self._strategy_symbols: Dict[str, List[str]] = {}
        self._strategy_timeframes: Dict[str, str] = {}

        # State
        self._is_running = False
        self._scan_count = 0
        self._signals_generated = 0
        self._orders_placed = 0

        # Data fetcher reference (set externally)
        self.data_fetcher = None

        logger.info(
            f"LiveExecutor initialized: scan={scan_interval}s, "
            f"timeout={order_timeout}s, retries={max_retries}"
        )

    def add_strategy(
        self,
        strategy: BaseStrategy,
        symbols: List[str],
        timeframe: str = "1d",
    ) -> None:
        """
        Add a strategy to the live executor.

        Args:
            strategy: Strategy instance
            symbols: Symbols this strategy trades
            timeframe: Bar frequency
        """
        name = strategy.name
        self._strategies[name] = strategy
        self._strategy_symbols[name] = symbols
        self._strategy_timeframes[name] = timeframe
        logger.info(f"Strategy '{name}' added: {symbols} ({timeframe})")

    async def start(self) -> None:
        """Start the main execution loop."""
        self._is_running = True
        logger.info("Live executor started")

        # Initialize daily risk tracking
        balance = await self.broker.get_balance()
        self.risk_manager.reset_daily(balance.total_equity)

        # Activate all strategies
        for strategy in self._strategies.values():
            strategy.on_start()

        # Main loop
        while self._is_running:
            try:
                await self._scan_cycle()
                self._scan_count += 1
            except Exception as e:
                logger.error(f"Scan cycle error: {e}")

            await asyncio.sleep(self.scan_interval)

    async def stop(self) -> None:
        """Stop the execution loop."""
        self._is_running = False
        for strategy in self._strategies.values():
            strategy.on_stop()
        logger.info("Live executor stopped")

    async def _scan_cycle(self) -> None:
        """Execute one full scan cycle."""
        # Check if trading is allowed
        if not self.risk_manager.is_trading_allowed:
            logger.debug("Trading paused (circuit breaker)")
            return

        # Get current positions and balance
        positions = await self.broker.get_positions()
        balance = await self.broker.get_balance()

        # Convert positions to context format
        position_dict = {
            p.symbol: {
                "quantity": p.quantity,
                "avg_price": p.avg_price,
                "current_price": p.current_price,
                "unrealized_pnl": p.unrealized_pnl,
            }
            for p in positions
        }

        # Iterate through strategies
        for name, strategy in self._strategies.items():
            symbols = self._strategy_symbols.get(name, [])

            for symbol in symbols:
                # Fetch latest bar data (requires data_fetcher)
                if self.data_fetcher is None:
                    logger.warning("No data_fetcher configured, skipping data fetch")
                    continue

                try:
                    # Get latest bar
                    df = await self.data_fetcher.fetch_kline(
                        symbol=symbol,
                        freq=self._strategy_timeframes.get(name, "1d"),
                        limit=100,
                    )

                    if df.empty:
                        continue

                    # Build strategy context
                    from quantengine.strategy.base import StrategyContext
                    current_bar = df.iloc[-1]
                    context = StrategyContext(
                        symbol=symbol,
                        timeframe=self._strategy_timeframes.get(name, "1d"),
                        current_bar=current_bar,
                        history=df.iloc[:-1],
                        positions={
                            s: p for s, p in position_dict.items()
                            if s == symbol
                        },
                        portfolio_value=balance.total_equity,
                        cash=balance.available_cash,
                        metadata={"strategy_name": name},
                    )

                    # Generate signal
                    signal = strategy.on_bar(current_bar, context)

                    if signal is None:
                        continue

                    self._signals_generated += 1

                    # Risk check
                    price = signal.price or current_bar["close"]
                    quantity = signal.quantity or 0.01

                    risk_result = self.risk_manager.check_order(
                        symbol=symbol,
                        quantity=quantity,
                        price=price,
                        portfolio_value=balance.total_equity,
                        current_positions=position_dict,
                    )

                    if not risk_result.passed:
                        logger.warning(
                            f"Risk check failed for {symbol}: {risk_result.message}"
                        )
                        continue

                    # Place order
                    order = await self._place_order_from_signal(signal, current_bar)
                    if order:
                        self._orders_placed += 1

                except Exception as e:
                    logger.error(f"Error processing {symbol} [{name}]: {e}")

    async def _place_order_from_signal(self, signal: Signal, bar) -> Optional[object]:
        """
        Convert signal to broker order and place it.

        Args:
            signal: Trading signal
            bar: Current market data

        Returns:
            BrokerOrder or None
        """
        # Map signal type to order side
        if signal.type == SignalType.BUY:
            side = OrderSide.BUY
        elif signal.type in (SignalType.SELL, SignalType.CLOSE):
            side = OrderSide.SELL
        else:
            return None

        # Determine order type
        order_type = OrderType.LIMIT if signal.price else OrderType.MARKET
        price = signal.price or bar["close"]
        quantity = signal.quantity or (0.01 * self._strategies.get(
            signal.metadata.get("strategy_name", ""), type("", (), {"params": {}})().params.get("order_size", 0.01)
        ))

        # Place with retry
        for attempt in range(self.max_retries):
            order = await self.broker.place_order(
                symbol=signal.symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
                stop_price=signal.stop_loss,
            )

            if order.status.value not in ("REJECTED", "EXPIRED"):
                logger.info(
                    f"Order placed: {order.order_id} {side.value} "
                    f"{quantity} {signal.symbol} @ {price}"
                )
                return order

            logger.warning(
                f"Order rejected (attempt {attempt+1}/{self.max_retries}): "
                f"{signal.symbol}"
            )
            await asyncio.sleep(1.0)

        return None

    @property
    def stats(self) -> Dict:
        """Get executor statistics."""
        return {
            "running": self._is_running,
            "scan_count": self._scan_count,
            "signals_generated": self._signals_generated,
            "orders_placed": self._orders_placed,
            "active_strategies": len(self._strategies),
            "risk": self.risk_manager.stats,
        }
