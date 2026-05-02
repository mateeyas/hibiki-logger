"""
Hibiki Logger - Production Logging with Discord Notifications

A logging package with console, database, and Discord notification support.

Features:
- Console logging (human-readable or JSON)
- Database logging via SQLAlchemy (engine-agnostic; bring your own async driver)
- Discord error notifications (via webhook URL)
- Configurable log levels for each destination
- Non-blocking async operations

Installation:
    pip install hibiki-logger

Usage:
    from hibiki_logger import configure_logging, get_logger

    configure_logging(namespace="myapp")

    logger = get_logger("myapp.service")
    logger.error("Something went wrong", exc_info=True)
"""

__version__ = "1.3.0"

from .logger import (
    configure_logging,
    setup_db_logging,
    get_logger,
    add_context_to_logger,
    log_to_db,
    log_to_discord,
    log_error,
)

__all__ = [
    "configure_logging",
    "setup_db_logging",
    "get_logger",
    "add_context_to_logger",
    "log_to_db",
    "log_to_discord",
    "log_error",
]
