import copy
import logging
import logging.config
import traceback
from typing import Optional, List
import asyncio

from .config import config as logging_config

async_session_maker = None
Log = None

DB_LOG_MIN_LEVEL = logging.WARNING
DISCORD_LOG_MIN_LEVEL = logging.ERROR

_logger_namespace = "app"
_discord_webhook_url: Optional[str] = None
_discord_username: Optional[str] = None

_BASE_LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        },
        "json": {
            "format": '{"timestamp": "%(asctime)s", "logger": "%(name)s", "level": "%(levelname)s", "message": "%(message)s"}',
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
        },
        "json_console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "root": {
        "level": "INFO",
        "handlers": ["console"],
    },
    "loggers": {},
}


def configure_logging(
    namespace: str = "app",
    extra_loggers: Optional[List[str]] = None,
):
    """
    Configure console logging and optional Discord error notifications.

    Discord notifications are enabled by setting the LOG_DISCORD_WEBHOOK_URL environment variable.

    Args:
        namespace: The logger namespace for your application (e.g. "app", "myproject").
            Loggers under this namespace will receive DB/Discord handlers.
        extra_loggers: Additional logger names to configure (e.g. ["uvicorn", "fastapi"]).
    """
    global _logger_namespace, _discord_webhook_url, _discord_username
    _logger_namespace = namespace
    _discord_webhook_url = logging_config.LOG_DISCORD_WEBHOOK_URL
    _discord_username = logging_config.LOG_DISCORD_USERNAME

    config = copy.deepcopy(_BASE_LOGGING_CONFIG)
    config["loggers"] = {}

    all_logger_names = [namespace]
    if extra_loggers:
        all_logger_names.extend(extra_loggers)

    console_level = logging_config.LOG_CONSOLE_MIN_LEVEL.upper()
    use_json = logging_config.LOG_CONSOLE_FORMAT.lower() == "json"
    handler = "json_console" if use_json else "console"

    for name in all_logger_names:
        config["loggers"][name] = {
            "handlers": [handler],
            "level": console_level,
            "propagate": False,
        }

    if use_json:
        config["root"]["handlers"] = ["json_console"]

    logging.config.dictConfig(config)


def setup_db_logging(session_maker, log_model, namespace: str = "app"):
    """
    Initialize database logging with session maker and Log model.
    Call this after app startup to avoid circular imports.

    Args:
        session_maker: The async session maker for database operations
        log_model: The Log model class
        namespace: The logger namespace to attach DB/Discord handlers to
    """
    global async_session_maker, Log, DB_LOG_MIN_LEVEL, DISCORD_LOG_MIN_LEVEL, _logger_namespace
    async_session_maker = session_maker
    Log = log_model
    _logger_namespace = namespace

    from .config import config as settings

    DB_LOG_MIN_LEVEL = getattr(logging, settings.LOG_DB_MIN_LEVEL.upper(), logging.WARNING)
    DISCORD_LOG_MIN_LEVEL = getattr(logging, settings.LOG_DISCORD_MIN_LEVEL.upper(), logging.ERROR)

    register_db_handler_with_loggers()


async def log_to_db(
    level: str,
    message: str,
    logger_name: str,
    user_id: Optional[str] = None,
    path: Optional[str] = None,
    method: Optional[str] = None,
    trace: Optional[str] = None,
):
    """
    Log an event to the database.
    Only logs messages at or above the configured minimum level (default: WARNING).

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        message: Log message
        logger_name: Name of the logger
        user_id: Optional user ID
        path: Optional request path
        method: Optional request method (GET, POST, etc.)
        trace: Optional stack trace for errors
    """
    if not async_session_maker or not Log:
        return

    numeric_level = getattr(logging, level.upper(), None)
    if not numeric_level or numeric_level < DB_LOG_MIN_LEVEL:
        return

    try:
        async with async_session_maker() as session:
            log_entry = Log(
                level=level.upper(),
                message=message,
                logger_name=logger_name,
                user_id=user_id,
                path=path,
                method=method,
                trace=trace,
            )
            session.add(log_entry)
            await session.commit()
    except Exception as e:
        print(f"Error logging to database: {str(e)}")


async def log_error(
    error: Exception,
    logger_name: str,
    message: Optional[str] = None,
    user_id: Optional[str] = None,
    path: Optional[str] = None,
    method: Optional[str] = None,
):
    """
    Log an exception to the database.

    Args:
        error: The exception to log
        logger_name: Name of the logger
        message: Optional custom message (defaults to str(error))
        user_id: Optional user ID
        path: Optional request path
        method: Optional request method
    """
    error_message = message or str(error)
    trace = "".join(traceback.format_exception(type(error), error, error.__traceback__))

    await log_to_db(
        level="ERROR",
        message=error_message,
        logger_name=logger_name,
        user_id=user_id,
        path=path,
        method=method,
        trace=trace,
    )


