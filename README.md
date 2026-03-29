# Hibiki Logger

Production logging with console, database, and Discord notification support.

[![GitHub](https://img.shields.io/github/stars/mateeyas/hibiki-logger?style=social)](https://github.com/mateeyas/hibiki-logger)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **AI coding assistant?** Provide [`LLMGUIDE.md`](LLMGUIDE.md) as context for a complete API reference.

## Features

- Console logging (human-readable or JSON)
- Database logging via SQLAlchemy (async, non-blocking)
- Discord webhook notifications for errors
- Request context support (`user_id`, `path`, `method`)
- Separate log level thresholds for console, DB, and Discord

## Installation

```bash
pip install hibiki-logger
```

## Quick start

### Console only

```python
from hibiki_logger import configure_logging, get_logger

configure_logging(namespace="myapp")
logger = get_logger("myapp.service")
logger.info("Ready")
```

### Add Discord notifications

Set the `LOG_DISCORD_WEBHOOK_URL` environment variable — no code changes needed.

### Add database logging

Uses SQLAlchemy. Call `setup_db_logging()` after your DB is ready, passing your existing `session_maker` and a log model created with `create_log_model`:

```python
from hibiki_logger import setup_db_logging
from hibiki_logger.models import create_log_model

Log = create_log_model(Base)
setup_db_logging(session_maker=session_maker, log_model=Log, namespace="myapp")
```

The `log` table must exist before logging starts. The expected schema:

| Column        | Type                       | Nullable |
| ------------- | -------------------------- | -------- |
| `id`          | `VARCHAR(36)` primary key  | no       |
| `level`       | `VARCHAR(20)`              | no       |
| `message`     | `TEXT`                     | no       |
| `logger_name` | `VARCHAR(255)`             | no       |
| `user_id`     | `VARCHAR(36)`              | yes      |
| `path`        | `VARCHAR(255)`             | yes      |
| `method`      | `VARCHAR(10)`              | yes      |
| `trace`       | `TEXT`                     | yes      |
| `created_at`  | `TIMESTAMP WITH TIME ZONE` | yes      |

If you use Alembic or another migration tool, generate a migration after calling `create_log_model(Base)`. Otherwise, create it directly:

```python
async with engine.begin() as conn:
    await conn.run_sync(Base.metadata.create_all)
```

Not using SQLAlchemy? Use the raw DDL from `from hibiki_logger.models import LOG_TABLE_SQL`.

## Configuration

| Variable                  | Default       | Description                                                      |
| ------------------------- | ------------- | ---------------------------------------------------------------- |
| `LOG_DISCORD_WEBHOOK_URL` | _(none)_      | Discord webhook URL                                              |
| `LOG_DISCORD_USERNAME`    | _(none)_      | Display name for Discord webhook messages                        |
| `LOG_DB_TABLE_NAME`       | `log`         | Database table name for log entries (also reads `LOG_TABLE_NAME`) |
| `LOG_CONSOLE_FORMAT`      | `text`        | Console output format (`text` or `json`)                         |
| `LOG_CONSOLE_MIN_LEVEL`   | `INFO`        | Minimum level for console output                                 |
| `LOG_DB_MIN_LEVEL`        | `WARNING`     | Minimum level saved to DB                                        |
| `LOG_DISCORD_MIN_LEVEL`   | `ERROR`       | Minimum level sent to Discord                                    |

> **Tip:** Use `LOG_CONSOLE_FORMAT=json` in production for structured logging compatible with log aggregators.

### Namespace

Only loggers whose names start with the namespace receive DB and Discord handlers:

```python
get_logger("myapp.api")     # DB + Discord handlers
get_logger("other.module")  # console only
```

Use `extra_loggers` to include third-party loggers:

```python
configure_logging(namespace="myapp", extra_loggers=["uvicorn", "fastapi"])
```

### Request context

```python
from hibiki_logger import add_context_to_logger

logger = add_context_to_logger(get_logger("myapp.users"), user_id="123", path="/api/users", method="POST")
logger.error("User creation failed")
```

## API reference

| Function                                                 | Description                                                                |
| -------------------------------------------------------- | -------------------------------------------------------------------------- |
| `configure_logging(namespace, extra_loggers=None)`       | Configure console + Discord. Call once at startup.                         |
| `setup_db_logging(session_maker, log_model, namespace)`  | Enable DB logging. Call after DB is ready.                                 |
| `get_logger(name)`                                       | Get a logger; DB/Discord handlers auto-attached if name matches namespace. |
| `add_context_to_logger(logger, user_id, path, method)`   | Wrap a logger with request context.                                        |
| `async log_to_db(level, message, logger_name, ...)`      | Manually log to DB.                                                        |
| `async log_to_discord(level, message, logger_name, ...)` | Manually send to Discord.                                                  |
| `async log_error(error, logger_name, ...)`               | Log an exception with traceback to DB.                                     |

### Manual Discord notifications

Standard logging calls (`logger.error(...)`) send Discord notifications in the background automatically. Your code is never blocked. If you need to send a Discord message explicitly and confirm it was delivered, await `log_to_discord()` directly:

```python
from hibiki_logger import log_to_discord

await log_to_discord(
    level="ERROR",
    message="Payment processing failed",
    logger_name="myapp.billing",
    user_id="123",
)
```

## Framework integration

**FastAPI** — call both functions inside your lifespan handler:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(namespace="app", extra_loggers=["uvicorn", "fastapi"])
    setup_db_logging(session_maker=async_session_maker, log_model=Log, namespace="app")
    yield
```

**Django** — call `configure_logging()` in `settings.py`.

**Flask** — call `configure_logging()` at app initialization.

## Troubleshooting

**Logs not appearing in database** — verify `setup_db_logging()` was called, the logger name matches the namespace, and `LOG_DB_MIN_LEVEL` allows the level.

**Discord notifications not sending** — verify `LOG_DISCORD_WEBHOOK_URL` is set and `LOG_DISCORD_MIN_LEVEL` allows the level.

## License

MIT
