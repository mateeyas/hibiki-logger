# Changelog

All notable changes to Hibiki Logger will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-03-10

### Added

- Console logging with human-readable and JSON formats
- Database logging with configurable minimum level (via SQLAlchemy + asyncpg)
- Discord webhook notifications for errors (via `LOG_DISCORD_WEBHOOK_URL` env var)
- `configure_logging()` for console setup
- `setup_db_logging()` for database logging initialization
- `get_logger()` with namespace-based handler attachment
- `add_context_to_logger()` for attaching user_id, path, method to log entries
- `log_to_db()`, `log_to_discord()`, `log_error()` for manual async logging
- `create_log_model()` factory and `LOG_TABLE_SQL` for database schema
- Non-blocking async operations for DB and Discord
- Configurable log levels per destination (`LOG_DB_MIN_LEVEL`, `LOG_DISCORD_MIN_LEVEL`)
- Framework integration support for FastAPI, Django, and Flask
- `LLMGUIDE.md` for AI coding assistant context

[1.0.0]: https://github.com/mateeyas/hibiki-logger/releases/tag/v1.0.0