async def log_to_discord(
    level: str,
    message: str,
    logger_name: str,
    trace: Optional[str] = None,
    user_id: Optional[str] = None,
    path: Optional[str] = None,
    method: Optional[str] = None,
    username: Optional[str] = None,
):
    """
    Send error notification to Discord if configured (non-blocking).
    Only sends logs at or above the configured minimum level (default: ERROR).

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        message: Error message
        logger_name: Name of the logger
        trace: Optional stack trace
        user_id: Optional user ID
        path: Optional request path
        method: Optional HTTP method
        username: Optional webhook display name
    """
    numeric_level = getattr(logging, level.upper(), None)
    if not numeric_level or numeric_level < DISCORD_LOG_MIN_LEVEL:
        return

    if not _discord_webhook_url:
        return

    try:
        from .discord_service import send_error_notification

        await send_error_notification(
            level=level,
            message=message,
            logger_name=logger_name,
            webhook_url=_discord_webhook_url,
            username=username,
            trace=trace,
            user_id=user_id,
            path=path,
            method=method,
        )

    except Exception as e:
        print(f"Error sending Discord error notification: {str(e)}")


class AsyncDBHandler(logging.Handler):
    """
    Custom logging handler that asynchronously logs to the database.
    Only logs messages at or above the configured minimum level.
    """

    def __init__(self, level=None):
        if level is None:
            level = DB_LOG_MIN_LEVEL
        super().__init__(level)
        self._background_tasks: set = set()

    def emit(self, record):
        if record.levelno < DB_LOG_MIN_LEVEL:
            return

        try:
            user_id = getattr(record, "user_id", None)
            path = getattr(record, "path", None)
            method = getattr(record, "method", None)

            message = self.format(record)

            trace = None
            if record.exc_info:
                trace = "".join(traceback.format_exception(*record.exc_info))

            try:
                loop = asyncio.get_running_loop()
                db_task = asyncio.create_task(
                    log_to_db(
                        level=record.levelname,
                        message=message,
                        logger_name=record.name,
                        user_id=user_id,
                        path=path,
                        method=method,
                        trace=trace,
                    )
                )
                self._background_tasks.add(db_task)
                db_task.add_done_callback(self._background_tasks.discard)

                if record.levelno >= DISCORD_LOG_MIN_LEVEL:
                    discord_task = asyncio.create_task(
                        log_to_discord(
                            level=record.levelname,
                            message=message,
                            logger_name=record.name,
                            trace=trace,
                            user_id=user_id,
                            path=path,
                            method=method,
                            username=_discord_username,
                        )
                    )
                    self._background_tasks.add(discord_task)
                    discord_task.add_done_callback(self._background_tasks.discard)
            except RuntimeError:
                print(f"DB Log: {record.levelname} - {message}")
        except Exception as e:
            print(f"Error in AsyncDBHandler: {str(e)}")
            print(f"Original log: {record.levelname} - {self.format(record)}")


_db_handler = None


def reset_db_handler():
    """Reset the global DB handler. Intended for use in tests."""
    global _db_handler
    _db_handler = None


def register_db_handler_with_loggers():
    """Register the database handler with all loggers in the configured namespace."""
    global _db_handler

    if not _db_handler:
        _db_handler = AsyncDBHandler()

    for logger_name, logger in logging.Logger.manager.loggerDict.items():
        if isinstance(logger, logging.Logger) and (
            logger_name.startswith(f"{_logger_namespace}.") or logger_name == _logger_namespace
        ):
            has_db_handler = any(
                isinstance(handler, AsyncDBHandler) for handler in logger.handlers
            )
            if not has_db_handler:
                logger.addHandler(_db_handler)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the specified name.
    If the name is in the configured namespace, adds a database handler.

    Args:
        name: The name of the logger.

    Returns:
        A logger instance with database logging enabled for namespace loggers.
    """
    logger = logging.getLogger(name)

    if name.startswith(f"{_logger_namespace}.") or name == _logger_namespace:
        global _db_handler

        has_db_handler = any(
            isinstance(handler, AsyncDBHandler) for handler in logger.handlers
        )

        if not has_db_handler:
            if not _db_handler:
                _db_handler = AsyncDBHandler()
            logger.addHandler(_db_handler)

    return logger


def add_context_to_logger(logger, user_id=None, path=None, method=None):
    """
    Add contextual information to a logger for database logging.

    Args:
        logger: The logger to add context to
        user_id: The ID of the user making the request
        path: The path of the request
        method: The HTTP method of the request

    Returns:
        A logger adapter with added context
    """

    class ContextAdapter(logging.LoggerAdapter):
        def process(self, msg, kwargs):
            kwargs.setdefault("extra", {})
            if user_id is not None:
                kwargs["extra"]["user_id"] = user_id
            if path is not None:
                kwargs["extra"]["path"] = path
            if method is not None:
                kwargs["extra"]["method"] = method
            return msg, kwargs

    return ContextAdapter(logger, {})
