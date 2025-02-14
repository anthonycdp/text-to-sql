"""Tests for Security Layer."""

import pytest
from src.security import SecurityLayer, SecurityConfig, sanitize_identifier, escape_value


class TestSecurityLayer:
    """Test cases for the security layer."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = SecurityConfig(
            max_rows=100,
            query_timeout=5,
            allow_destructive=False
        )
        self.security = SecurityLayer(config=self.config)

    def test_validate_query_length(self):
        """Test query length validation."""
        long_query = "SELECT * FROM employees WHERE " + " AND ".join([f"col{i} = {i}" for i in range(1000)])
        result = self.security.validate_query(long_query)
        # Should still be valid but might have warnings

    def test_add_limit_clause(self):
        """Test automatic LIMIT clause addition."""
        sql = "SELECT * FROM employees"
        safe_sql = self.security._apply_row_limit(sql)
        assert "LIMIT" in safe_sql
        assert str(self.config.max_rows) in safe_sql

    def test_preserve_existing_limit(self):
        """Test that existing LIMIT is preserved."""
        sql = "SELECT * FROM employees LIMIT 10"
        safe_sql = self.security._apply_row_limit(sql)
        assert "LIMIT 10" in safe_sql
        assert safe_sql.count("LIMIT") == 1

    def test_statistics_tracking(self):
        """Test statistics tracking."""
        stats = self.security.get_statistics()
        assert stats["total_queries"] == 0
        assert stats["config"]["max_rows"] == 100

    def test_reset_statistics(self):
        """Test resetting statistics."""
        self.security._query_count = 10
        self.security._total_rows_returned = 500

        self.security.reset_statistics()
        stats = self.security.get_statistics()
        assert stats["total_queries"] == 0


class TestSanitizeIdentifier:
    """Test cases for identifier sanitization."""

    def test_valid_identifier(self):
        """Test valid identifier passes through."""
        assert sanitize_identifier("employees") == "employees"
        assert sanitize_identifier("employee_table") == "employee_table"
        assert sanitize_identifier("table123") == "table123"

    def test_remove_special_chars(self):
        """Test removal of special characters."""
        assert sanitize_identifier("table;name") == "tablename"
        assert sanitize_identifier("table-name") == "tablename"
        assert sanitize_identifier("table'name") == "tablename"

    def test_number_prefix(self):
        """Test handling of identifiers starting with numbers."""
        assert sanitize_identifier("123table") == "_123table"


class TestEscapeValue:
    """Test cases for value escaping."""

    def test_null(self):
        """Test NULL value escaping."""
        assert escape_value(None) == "NULL"

    def test_boolean(self):
        """Test boolean value escaping."""
        assert escape_value(True) == "1"
        assert escape_value(False) == "0"

    def test_numbers(self):
        """Test numeric value escaping."""
        assert escape_value(42) == "42"
        assert escape_value(3.14) == "3.14"

    def test_string(self):
        """Test string value escaping."""
        assert escape_value("hello") == "'hello'"
        assert escape_value("it's") == "'it''s'"

    def test_sql_injection_attempt(self):
        """Test escaping potential SQL injection."""
        dangerous = "'; DROP TABLE users; --"
        escaped = escape_value(dangerous)
        assert "''" in escaped  # Single quotes doubled
        assert escaped.startswith("'")
        assert escaped.endswith("'")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
