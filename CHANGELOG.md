# Changelog

All notable changes to Hibiki Logger will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.4.1] - 2026-08-30

### Fixed

- An alert cancelled mid-send — by a `wait_for` timeout, or at shutdown while a
  retry was backing off — left its deduplication window open, silently
  collapsing every later occurrence of that fault into an alert nobody
  received. `CancelledError` is a `BaseException`, so it passed over the
  rollback that a failed send triggers. This is the failure deduplication is
  meant to prevent, so cancellation now rolls the window back like any other
  undelivered send.
- Occurrences arriving while a send was in flight were discarded if that send
  then failed. They landed on the window the send had opened, and the rollback
  replaced that window wholesale, so the repeats were neither delivered nor
  counted in the next alert. They are now carried forward and reported.

## [1.4.0] - 2026-08-30

### Added

- Discord alerts are deduplicated by fault signature. Alerts sharing a signature within `LOG_DISCORD_DEDUP_WINDOW` (default 300 seconds) collapse into a single send, and the number collapsed is reported in the next alert for that signature. The signature is the exception type plus innermost frame when a traceback is present, falling back to logger name plus message. Keying on the traceback rather than the message matters in practice: messages routinely embed request and user ids, so a single repeating fault would otherwise produce an unbounded number of distinct alerts.
- Webhook send budget via `LOG_DISCORD_MAX_PER_MINUTE` (default 30), capping how many alerts may be sent in any 60 second window. Alerts beyond the budget are dropped and counted, and the count is reported on the next successful send. They are dropped rather than queued because every record is still written to the database by the DB handler; this keeps the package free of a background worker and its lifecycle.
- Discord errors are sent as embeds, coloured by level (WARNING amber, ERROR red, CRITICAL dark red), with `logger_name`, `user_id`, `path`, and `method` as fields where set, and suppression counts in the footer. Tracebacks go in the description and are truncated from the middle so the exception line and innermost frames survive. Payloads are truncated against Discord's 4096 / 1024 / 6000 character limits. If embed construction fails the alert still goes out as plain text.
- `LOG_DISCORD_EMBED` (default `true`) to control embed rendering, and `reset_discord_throttle()` to discard deduplication and rate-limit state.

### Changed

- **Discord alerts now render as embeds by default.** This is not a breaking API change — existing callers work unchanged — but it does change how alerts look in your channel. Set `LOG_DISCORD_EMBED=false` to restore the previous plain-text rendering.
- Failed Discord sends are retried. 429 responses honour Discord's `Retry-After` exactly and 5xx responses back off exponentially, up to 4 attempts. Where `Retry-After` exceeds 30 seconds the alert is dropped rather than retried early, since retrying before the limit clears only extends it. Previously a rate-limited send was logged and discarded, which meant alerts were lost precisely during the error bursts that triggered the rate limiting.
- A Discord send that fails does not open a deduplication window, so a webhook outage cannot silence a fault for the length of the window. The budget slot is still consumed, which bounds retry attempts for an undeliverable fault to `LOG_DISCORD_MAX_PER_MINUTE`.
- `LOG_DISCORD_DEDUP_WINDOW=0` disables deduplication rather than falling back to the default, so the stage can be switched off when diagnosing missing alerts.
- `send_discord_notification` accepts an optional `embed` argument and truncates `content` to Discord's 2000 character limit. `message` is now optional when an embed is supplied.
- Awaiting `log_to_discord()` no longer implies the alert reached Discord; it returns without sending when the alert is collapsed or shed. Documented in the README.

## [1.3.1] - 2026-05-07

### Fixed

- `AsyncDBHandler` no longer writes each namespace log record to the database twice. The handler is now attached to the namespace logger only; child loggers reach it via standard log-record propagation, so every record produces exactly one DB insert. Previously both `setup_db_logging` and `get_logger` could attach the same handler to the namespace logger and to each child, causing duplicate writes when a child logger emitted a record.

## [1.3.0] - 2026-05-03

### Changed

- Removed `asyncpg` from runtime dependencies. The library is engine-agnostic and only requires SQLAlchemy; users install whichever async driver matches their database (e.g. `asyncpg`/`psycopg`, `aiosqlite`, `aiomysql`/`asyncmy`).

### Removed

- `LoggingConfig.ENVIRONMENT` and the `ENV` environment variable. The attribute was no longer read by the library after 1.2.0 introduced `LOG_CONSOLE_FORMAT` and `LOG_CONSOLE_MIN_LEVEL`. Use those variables to control console output instead.

### Fixed

- `LLMGUIDE.md`: removed stale `ENV` env-var entry that described behavior superseded in 1.2.0, added the missing `LOG_CONSOLE_FORMAT` and `LOG_CONSOLE_MIN_LEVEL` rows, and clarified that env vars are only read once at config-module import.

## [1.2.0] - 2026-03-29

### Added

- `LOG_CONSOLE_MIN_LEVEL` env var to configure the minimum log level for console output
- `LOG_CONSOLE_FORMAT` env var to configure the console output format

### Fixed

- Root logger no longer overridden by `configure_logging()`, preventing interference with other loggers

## [1.0.1] - 2026-03-11

### Fixed

- Standardized README headings to sentence case

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

[1.4.0]: https://github.com/mateeyas/hibiki-logger/releases/tag/v1.4.0
[1.3.1]: https://github.com/mateeyas/hibiki-logger/releases/tag/v1.3.1
[1.3.0]: https://github.com/mateeyas/hibiki-logger/releases/tag/v1.3.0
[1.2.0]: https://github.com/mateeyas/hibiki-logger/releases/tag/v1.2.0
[1.0.1]: https://github.com/mateeyas/hibiki-logger/releases/tag/v1.0.1
[1.0.0]: https://github.com/mateeyas/hibiki-logger/releases/tag/v1.0.0
