"""Tests for SQL Validator."""

import pytest
from src.validator import SQLValidator, ValidationLevel, ValidationResult


class TestSQLValidator:
    """Test cases for SQL validation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.validator = SQLValidator(allow_destructive=False)
        self.destructive_validator = SQLValidator(allow_destructive=True)

    def test_valid_select_query(self):
        """Test validation of a valid SELECT query."""
        result = self.validator.validate("SELECT * FROM employees WHERE salary > 50000")
        assert result.is_valid
        assert result.statement_type == "SELECT"

    def test_valid_select_with_join(self):
        """Test validation of SELECT with JOIN."""
        sql = """
        SELECT e.name, d.name as department
        FROM employees e
        JOIN departments d ON e.department_id = d.id
        """
        result = self.validator.validate(sql)
        assert result.is_valid

    def test_empty_query(self):
        """Test validation of empty query."""
        result = self.validator.validate("")
        assert not result.is_valid
        assert "Empty" in result.errors[0]

    def test_destructive_query_blocked(self):
        """Test that destructive queries are blocked by default."""
        result = self.validator.validate("DROP TABLE employees")
        assert not result.is_valid
        assert any("DROP" in e for e in result.errors)

    def test_delete_blocked_without_where(self):
        """Test DELETE without WHERE clause."""
        result = self.destructive_validator.validate("DELETE FROM employees")
        assert result.is_valid  # Valid syntax but has warning
        assert any("WHERE" in w for w in result.warnings)

    def test_update_without_where_warning(self):
        """Test UPDATE without WHERE clause produces warning."""
        result = self.destructive_validator.validate("UPDATE employees SET salary = 100000")
        assert result.is_valid
        assert any("WHERE" in w for w in result.warnings)

    def test_sql_injection_detection(self):
        """Test detection of SQL injection patterns."""
        injection_attempts = [
            "SELECT * FROM employees WHERE id = 1 OR 1=1",
            "SELECT * FROM employees; DROP TABLE employees",
            "SELECT * FROM employees WHERE name = 'admin'--",
        ]

        for sql in injection_attempts:
            result = self.validator.validate(sql)
            # Either blocked or has warnings
            assert not result.is_valid or len(result.warnings) > 0

    def test_select_all_from_table(self):
        """Test simple SELECT all."""
        result = self.validator.validate("SELECT * FROM products")
        assert result.is_valid

    def test_aggregate_functions(self):
        """Test queries with aggregate functions."""
        aggregates = [
            "SELECT COUNT(*) FROM employees",
            "SELECT AVG(salary) FROM employees",
            "SELECT MAX(salary), MIN(salary) FROM employees",
            "SELECT SUM(total_amount) FROM sales",
        ]

        for sql in aggregates:
            result = self.validator.validate(sql)
            assert result.is_valid, f"Failed for: {sql}"

    def test_subquery(self):
        """Test queries with subqueries."""
        sql = """
        SELECT * FROM employees
        WHERE department_id IN (SELECT id FROM departments WHERE budget > 100000)
        """
        result = self.validator.validate(sql)
        assert result.is_valid

    def test_cte_query(self):
        """Test Common Table Expression queries."""
        sql = """
        WITH high_earners AS (
            SELECT * FROM employees WHERE salary > 100000
        )
        SELECT * FROM high_earners
        """
        result = self.validator.validate(sql)
        assert result.is_valid
        assert result.statement_type == "WITH"

    def test_format_sql(self):
        """Test SQL formatting."""
        sql = "select * from employees where salary>50000"
        formatted = self.validator.format_sql(sql)
        assert "SELECT" in formatted
        assert "FROM" in formatted
        assert "WHERE" in formatted


class TestValidationResult:
    """Test cases for ValidationResult."""

    def test_add_error(self):
        """Test adding an error."""
        result = ValidationResult(is_valid=True)
        result.add_issue(ValidationLevel.ERROR, "Test error")
        assert not result.is_valid
        assert "Test error" in result.errors

    def test_add_warning(self):
        """Test adding a warning."""
        result = ValidationResult(is_valid=True)
        result.add_issue(ValidationLevel.WARNING, "Test warning")
        assert result.is_valid  # Warnings don't invalidate
        assert "Test warning" in result.warnings

    def test_add_info(self):
        """Test adding info message."""
        result = ValidationResult(is_valid=True)
        result.add_issue(ValidationLevel.INFO, "Test info")
        assert result.is_valid
        assert "Test info" in result.info


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
