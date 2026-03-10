import logging
import pytest

from hibiki_logger.logger import (
    configure_logging,
    setup_db_logging,
    get_logger,
    add_context_to_logger,
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
        try:
            monkeypatch.setenv("ENV", "production")
            configure_logging(namespace="app")
            assert len(root.handlers) > 0
        finally:
            root.handlers = original_handlers
            monkeypatch.setenv("ENV", "development")
            configure_logging(namespace="app")

    def test_discord_webhook_url_from_env(self, monkeypatch):
        monkeypatch.setattr(logger_module, "logging_config", type("C", (), {"LOG_DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/env"})())
        configure_logging(namespace="app")
        assert logger_module._discord_webhook_url == "https://discord.com/api/webhooks/env"

    def test_discord_webhook_url_none_when_env_unset(self, monkeypatch):
        monkeypatch.setattr(logger_module, "logging_config", type("C", (), {"LOG_DISCORD_WEBHOOK_URL": None})())
        configure_logging(namespace="app")
        assert logger_module._discord_webhook_url is None


class TestGetLogger:
    def test_returns_logger(self):
        configure_logging(namespace="testapp")
        lgr = get_logger("testapp.module")
        assert isinstance(lgr, logging.Logger)
        assert lgr.name == "testapp.module"

    def test_namespace_logger_gets_db_handler(self):
        configure_logging(namespace="testns")
        reset_db_handler()
        lgr = get_logger("testns.sub")
        has_db = any(isinstance(h, AsyncDBHandler) for h in lgr.handlers)
        assert has_db

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
