"""
Database models for logging package.

Copy these to your project's database models file or use as-is.
"""

from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.sql import func
import uuid

from .config import config as logging_config


def _get_table_name(table_name=None):
    return table_name or logging_config.LOG_TABLE_NAME


def create_log_model(Base, table_name=None):
    """
    Factory function to create Log model with your Base class.

    Args:
        Base: Your SQLAlchemy declarative base.
        table_name: Override table name (defaults to LOG_TABLE_NAME env var, then "log").

    Usage:
        from hibiki_logger.models import create_log_model

        Log = create_log_model(Base)
    """
    resolved_name = _get_table_name(table_name)

    class Log(Base):
        __tablename__ = resolved_name

        id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
        level = Column(String(20), nullable=False)
        message = Column(Text, nullable=False)
        logger_name = Column(String(255), nullable=False)
        user_id = Column(String(36), nullable=True)
        path = Column(String(255), nullable=True)
        method = Column(String(10), nullable=True)
        trace = Column(Text, nullable=True)
        created_at = Column(DateTime(timezone=True), server_default=func.now())

    return Log


def get_log_table_sql(table_name=None):
    """Return raw PostgreSQL DDL for the log table.

    Args:
        table_name: Override table name (defaults to LOG_TABLE_NAME env var, then "log").
    """
    name = _get_table_name(table_name)
    return f"""
CREATE TABLE {name} (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    level VARCHAR(20) NOT NULL,
    message TEXT NOT NULL,
    logger_name VARCHAR(255) NOT NULL,
    user_id VARCHAR(36),
    path VARCHAR(255),
    method VARCHAR(10),
    trace TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_{name}_level ON {name}(level);
CREATE INDEX idx_{name}_logger_name ON {name}(logger_name);
CREATE INDEX idx_{name}_created_at ON {name}(created_at);
"""


LOG_TABLE_SQL = get_log_table_sql()
