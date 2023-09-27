"""Database management for Text-to-SQL Interface."""

import sqlite3
from pathlib import Path
from typing import Any, Optional
from contextlib import contextmanager

from sqlalchemy import create_engine, text, MetaData, Table, inspect
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.engine import Engine

from src.config import settings


class DatabaseManager:
    """Manages database connections and operations."""

    def __init__(self, database_url: Optional[str] = None):
        self.database_url = database_url or settings.database_url
        self.engine: Optional[Engine] = None
        self.SessionLocal: Optional[sessionmaker] = None
        self.metadata = MetaData()
        self._connect()

    def _connect(self) -> None:
        """Initialize database connection."""
        # Ensure data directory exists for SQLite
        if self.database_url.startswith("sqlite"):
            db_path = self.database_url.replace("sqlite:///", "")
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self.engine = create_engine(
            self.database_url,
            echo=settings.debug,
            pool_pre_ping=True,
        )
        self.SessionLocal = sessionmaker(bind=self.engine)

    @contextmanager
    def get_session(self):
        """Get a database session context manager."""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def execute_query(self, sql: str, params: Optional[dict] = None) -> tuple[list[dict], int]:
        """
        Execute a SQL query safely.

        Returns:
            Tuple of (results as list of dicts, row count)
        """
        with self.engine.connect() as conn:
            result = conn.execute(text(sql), params or {})
            columns = result.keys() if result.returns_rows else []
            rows = [dict(zip(columns, row)) for row in result.fetchall()] if result.returns_rows else []
            return rows, len(rows)

    def get_schema_info(self) -> dict[str, dict]:
        """Get comprehensive schema information for all tables."""
        inspector = inspect(self.engine)
        schema = {}

        for table_name in inspector.get_table_names():
            columns = inspector.get_columns(table_name)
            foreign_keys = inspector.get_foreign_keys(table_name)
            indexes = inspector.get_indexes(table_name)

            schema[table_name] = {
                "columns": [
                    {
                        "name": col["name"],
                        "type": str(col["type"]),
                        "nullable": col.get("nullable", True),
                        "primary_key": col.get("primary_key", False),
                        "default": col.get("default"),
                    }
                    for col in columns
                ],
                "foreign_keys": [
                    {
                        "constrained_columns": fk["constrained_columns"],
                        "referred_table": fk["referred_table"],
                        "referred_columns": fk["referred_columns"],
                    }
                    for fk in foreign_keys
                ],
                "indexes": indexes,
                "sample_rows": self._get_sample_rows(table_name, 3),
            }

        return schema

    def _get_sample_rows(self, table_name: str, limit: int = 3) -> list[dict]:
        """Get sample rows from a table."""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(f"SELECT * FROM {table_name} LIMIT {limit}"))
                columns = result.keys()
                return [dict(zip(columns, row)) for row in result.fetchall()]
        except Exception:
            return []

    def get_table_names(self) -> list[str]:
        """Get list of all table names."""
        inspector = inspect(self.engine)
        return inspector.get_table_names()

    def get_column_names(self, table_name: str) -> list[str]:
        """Get column names for a specific table."""
        inspector = inspect(self.engine)
        columns = inspector.get_columns(table_name)
        return [col["name"] for col in columns]

    def test_connection(self) -> bool:
        """Test database connection."""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def close(self) -> None:
        """Close database connection."""
        if self.engine:
            self.engine.dispose()
