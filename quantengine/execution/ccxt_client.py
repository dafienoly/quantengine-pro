"""
QuantEngine Pro - CCXT Broker Client
======================================
Cryptocurrency exchange broker client using CCXT library.

Supports Binance, OKX, Bybit, and 100+ other exchanges.
Testnet mode for safe development and testing.
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


class CCXTBrokerClient(BaseBrokerClient):
    """
    CCXT-based broker client for cryptocurrency exchanges.

    Usage:
        client = CCXTBrokerClient({
            "exchange": "binance",
            "testnet": True,
            "api_key": "...",
            "secret": "...",
        })
        await client.connect()
        order = await client.place_order("BTC/USDT", OrderSide.BUY, OrderType.LIMIT, 0.01, 50000)
    """

    def __init__(self, config: Dict):
        """
        Initialize CCXT broker client.

        Args:
            config: Dict with keys:
                - exchange: Exchange name (binance, okx, bybit, etc.)
                - testnet: Use testnet/sandbox (default True)
                - api_key: API key
                - secret: API secret
                - password: API password (required for some exchanges)
        """
        super().__init__(config)
        self.exchange_name = config.get("exchange", "binance")
        self.is_testnet = config.get("testnet", True)
        self.api_key = config.get("api_key", "")
        self.secret = config.get("secret", "")
        self.password = config.get("password", "")
        self._exchange = None
        self._connected = False

    async def connect(self) -> bool:
        """Connect to exchange and load markets."""
        try:
            import ccxt

            exchange_class = getattr(ccxt, self.exchange_name)
            exchange_config = {
                "apiKey": self.api_key,
                "secret": self.secret,
                "enableRateLimit": True,
                "options": {"defaultType": "spot"},
            }

            if self.password:
                exchange_config["password"] = self.password

            # Testnet configuration
            if self.is_testnet:
                if self.exchange_name == "binance":
                    exchange_config["urls"] = {"api": "https://testnet.binance.vision"}
                    exchange_config["options"]["defaultType"] = "spot"

            loop = asyncio.get_event_loop()
            self._exchange = exchange_class(exchange_config)

            # Load markets
            await loop.run_in_executor(None, self._exchange.load_markets)

            self._connected = True
            logger.info(f"Connected to {self.exchange_name} (testnet={self.is_testnet})")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to {self.exchange_name}: {e}")
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Close exchange connection."""
        self._connected = False
        logger.info(f"Disconnected from {self.exchange_name}")

    async def is_connected(self) -> bool:
        return self._connected

    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
    ) -> BrokerOrder:
        """Place order on exchange."""
        if not self._exchange:
            return BrokerOrder(
                order_id="",
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                status=OrderStatus.REJECTED,
            )

        try:
            # Convert to CCXT format
            ccxt_side = "buy" if side == OrderSide.BUY else "sell"
            ccxt_type = order_type.value.lower()

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self._exchange.create_order(
                    symbol=symbol,
                    type=ccxt_type,
                    side=ccxt_side,
                    amount=quantity,
                    price=price,
                    params={"stopPrice": stop_price} if stop_price else {},
                ),
            )

            return BrokerOrder(
                order_id=str(result.get("id", "")),
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
                status=OrderStatus.SUBMITTED,
                filled_qty=float(result.get("filled", 0)),
                filled_price=float(result.get("average", 0) or 0),
                commission=float(result.get("fee", {}).get("cost", 0) or 0),
            )

        except Exception as e:
            logger.error(f"Order placement failed: {e}")
            return BrokerOrder(
                order_id="",
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                status=OrderStatus.REJECTED,
            )

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        if not self._exchange:
            return False

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._exchange.cancel_order(order_id),
            )
            logger.info(f"Order cancelled: {order_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    async def get_positions(self) -> List[BrokerPosition]:
        """Get current positions (spot balances)."""
        if not self._exchange:
            return []

        try:
            loop = asyncio.get_event_loop()
            balance = await loop.run_in_executor(
                None, self._exchange.fetch_balance
            )

            positions = []
            for currency, info in balance.get("total", {}).items():
                if info > 0:
                    # Get current price in USDT
                    try:
                        ticker = await loop.run_in_executor(
                            None,
                            lambda c=currency: self._exchange.fetch_ticker(f"{c}/USDT"),
                        )
                        current_price = ticker.get("last", 0)
                    except Exception:
                        continue

                    positions.append(BrokerPosition(
                        symbol=f"{currency}/USDT",
                        quantity=info,
                        avg_price=0,  # Not tracked at spot level
                        current_price=current_price,
                    ))

            return positions

        except Exception as e:
            logger.error(f"Failed to fetch positions: {e}")
            return []

    async def get_balance(self) -> AccountBalance:
        """Get account balance."""
        if not self._exchange:
            return AccountBalance()

        try:
            loop = asyncio.get_event_loop()
            balance = await loop.run_in_executor(
                None, self._exchange.fetch_balance
            )

            return AccountBalance(
                total_equity=float(balance.get("total", {}).get("USDT", 0)),
                available_cash=float(balance.get("free", {}).get("USDT", 0)),
                frozen_cash=float(balance.get("used", {}).get("USDT", 0)),
                currency="USDT",
            )

        except Exception as e:
            logger.error(f"Failed to fetch balance: {e}")
            return AccountBalance()

    async def get_order(self, order_id: str) -> Optional[BrokerOrder]:
        """Query order status."""
        if not self._exchange:
            return None

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self._exchange.fetch_order(order_id),
            )

            return BrokerOrder(
                order_id=str(result.get("id", "")),
                symbol=result.get("symbol", ""),
                side=OrderSide.BUY if result.get("side") == "buy" else OrderSide.SELL,
                order_type=OrderType.LIMIT if result.get("type") == "limit" else OrderType.MARKET,
                quantity=float(result.get("amount", 0)),
                price=float(result.get("price", 0) or 0),
                status=OrderStatus.FILLED if result.get("status") == "closed" else OrderStatus.SUBMITTED,
                filled_qty=float(result.get("filled", 0)),
                filled_price=float(result.get("average", 0) or 0),
            )

        except Exception as e:
            logger.error(f"Failed to fetch order {order_id}: {e}")
            return None
