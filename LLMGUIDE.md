# Hibiki Logger -- AI Reference Guide

> This document is designed to be provided to AI coding assistants as context when working with or integrating the `hibiki-logger` package. It covers architecture, API surface, initialization requirements, and common pitfalls.

## What is hibiki-logger?

Hibiki Logger (v1.0.1) is a Python 3.10+ logging library that routes log messages to three destinations: **console**, **PostgreSQL** (or any SQLAlchemy-supported database), and **Discord** (via webhooks). All DB and Discord I/O is async and non-blocking.

**Runtime dependencies:** `sqlalchemy>=2.0.0`, `asyncpg>=0.28.0`, `aiohttp>=3.8.0`

## Quick Start

```python
from hibiki_logger import configure_logging, setup_db_logging, get_logger
from hibiki_logger.models import create_log_model
from sqlalchemy.orm import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

Base = declarative_base()
Log = create_log_model(Base)
engine = create_async_engine("postgresql+asyncpg://user:pass@localhost/db")
session_maker = async_sessionmaker(engine, expire_on_commit=False)

configure_logging(namespace="myapp")
setup_db_logging(session_maker=session_maker, log_model=Log, namespace="myapp")

logger = get_logger("myapp.api")
logger.info("Ready")
```

## Module Map

```
hibiki_logger/
├── __init__.py          # Public API -- 7 exported functions
├── logger.py            # Core: configure_logging, setup_db_logging, get_logger, AsyncDBHandler
├── config.py            # LoggingConfig -- reads env vars
├── models.py            # SQLAlchemy model factory + raw SQL constant
└── discord_service.py   # Discord webhook helpers
```

**Dependency flow:** `config` feeds into `logger`. `logger` imports `discord_service` lazily at send time. `models` is independent and consumed by the host application.

## Initialization Sequence (REQUIRED)

Initialization is a **two-step process** that must happen in order:

```python
from hibiki_logger import configure_logging, setup_db_logging, get_logger
from hibiki_logger.models import create_log_model
from sqlalchemy.orm import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

Base = declarative_base()
Log = create_log_model(Base)

engine = create_async_engine("postgresql+asyncpg://user:pass@localhost/db")
session_maker = async_sessionmaker(engine, expire_on_commit=False)

# Step 1: Console logging + set namespace + optional Discord
configure_logging(namespace="myapp")

# Step 2: DB logging (call AFTER engine/session are ready)
setup_db_logging(
    session_maker=session_maker,
    log_model=Log,
    namespace="myapp",
)
```

**Rules:**
- `configure_logging` must be called before `setup_db_logging`.
- `setup_db_logging` must be called after the database engine and session maker are created.
- The `namespace` argument must be the same in both calls.
- `get_logger` is safe to call at module level (before `configure_logging`). It returns a standard `logging.Logger`. DB/Discord handlers may be attached, but no writes happen until `setup_db_logging` has been called.

## Discord Setup

Discord error notifications are enabled by setting the `LOG_DISCORD_WEBHOOK_URL` environment variable. No code changes are needed.

No encryption, database tables, or additional configuration is needed.

## Namespace Convention

The namespace controls which loggers receive DB and Discord handlers. Only loggers whose name equals or starts with `namespace + "."` get those handlers.

```python
configure_logging(namespace="myapp")
setup_db_logging(session_maker=..., log_model=..., namespace="myapp")

get_logger("myapp")          # DB + Discord + console
get_logger("myapp.api")      # DB + Discord + console
get_logger("myapp.api.auth") # DB + Discord + console
get_logger("other.module")   # console ONLY
```

To include third-party loggers in console configuration (not DB/Discord):

```python
configure_logging(namespace="myapp", extra_loggers=["uvicorn", "fastapi"])
```

## Public API Reference

### Top-level exports (`from hibiki_logger import ...`)

