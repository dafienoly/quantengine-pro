"""
QuantEngine Pro - Position Manager
====================================
Tracks positions, margin, and portfolio state during backtesting.

Responsibilities:
- Track positions per strategy per symbol
- Calculate portfolio equity and available cash
- Monitor margin requirements and trigger forced liquidation
- Handle multi-strategy capital competition
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple

from loguru import logger


class PositionSide(str, Enum):
    """Position direction."""
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass
class Position:
    """
    A single position in a symbol.

    Tracks cost basis, unrealized P&L, and margin usage.
    """
    symbol: str
    side: PositionSide
    quantity: float
    avg_price: float
    current_price: float = 0.0
    strategy_name: str = ""
    opened_at: datetime = field(default_factory=datetime.now)
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    leverage: float = 1.0  # 1.0 = spot, >1.0 = leveraged

    @property
    def market_value(self) -> float:
        """Current market value of the position."""
        return abs(self.quantity) * self.current_price

    @property
    def cost_basis(self) -> float:
        """Total cost of entering the position."""
        return abs(self.quantity) * self.avg_price

    @property
    def unrealized_pnl(self) -> float:
        """Unrealized profit/loss."""
        if self.side == PositionSide.LONG:
            return (self.current_price - self.avg_price) * self.quantity
        else:  # SHORT
            return (self.avg_price - self.current_price) * abs(self.quantity)

    @property
    def unrealized_pnl_pct(self) -> float:
        """Unrealized P&L as percentage of cost basis."""
        if self.cost_basis == 0:
            return 0.0
        return self.unrealized_pnl / self.cost_basis

    @property
    def margin_used(self) -> float:
        """Margin (collateral) required for this position."""
        return self.market_value / self.leverage

    @property
    def maintenance_margin_ratio(self) -> float:
        """
        Maintenance margin ratio = equity / market_value.
        Below 130% triggers forced liquidation in Chinese markets.
        For crypto: below maintenance margin rate triggers liquidation.
        """
        if self.market_value == 0:
            return float("inf")
        equity = self.market_value + self.unrealized_pnl
        return equity / self.market_value


@dataclass
class PortfolioState:
    """Snapshot of portfolio state at a point in time."""
    timestamp: datetime
    total_equity: float = 0.0
    cash: float = 0.0
    positions_value: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    margin_used: float = 0.0
    margin_available: float = 0.0
    total_cost: float = 0.0  # Cumulative transaction costs


class PositionManager:
    """
    Manages portfolio positions and capital allocation.

    Supports:
    - Multiple strategies sharing capital pool
    - Per-symbol position tracking
    - Margin monitoring and forced liquidation
    - Equity curve tracking
    """

    def __init__(
        self,
        initial_capital: float = 100000.0,
        maintenance_margin_ratio: float = 1.3,
        force_liquidation_ratio: float = 1.1,
        max_leverage: float = 3.0,
    ):
        """
        Initialize position manager.

        Args:
            initial_capital: Starting portfolio value
            maintenance_margin_ratio: Below this triggers margin call (default 130%)
            force_liquidation_ratio: Below this triggers forced close (default 110%)
            max_leverage: Maximum allowed leverage
        """
        self.initial_capital = initial_capital
        self.maintenance_margin_ratio = maintenance_margin_ratio
        self.force_liquidation_ratio = force_liquidation_ratio
        self.max_leverage = max_leverage

        # Portfolio state
        self.cash = initial_capital
        self.realized_pnl = 0.0
        self.total_cost = 0.0  # Cumulative transaction costs

        # Positions: strategy_name → symbol → Position
        self._positions: Dict[str, Dict[str, Position]] = defaultdict(dict)

        # Trade history
        self._trades: List[Dict] = []

        # Equity curve: List of (timestamp, equity)
        self._equity_curve: List[Tuple[datetime, float]] = []

        # Strategy capital weights (for multi-strategy competition)
        self._strategy_weights: Dict[str, float] = {}

        logger.info(
            f"PositionManager initialized: capital={initial_capital:,.0f}, "
            f"maintenance_margin={maintenance_margin_ratio:.0%}"
        )

    # ---- Position Operations ----

    def open_position(
        self,
        symbol: str,
        side: PositionSide,
        quantity: float,
        price: float,
        strategy_name: str = "default",
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        leverage: float = 1.0,
    ) -> Optional[Position]:
        """
        Open a new position.

        Args:
            symbol: Trading symbol
            side: LONG or SHORT
            quantity: Number of units
            price: Entry price
            strategy_name: Owning strategy
            stop_loss: Stop-loss price
            take_profit: Take-profit price
            leverage: Position leverage

        Returns:
            Position object, or None if rejected
        """
        # Calculate cost
        cost = quantity * price / leverage

        # Check cash availability
        if cost > self.cash:
            logger.warning(
                f"Insufficient cash for {symbol}: need {cost:,.2f}, have {self.cash:,.2f}"
            )
            # Auto-adjust quantity
            quantity = (self.cash * leverage * 0.95) / price  # 95% of available
            if quantity <= 0:
                return None
            logger.info(f"Adjusted quantity for {symbol}: {quantity:.4f}")

        # Deduct cash (margin)
        actual_cost = quantity * price / leverage
        self.cash -= actual_cost

        # Create position
        pos = Position(
            symbol=symbol,
            side=side,
            quantity=quantity,
            avg_price=price,
            current_price=price,
            strategy_name=strategy_name,
            stop_loss=stop_loss,
            take_profit=take_profit,
            leverage=leverage,
        )
        self._positions[strategy_name][symbol] = pos

        logger.info(
            f"Opened {side.value} {quantity:.4f} {symbol} @ {price:.2f} "
            f"[{strategy_name}] margin={actual_cost:,.2f}"
        )
        return pos

    def close_position(
        self,
        symbol: str,
        price: float,
        strategy_name: str = "default",
        quantity: Optional[float] = None,
    ) -> Tuple[float, float]:
        """
        Close (or reduce) a position.

        Args:
            symbol: Trading symbol
            price: Exit price
            strategy_name: Strategy that owns the position
            quantity: Amount to close (None = close entire position)

        Returns:
            Tuple of (realized_pnl, total_proceeds)
        """
        pos = self._positions.get(strategy_name, {}).get(symbol)
        if pos is None:
            logger.warning(f"No position found for {symbol} [{strategy_name}]")
            return (0.0, 0.0)

        close_qty = quantity if quantity else pos.quantity
        close_qty = min(close_qty, pos.quantity)

        # Calculate P&L
        if pos.side == PositionSide.LONG:
            pnl = (price - pos.avg_price) * close_qty
        else:
            pnl = (pos.avg_price - price) * close_qty

        # Return margin + P&L to cash
        margin_returned = (close_qty * pos.avg_price) / pos.leverage
        proceeds = margin_returned + pnl
        self.cash += proceeds
        self.realized_pnl += pnl

        # Update or remove position
        if close_qty >= pos.quantity:
            del self._positions[strategy_name][symbol]
        else:
            pos.quantity -= close_qty

        # Record trade
        self._trades.append({
            "symbol": symbol,
            "strategy": strategy_name,
            "side": pos.side.value,
            "quantity": close_qty,
            "entry_price": pos.avg_price,
            "exit_price": price,
            "pnl": pnl,
            "timestamp": datetime.now(),
        })

        logger.info(
            f"Closed {close_qty:.4f} {symbol} @ {price:.2f} → PnL: {pnl:,.2f} "
            f"[{strategy_name}]"
        )
        return (pnl, proceeds)

    def update_price(self, symbol: str, price: float) -> None:
        """
        Update the current market price for a position.

        Also checks stop-loss/take-profit triggers and margin levels.

        Args:
            symbol: Trading symbol
            price: Current market price
        """
        for strategy_positions in self._positions.values():
            if symbol in strategy_positions:
                strategy_positions[symbol].current_price = price

    def check_risk_events(self) -> List[Dict]:
        """
        Check for stop-loss, take-profit, and margin call events.

        Returns:
            List of risk events requiring action:
            [{type: 'stop_loss'|'take_profit'|'margin_call'|'force_liquidate',
              symbol: str, strategy: str, position: Position}]
        """
        events = []

        for strategy_name, positions in self._positions.items():
            for symbol, pos in positions.items():
                # Stop-loss check
                if pos.stop_loss:
                    if (pos.side == PositionSide.LONG and pos.current_price <= pos.stop_loss) or \
                       (pos.side == PositionSide.SHORT and pos.current_price >= pos.stop_loss):
                        events.append({
                            "type": "stop_loss",
                            "symbol": symbol,
                            "strategy": strategy_name,
                            "position": pos,
                        })

                # Take-profit check
                if pos.take_profit:
                    if (pos.side == PositionSide.LONG and pos.current_price >= pos.take_profit) or \
                       (pos.side == PositionSide.SHORT and pos.current_price <= pos.take_profit):
                        events.append({
                            "type": "take_profit",
                            "symbol": symbol,
                            "strategy": strategy_name,
                            "position": pos,
                        })

                # Margin call check
                mmr = pos.maintenance_margin_ratio
                if mmr < self.maintenance_margin_ratio:
                    events.append({
                        "type": "margin_call",
                        "symbol": symbol,
                        "strategy": strategy_name,
                        "position": pos,
                        "margin_ratio": mmr,
                    })

                # Force liquidation check
                if mmr < self.force_liquidation_ratio:
                    events.append({
                        "type": "force_liquidate",
                        "symbol": symbol,
                        "strategy": strategy_name,
                        "position": pos,
                        "margin_ratio": mmr,
                    })

        return events

    # ---- Portfolio Queries ----

    @property
    def total_equity(self) -> float:
        """Total portfolio equity (cash + position values + unrealized PnL)."""
        positions_value = sum(
            pos.market_value
            for sp in self._positions.values()
            for pos in sp.values()
        )
        unrealized = sum(
            pos.unrealized_pnl
            for sp in self._positions.values()
            for pos in sp.values()
        )
        return self.cash + positions_value + unrealized

    @property
    def positions_value(self) -> float:
        """Total market value of all positions."""
        return sum(
            pos.market_value
            for sp in self._positions.values()
            for pos in sp.values()
        )

    @property
    def total_unrealized_pnl(self) -> float:
        """Total unrealized profit/loss across all positions."""
        return sum(
            pos.unrealized_pnl
            for sp in self._positions.values()
            for pos in sp.values()
        )

    @property
    def total_margin_used(self) -> float:
        """Total margin collateral in use."""
        return sum(
            pos.margin_used
            for sp in self._positions.values()
            for pos in sp.values()
        )

    def get_position(self, symbol: str, strategy_name: str = "default") -> Optional[Position]:
        """Get position for a specific symbol and strategy."""
        return self._positions.get(strategy_name, {}).get(symbol)

    def get_all_positions(self) -> List[Position]:
        """Get all open positions across all strategies."""
        return [
            pos
            for sp in self._positions.values()
            for pos in sp.values()
        ]

    def get_strategy_positions(self, strategy_name: str) -> Dict[str, Position]:
        """Get all positions for a specific strategy."""
        return dict(self._positions.get(strategy_name, {}))

    def record_equity(self, timestamp: datetime) -> None:
        """Record current equity in the equity curve."""
        self._equity_curve.append((timestamp, self.total_equity))

    def get_equity_curve(self) -> List[Tuple[datetime, float]]:
        """Get the full equity curve."""
        return self._equity_curve

    def get_trades(self) -> List[Dict]:
        """Get all closed trades."""
        return self._trades

    def get_portfolio_state(self, timestamp: datetime) -> PortfolioState:
        """Get a snapshot of current portfolio state."""
        return PortfolioState(
            timestamp=timestamp,
            total_equity=self.total_equity,
            cash=self.cash,
            positions_value=self.positions_value,
            unrealized_pnl=self.total_unrealized_pnl,
            realized_pnl=self.realized_pnl,
            margin_used=self.total_margin_used,
            margin_available=self.cash,
            total_cost=self.total_cost,
        )

    def add_transaction_cost(self, cost: float) -> None:
        """Record transaction cost."""
        self.total_cost += cost
        self.cash -= cost

    def set_strategy_weight(self, strategy_name: str, weight: float) -> None:
        """
        Set capital allocation weight for a strategy.

        Args:
            strategy_name: Strategy identifier
            weight: Capital weight (1.0 = full allocation)
        """
        self._strategy_weights[strategy_name] = weight

    def get_strategy_capital(self, strategy_name: str) -> float:
        """
        Get available capital for a strategy based on its weight.

        Args:
            strategy_name: Strategy identifier

        Returns:
            Capital allocated to this strategy
        """
        weight = self._strategy_weights.get(strategy_name, 1.0)
        total_weight = sum(self._strategy_weights.values()) or 1.0
        return self.total_equity * (weight / total_weight)
