"""
QuantEngine Pro - Risk Manager
================================
Real-time risk monitoring and enforcement.

Checks:
- Single symbol position ≤ 20% of portfolio
- Total position ≤ 95% of capital
- Daily loss ≥ 5% → pause trading
- 5 consecutive losses → circuit breaker until next day
- Blacklist: ST stocks, low liquidity, abnormal volatility
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Deque, Dict, List, Optional

from loguru import logger


class RiskLevel(str, Enum):
    """Risk alert severity levels."""
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass
class RiskCheckResult:
    """Result of a risk check."""
    passed: bool = True
    level: RiskLevel = RiskLevel.INFO
    message: str = ""
    action_required: str = ""


class RiskManager:
    """
    Real-time risk management system.

    Monitors positions, P&L, and trading behavior to enforce
    risk limits and prevent catastrophic losses.
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize risk manager.

        Args:
            config: Risk configuration dict with keys:
                - max_single_symbol_pct: Max single position (default 0.20)
                - max_total_position_pct: Max total allocation (default 0.95)
                - max_daily_loss_pct: Daily loss limit (default 0.05)
                - consecutive_loss_limit: Max consecutive losses (default 5)
                - circuit_breaker_hours: Lock duration after breaker (default 24)
        """
        config = config or {}
        self.max_single_symbol_pct = config.get("max_single_symbol_pct", 0.20)
        self.max_total_position_pct = config.get("max_total_position_pct", 0.95)
        self.max_daily_loss_pct = config.get("max_daily_loss_pct", 0.05)
        self.consecutive_loss_limit = config.get("consecutive_loss_limit", 5)
        self.circuit_breaker_hours = config.get("circuit_breaker_hours", 24)

        # State tracking
        self._daily_start_equity: Optional[float] = None
        self._daily_pnl: float = 0.0
        self._consecutive_losses: int = 0
        self._is_circuit_breaker: bool = False
        self._circuit_breaker_until: Optional[datetime] = None
        self._last_trade_results: Deque[bool] = deque(maxlen=20)  # True=win, False=loss

        # Blacklist
        self._blacklist: set = set()

        logger.info(
            f"RiskManager initialized: max_single={self.max_single_symbol_pct:.0%}, "
            f"max_total={self.max_total_position_pct:.0%}, "
            f"daily_loss_limit={self.max_daily_loss_pct:.0%}"
        )

    def check_order(
        self,
        symbol: str,
        quantity: float,
        price: float,
        portfolio_value: float,
        current_positions: Dict[str, Dict],
    ) -> RiskCheckResult:
        """
        Check if an order passes all risk constraints.

        Args:
            symbol: Trading symbol
            quantity: Order quantity
            price: Order price
            portfolio_value: Current total portfolio value (equity)
            current_positions: Current position dict

        Returns:
            RiskCheckResult with pass/fail status
        """
        if portfolio_value <= 0:
            return RiskCheckResult(
                passed=False,
                level=RiskLevel.CRITICAL,
                message="Portfolio value is zero or negative",
            )

        # Check 1: Circuit breaker
        if self._is_circuit_breaker:
            if self._circuit_breaker_until and datetime.now() < self._circuit_breaker_until:
                remaining = (self._circuit_breaker_until - datetime.now()).total_seconds() / 3600
                return RiskCheckResult(
                    passed=False,
                    level=RiskLevel.CRITICAL,
                    message=f"Circuit breaker active for {remaining:.1f} more hours",
                )
            else:
                self._is_circuit_breaker = False
                self._consecutive_losses = 0

        # Check 2: Blacklist
        if symbol in self._blacklist:
            return RiskCheckResult(
                passed=False,
                level=RiskLevel.WARNING,
                message=f"Symbol {symbol} is blacklisted",
            )

        # Check 3: Daily loss limit
        if self._daily_start_equity:
            daily_return = (portfolio_value - self._daily_start_equity) / self._daily_start_equity
            if daily_return < -self.max_daily_loss_pct:
                return RiskCheckResult(
                    passed=False,
                    level=RiskLevel.CRITICAL,
                    message=f"Daily loss limit reached: {daily_return:.2%}",
                )

        # Check 4: Single symbol position limit
        order_value = quantity * price
        position_pct = order_value / portfolio_value

        # Include existing position
        existing = current_positions.get(symbol, {})
        existing_qty = existing.get("quantity", 0)
        existing_price = existing.get("current_price", price)
        total_exposure = (existing_qty * existing_price + order_value) / portfolio_value

        if total_exposure > self.max_single_symbol_pct:
            return RiskCheckResult(
                passed=False,
                level=RiskLevel.WARNING,
                message=f"Position {total_exposure:.1%} exceeds limit {self.max_single_symbol_pct:.0%}",
            )

        # Check 5: Total position limit
        total_current = sum(
            p.get("quantity", 0) * p.get("current_price", 0)
            for p in current_positions.values()
        )
        if (total_current + order_value) / portfolio_value > self.max_total_position_pct:
            return RiskCheckResult(
                passed=False,
                level=RiskLevel.WARNING,
                message=f"Total position would exceed {self.max_total_position_pct:.0%}",
            )

        return RiskCheckResult(passed=True)

    def record_trade(self, pnl: float) -> None:
        """
        Record a completed trade for loss streak tracking.

        Args:
            pnl: Realized profit/loss from the trade
        """
        is_win = pnl > 0
        self._last_trade_results.append(is_win)

        self._daily_pnl += pnl

        if is_win:
            self._consecutive_losses = 0
        else:
            self._consecutive_losses += 1

        # Check circuit breaker
        if self._consecutive_losses >= self.consecutive_loss_limit:
            self._is_circuit_breaker = True
            self._circuit_breaker_until = datetime.now() + timedelta(
                hours=self.circuit_breaker_hours
            )
            logger.error(
                f"CIRCUIT BREAKER: {self.consecutive_losses} consecutive losses. "
                f"Trading paused until {self._circuit_breaker_until}"
            )

    def reset_daily(self, current_equity: float) -> None:
        """
        Reset daily tracking at start of new trading day.

        Args:
            current_equity: Current portfolio value
        """
        self._daily_start_equity = current_equity
        self._daily_pnl = 0.0
        logger.info(f"Daily risk reset. Starting equity: {current_equity:,.2f}")

    def add_to_blacklist(self, symbol: str, reason: str = "") -> None:
        """
        Add symbol to trading blacklist.

        Args:
            symbol: Symbol to blacklist
            reason: Reason for blacklisting
        """
        self._blacklist.add(symbol)
        logger.warning(f"Blacklisted {symbol}: {reason}")

    def remove_from_blacklist(self, symbol: str) -> None:
        """Remove symbol from blacklist."""
        self._blacklist.discard(symbol)

    def filter_blacklist(self, symbols: List[str]) -> List[str]:
        """
        Filter out blacklisted symbols.

        Args:
            symbols: List of candidate symbols

        Returns:
            Filtered symbol list
        """
        filtered = [s for s in symbols if s not in self._blacklist]
        removed = len(symbols) - len(filtered)
        if removed > 0:
            logger.info(f"Filtered {removed} blacklisted symbols")
        return filtered

    @property
    def is_trading_allowed(self) -> bool:
        """Check if trading is currently allowed."""
        if self._is_circuit_breaker:
            if self._circuit_breaker_until and datetime.now() >= self._circuit_breaker_until:
                self._is_circuit_breaker = False
                self._consecutive_losses = 0
                return True
            return False
        return True

    @property
    def stats(self) -> Dict:
        """Get current risk statistics."""
        return {
            "circuit_breaker": self._is_circuit_breaker,
            "consecutive_losses": self._consecutive_losses,
            "daily_pnl": self._daily_pnl,
            "blacklist_size": len(self._blacklist),
            "trading_allowed": self.is_trading_allowed,
        }