| Function | Signature | Description |
|----------|-----------|-------------|
| `configure_logging` | `(namespace="app", extra_loggers=None)` | Configure console logging, set namespace, and optionally enable Discord. Call once at startup. |
| `setup_db_logging` | `(session_maker, log_model, namespace="app")` | Initialize DB logging. Call after DB is ready. |
| `get_logger` | `(name: str) -> logging.Logger` | Get a logger. Attaches DB/Discord handlers if name matches namespace. |
| `add_context_to_logger` | `(logger, user_id=None, path=None, method=None) -> LoggerAdapter` | Wrap a logger with request context (stored in DB and Discord entries). |
| `log_to_db` | `async (level, message, logger_name, user_id?, path?, method?, trace?)` | Manually write a log entry to the database. Respects `LOG_DB_MIN_LEVEL`. |
| `log_to_discord` | `async (level, message, logger_name, trace?, user_id?, path?, method?)` | Manually send a Discord notification. Respects `LOG_DISCORD_MIN_LEVEL`. |
| `log_error` | `async (error, logger_name, message?, user_id?, path?, method?)` | Log an exception to DB with auto-extracted traceback. |

### Internal helpers (test use)

| Function | Import Path | Description |
|----------|-------------|-------------|
| `reset_db_handler` | `from hibiki_logger.logger import reset_db_handler` | Clear the global DB handler singleton. Call between tests to ensure handler isolation. Takes no arguments. |

### Models (`from hibiki_logger.models import ...`)

| Export | Type | Description |
|--------|------|-------------|
| `create_log_model(Base, table_name?)` | Factory function | Returns a `Log` SQLAlchemy model bound to the given `Base`. Table name defaults to `LOG_TABLE_NAME` env var (then `"log"`). |
| `get_log_table_sql(table_name?)` | Function | Returns raw PostgreSQL DDL for the log table. Table name defaults to `LOG_TABLE_NAME` env var (then `"log"`). |
| `LOG_TABLE_SQL` | `str` | Pre-built DDL using the default table name (convenience shorthand for `get_log_table_sql()`). |

### Discord Service (`from hibiki_logger.discord_service import ...`)

| Function | Signature | Description |
|----------|-----------|-------------|
| `send_discord_notification` | `async (message, webhook_url, username?, avatar_url?) -> bool` | Send a plain message to a Discord webhook. |
| `send_error_notification` | `async (level, message, logger_name, webhook_url, username?, trace?, user_id?, path?, method?) -> bool` | Send a formatted error notification. |

## Model Factory Pattern

Models are created via factory functions so they bind to the host application's SQLAlchemy `Base`:

```python
from sqlalchemy.orm import declarative_base
from hibiki_logger.models import create_log_model

Base = declarative_base()
Log = create_log_model(Base)                          # table "log" (default)
Log = create_log_model(Base, table_name="app_log")    # custom table name
```

The table name can also be set globally via the `LOG_TABLE_NAME` environment variable.

The `Log` model has columns: `id` (UUID string), `level`, `message`, `logger_name`, `user_id`, `path`, `method`, `trace`, `created_at`.

If you don't use SQLAlchemy, use `get_log_table_sql()` or the pre-built `LOG_TABLE_SQL` constant instead.

## Async Behavior

`AsyncDBHandler` is a `logging.Handler` subclass. When its `emit()` method fires:

1. It checks for a running asyncio event loop via `asyncio.get_running_loop()`.
2. It creates background `asyncio.Task`s for `log_to_db()` and (if level is high enough) `log_to_discord()`.
3. Tasks are fire-and-forget -- the logging call returns immediately.
4. If no event loop is running, it falls back to printing the log to stdout.

**When calling `log_to_db`, `log_to_discord`, or `log_error` directly**, they are `async` functions and must be awaited:

```python
await log_to_db(level="ERROR", message="something broke", logger_name="myapp.api")
await log_error(error=exc, logger_name="myapp.api", user_id="123")
```

Using `logger.error(...)` via `get_logger` does NOT require await -- the handler manages async internally.

## Configuration via Environment Variables

| Variable | Default | Effect |
|----------|---------|--------|
| `ENV` | `development` | `production` switches console to JSON format and ERROR-only level. |
| `LOG_TABLE_NAME` | `log` | Database table name for log entries. |
| `LOG_DB_MIN_LEVEL` | `WARNING` | Minimum level for database logging. Options: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. |
| `LOG_DISCORD_MIN_LEVEL` | `ERROR` | Minimum level for Discord notifications. Same options. |
| `LOG_DISCORD_WEBHOOK_URL` | *(none)* | Discord webhook URL for error notifications. |

Config is read at import time by `hibiki_logger.config.LoggingConfig` and re-read when `setup_db_logging` is called.

## Framework Integration Patterns

### FastAPI

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from hibiki_logger import configure_logging, setup_db_logging, get_logger

