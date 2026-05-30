"""
QuantEngine Pro - Logging System
=================================
Centralized logging configuration using loguru.
Provides structured, rotating file logs with configurable levels.
"""

import sys
from pathlib import Path

from loguru import logger


def setup_logging(
    log_level: str = "INFO",
    log_dir: str = "./logs",
    rotation: str = "10 MB",
    retention: str = "30 days",
    json_format: bool = False,
) -> None:
    """
    Configure the global logging system for QuantEngine Pro.

    Args:
        log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR)
        log_dir: Directory for log files
        rotation: When to rotate log files
        retention: How long to keep old logs
        json_format: If True, output JSON-formatted logs for machine parsing
    """
    # Remove default handler
    logger.remove()

    # Console handler - colored, human-readable
    logger.add(
        sys.stderr,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        level=log_level,
        colorize=True,
    )

    # Ensure log directory exists
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    if json_format:
        # JSON format for machine parsing
        logger.add(
            log_path / "quantengine_{time:YYYY-MM-DD}.jsonl",
            format="{message}",
            level=log_level,
            rotation=rotation,
            retention=retention,
            serialize=True,  # JSON serialization
        )
    else:
        # Standard file log - detailed
        logger.add(
            log_path / "quantengine_{time:YYYY-MM-DD}.log",
            format=(
                "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
                "{name}:{function}:{line} | {message}"
            ),
            level="DEBUG",  # File always logs DEBUG
            rotation=rotation,
            retention=retention,
        )

        # Error-only log file
        logger.add(
            log_path / "error_{time:YYYY-MM-DD}.log",
            format=(
                "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
                "{name}:{function}:{line} | {message}\n{exception}"
            ),
            level="ERROR",
            rotation=rotation,
            retention=retention * 2,  # Keep errors longer
            backtrace=True,
            diagnose=True,
        )

    logger.info("QuantEngine Pro logging system initialized")
    logger.debug(f"Log level: {log_level}, log dir: {log_dir}")


def get_logger(name: str):
    """
    Get a logger instance with the given name.

    Args:
        name: Logger name (usually __name__)

    Returns:
        loguru.Logger: Configured logger instance
    """
    return logger.bind(name=name)
