"""
Configuration for the logging package.

Set these in your environment or pass them to configure_logging().
"""

import os
from typing import Optional

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def _int_env(name: str, default: int, minimum: int = 1) -> int:
    """Read an integer env var, falling back on anything unusable.

    `minimum` is 1 by default but 0 where zero is a meaningful setting, so
    an operator can switch a stage off rather than silently receiving the
    default they were trying to override.
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value >= minimum else default


def _bool_env(name: str, default: bool) -> bool:
    """Read a boolean env var, falling back on anything unrecognised."""
    raw = os.getenv(name)
    if raw is None:
        return default
    normalised = raw.strip().lower()
    if normalised in _TRUE_VALUES:
        return True
    if normalised in _FALSE_VALUES:
        return False
    return default


class LoggingConfig:
    """Configuration class for logging settings"""

    LOG_CONSOLE_FORMAT: str = os.getenv("LOG_CONSOLE_FORMAT", "text")

    LOG_DB_MIN_LEVEL: str = os.getenv("LOG_DB_MIN_LEVEL", "WARNING")

    LOG_CONSOLE_MIN_LEVEL: str = os.getenv("LOG_CONSOLE_MIN_LEVEL", "INFO")

    LOG_DISCORD_MIN_LEVEL: str = os.getenv("LOG_DISCORD_MIN_LEVEL", "ERROR")

    LOG_DISCORD_WEBHOOK_URL: Optional[str] = os.getenv("LOG_DISCORD_WEBHOOK_URL")

    LOG_DISCORD_USERNAME: Optional[str] = os.getenv("LOG_DISCORD_USERNAME")

    LOG_DB_TABLE_NAME: str = os.getenv("LOG_DB_TABLE_NAME") or os.getenv("LOG_TABLE_NAME", "log")

    # Seconds during which alerts sharing a dedup key collapse into one send.
    # Set to 0 to disable deduplication.
    LOG_DISCORD_DEDUP_WINDOW: int = _int_env("LOG_DISCORD_DEDUP_WINDOW", 300, minimum=0)

    # Webhook send budget over a sliding 60 second window. Discord allows
    # roughly 5 requests per 2 seconds; the default sits well below that.
    # Alerts beyond the budget are dropped and counted, not queued. Must be
    # at least 1; there is no "send nothing" setting, as unsetting
    # LOG_DISCORD_WEBHOOK_URL already disables Discord entirely.
    LOG_DISCORD_MAX_PER_MINUTE: int = _int_env("LOG_DISCORD_MAX_PER_MINUTE", 30)

    LOG_DISCORD_EMBED: bool = _bool_env("LOG_DISCORD_EMBED", True)

    @classmethod
    def from_dict(cls, config: dict):
        """Create config from dictionary"""
        for key, value in config.items():
            if hasattr(cls, key):
                setattr(cls, key, value)
        return cls


config = LoggingConfig()
