import asyncio
import logging
import pytest
from unittest.mock import AsyncMock, patch

from hibiki_logger.logger import (
    configure_logging,
    setup_db_logging,
    get_logger,
    add_context_to_logger,
    log_to_discord,
    AsyncDBHandler,
    reset_db_handler,
    _logger_namespace,
)
import hibiki_logger.logger as logger_module


class TestConfigureLogging:
    def test_default_namespace(self):
        configure_logging()
        assert logger_module._logger_namespace == "app"

    def test_custom_namespace(self):
        configure_logging(namespace="myproject")
        assert logger_module._logger_namespace == "myproject"
        configure_logging(namespace="app")

    def test_extra_loggers(self):
        configure_logging(namespace="app", extra_loggers=["uvicorn", "fastapi"])
        uvicorn_logger = logging.getLogger("uvicorn")
        assert uvicorn_logger.level == logging.INFO
        assert len(uvicorn_logger.handlers) > 0

    def test_production_mode_sets_json(self, monkeypatch):
        root = logging.getLogger()
        original_handlers = root.handlers[:]
        original_level = root.level
        try:
            monkeypatch.setattr(logger_module, "logging_config",
                type("C", (), {
                    "LOG_CONSOLE_MIN_LEVEL": "INFO",
                    "LOG_CONSOLE_FORMAT": "json",
                    "LOG_DISCORD_WEBHOOK_URL": None,
                    "LOG_DISCORD_USERNAME": None,
                })())
            configure_logging(namespace="app")
            assert len(root.handlers) > 0
            assert root.level == original_level
        finally:
            root.handlers = original_handlers
            configure_logging(namespace="app")

    def test_json_format_does_not_override_root_level(self, monkeypatch):
        root = logging.getLogger()
        original_handlers = root.handlers[:]
        try:
            monkeypatch.setattr(logger_module, "logging_config",
                type("C", (), {
                    "LOG_CONSOLE_MIN_LEVEL": "INFO",
                    "LOG_CONSOLE_FORMAT": "json",
                    "LOG_DISCORD_WEBHOOK_URL": None,
                    "LOG_DISCORD_USERNAME": None,
                })())
            configure_logging(namespace="app")
            assert root.level == logging.INFO
        finally:
            root.handlers = original_handlers
            configure_logging(namespace="app")

    def test_console_min_level_default(self):
        configure_logging(namespace="lvltest")
        lgr = logging.getLogger("lvltest")
        assert lgr.level == logging.INFO

    def test_console_min_level_env(self, monkeypatch):
        monkeypatch.setattr(logger_module, "logging_config",
            type("C", (), {
                "LOG_CONSOLE_MIN_LEVEL": "WARNING",
                "LOG_CONSOLE_FORMAT": "text",
                "LOG_DISCORD_WEBHOOK_URL": None,
                "LOG_DISCORD_USERNAME": None,
            })())
        configure_logging(namespace="lvltest2")
        lgr = logging.getLogger("lvltest2")
        assert lgr.level == logging.WARNING

    def test_discord_webhook_url_from_env(self, monkeypatch):
        monkeypatch.setattr(logger_module, "logging_config", type("C", (), {"LOG_DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/env", "LOG_DISCORD_USERNAME": None, "LOG_CONSOLE_MIN_LEVEL": "INFO", "LOG_CONSOLE_FORMAT": "text"})())
        configure_logging(namespace="app")
        assert logger_module._discord_webhook_url == "https://discord.com/api/webhooks/env"

    def test_discord_webhook_url_none_when_env_unset(self, monkeypatch):
        monkeypatch.setattr(logger_module, "logging_config", type("C", (), {"LOG_DISCORD_WEBHOOK_URL": None, "LOG_DISCORD_USERNAME": None, "LOG_CONSOLE_MIN_LEVEL": "INFO", "LOG_CONSOLE_FORMAT": "text"})())
        configure_logging(namespace="app")
        assert logger_module._discord_webhook_url is None

    def test_discord_username_from_config(self, monkeypatch):
        monkeypatch.setattr(logger_module, "logging_config", type("C", (), {"LOG_DISCORD_WEBHOOK_URL": None, "LOG_DISCORD_USERNAME": "My Bot", "LOG_CONSOLE_MIN_LEVEL": "INFO", "LOG_CONSOLE_FORMAT": "text"})())
        configure_logging(namespace="app")
        assert logger_module._discord_username == "My Bot"

    def test_discord_username_none_when_unset(self, monkeypatch):
        monkeypatch.setattr(logger_module, "logging_config", type("C", (), {"LOG_DISCORD_WEBHOOK_URL": None, "LOG_DISCORD_USERNAME": None, "LOG_CONSOLE_MIN_LEVEL": "INFO", "LOG_CONSOLE_FORMAT": "text"})())
        configure_logging(namespace="app")
        assert logger_module._discord_username is None


