"""
QuantEngine Pro - Performance Analyzer
=======================================
Comprehensive backtest performance analysis.

Metrics calculated:
- Total/Annual return, Sharpe ratio, Sortino ratio
- Maximum drawdown, Calmar ratio
- Win rate, profit factor, expectancy
- Monthly/annual returns heatmap
- Benchmark comparison
"""

import math
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from loguru import logger


class PerformanceAnalyzer:
    """
    Calculate comprehensive performance metrics from backtest results.

    Usage:
        analyzer = PerformanceAnalyzer(equity_curve, trades, initial_capital)
        report = analyzer.analyze()
        print(analyzer.summary())
    """

    def __init__(
        self,
        equity_curve: List[Tuple[datetime, float]],
        trades: List[Dict],
        initial_capital: float = 100000.0,
        benchmark_returns: Optional[pd.Series] = None,
        signals: Optional[List] = None,
        risk_free_rate: float = 0.03,  # 3% annual risk-free rate
    ):
        """
        Initialize analyzer.

        Args:
            equity_curve: List of (timestamp, equity) tuples
            trades: List of trade dicts with 'pnl', 'symbol', etc.
            initial_capital: Starting portfolio value
            benchmark_returns: Optional benchmark return series (e.g., CSI 300)
            signals: Optional list of generated signals
            risk_free_rate: Annual risk-free rate (default 3%)
        """
        self.initial_capital = initial_capital
        self.risk_free_rate = risk_free_rate
        self.benchmark_returns = benchmark_returns
        self.signals = signals or []

        # Convert to DataFrames
        if equity_curve:
            self.equity_df = pd.DataFrame(
                equity_curve, columns=["timestamp", "equity"]
            )
            self.equity_df["daily_return"] = self.equity_df["equity"].pct_change()
        else:
            self.equity_df = pd.DataFrame(columns=["timestamp", "equity", "daily_return"])

        self.trades_df = pd.DataFrame(trades) if trades else pd.DataFrame()
        self._report: Optional[Dict] = None

    def analyze(self) -> Dict:
        """
        Run full performance analysis.

        Returns:
            Dict with all performance metrics
        """
        if self.equity_df.empty:
            logger.warning("No equity data to analyze")
            return {"error": "No data"}

        returns = self.equity_df["daily_return"].dropna()

        # Calculate all metrics
        total_return = self._calc_total_return()
        annual_return = self._calc_annual_return(returns)
        volatility = self._calc_volatility(returns)
        sharpe = self._calc_sharpe(returns)
        sortino = self._calc_sortino(returns)
        max_dd, max_dd_duration = self._calc_max_drawdown()
        calmar = self._calc_calmar(annual_return, max_dd)
        win_rate, avg_win, avg_loss, profit_factor = self._calc_trade_stats()
        var_95 = self._calc_var(returns, 0.95)
        cvar_95 = self._calc_cvar(returns, 0.95)

        # Monthly returns
        monthly_returns = self._calc_monthly_returns()

        # Benchmark comparison
        benchmark_metrics = self._calc_benchmark_comparison(returns)

        self._report = {
            # Basic metrics
            "start_date": self.equity_df["timestamp"].iloc[0],
            "end_date": self.equity_df["timestamp"].iloc[-1],
            "trading_days": len(returns),
            "initial_capital": self.initial_capital,
            "final_equity": float(self.equity_df["equity"].iloc[-1]),

            # Returns
            "total_return_pct": round(total_return * 100, 2),
            "annual_return_pct": round(annual_return * 100, 2),
            "volatility_pct": round(volatility * 100, 2),
            "total_pnl": float(self.equity_df["equity"].iloc[-1] - self.initial_capital),

            # Risk-adjusted
            "sharpe_ratio": round(sharpe, 3),
            "sortino_ratio": round(sortino, 3),
            "calmar_ratio": round(calmar, 3),
            "max_drawdown_pct": round(max_dd * 100, 2),
            "max_drawdown_duration_days": max_dd_duration,

            # Risk
            "var_95_pct": round(var_95 * 100, 3),
            "cvar_95_pct": round(cvar_95 * 100, 3),

            # Trade stats
            "total_trades": len(self.trades_df),
            "win_rate_pct": round(win_rate * 100, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(profit_factor, 2),
            "total_costs": 0.0,  # Populated by engine

            # Benchmark
            "benchmark": benchmark_metrics,

            # Monthly returns
            "monthly_returns": monthly_returns.to_dict() if not monthly_returns.empty else {},

            # Signals
            "total_signals": len(self.signals),
        }

        logger.info(
            f"Analysis complete: total_return={self._report['total_return_pct']}%, "
            f"sharpe={sharpe:.2f}, max_dd={self._report['max_drawdown_pct']}%"
        )
        return self._report

    def _calc_total_return(self) -> float:
        """Calculate total return."""
        if self.initial_capital <= 0:
            return 0.0
        final = self.equity_df["equity"].iloc[-1]
        return (final - self.initial_capital) / self.initial_capital

    def _calc_annual_return(self, returns: pd.Series) -> float:
        """Calculate annualized return (CAGR)."""
        if len(returns) < 2:
            return 0.0

        total_return = self._calc_total_return()
        years = len(returns) / 252  # Trading days per year
        if years <= 0:
            return 0.0

        return (1 + total_return) ** (1 / years) - 1

    def _calc_volatility(self, returns: pd.Series) -> float:
        """Calculate annualized volatility."""
        if len(returns) < 2:
            return 0.0
        return returns.std() * math.sqrt(252)

    def _calc_sharpe(self, returns: pd.Series) -> float:
        """Calculate Sharpe ratio (annualized)."""
        if len(returns) < 2:
            return 0.0

        excess = returns - self.risk_free_rate / 252
        if excess.std() == 0:
            return 0.0

        return (excess.mean() / excess.std()) * math.sqrt(252)

    def _calc_sortino(self, returns: pd.Series) -> float:
        """Calculate Sortino ratio (uses downside deviation only)."""
        if len(returns) < 2:
            return 0.0

        downside = returns[returns < 0]
        if len(downside) == 0 or downside.std() == 0:
            return 0.0

        excess = returns.mean() - self.risk_free_rate / 252
        return (excess / downside.std()) * math.sqrt(252)

    def _calc_max_drawdown(self) -> Tuple[float, int]:
        """
        Calculate maximum drawdown and longest drawdown duration.

        Returns:
            Tuple of (max_drawdown_pct, max_drawdown_duration_days)
        """
        equity = self.equity_df["equity"].values
        if len(equity) < 2:
            return (0.0, 0)

        # Running maximum
        running_max = np.maximum.accumulate(equity)
        drawdowns = (equity - running_max) / running_max

        max_dd = abs(drawdowns.min()) if len(drawdowns) > 0 else 0.0

        # Max drawdown duration (days underwater)
        max_duration = 0
        current_duration = 0
        for dd in drawdowns:
            if dd < 0:
                current_duration += 1
                max_duration = max(max_duration, current_duration)
            else:
                current_duration = 0

        return (float(max_dd), max_duration)

    def _calc_calmar(self, annual_return: float, max_dd: float) -> float:
        """Calculate Calmar ratio (annual return / max drawdown)."""
        if max_dd == 0:
            return 0.0
        return annual_return / max_dd

    def _calc_trade_stats(self) -> Tuple[float, float, float, float]:
        """
        Calculate trade statistics.

        Returns:
            Tuple of (win_rate, avg_win, avg_loss, profit_factor)
        """
        if self.trades_df.empty or "pnl" not in self.trades_df.columns:
            return (0.0, 0.0, 0.0, 0.0)

        wins = self.trades_df[self.trades_df["pnl"] > 0]["pnl"]
        losses = self.trades_df[self.trades_df["pnl"] <= 0]["pnl"]

        total_trades = len(self.trades_df)
        win_rate = len(wins) / total_trades if total_trades > 0 else 0.0
        avg_win = wins.mean() if len(wins) > 0 else 0.0
        avg_loss = abs(losses.mean()) if len(losses) > 0 else 0.0

        # Profit factor: gross profit / gross loss
        gross_profit = wins.sum() if len(wins) > 0 else 0.0
        gross_loss = abs(losses.sum()) if len(losses) > 0 else 0.0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        return (win_rate, avg_win, avg_loss, profit_factor)

    def _calc_var(self, returns: pd.Series, confidence: float = 0.95) -> float:
        """
        Calculate Value at Risk (historical method).

        Args:
            returns: Daily return series
            confidence: Confidence level

        Returns:
            VaR as a positive number (e.g., 0.02 = 2% daily VaR)
        """
        if len(returns) < 10:
            return 0.0
        return abs(returns.quantile(1 - confidence))

    def _calc_cvar(self, returns: pd.Series, confidence: float = 0.95) -> float:
        """
        Calculate Conditional VaR (Expected Shortfall).

        Args:
            returns: Daily return series
            confidence: Confidence level

        Returns:
            CVaR as a positive number
        """
        if len(returns) < 10:
            return 0.0
        var = returns.quantile(1 - confidence)
        return abs(returns[returns <= var].mean())

    def _calc_monthly_returns(self) -> pd.DataFrame:
        """Calculate monthly returns matrix for heatmap."""
        if self.equity_df.empty:
            return pd.DataFrame()

        df = self.equity_df.set_index("timestamp")
        if len(df) < 20:
            return pd.DataFrame()

        # Resample to monthly
        monthly = df["equity"].resample("ME").last().pct_change()

        # Create pivot: rows=years, cols=months
        monthly_df = monthly.reset_index()
        monthly_df["year"] = monthly_df["timestamp"].dt.year
        monthly_df["month"] = monthly_df["timestamp"].dt.month

        pivot = monthly_df.pivot(
            index="year", columns="month", values="equity"
        )
        pivot.columns = [
            "Jan","Feb","Mar","Apr","May","Jun",
            "Jul","Aug","Sep","Oct","Nov","Dec"
        ][:len(pivot.columns)]

        return pivot

    def _calc_benchmark_comparison(self, returns: pd.Series) -> Dict:
        """
        Compare strategy returns to benchmark.

        Returns:
            Dict with alpha, beta, information ratio, tracking error
        """
        if self.benchmark_returns is None or self.benchmark_returns.empty:
            return {"available": False}

        # Align returns
        aligned = pd.concat([returns, self.benchmark_returns], axis=1).dropna()
        if len(aligned) < 30:
            return {"available": False, "error": "Insufficient data"}

        aligned.columns = ["strategy", "benchmark"]

        # Beta
        cov = aligned.cov().iloc[0, 1]
        bench_var = aligned["benchmark"].var()
        beta = cov / bench_var if bench_var > 0 else 1.0

        # Alpha (annualized)
        excess_strategy = aligned["strategy"].mean() * 252
        excess_benchmark = aligned["benchmark"].mean() * 252
        alpha = excess_strategy - beta * excess_benchmark

        # Information ratio
        tracking_error = (aligned["strategy"] - aligned["benchmark"]).std() * math.sqrt(252)
        ir = (excess_strategy - excess_benchmark) / tracking_error if tracking_error > 0 else 0

        return {
            "available": True,
            "alpha": round(alpha, 4),
            "beta": round(beta, 4),
            "information_ratio": round(ir, 3),
            "tracking_error": round(tracking_error, 4),
        }

    def summary(self) -> str:
        """Get human-readable performance summary."""
        if not self._report:
            self.analyze()

        r = self._report or {}
        if "error" in r:
            return f"Analysis error: {r['error']}"

        lines = [
            "=" * 55,
            "          QuantEngine Pro - Performance Report",
            "=" * 55,
            f"  Period:       {r.get('start_date', 'N/A')} → {r.get('end_date', 'N/A')}",
            f"  Trading Days: {r.get('trading_days', 0)}",
            "",
            f"  Initial:      {r.get('initial_capital', 0):>12,.2f}",
            f"  Final:        {r.get('final_equity', 0):>12,.2f}",
            f"  Total PnL:    {r.get('total_pnl', 0):>12,.2f}",
            f"  Total Return: {r.get('total_return_pct', 0):>11.2f}%",
            f"  Annual Return:{r.get('annual_return_pct', 0):>11.2f}%",
            "",
            f"  Sharpe:       {r.get('sharpe_ratio', 0):>12.3f}",
            f"  Sortino:      {r.get('sortino_ratio', 0):>12.3f}",
            f"  Calmar:       {r.get('calmar_ratio', 0):>12.3f}",
            f"  Max DD:       {r.get('max_drawdown_pct', 0):>11.2f}%",
            f"  Volatility:   {r.get('volatility_pct', 0):>11.2f}%",
            f"  VaR (95%):    {r.get('var_95_pct', 0):>11.3f}%",
            f"  CVaR (95%):   {r.get('cvar_95_pct', 0):>11.3f}%",
            "",
            f"  Total Trades: {r.get('total_trades', 0)}",
            f"  Win Rate:     {r.get('win_rate_pct', 0):>11.2f}%",
            f"  Avg Win:      {r.get('avg_win', 0):>12,.2f}",
            f"  Avg Loss:     {r.get('avg_loss', 0):>12,.2f}",
            f"  Profit Factor:{r.get('profit_factor', 0):>11.2f}",
            f"  Total Signals:{r.get('total_signals', 0)}",
            "=" * 55,
        ]
        return "\n".join(lines)

    def to_dataframe(self) -> pd.DataFrame:
        """Convert report metrics to a DataFrame for easy viewing."""
        if not self._report:
            self.analyze()

        # Flatten the report dict
        flat = {}
        for k, v in (self._report or {}).items():
            if isinstance(v, dict):
                for sk, sv in v.items():
                    flat[f"{k}.{sk}"] = sv
            else:
                flat[k] = v

        return pd.DataFrame([flat]).T
