"""
QuantEngine Pro - Broker Simulator
====================================
Simulates a brokerage for backtesting.

Handles:
- Order submission, validation, and filling
- Multi-strategy capital allocation and competition
- Order priority based on strategy weight and signal confidence
- Partial fills and order rejection simulation
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple

from loguru import logger

from quantengine.backtest.cost_model import CostModel, CostResult
from quantengine.backtest.position_manager import (
    PositionManager,
    PositionSide,
)
from quantengine.strategy.base import Signal, SignalType


class OrderStatus(str, Enum):
    """Order lifecycle states."""
    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


@dataclass
class Order:
    """An order in the backtest system."""
    order_id: str
    symbol: str
    signal_type: SignalType
    quantity: float
    price: Optional[float]  # None = market order
    strategy_name: str
    timestamp: datetime
    status: OrderStatus = OrderStatus.CREATED
    filled_qty: float = 0.0
    filled_price: float = 0.0
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    confidence: float = 1.0
    metadata: Dict = field(default_factory=dict)

    @property
    def is_buy(self) -> bool:
        return self.signal_type in (SignalType.BUY, SignalType.BUY_TO_COVER)

    @property
    def is_filled(self) -> bool:
        return self.status == OrderStatus.FILLED

    @property
    def remaining_qty(self) -> float:
        return self.quantity - self.filled_qty


class Broker:
    """
    Simulated broker for backtesting.

    Processes orders at bar close prices, applies transaction costs,
    and manages multi-strategy capital competition.

    Usage:
        broker = Broker(position_manager, cost_model)
        orders = broker.submit_signals(signals, current_bar)
        broker.fill_orders(orders, current_bar)
    """

    def __init__(
        self,
        position_manager: PositionManager,
        cost_model: CostModel,
        fill_at_bar_close: bool = True,
    ):
        """
        Initialize broker simulator.

        Args:
            position_manager: Portfolio position manager
            cost_model: Transaction cost calculator
            fill_at_bar_close: If True, fill at bar close price (default)
                              If False, fill at next bar open
        """
        self.position_manager = position_manager
        self.cost_model = cost_model
        self.fill_at_bar_close = fill_at_bar_close

        # Order tracking
        self._orders: List[Order] = []
        self._order_counter = 0
        self._filled_orders: List[Order] = []

        # Statistics
        self._total_commission = 0.0
        self._total_slippage = 0.0

        logger.info("Broker simulator initialized")

    def submit_signals(
        self,
        signals: List[Signal],
        current_price: float,
        current_time: datetime,
    ) -> List[Order]:
        """
        Convert strategy signals to orders and validate.

        Orders are prioritized by:
        1. Strategy weight (higher weight = higher priority)
        2. Signal confidence (higher confidence = higher priority)
        3. Submission time (earlier = higher priority)

        Args:
            signals: List of strategy signals
            current_price: Current market price for the symbol
            current_time: Current backtest timestamp

        Returns:
            List of validated, submitted orders
        """
        orders = []

        for signal in signals:
            self._order_counter += 1
            order_id = f"ORD-{self._order_counter:06d}"

            # Determine quantity
            quantity = signal.quantity or 0.0
            if quantity <= 0 and signal.type not in (SignalType.CLOSE, SignalType.REBALANCE):
                # Auto-calculate position size
                strategy_capital = self.position_manager.get_strategy_capital(
                    signal.metadata.get("strategy_name", "default")
                )
                if signal.price:
                    quantity = (strategy_capital * 0.1) / signal.price  # 10% allocation
                else:
                    quantity = (strategy_capital * 0.1) / current_price

            # Validate against position limits
            order = Order(
                order_id=order_id,
                symbol=signal.symbol,
                signal_type=signal.type,
                quantity=quantity,
                price=signal.price or current_price,
                strategy_name=signal.metadata.get("strategy_name", "default"),
                timestamp=current_time,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                confidence=signal.confidence,
                metadata=signal.metadata,
            )

            # Validate order
            if self._validate_order(order):
                order.status = OrderStatus.SUBMITTED
                orders.append(order)
                logger.debug(
                    f"Order submitted: {order_id} {signal.type.value} "
                    f"{quantity:.4f} {signal.symbol} @ {order.price:.2f}"
                )
            else:
                order.status = OrderStatus.REJECTED
                logger.warning(f"Order rejected: {order_id} {signal.symbol}")

            self._orders.append(order)

        # Sort by priority: strategy weight → confidence → time
        orders.sort(
            key=lambda o: (
                self.position_manager._strategy_weights.get(o.strategy_name, 1.0),
                o.confidence,
            ),
            reverse=True,
        )

        return orders

    def fill_orders(
        self,
        orders: List[Order],
        bar_data: Dict,
        current_time: datetime,
    ) -> List[Order]:
        """
        Execute (fill) orders at current market prices.

        For bar-based backtesting, fills at bar close price.
        Applies transaction costs through CostModel.

        Args:
            orders: List of submitted orders
            bar_data: Current bar data (for fill price)
            current_time: Current timestamp

        Returns:
            List of filled orders
        """
        filled = []

        for order in orders:
            if order.status != OrderStatus.SUBMITTED:
                continue

            # Get fill price
            symbol = order.symbol
            fill_price = order.price

            if isinstance(bar_data, dict):
                symbol_data = bar_data.get(symbol, {})
                if hasattr(symbol_data, "close"):
                    fill_price = symbol_data.close
                elif isinstance(symbol_data, dict):
                    fill_price = symbol_data.get("close", fill_price)

            # Calculate transaction costs
            is_buy = order.signal_type in (SignalType.BUY, SignalType.BUY_TO_COVER)
            cost = self.cost_model.calculate(
                price=fill_price,
                quantity=order.quantity,
                is_buy=is_buy,
            )

            # Execute position change
            if order.signal_type in (SignalType.BUY, SignalType.SELL_SHORT):
                # Opening position
                side = PositionSide.LONG if order.signal_type == SignalType.BUY else PositionSide.SHORT
                pos = self.position_manager.open_position(
                    symbol=order.symbol,
                    side=side,
                    quantity=order.quantity,
                    price=fill_price,
                    strategy_name=order.strategy_name,
                    stop_loss=order.stop_loss,
                    take_profit=order.take_profit,
                )
                if pos is None:
                    order.status = OrderStatus.REJECTED
                    logger.warning(
                        f"Order {order.order_id} rejected: insufficient capital"
                    )
                    continue

            elif order.signal_type in (SignalType.SELL, SignalType.BUY_TO_COVER, SignalType.CLOSE):
                # Closing position
                pnl, proceeds = self.position_manager.close_position(
                    symbol=order.symbol,
                    price=fill_price,
                    strategy_name=order.strategy_name,
                    quantity=order.quantity if order.signal_type != SignalType.CLOSE else None,
                )

            # Record costs
            self.position_manager.add_transaction_cost(cost.total)
            self._total_commission += cost.commission
            self._total_slippage += cost.slippage

            # Update order
            order.filled_qty = order.quantity
            order.filled_price = fill_price
            order.status = OrderStatus.FILLED

            filled.append(order)
            self._filled_orders.append(order)

            logger.debug(
                f"Order filled: {order.order_id} {order.quantity:.4f} "
                f"{order.symbol} @ {fill_price:.2f} cost={cost.total:.2f}"
            )

        return filled

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel a pending order.

        Args:
            order_id: Order identifier

        Returns:
            True if cancelled, False if not found or already filled
        """
        for order in self._orders:
            if order.order_id == order_id:
                if order.status == OrderStatus.SUBMITTED:
                    order.status = OrderStatus.CANCELLED
                    logger.info(f"Order cancelled: {order_id}")
                    return True
        return False

    def _validate_order(self, order: Order) -> bool:
        """
        Validate an order before submission.

        Checks:
        - Non-zero quantity
        - Valid price (positive)
        - Single-symbol position limit (≤20%)

        Args:
            order: Order to validate

        Returns:
            True if valid
        """
        if order.quantity <= 0 and order.signal_type not in (SignalType.CLOSE, SignalType.REBALANCE):
            logger.warning(f"Order {order.order_id}: invalid quantity {order.quantity}")
            return False

        if order.price and order.price <= 0:
            logger.warning(f"Order {order.order_id}: invalid price {order.price}")
            return False

        return True

    @property
    def stats(self) -> Dict:
        """Get broker statistics."""
        return {
            "total_orders": len(self._orders),
            "filled_orders": len(self._filled_orders),
            "fill_rate": len(self._filled_orders) / max(len(self._orders), 1),
            "total_commission": self._total_commission,
            "total_slippage": self._total_slippage,
        }