class TestGetLogger:
    def test_returns_logger(self):
        configure_logging(namespace="testapp")
        lgr = get_logger("testapp.module")
        assert isinstance(lgr, logging.Logger)
        assert lgr.name == "testapp.module"

    def test_namespace_logger_gets_db_handler(self):
        configure_logging(namespace="testns")
        reset_db_handler()
        get_logger("testns.sub")
        ns_logger = logging.getLogger("testns")
        has_db = any(isinstance(h, AsyncDBHandler) for h in ns_logger.handlers)
        assert has_db

    def test_child_logger_does_not_get_db_handler_directly(self):
        # The DB handler must live on the namespace logger only; children
        # reach it via propagation. Attaching it to a child too would
        # cause duplicate DB writes.
        configure_logging(namespace="testns_child")
        reset_db_handler()
        child = get_logger("testns_child.sub")
        has_db_on_child = any(isinstance(h, AsyncDBHandler) for h in child.handlers)
        assert not has_db_on_child

    def test_non_namespace_logger_no_db_handler(self):
        configure_logging(namespace="testns2")
        lgr = get_logger("other.module")
        has_db = any(isinstance(h, AsyncDBHandler) for h in lgr.handlers)
        assert not has_db

    def test_exact_namespace_match(self):
        configure_logging(namespace="exact")
        reset_db_handler()
        lgr = get_logger("exact")
        has_db = any(isinstance(h, AsyncDBHandler) for h in lgr.handlers)
        assert has_db


class TestAddContextToLogger:
    def test_returns_adapter(self):
        lgr = logging.getLogger("test.context")
        adapted = add_context_to_logger(lgr, user_id="u1", path="/test", method="GET")
        assert isinstance(adapted, logging.LoggerAdapter)

    def test_context_is_passed_through(self):
        lgr = logging.getLogger("test.context2")
        adapted = add_context_to_logger(lgr, user_id="u1", path="/api", method="POST")
        msg, kwargs = adapted.process("hello", {})
        assert kwargs["extra"]["user_id"] == "u1"
        assert kwargs["extra"]["path"] == "/api"
        assert kwargs["extra"]["method"] == "POST"

    def test_partial_context(self):
        lgr = logging.getLogger("test.context3")
        adapted = add_context_to_logger(lgr, user_id="u2")
        msg, kwargs = adapted.process("hello", {})
        assert kwargs["extra"]["user_id"] == "u2"
        assert "path" not in kwargs["extra"]
        assert "method" not in kwargs["extra"]


