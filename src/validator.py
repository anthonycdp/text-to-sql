"""SQL Validation module for syntax and safety checks."""

import re
import sqlparse
from sqlparse.sql import Statement
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ValidationLevel(Enum):
    """Severity level of validation issues."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationResult:
    """Result of SQL validation."""
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)
    parsed_sql: Optional[str] = None
    statement_type: Optional[str] = None

    def add_issue(self, level: ValidationLevel, message: str) -> None:
        """Add a validation issue."""
        if level == ValidationLevel.ERROR:
            self.errors.append(message)
            self.is_valid = False
        elif level == ValidationLevel.WARNING:
            self.warnings.append(message)
        else:
            self.info.append(message)


class SQLValidator:
    """Validates SQL queries for syntax correctness and safety."""

    # Allowed statement types for read-only mode
    SAFE_STATEMENTS = {"SELECT", "WITH", "EXPLAIN", "PRAGMA"}

    # Potentially dangerous keywords
    DANGEROUS_KEYWORDS = {
        "DROP", "DELETE", "TRUNCATE", "ALTER", "CREATE", "GRANT",
        "REVOKE", "EXEC", "EXECUTE", "XP_", "SP_", "SHUTDOWN",
        "BULK", "OPENROWSET", "OPENDATASOURCE"
    }

    # SQL injection patterns
    INJECTION_PATTERNS = [
        r";\s*(?:DROP|DELETE|TRUNCATE|ALTER|CREATE|INSERT|UPDATE)",  # Multiple statements
        r"--",  # SQL comments
        r"/\*",  # Block comments
        r"UNION\s+ALL\s+SELECT",  # Union injection
        r"UNION\s+SELECT",
        r"'\s*OR\s+'?\d*'?\s*=\s*'?\d*",  # OR 1=1 pattern
        r"'\s*OR\s+'[^']*'\s*=\s*'",  # OR string comparison
        r"1\s*=\s*1",  # Always true
        r"'\s*;\s*--",  # Quote-semicolon-comment
        r"xp_cmdshell",
        r"sp_executesql",
        r"INTO\s+OUTFILE",
        r"LOAD_FILE",
    ]

    def __init__(self, allow_destructive: bool = False):
        """Initialize validator.

        Args:
            allow_destructive: Whether to allow destructive queries
        """
        self.allow_destructive = allow_destructive

    def validate(self, sql: str) -> ValidationResult:
        """Validate a SQL query.

        Args:
            sql: The SQL query to validate

        Returns:
            ValidationResult with validity status and any issues
        """
        result = ValidationResult(is_valid=True)

        # Empty check
        if not sql or not sql.strip():
            result.add_issue(ValidationLevel.ERROR, "Empty SQL query")
            return result

        # Parse the SQL
        try:
            parsed = sqlparse.parse(sql)
            if not parsed:
                result.add_issue(ValidationLevel.ERROR, "Failed to parse SQL query")
                return result
        except Exception as e:
            result.add_issue(ValidationLevel.ERROR, f"SQL parsing error: {str(e)}")
            return result

        # Format and store parsed SQL
        result.parsed_sql = sqlparse.format(sql, reindent=True, keyword_case='upper')

        # Analyze each statement
        for stmt in parsed:
            self._analyze_statement(stmt, result)

        # Check for injection patterns
        self._check_injection_patterns(sql, result)

        # Check for dangerous keywords
        self._check_dangerous_keywords(sql, result)

        return result

    def _analyze_statement(self, statement: Statement, result: ValidationResult) -> None:
        """Analyze a single SQL statement."""
        # Get the first meaningful token to determine statement type
        first_token = statement.token_first(skip_ws=True, skip_cm=True)

        if first_token is None:
            result.add_issue(ValidationLevel.ERROR, "Empty statement")
            return

        token_value = first_token.value.upper()
        result.statement_type = token_value

        # Check if statement type is allowed
        if not self.allow_destructive:
            if token_value not in self.SAFE_STATEMENTS:
                result.add_issue(
                    ValidationLevel.ERROR,
                    f"Statement type '{token_value}' is not allowed. Only read-only queries are permitted."
                )

        # Validate based on statement type
        if token_value == "SELECT":
            self._validate_select(statement, result)
        elif token_value == "WITH":
            self._validate_cte(statement, result)
        elif token_value == "INSERT":
            self._validate_insert(statement, result)
        elif token_value == "UPDATE":
            self._validate_update(statement, result)
        elif token_value == "DELETE":
            self._validate_delete(statement, result)

    def _validate_select(self, statement: Statement, result: ValidationResult) -> None:
        """Validate SELECT statement."""
        sql_upper = str(statement).upper()

        # Check for missing FROM clause (valid but unusual)
        if "FROM" not in sql_upper and not sql_upper.strip().startswith("SELECT 1"):
            result.add_issue(ValidationLevel.INFO, "SELECT without FROM clause")

        # Check for Cartesian products (cross joins without explicit CROSS JOIN)
        if sql_upper.count(",") > 0 and "JOIN" not in sql_upper:
            from_match = re.search(r"FROM\s+(\w+)", sql_upper)
            if from_match:
                tables_in_from = re.findall(r"FROM\s+[\w\s,]+", sql_upper)
                for tables in tables_in_from:
                    if "," in tables:
                        result.add_issue(
                            ValidationLevel.WARNING,
                            "Implicit cross join detected. Consider using explicit JOIN syntax."
                        )
                        break

    def _validate_cte(self, statement: Statement, result: ValidationResult) -> None:
        """Validate WITH (CTE) statement."""
        # CTEs are generally safe, but we should check the inner statements
        result.add_issue(ValidationLevel.INFO, "Common Table Expression (CTE) detected")

    def _validate_insert(self, statement: Statement, result: ValidationResult) -> None:
        """Validate INSERT statement."""
        if not self.allow_destructive:
            return  # Already flagged as error

        result.add_issue(ValidationLevel.WARNING, "INSERT statement will modify data")

    def _validate_update(self, statement: Statement, result: ValidationResult) -> None:
        """Validate UPDATE statement."""
        if not self.allow_destructive:
            return

        sql_upper = str(statement).upper()

        # Check for UPDATE without WHERE
        if "WHERE" not in sql_upper:
            result.add_issue(
                ValidationLevel.WARNING,
                "UPDATE without WHERE clause will affect all rows"
            )

    def _validate_delete(self, statement: Statement, result: ValidationResult) -> None:
        """Validate DELETE statement."""
        if not self.allow_destructive:
            return

        sql_upper = str(statement).upper()

        # Check for DELETE without WHERE
        if "WHERE" not in sql_upper:
            result.add_issue(
                ValidationLevel.WARNING,
                "DELETE without WHERE clause will remove all rows"
            )

    def _check_injection_patterns(self, sql: str, result: ValidationResult) -> None:
        """Check for SQL injection patterns."""
        sql_normalized = sql.upper()

        for pattern in self.INJECTION_PATTERNS:
            matches = re.finditer(pattern, sql_normalized, re.IGNORECASE)
            for match in matches:
                result.add_issue(
                    ValidationLevel.ERROR,
                    f"Potential SQL injection pattern detected: '{match.group()}'"
                )

    def _check_dangerous_keywords(self, sql: str, result: ValidationResult) -> None:
        """Check for dangerous SQL keywords."""
        sql_upper = sql.upper()

        # Split by whitespace and punctuation to get keywords
        keywords = set(re.findall(r'\b\w+\b', sql_upper))

        dangerous_found = keywords.intersection(self.DANGEROUS_KEYWORDS)

        for keyword in dangerous_found:
            if self.allow_destructive:
                result.add_issue(
                    ValidationLevel.WARNING,
                    f"Dangerous keyword detected: '{keyword}'"
                )
            else:
                result.add_issue(
                    ValidationLevel.ERROR,
                    f"Dangerous keyword '{keyword}' is not allowed"
                )

    def is_read_only(self, sql: str) -> bool:
        """Check if the query is read-only (SELECT only)."""
        result = self.validate(sql)
        return result.is_valid and result.statement_type in {"SELECT", "WITH"}

    def format_sql(self, sql: str) -> str:
        """Format SQL query for readability."""
        return sqlparse.format(sql, reindent=True, keyword_case='upper')
