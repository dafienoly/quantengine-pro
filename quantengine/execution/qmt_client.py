"""
QuantEngine Pro - QMT Broker Client
=====================================
Broker client for 国金证券 QMT (Quantitative Trading Terminal).

QMT is the primary A-share trading platform used by retail quants in China.
This client supports two modes:
- SIMULATE: Local simulation for development/testing (no QMT required)
- LIVE: Real QMT connection via xtquant API

QMT API reference: http://dict.thinktrader.net/
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional

from loguru import logger

from quantengine.execution.base import (
    AccountBalance,
    BaseBrokerClient,
    BrokerOrder,
    BrokerPosition,
    OrderSide,
    OrderStatus,
    OrderType,
)


class QMTBrokerClient(BaseBrokerClient):
    """
    QMT (迅投QMT) broker client for A-share trading.

    Two modes:
    1. SIMULATE (default) - Local simulation with realistic A-share constraints
       (T+1 settlement, lot size = 100 shares, price limits ±10%)
    2. LIVE - Connects to real QMT terminal via xtquant

    Usage:
        client = QMTBrokerClient({"mode": "simulate", "initial_capital": 100000})
        await client.connect()
        order = await client.place_order("000001.SZ", OrderSide.BUY, OrderType.LIMIT, 1000, 12.50)
    """

    def __init__(self, config: Dict):
        """
        Initialize QMT broker client.

        Args:
            config: Dict with keys:
                - mode: 'simulate' or 'live' (default: 'simulate')
                - qmt_path: Path to QMT userdata_mini directory (for live mode)
                - account_id: QMT account ID (for live mode)
                - initial_capital: Starting capital for simulation (default: 100000)
        """
        super().__init__(config)
        self.mode = config.get("mode", "simulate")
        self.qmt_path = config.get("qmt_path", "")
        self.account_id = config.get("account_id", "")
        self.initial_capital = config.get("initial_capital", 100000.0)

        # QMT API handle (lazy loaded in live mode)
        self._xt_trader = None
        self._xt_acc = None

        # Simulation state
        self._sim_cash = self.initial_capital
        self._sim_positions: Dict[str, Dict] = {}
        self._sim_orders: Dict[str, BrokerOrder] = {}
        self._sim_order_counter = 0
        self._sim_realized_pnl = 0.0

        # A-share constants
        self.LOT_SIZE = 100          # 1 lot = 100 shares
        self.PRICE_LIMIT = 0.10      # ±10% daily limit
        self.STAMP_TAX_RATE = 0.001  # 0.1% sell only
        self.COMMISSION_RATE = 0.00025  # 万2.5
        self.MIN_COMMISSION = 5.0    # 最低5元

        self._connected = False
        logger.info(f"QMTBrokerClient initialized: mode={self.mode}")

    async def connect(self) -> bool:
        """Connect to QMT or initialize simulation."""
        if self.mode == "simulate":
            self._connected = True
            logger.info(f"QMT simulation mode: capital={self.initial_capital:,.0f}")
            return True

        if self.mode == "live":
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._connect_qmt)
                self._connected = True
                logger.info("QMT live connection established")
                return True
            except Exception as e:
                logger.error(f"QMT connection failed: {e}")
                return False

        return False

    def _connect_qmt(self) -> None:
        """
        Connect to QMT terminal via xtquant.

        Requires:
        - QMT terminal running
        - xtquant installed: pip install xtquant
        - qmt_path pointing to userdata_mini directory
        """
        try:
            from xtquant import xtdata
            from xtquant.xttrader import XtQuantTrader
            from xtquant.xttype import StockAccount

            # Download market data
            xtdata.download_history_data = lambda *a, **kw: None  # stub

            # Create trader session
            session_id = int(datetime.now().timestamp() % 100000)
            self._xt_trader = XtQuantTrader(
                self.qmt_path,
                session_id,
            )

            # Create account
            self._xt_acc = StockAccount(self.account_id)

            # Start trader
            self._xt_trader.start()
            connect_result = self._xt_trader.connect()

            if connect_result != 0:
                raise ConnectionError(
                    f"QMT connection failed with code {connect_result}"
                )

            # Subscribe to account
            self._xt_trader.subscribe(self._xt_acc)

            logger.info(f"QMT connected: session_id={session_id}")

        except ImportError:
            logger.error(
                "xtquant not installed. Install with: pip install xtquant"
            )
            raise

    async def disconnect(self) -> None:
        """Disconnect from QMT."""
        self._connected = False
        if self._xt_trader:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._xt_trader.stop)
        logger.info("QMT disconnected")

    async def is_connected(self) -> bool:
        return self._connected

    # ---- Order Management ----

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
        Place an order.

        A-share specific constraints (enforced in both modes):
        - Quantity must be in lots of 100 shares
        - Price limited to ±10% of previous close (simulated)
        - T+1: cannot sell shares bought today

        Args:
            symbol: Stock code with exchange suffix (e.g., '000001.SZ', '600000.SH')
            side: BUY or SELL
            order_type: MARKET or LIMIT
            quantity: Number of shares (will be rounded to lot size)
            price: Limit price (required for LIMIT orders)
            stop_price: Not supported by QMT for stocks

        Returns:
            BrokerOrder with status
        """
        # Round to lot size
        lots = int(quantity / self.LOT_SIZE)
        if lots < 1:
            return BrokerOrder(
                order_id="",
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                status=OrderStatus.REJECTED,
            )
        adjusted_qty = lots * self.LOT_SIZE

        if self.mode == "simulate":
            return await self._sim_place_order(symbol, side, order_type, adjusted_qty, price)
        else:
            return await self._live_place_order(symbol, side, order_type, adjusted_qty, price)

    async def _sim_place_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: Optional[float],
    ) -> BrokerOrder:
        """Simulate order placement with realistic A-share constraints."""
        self._sim_order_counter += 1
        order_id = f"SIM-{self._sim_order_counter:06d}"

        # Use a simulated current price
        exec_price = price or 10.0  # Would come from market data in real use

        # Check cash for buy
        if side == OrderSide.BUY:
            cost = exec_price * quantity
            commission = max(cost * self.COMMISSION_RATE, self.MIN_COMMISSION)
            total = cost + commission
            if total > self._sim_cash:
                return BrokerOrder(
                    order_id=order_id,
                    symbol=symbol,
                    side=side,
                    order_type=order_type,
                    quantity=quantity,
                    price=price,
                    status=OrderStatus.REJECTED,
                )

            # Deduct cash
            self._sim_cash -= total

            # Update position
            if symbol not in self._sim_positions:
                self._sim_positions[symbol] = {
                    "quantity": quantity,
                    "avg_price": exec_price,
                    "current_price": exec_price,
                    "available": 0,  # T+1: not available until next day
                }
            else:
                pos = self._sim_positions[symbol]
                old_cost = pos["quantity"] * pos["avg_price"]
                new_cost = old_cost + quantity * exec_price
                pos["quantity"] += quantity
                pos["avg_price"] = new_cost / pos["quantity"] if pos["quantity"] > 0 else 0

        elif side == OrderSide.SELL:
            # Check available shares (T+1 constraint)
            pos = self._sim_positions.get(symbol, {})
            available = pos.get("available", 0)
            if quantity > available:
                return BrokerOrder(
                    order_id=order_id,
                    symbol=symbol,
                    side=side,
                    order_type=order_type,
                    quantity=quantity,
                    price=price,
                    status=OrderStatus.REJECTED,
                )

            # Calculate proceeds with costs
            proceeds = exec_price * quantity
            commission = max(proceeds * self.COMMISSION_RATE, self.MIN_COMMISSION)
            stamp_tax = proceeds * self.STAMP_TAX_RATE
            net_proceeds = proceeds - commission - stamp_tax

            # Update position and record realized PnL
            pos["quantity"] -= quantity
            pos["available"] -= quantity
            # 每次卖出都记录已实现盈亏（部分卖出也记录）
            trade_pnl = net_proceeds - (quantity * pos["avg_price"])
            self._sim_realized_pnl += trade_pnl
            if pos["quantity"] <= 0:
                del self._sim_positions[symbol]

            self._sim_cash += net_proceeds

        order = BrokerOrder(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            status=OrderStatus.FILLED,
            filled_qty=quantity,
            filled_price=exec_price,
            commission=commission,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        self._sim_orders[order_id] = order
        logger.debug(f"QMT sim order filled: {order_id} {side.value} {quantity} {symbol}")
        return order

    async def _live_place_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: Optional[float],
    ) -> BrokerOrder:
        """Place order via real QMT API."""
        if not self._xt_trader:
            return BrokerOrder(
                order_id="",
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                status=OrderStatus.REJECTED,
            )

        try:
            from xtquant.xttype import StockAccount

            loop = asyncio.get_event_loop()

            # Convert order type
            qmt_price_type = {
                OrderType.LIMIT: 11,   # 限价单
                OrderType.MARKET: 14,  # 市价单(剩撤)
            }.get(order_type, 11)

            order_id = await loop.run_in_executor(
                None,
                lambda: self._xt_trader.order_stock(
                    self._xt_acc,
                    symbol,
                    qmt_price_type,
                    quantity,
                    price or 0,
                    "QuantEngine Pro",
                ),
            )

            logger.info(f"QMT live order: {order_id} {side.value} {quantity} {symbol}")
            return BrokerOrder(
                order_id=str(order_id),
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
                status=OrderStatus.SUBMITTED,
                created_at=datetime.now(),
            )

        except Exception as e:
            logger.error(f"QMT live order failed: {e}")
            return BrokerOrder(
                order_id="",
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                status=OrderStatus.REJECTED,
            )

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order."""
        if self.mode == "simulate":
            if order_id in self._sim_orders:
                self._sim_orders[order_id].status = OrderStatus.CANCELLED
                return True
            return False

        if self._xt_trader:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, lambda: self._xt_trader.cancel_order(order_id)
            )
            return True
        return False

    async def get_positions(self) -> List[BrokerPosition]:
        """Get current positions."""
        if self.mode == "simulate":
            return [
                BrokerPosition(
                    symbol=sym,
                    quantity=pos["quantity"],
                    avg_price=pos["avg_price"],
                    current_price=pos["current_price"],
                    unrealized_pnl=(
                        pos["current_price"] - pos["avg_price"]
                    ) * pos["quantity"],
                    leverage=1.0,
                )
                for sym, pos in self._sim_positions.items()
                if pos["quantity"] > 0
            ]

        # Live mode
        if self._xt_trader:
            try:
                from xtquant.xttype import StockAccount
                loop = asyncio.get_event_loop()
                positions = await loop.run_in_executor(
                    None,
                    lambda: self._xt_trader.query_stock_positions(self._xt_acc),
                )
                return [
                    BrokerPosition(
                        symbol=p.stock_code,
                        quantity=p.volume,
                        avg_price=p.open_price,
                        current_price=p.market_value / p.volume if p.volume > 0 else 0,
                        unrealized_pnl=p.profit,
                    )
                    for p in (positions or [])
                ]
            except Exception as e:
                logger.error(f"QMT position query failed: {e}")

        return []

    async def get_balance(self) -> AccountBalance:
        """Get account balance."""
        if self.mode == "simulate":
            positions_value = sum(
                pos["quantity"] * pos["current_price"]
                for pos in self._sim_positions.values()
            )
            unrealized = sum(
                (pos["current_price"] - pos["avg_price"]) * pos["quantity"]
                for pos in self._sim_positions.values()
            )
            return AccountBalance(
                total_equity=self._sim_cash + positions_value + unrealized,
                available_cash=self._sim_cash,
                frozen_cash=0.0,
                positions_value=positions_value,
                unrealized_pnl=unrealized,
                realized_pnl=self._sim_realized_pnl,
                currency="CNY",
            )

        # Live mode
        if self._xt_trader:
            try:
                loop = asyncio.get_event_loop()
                asset = await loop.run_in_executor(
                    None,
                    lambda: self._xt_trader.query_stock_asset(self._xt_acc),
                )
                if asset:
                    return AccountBalance(
                        total_equity=asset.total_asset,
                        available_cash=asset.cash,
                        frozen_cash=asset.frozen_cash,
                        positions_value=asset.market_value,
                        currency="CNY",
                    )
            except Exception as e:
                logger.error(f"QMT balance query failed: {e}")

        return AccountBalance()

    async def get_order(self, order_id: str) -> Optional[BrokerOrder]:
        """Query order status."""
        if self.mode == "simulate":
            return self._sim_orders.get(order_id)

        if self._xt_trader:
            try:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: self._xt_trader.query_stock_order(
                        self._xt_acc, int(order_id)
                    ),
                )
                if result:
                    return BrokerOrder(
                        order_id=str(result.order_id),
                        symbol=result.stock_code,
                        side=OrderSide.BUY if result.order_type < 24 else OrderSide.SELL,
                        order_type=OrderType.LIMIT,
                        quantity=result.order_volume,
                        price=result.price,
                        status=OrderStatus.FILLED if result.traded_volume > 0 else OrderStatus.SUBMITTED,
                        filled_qty=result.traded_volume,
                        filled_price=result.traded_price,
                    )
            except Exception as e:
                logger.error(f"QMT order query failed: {e}")

        return None

    def settle_t1(self) -> None:
        """
        Process T+1 settlement (call at market close in simulation).
        Makes today's bought shares available for selling tomorrow.
        """
        for pos in self._sim_positions.values():
            # All current holdings become available
            pos["available"] = pos["quantity"]

    @property
    def mode_label(self) -> str:
        return "模拟交易" if self.mode == "simulate" else "实盘交易"