class TestLogToDiscord:
    @pytest.mark.asyncio
    async def test_passes_username_to_send_error_notification(self, monkeypatch):
        monkeypatch.setattr(logger_module, "_discord_webhook_url", "https://discord.com/api/webhooks/test")
        monkeypatch.setattr(logger_module, "DISCORD_LOG_MIN_LEVEL", logging.ERROR)

        with patch(
            "hibiki_logger.discord_service.send_error_notification",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_send:
            await log_to_discord(
                level="ERROR",
                message="something broke",
                logger_name="app.test",
                username="Custom Bot",
            )
            mock_send.assert_called_once()
            assert mock_send.call_args[1]["username"] == "Custom Bot"

    @pytest.mark.asyncio
    async def test_passes_none_username_when_not_set(self, monkeypatch):
        monkeypatch.setattr(logger_module, "_discord_webhook_url", "https://discord.com/api/webhooks/test")
        monkeypatch.setattr(logger_module, "DISCORD_LOG_MIN_LEVEL", logging.ERROR)

        with patch(
            "hibiki_logger.discord_service.send_error_notification",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_send:
            await log_to_discord(
                level="ERROR",
                message="something broke",
                logger_name="app.test",
            )
            mock_send.assert_called_once()
            assert mock_send.call_args[1]["username"] is None


class _FakeLog:
    """Minimal stand-in for the user's Log model. Records inserts."""

    instances: list = []

    def __init__(self, **fields):
        self.fields = fields
        _FakeLog.instances.append(self)


class _FakeSession:
    def __init__(self, store):
        self._store = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def add(self, entry):
        self._store.append(entry)

    async def commit(self):
        return None


def _make_session_maker(store):
    def _maker():
        return _FakeSession(store)

    return _maker


class TestNoDuplicateDBWrites:
    @pytest.mark.asyncio
    async def test_child_logger_emits_single_db_row(self, monkeypatch):
        """Regression: a record emitted from a child logger under the
        configured namespace must produce exactly one DB insert, not two.

        Before the fix, both the namespace logger and each child logger
        had their own AsyncDBHandler attached, so propagation produced
        duplicate writes.
        """
        monkeypatch.setattr(
            logger_module,
            "logging_config",
            type(
                "C",
                (),
                {
                    "LOG_CONSOLE_MIN_LEVEL": "INFO",
                    "LOG_CONSOLE_FORMAT": "text",
                    "LOG_DISCORD_WEBHOOK_URL": None,
                    "LOG_DISCORD_USERNAME": None,
                    "LOG_DB_MIN_LEVEL": "WARNING",
                    "LOG_DISCORD_MIN_LEVEL": "ERROR",
                },
            )(),
        )

        rows: list = []
        reset_db_handler()
        configure_logging(namespace="dupcheck")
        setup_db_logging(_make_session_maker(rows), _FakeLog, namespace="dupcheck")

        # Call get_logger AFTER setup_db_logging to exercise the path
        # that previously double-attached the handler.
        child = get_logger("dupcheck.sub")
        child.warning("hello from child")

        # Drain background tasks created by AsyncDBHandler.emit.
        pending = [
            t for t in asyncio.all_tasks() if t is not asyncio.current_task()
        ]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        assert len(rows) == 1, (
            f"expected exactly one DB row, got {len(rows)}: "
            f"{[r.fields for r in rows]}"
        )
        assert rows[0].fields["message"] == "hello from child"
        assert rows[0].fields["logger_name"] == "dupcheck.sub"
        assert rows[0].fields["level"] == "WARNING"

    @pytest.mark.asyncio
    async def test_single_db_row_when_get_logger_called_first(self, monkeypatch):
        """Regression: calling get_logger before setup_db_logging must
        also yield a single DB write per record.
        """
        monkeypatch.setattr(
            logger_module,
            "logging_config",
            type(
                "C",
                (),
                {
                    "LOG_CONSOLE_MIN_LEVEL": "INFO",
                    "LOG_CONSOLE_FORMAT": "text",
                    "LOG_DISCORD_WEBHOOK_URL": None,
                    "LOG_DISCORD_USERNAME": None,
                    "LOG_DB_MIN_LEVEL": "WARNING",
                    "LOG_DISCORD_MIN_LEVEL": "ERROR",
                },
            )(),
        )

        rows: list = []
        reset_db_handler()
        configure_logging(namespace="dupcheck2")

        child = get_logger("dupcheck2.sub")
        setup_db_logging(_make_session_maker(rows), _FakeLog, namespace="dupcheck2")

        child.error("boom")

        pending = [
            t for t in asyncio.all_tasks() if t is not asyncio.current_task()
        ]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        # Filter to only rows from this test (other tests may share state).
        my_rows = [r for r in rows if r.fields["logger_name"] == "dupcheck2.sub"]
        assert len(my_rows) == 1, (
            f"expected exactly one DB row, got {len(my_rows)}: "
            f"{[r.fields for r in my_rows]}"
        )
