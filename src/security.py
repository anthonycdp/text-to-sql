"""Security layer for SQL query execution."""

import re
import time
from dataclasses import dataclass, field
from typing import Optional, Callable, Any
import threading

from src.config import settings
from src.validator import SQLValidator, ValidationResult, ValidationLevel


# Default configuration values
DEFAULT_MAX_ROWS = 1000
DEFAULT_QUERY_TIMEOUT = 30
DEFAULT_MAX_QUERY_LENGTH = 10000


@dataclass
class SecurityConfig:
    """Configuration for security layer."""
    max_rows: int = DEFAULT_MAX_ROWS
    query_timeout: int = DEFAULT_QUERY_TIMEOUT
    allow_destructive: bool = False
    max_query_length: int = DEFAULT_MAX_QUERY_LENGTH
    allowed_tables: Optional[list[str]] = None
    blocked_tables: Optional[list[str]] = None


@dataclass
class QueryExecutionResult:
    """Result of a secured query execution."""
    success: bool
    data: list[dict] = field(default_factory=list)
    row_count: int = 0
    execution_time: float = 0.0
    truncated: bool = False
    error_message: Optional[str] = None
    validation: Optional[ValidationResult] = None
    security_warnings: list[str] = field(default_factory=list)


class SecurityLayer:
    """Security layer for SQL query execution with validation and limits."""

    def __init__(
        self,
        validator: Optional[SQLValidator] = None,
        config: Optional[SecurityConfig] = None
    ):
        self.validator = validator or SQLValidator(
            allow_destructive=config.allow_destructive if config else False
        )
        self.config = config or SecurityConfig(
            max_rows=settings.max_rows_returned,
            query_timeout=settings.query_timeout_seconds,
            allow_destructive=settings.allow_destructive_queries
        )
        self._query_count = 0
        self._total_rows_returned = 0

    def validate_query(self, sql: str) -> ValidationResult:
        """Validate a SQL query before execution."""
        result = self.validator.validate(sql)
        self._check_query_length(sql, result)
        self._check_table_access(sql, result)
        self._check_row_limits(sql, result)
        return result

    def secure_execute(
        self,
        sql: str,
        executor: Callable[[str, Optional[dict]], tuple[list[dict], int]],
        params: Optional[dict] = None
    ) -> QueryExecutionResult:
        """Execute a SQL query with security measures."""
        start_time = time.time()
        result = QueryExecutionResult(success=False)

        validation = self.validate_query(sql)
        result.validation = validation

        if not validation.is_valid:
            result.error_message = self._format_errors(validation.errors)
            result.security_warnings = validation.warnings
            return result

        result.security_warnings = validation.warnings.copy()
        safe_sql = self._apply_row_limit(sql)

        execution_data = self._execute_with_timeout(executor, safe_sql, params)

        if execution_data.error:
            result.error_message = execution_data.error
            return result

        self._populate_result(result, execution_data, start_time)
        return result

    def get_statistics(self) -> dict:
        """Get security statistics."""
        return {
            "total_queries": self._query_count,
            "total_rows_returned": self._total_rows_returned,
            "average_rows_per_query": (
                self._total_rows_returned / self._query_count
                if self._query_count > 0 else 0
            ),
            "config": {
                "max_rows": self.config.max_rows,
                "query_timeout": self.config.query_timeout,
                "allow_destructive": self.config.allow_destructive,
            }
        }

    def reset_statistics(self) -> None:
        """Reset security statistics."""
        self._query_count = 0
        self._total_rows_returned = 0

    def _format_errors(self, errors: list[str]) -> str:
        """Format validation errors into a single message."""
        return "Query validation failed: " + "; ".join(errors)

    def _check_query_length(self, sql: str, result: ValidationResult) -> None:
        """Check if query exceeds maximum length."""
        if len(sql) > self.config.max_query_length:
            result.add_issue(
                ValidationLevel.ERROR,
                f"Query exceeds maximum length of {self.config.max_query_length} characters"
            )

    def _check_table_access(self, sql: str, result: ValidationResult) -> None:
        """Check if query accesses allowed tables only."""
        table_pattern = r'(?:FROM|JOIN|INTO|UPDATE)\s+([a-zA-Z_][a-zA-Z0-9_]*)'
        tables = re.findall(table_pattern, sql, re.IGNORECASE)

        for table in tables:
            table_lower = table.lower()

            if self.config.blocked_tables and table_lower in [t.lower() for t in self.config.blocked_tables]:
                result.add_issue(ValidationLevel.ERROR, f"Access to table '{table}' is blocked")

            if self.config.allowed_tables and table_lower not in [t.lower() for t in self.config.allowed_tables]:
                result.add_issue(ValidationLevel.ERROR, f"Access to table '{table}' is not allowed")

    def _check_row_limits(self, sql: str, result: ValidationResult) -> None:
        """Check if query has appropriate LIMIT clause."""
        sql_upper = sql.upper()
        has_limit = bool(re.search(r'\bLIMIT\s+\d+', sql_upper))

        if not has_limit and 'SELECT' in sql_upper:
            result.add_issue(
                ValidationLevel.WARNING,
                f"No LIMIT clause. Results will be capped at {self.config.max_rows} rows."
            )

    def _apply_row_limit(self, sql: str) -> str:
        """Apply row limit to SELECT queries if not present."""
        sql_upper = sql.upper()

        if not sql_upper.strip().startswith('SELECT'):
            return sql

        if re.search(r'\bLIMIT\s+\d+', sql_upper):
            return sql

        sql = sql.rstrip()
        if sql.endswith(';'):
            sql = sql[:-1]

        return f"{sql} LIMIT {self.config.max_rows}"

    def _execute_with_timeout(
        self,
        executor: Callable,
        sql: str,
        params: Optional[dict]
    ) -> "_ExecutionData":
        """Execute query with timeout protection."""
        execution_data = _ExecutionData()

        def run_query():
            try:
                execution_data.result = executor(sql, params)
            except Exception as e:
                execution_data.error = str(e)

        thread = threading.Thread(target=run_query)
        thread.start()
        thread.join(timeout=self.config.query_timeout)

        if thread.is_alive():
            execution_data.error = f"Query exceeded timeout of {self.config.query_timeout} seconds"

        return execution_data

    def _populate_result(
        self,
        result: QueryExecutionResult,
        execution_data: "_ExecutionData",
        start_time: float
    ) -> None:
        """Populate result with successful execution data."""
        rows, count = execution_data.result

        result.execution_time = time.time() - start_time
        result.row_count = len(rows)

        if len(rows) > self.config.max_rows:
            rows = rows[:self.config.max_rows]
            result.truncated = True
            result.security_warnings.append(
                f"Results truncated to {self.config.max_rows} rows (actual: {count})"
            )

        result.data = rows
        result.success = True

        self._query_count += 1
        self._total_rows_returned += len(rows)


class _ExecutionData:
    """Internal class to hold thread execution results."""
    __slots__ = ('result', 'error')

    def __init__(self):
        self.result = None
        self.error = None


def sanitize_identifier(identifier: str) -> str:
    """Sanitize a SQL identifier (table/column name).

    Args:
        identifier: The identifier to sanitize

    Returns:
        Sanitized identifier safe for use in SQL
    """
    sanitized = re.sub(r'[^a-zA-Z0-9_]', '', identifier)

    if sanitized and sanitized[0].isdigit():
        sanitized = '_' + sanitized

    return sanitized


def escape_value(value: Any) -> str:
    """Escape a value for safe use in SQL.

    Args:
        value: The value to escape

    Returns:
        Escaped value string
    """
    if value is None:
        return "NULL"

    if isinstance(value, bool):
        return "1" if value else "0"

    if isinstance(value, (int, float)):
        return str(value)

    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"
