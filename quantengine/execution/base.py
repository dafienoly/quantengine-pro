"""
QuantEngine Pro - Broker Client Abstraction
=============================================
Abstract base class for broker/exchange clients.

All broker implementations must implement:
- place_order: Submit an order
- cancel_order: Cancel a pending order
- get_positions: Get current positions
- get_balance: Get account balance
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


@dataclass
class BrokerOrder:
    """Standardized order across all brokers."""
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float] = None  # None for market orders
    stop_price: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_qty: float = 0.0
    filled_price: float = 0.0
    commission: float = 0.0
    created_at: datetime = None
    updated_at: datetime = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()
        if self.metadata is None:
            self.metadata = {}


@dataclass
class AccountBalance:
    """Standardized account balance."""
    total_equity: float = 0.0
    available_cash: float = 0.0
    frozen_cash: float = 0.0
    positions_value: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    margin_used: float = 0.0
    currency: str = "CNY"


@dataclass
class BrokerPosition:
    """Standardized position across all brokers."""
    symbol: str
    quantity: float
    avg_price: float
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    margin: float = 0.0
    leverage: float = 1.0


class BaseBrokerClient(ABC):
    """
    Abstract broker client interface.

    All broker implementations (QMT, CCXT, etc.) must implement this interface.
    This ensures the execution layer is broker-agnostic.
    """

    def __init__(self, config: Dict):
        """
        Initialize broker client.

        Args:
            config: Broker-specific configuration
        """
        self.config = config
        self.name = self.__class__.__name__

    @abstractmethod
    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
    ) -> BrokerOrder:
        """
        Place an order with the broker.

        Args:
            symbol: Trading symbol
            side: BUY or SELL
            order_type: MARKET, LIMIT, STOP, STOP_LIMIT
            quantity: Order quantity
            price: Limit price (required for LIMIT orders)
            stop_price: Stop price (required for STOP orders)

        Returns:
            BrokerOrder with order details and status
        """
        ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel a pending order.

        Args:
            order_id: Order identifier

        Returns:
            True if cancellation was successful
        """
        ...

    @abstractmethod
    async def get_positions(self) -> List[BrokerPosition]:
        """
        Get current positions.

        Returns:
            List of BrokerPosition objects
        """
        ...

    @abstractmethod
    async def get_balance(self) -> AccountBalance:
        """
        Get current account balance.

        Returns:
            AccountBalance with equity, cash, margin info
        """
        ...

    @abstractmethod
    async def get_order(self, order_id: str) -> Optional[BrokerOrder]:
        """
        Query an order's status.

        Args:
            order_id: Order identifier

        Returns:
            BrokerOrder or None if not found
        """
        ...

    async def connect(self) -> bool:
        """Establish connection to broker. Returns True on success."""
        return True

    async def disconnect(self) -> None:
        """Close connection to broker."""
        pass

    async def is_connected(self) -> bool:
        """Check if connected to broker."""
        return True
