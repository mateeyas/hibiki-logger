import os
import importlib
import pytest
from hibiki_logger.config import LoggingConfig, config
import hibiki_logger.config as config_module


@pytest.fixture(autouse=True)
def restore_config(monkeypatch):
    """Reset environment variables and reload config_module after each test."""
    yield
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("LOG_DB_MIN_LEVEL", raising=False)
    monkeypatch.delenv("LOG_CONSOLE_MIN_LEVEL", raising=False)
    monkeypatch.delenv("LOG_DISCORD_MIN_LEVEL", raising=False)
    monkeypatch.delenv("LOG_DISCORD_WEBHOOK_URL", raising=False)
    importlib.reload(config_module)


class TestLoggingConfigDefaults:
    def test_default_environment(self, monkeypatch):
        monkeypatch.delenv("ENV", raising=False)
        importlib.reload(config_module)
        assert config_module.config.ENVIRONMENT == "development"

    def test_custom_environment(self, monkeypatch):
        monkeypatch.setenv("ENV", "production")
        importlib.reload(config_module)
        assert config_module.config.ENVIRONMENT == "production"

    def test_default_db_min_level(self, monkeypatch):
        monkeypatch.delenv("LOG_DB_MIN_LEVEL", raising=False)
        importlib.reload(config_module)
        assert config_module.config.LOG_DB_MIN_LEVEL == "WARNING"

    def test_custom_db_min_level(self, monkeypatch):
        monkeypatch.setenv("LOG_DB_MIN_LEVEL", "DEBUG")
        importlib.reload(config_module)
        assert config_module.config.LOG_DB_MIN_LEVEL == "DEBUG"

    def test_default_discord_min_level(self, monkeypatch):
        monkeypatch.delenv("LOG_DISCORD_MIN_LEVEL", raising=False)
        importlib.reload(config_module)
        assert config_module.config.LOG_DISCORD_MIN_LEVEL == "ERROR"

    def test_custom_discord_min_level(self, monkeypatch):
        monkeypatch.setenv("LOG_DISCORD_MIN_LEVEL", "WARNING")
        importlib.reload(config_module)
        assert config_module.config.LOG_DISCORD_MIN_LEVEL == "WARNING"

    def test_default_console_min_level(self, monkeypatch):
        monkeypatch.delenv("LOG_CONSOLE_MIN_LEVEL", raising=False)
        importlib.reload(config_module)
        assert config_module.config.LOG_CONSOLE_MIN_LEVEL == "INFO"

    def test_custom_console_min_level(self, monkeypatch):
        monkeypatch.setenv("LOG_CONSOLE_MIN_LEVEL", "WARNING")
        importlib.reload(config_module)
        assert config_module.config.LOG_CONSOLE_MIN_LEVEL == "WARNING"

    def test_discord_webhook_url_none_by_default(self, monkeypatch):
        monkeypatch.delenv("LOG_DISCORD_WEBHOOK_URL", raising=False)
        importlib.reload(config_module)
        assert config_module.config.LOG_DISCORD_WEBHOOK_URL is None

    def test_discord_webhook_url_when_set(self, monkeypatch):
        monkeypatch.setenv("LOG_DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/test")
        importlib.reload(config_module)
        assert config_module.config.LOG_DISCORD_WEBHOOK_URL == "https://discord.com/api/webhooks/test"


class TestLoggingConfigFromDict:
    def test_from_dict_sets_attributes(self):
        LoggingConfig.from_dict({
            "LOG_DB_MIN_LEVEL": "DEBUG",
            "LOG_DISCORD_MIN_LEVEL": "WARNING",
        })
        assert LoggingConfig.LOG_DB_MIN_LEVEL == "DEBUG"
        assert LoggingConfig.LOG_DISCORD_MIN_LEVEL == "WARNING"
        LoggingConfig.LOG_DB_MIN_LEVEL = "WARNING"
        LoggingConfig.LOG_DISCORD_MIN_LEVEL = "ERROR"

    def test_from_dict_ignores_unknown_keys(self):
        LoggingConfig.from_dict({"UNKNOWN_KEY": "value"})