@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(namespace="myapp", extra_loggers=["uvicorn", "fastapi"])
    setup_db_logging(
        session_maker=async_session_maker,
        log_model=Log,
        namespace="myapp",
    )
    yield

app = FastAPI(lifespan=lifespan)
logger = get_logger("myapp.routes")  # safe at module level -- see init rules above
```

### Django

```python
# settings.py
from hibiki_logger import configure_logging
configure_logging(namespace="myproject")

# views.py
from hibiki_logger import get_logger
logger = get_logger("myproject.views")
```

### Flask

```python
from hibiki_logger import configure_logging, get_logger

configure_logging(namespace="myapp")
logger = get_logger("myapp.routes")
```

## Common Mistakes to Avoid

| Mistake | Why it fails | Fix |
|---------|-------------|-----|
| Namespace mismatch between `configure_logging` and `get_logger` | Logger won't get DB/Discord handlers | Use the same namespace prefix everywhere |
| Calling `setup_db_logging` before engine is created | Session maker doesn't work | Call in FastAPI lifespan, Django `AppConfig.ready()`, etc. |
| Skipping `configure_logging` entirely | No console handlers, namespace defaults to `"app"` | Always call it first |
| Using `__name__` as logger name when module path doesn't start with namespace | Logger gets console only | Use `get_logger("myapp.modulename")` explicitly |
| Calling `log_to_db(...)` without `await` | Coroutine is created but never executed | Use `await log_to_db(...)` or just use `logger.error(...)` which handles async internally |

### Do / Don't Examples

**Namespace mismatch:**

```python
# WRONG -- namespace is "myapp" but logger name starts with "api"
configure_logging(namespace="myapp")
logger = get_logger("api.routes")  # console only, no DB/Discord

# RIGHT
configure_logging(namespace="myapp")
logger = get_logger("myapp.routes")  # DB + Discord + console
```

**Forgetting `await` on async helpers:**

```python
# WRONG -- coroutine is created but never runs
log_to_db(level="ERROR", message="broke", logger_name="myapp")

# RIGHT -- option A: await the coroutine
await log_to_db(level="ERROR", message="broke", logger_name="myapp")

# RIGHT -- option B: use the standard logger (no await needed)
logger = get_logger("myapp")
logger.error("broke")
```

**Wrong init order:**

```python
# WRONG -- DB logging set up before engine exists
configure_logging(namespace="myapp")
setup_db_logging(session_maker=session_maker, log_model=Log, namespace="myapp")
engine = create_async_engine(...)  # too late
session_maker = async_sessionmaker(engine)

# RIGHT -- engine first, then logging
engine = create_async_engine(...)
session_maker = async_sessionmaker(engine, expire_on_commit=False)
configure_logging(namespace="myapp")
setup_db_logging(session_maker=session_maker, log_model=Log, namespace="myapp")
```

## Testing Conventions

- Call `reset_db_handler()` (from `hibiki_logger.logger`) between tests to clear the global DB handler singleton.
- Use `monkeypatch.setenv` for environment variables and `importlib.reload(config_module)` to pick up changes.
- Mock `aiohttp.ClientSession` for Discord tests to avoid real HTTP calls.
- Tests use `pytest` with `asyncio_mode = "strict"`. All async tests **must** use `@pytest.mark.asyncio`.

**Dev dependencies:** `pytest>=7.0`, `pytest-asyncio>=0.21`, `black>=23.0`, `flake8>=6.0`

### Handler isolation fixture

```python
from hibiki_logger.logger import reset_db_handler

@pytest.fixture(autouse=True)
def clean_handler():
    reset_db_handler()
    yield
    reset_db_handler()
```

### Async test example

```python
import pytest
from unittest.mock import AsyncMock, patch
from hibiki_logger.discord_service import send_discord_notification

@pytest.mark.asyncio
async def test_send_discord_returns_false_without_url():
    result = await send_discord_notification(message="test", webhook_url="")
    assert result is False

@pytest.mark.asyncio
async def test_send_discord_calls_webhook():
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.post.return_value.__aenter__.return_value.status = 204

    with patch("aiohttp.ClientSession", return_value=mock_session):
        result = await send_discord_notification(
            message="hello", webhook_url="https://discord.com/api/webhooks/test"
        )
    assert result is True
```
