"""
QuantEngine Pro - Cost Model
==============================
Realistic transaction cost simulation for backtesting.

Supports:
- Commission (proportional or fixed minimum)
- Stamp tax (A-share sell-side only: 0.1%)
- Slippage (fixed / proportional / volume-based models)
- Financing cost (margin interest for leveraged positions)

Configurable per market (A-share vs crypto) via execution.yaml.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional

from loguru import logger


class SlippageModel(str, Enum):
    """Slippage calculation methods."""
    FIXED = "fixed"             # Fixed tick amount
    PROPORTIONAL = "proportional"  # Percentage of price
    VOLUME = "volume"           # Based on trade volume vs market volume


@dataclass
class CostResult:
    """Breakdown of transaction costs for a single trade."""
    commission: float = 0.0
    stamp_tax: float = 0.0
    slippage: float = 0.0
    financing_cost: float = 0.0
    total: float = 0.0

    def __add__(self, other: "CostResult") -> "CostResult":
        return CostResult(
            commission=self.commission + other.commission,
            stamp_tax=self.stamp_tax + other.stamp_tax,
            slippage=self.slippage + other.slippage,
            financing_cost=self.financing_cost + other.financing_cost,
            total=self.total + other.total,
        )


class CostModel:
    """
    Transaction cost calculator for backtesting.

    Configurable per market with realistic cost parameters.

    Usage:
        model = CostModel(market="a_share", config={...})
        cost = model.calculate(price=10.0, quantity=1000, is_buy=True)
    """

    # Default cost parameters per market
    DEFAULT_CONFIGS = {
        "a_share": {
            "commission_rate": 0.00025,   # 0.025% (万2.5)
            "min_commission": 5.0,         # Min 5 yuan
            "stamp_tax_rate": 0.001,       # 0.1% (sell only)
            "slippage_model": "fixed",
            "slippage_value": 0.001,       # 0.1% slippage
            "financing_rate": 0.08,        # 8% annual margin rate
        },
        "crypto": {
            "maker_fee": 0.0002,           # 0.02% maker
            "taker_fee": 0.0004,           # 0.04% taker
            "slippage_model": "proportional",
            "slippage_value": 0.0005,      # 0.05% slippage
            "financing_rate": 0.0001,      # 0.01% per 8h funding rate
        },
    }

    def __init__(self, market: str = "a_share", config: Optional[Dict] = None):
        """
        Initialize cost model for a specific market.

        Args:
            market: 'a_share' or 'crypto'
            config: Override default cost parameters
        """
        self.market = market
        defaults = self.DEFAULT_CONFIGS.get(market, self.DEFAULT_CONFIGS["a_share"])
        self.config = {**defaults, **(config or {})}
        logger.info(
            f"CostModel initialized: market={market}, "
            f"commission={self.config.get('commission_rate', 'N/A')}"
        )

    def calculate(
        self,
        price: float,
        quantity: float,
        is_buy: bool = True,
        is_maker: bool = False,
        market_volume: float = 0.0,
        holding_days: float = 0.0,
    ) -> CostResult:
        """
        Calculate total transaction cost for a trade.

        Args:
            price: Execution price per unit
            quantity: Number of shares/contracts
            is_buy: True for buy, False for sell
            is_maker: True if limit order (maker), False if market/taker
            market_volume: Total market volume (for volume-based slippage)
            holding_days: Expected holding period (for financing cost)

        Returns:
            CostResult with cost breakdown
        """
        trade_value = price * quantity

        # Commission
        commission = self._calc_commission(trade_value, is_maker)

        # Stamp tax (A-share sell only)
        stamp_tax = self._calc_stamp_tax(trade_value, is_buy)

        # Slippage
        slippage = self._calc_slippage(price, quantity, trade_value, market_volume)

        # Financing cost (margin positions)
        financing = self._calc_financing(trade_value, holding_days)

        total = commission + stamp_tax + slippage + financing

        return CostResult(
            commission=commission,
            stamp_tax=stamp_tax,
            slippage=slippage,
            financing_cost=financing,
            total=total,
        )

    def _calc_commission(self, trade_value: float, is_maker: bool) -> float:
        """
        Calculate commission for a trade.

        Args:
            trade_value: price * quantity
            is_maker: True for maker orders (lower fees on crypto)

        Returns:
            Commission cost
        """
        if self.market == "crypto":
            rate = self.config["maker_fee" if is_maker else "taker_fee"]
            return trade_value * rate
        else:
            # A-share: proportional with minimum
            rate = self.config["commission_rate"]
            commission = trade_value * rate
            return max(commission, self.config.get("min_commission", 5.0))

    def _calc_stamp_tax(self, trade_value: float, is_buy: bool) -> float:
        """
        Calculate stamp tax.

        A-share: 0.1% on sell side only.
        Crypto: No stamp tax.

        Args:
            trade_value: Trade value
            is_buy: True for buy

        Returns:
            Stamp tax amount
        """
        if self.market == "crypto" or is_buy:
            return 0.0

        return trade_value * self.config.get("stamp_tax_rate", 0.001)

    def _calc_slippage(
        self,
        price: float,
        quantity: float,
        trade_value: float,
        market_volume: float,
    ) -> float:
        """
        Calculate slippage cost.

        Supports three models:
        - fixed: Fixed tick/percentage per trade
        - proportional: Percentage of price (spread-based)
        - volume: Increases with trade size relative to market volume

        Args:
            price: Execution price
            quantity: Trade quantity
            trade_value: Total trade value
            market_volume: Market volume for volume model

        Returns:
            Slippage cost
        """
        model = self.config.get("slippage_model", "proportional")
        value = self.config.get("slippage_value", 0.001)

        if model == SlippageModel.FIXED.value:
            # Fixed percentage of trade value
            return trade_value * value

        elif model == SlippageModel.PROPORTIONAL.value:
            # Spread-based: half the spread (assumes mid-price)
            return trade_value * value

        elif model == SlippageModel.VOLUME.value:
            # Volume-based: square root model (Almgren-Chriss simplified)
            # Slippage increases with sqrt(trade_size / market_volume)
            if market_volume > 0:
                participation = trade_value / market_volume
                return trade_value * value * (participation ** 0.5)
            return trade_value * value

        return 0.0

    def _calc_financing(self, trade_value: float, holding_days: float) -> float:
        """
        Calculate financing/margin interest cost.

        Args:
            trade_value: Position value
            holding_days: Days held

        Returns:
            Financing cost
        """
        if holding_days <= 0:
            return 0.0

        annual_rate = self.config.get("financing_rate", 0.08)
        daily_rate = annual_rate / 365
        return trade_value * daily_rate * holding_days
