"""
QuantEngine Pro - Full-featured Quantitative Trading System
===========================================================
Supports multi-market (spot/contracts), multi-strategy, multi-data-source
quantitative trading with full lifecycle: data → factors → strategy →
backtest → execution → monitoring.

Architecture: Layered + Event-driven + Plugin-based
"""

__version__ = "0.1.0"
__author__ = "QuantEngine Team"

from quantengine.utils.logging import setup_logging

# Auto-setup logging on import
setup_logging()
