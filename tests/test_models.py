import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import declarative_base

from hibiki_logger.models import (
    create_log_model,
    get_log_table_sql,
    LOG_TABLE_SQL,
)


class TestCreateLogModel:
    def test_creates_model_with_default_table_name(self):
        Base = declarative_base()
        Log = create_log_model(Base)
        assert Log.__tablename__ == "log"

    def test_creates_model_with_custom_table_name(self):
        Base = declarative_base()
        Log = create_log_model(Base, table_name="app_log")
        assert Log.__tablename__ == "app_log"

    def test_model_has_expected_columns(self):
        Base = declarative_base()
        Log = create_log_model(Base)
        mapper = inspect(Log)
        column_names = {col.key for col in mapper.columns}
        expected = {"id", "level", "message", "logger_name", "user_id", "path", "method", "trace", "created_at"}
        assert expected == column_names

    def test_model_instantiation(self):
        Base = declarative_base()
        Log = create_log_model(Base)
        entry = Log(level="ERROR", message="test", logger_name="app.test")
        assert entry.level == "ERROR"
        assert entry.message == "test"
        assert entry.logger_name == "app.test"


class TestRawSQL:
    def test_log_table_sql_uses_default_name(self):
        assert "CREATE TABLE log" in LOG_TABLE_SQL

    def test_get_log_table_sql_with_custom_name(self):
        sql = get_log_table_sql("audit_log")
        assert "CREATE TABLE audit_log" in sql
        assert "idx_audit_log_level" in sql
        assert "idx_audit_log_logger_name" in sql
        assert "idx_audit_log_created_at" in sql
