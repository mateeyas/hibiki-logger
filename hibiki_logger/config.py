"""
Configuration for the logging package.

Set these in your environment or pass them to configure_logging().
"""

import os
from typing import Optional


class LoggingConfig:
    """Configuration class for logging settings"""

    LOG_CONSOLE_FORMAT: str = os.getenv("LOG_CONSOLE_FORMAT", "text")

    LOG_DB_MIN_LEVEL: str = os.getenv("LOG_DB_MIN_LEVEL", "WARNING")

    LOG_CONSOLE_MIN_LEVEL: str = os.getenv("LOG_CONSOLE_MIN_LEVEL", "INFO")

    LOG_DISCORD_MIN_LEVEL: str = os.getenv("LOG_DISCORD_MIN_LEVEL", "ERROR")

    LOG_DISCORD_WEBHOOK_URL: Optional[str] = os.getenv("LOG_DISCORD_WEBHOOK_URL")

    LOG_DISCORD_USERNAME: Optional[str] = os.getenv("LOG_DISCORD_USERNAME")

    LOG_DB_TABLE_NAME: str = os.getenv("LOG_DB_TABLE_NAME") or os.getenv("LOG_TABLE_NAME", "log")

    @classmethod
    def from_dict(cls, config: dict):
        """Create config from dictionary"""
        for key, value in config.items():
            if hasattr(cls, key):
                setattr(cls, key, value)
        return cls


config = LoggingConfig()
