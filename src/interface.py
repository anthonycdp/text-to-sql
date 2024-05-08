"""Main Text-to-SQL Interface combining all components."""

from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

from src.config import settings
from src.database import DatabaseManager
from src.validator import SQLValidator
from src.security import SecurityLayer, SecurityConfig, QueryExecutionResult
from src.translator import TextToSQLTranslator, TranslationResult
from src.feedback import FeedbackSystem


@dataclass
class QueryResult:
    """Complete result of a natural language query."""
    natural_query: str
    sql: str
    translation_result: TranslationResult
    execution_result: Optional[QueryExecutionResult] = None
    learned_correction_used: bool = False
    suggestions: list[dict] = field(default_factory=list)
    success: bool = True
    error: Optional[str] = None


class TextToSQLInterface:
    """Main interface for Text-to-SQL translation and execution."""

    def __init__(
        self,
        database_url: Optional[str] = None,
        api_key: Optional[str] = None,
        allow_destructive: bool = False,
        max_rows: int = 1000,
    ):
        # Initialize database
        self.db_manager = DatabaseManager(database_url or settings.database_url)

        # Initialize security
        self.security_config = SecurityConfig(
            max_rows=max_rows,
            query_timeout=settings.query_timeout_seconds,
            allow_destructive=allow_destructive,
        )
        self.validator = SQLValidator(allow_destructive=allow_destructive)
        self.security = SecurityLayer(
            validator=self.validator,
            config=self.security_config
        )

        # Initialize translator
        self.translator = TextToSQLTranslator(
            self.db_manager,
            use_llm=True,
            api_key=api_key
        )

        # Initialize feedback system
        self.feedback = FeedbackSystem()

        # Query history
        self._history: list[QueryResult] = []

    def query(
        self,
        natural_language: str,
        execute: bool = True
    ) -> QueryResult:
        """
        Process a natural language query.

        Args:
            natural_language: The natural language query
            execute: Whether to execute the generated SQL

        Returns:
            QueryResult with translation and execution details
        """
        result = self._create_empty_result(natural_language)

        self._apply_translation_or_correction(result, natural_language)

        if result.error:
            self._history.append(result)
            return result

        if execute and result.sql:
            self._execute_and_populate_result(result)

        self._history.append(result)
        return result

    def _create_empty_result(self, natural_language: str) -> QueryResult:
        """Create an empty query result."""
        return QueryResult(
            natural_query=natural_language,
            sql="",
            translation_result=TranslationResult(sql="", original_query=natural_language),
        )

    def _apply_translation_or_correction(self, result: QueryResult, natural_language: str) -> None:
        """Apply learned correction or translate the query."""
        learned_sql = self.feedback.get_learned_correction(natural_language)

        if learned_sql:
            result.learned_correction_used = True
            result.sql = learned_sql
            result.translation_result.sql = learned_sql
            result.translation_result.explanation = "Using previously learned correction"
            result.translation_result.confidence = 1.0
            return

        translation = self.translator.translate(natural_language)
        result.translation_result = translation
        result.sql = translation.sql

        if translation.error:
            result.success = False
            result.error = translation.error
            return

        result.suggestions = self.feedback.get_correction_suggestions(
            natural_language,
            translation.sql
        )

    def _execute_and_populate_result(self, result: QueryResult) -> None:
        """Execute SQL and populate result with execution data."""
        execution = self.security.secure_execute(
            result.sql,
            lambda sql, _: self.db_manager.execute_query(sql)
        )
        result.execution_result = execution

        if not execution.success:
            result.success = False
            result.error = execution.error_message

    def execute_sql(self, sql: str) -> QueryExecutionResult:
        """
        Execute raw SQL with security checks.

        Args:
            sql: The SQL query to execute

        Returns:
            QueryExecutionResult
        """
        return self.security.secure_execute(
            sql,
            lambda q, _: self.db_manager.execute_query(q)
        )

    def provide_feedback(
        self,
        natural_query: str,
        original_sql: str,
        corrected_sql: Optional[str] = None,
        was_helpful: bool = True,
        notes: str = ""
    ) -> None:
        """
        Provide feedback on a translation.

        Args:
            natural_query: The original natural language query
            original_sql: The generated SQL
            corrected_sql: The corrected SQL (if any)
            was_helpful: Whether the translation was helpful
            notes: Additional notes
        """
        self.feedback.record_feedback(
            natural_query=natural_query,
            original_sql=original_sql,
            corrected_sql=corrected_sql,
            was_helpful=was_helpful,
            user_notes=notes
        )

    def get_schema(self) -> dict:
        """Get the database schema."""
        return self.db_manager.get_schema_info()

    def get_table_names(self) -> list[str]:
        """Get list of table names."""
        return self.db_manager.get_table_names()

    def get_history(self, limit: int = 10) -> list[QueryResult]:
        """Get recent query history."""
        return self._history[-limit:]

    def get_stats(self) -> dict:
        """Get statistics about the interface usage."""
        feedback_stats = self.feedback.get_stats()
        security_stats = self.security.get_statistics()

        return {
            "queries_total": len(self._history),
            "queries_successful": sum(1 for r in self._history if r.success),
            "feedback": {
                "total": feedback_stats.total_queries,
                "corrections": feedback_stats.total_corrections,
                "helpful_rate": feedback_stats.improvement_rate,
            },
            "security": security_stats,
        }

    def export_feedback(self, path: str) -> int:
        """Export feedback to a file."""
        return self.feedback.export_learnings(path)

    def import_feedback(self, path: str) -> int:
        """Import feedback from a file."""
        return self.feedback.import_learnings(path)

    def close(self) -> None:
        """Close database connections."""
        self.db_manager.close()


def create_sample_database(db_path: str = "./data/sample.db") -> DatabaseManager:
    """Create a sample database with test data."""
    from pathlib import Path
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    db = DatabaseManager(f"sqlite:///{db_path}")

    # Create tables
    create_tables_sql = """
    -- Employees table
    CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        department_id INTEGER,
        salary REAL NOT NULL,
        hire_date DATE NOT NULL,
        is_active BOOLEAN DEFAULT TRUE,
        FOREIGN KEY (department_id) REFERENCES departments(id)
    );

    -- Departments table
    CREATE TABLE IF NOT EXISTS departments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        budget REAL NOT NULL,
        location TEXT,
        manager_id INTEGER,
        FOREIGN KEY (manager_id) REFERENCES employees(id)
    );

    -- Projects table
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        start_date DATE NOT NULL,
        end_date DATE,
        budget REAL NOT NULL,
        status TEXT DEFAULT 'active',
        department_id INTEGER,
        FOREIGN KEY (department_id) REFERENCES departments(id)
    );

    -- Sales table
    CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER NOT NULL,
        product_name TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        unit_price REAL NOT NULL,
        total_amount REAL NOT NULL,
        sale_date DATE NOT NULL,
        region TEXT,
        FOREIGN KEY (employee_id) REFERENCES employees(id)
    );

    -- Products table
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        price REAL NOT NULL,
        stock_quantity INTEGER DEFAULT 0,
        supplier TEXT,
        is_available BOOLEAN DEFAULT TRUE
    );
    """

    with db.engine.connect() as conn:
        conn.connection.executescript(create_tables_sql)
        conn.commit()

    # Insert sample data
    insert_data_sql = """
    -- Insert departments
    INSERT OR IGNORE INTO departments (id, name, budget, location, manager_id) VALUES
    (1, 'Engineering', 500000.00, 'Building A', NULL),
    (2, 'Marketing', 200000.00, 'Building B', NULL),
    (3, 'Sales', 300000.00, 'Building C', NULL),
    (4, 'Human Resources', 150000.00, 'Building A', NULL),
    (5, 'Finance', 250000.00, 'Building D', NULL);

    -- Insert employees
    INSERT OR IGNORE INTO employees (id, first_name, last_name, email, department_id, salary, hire_date, is_active) VALUES
    (1, 'John', 'Smith', 'john.smith@company.com', 1, 95000.00, '2020-01-15', TRUE),
    (2, 'Jane', 'Doe', 'jane.doe@company.com', 1, 105000.00, '2019-03-20', TRUE),
    (3, 'Bob', 'Johnson', 'bob.johnson@company.com', 2, 75000.00, '2021-06-01', TRUE),
    (4, 'Alice', 'Williams', 'alice.williams@company.com', 3, 85000.00, '2020-09-10', TRUE),
    (5, 'Charlie', 'Brown', 'charlie.brown@company.com', 3, 72000.00, '2022-02-28', TRUE),
    (6, 'Diana', 'Miller', 'diana.miller@company.com', 4, 65000.00, '2021-11-15', TRUE),
    (7, 'Edward', 'Davis', 'edward.davis@company.com', 5, 90000.00, '2019-07-22', TRUE),
    (8, 'Fiona', 'Garcia', 'fiona.garcia@company.com', 1, 98000.00, '2020-04-05', TRUE),
    (9, 'George', 'Martinez', 'george.martinez@company.com', 2, 70000.00, '2022-01-10', FALSE),
    (10, 'Hannah', 'Anderson', 'hannah.anderson@company.com', 3, 78000.00, '2021-08-30', TRUE);

    -- Insert products
    INSERT OR IGNORE INTO products (id, name, category, price, stock_quantity, supplier, is_available) VALUES
    (1, 'Laptop Pro', 'Electronics', 1299.99, 50, 'TechSupply Inc', TRUE),
    (2, 'Wireless Mouse', 'Electronics', 29.99, 200, 'TechSupply Inc', TRUE),
    (3, 'Office Chair', 'Furniture', 249.99, 30, 'OfficeGoods Co', TRUE),
    (4, 'Standing Desk', 'Furniture', 599.99, 15, 'OfficeGoods Co', TRUE),
    (5, 'Monitor 27"', 'Electronics', 399.99, 75, 'TechSupply Inc', TRUE),
    (6, 'Keyboard', 'Electronics', 79.99, 150, 'TechSupply Inc', TRUE),
    (7, 'Desk Lamp', 'Furniture', 45.99, 100, 'OfficeGoods Co', TRUE),
    (8, 'Webcam HD', 'Electronics', 89.99, 80, 'TechSupply Inc', TRUE);

    -- Insert projects
    INSERT OR IGNORE INTO projects (id, name, description, start_date, end_date, budget, status, department_id) VALUES
    (1, 'Website Redesign', 'Complete overhaul of company website', '2024-01-01', '2024-06-30', 50000.00, 'active', 1),
    (2, 'Marketing Campaign Q1', 'Spring marketing initiative', '2024-02-01', '2024-04-30', 30000.00, 'completed', 2),
    (3, 'Sales Training', 'New sales team training program', '2024-03-01', '2024-05-31', 15000.00, 'active', 3),
    (4, 'HR System Upgrade', 'Update HR management system', '2024-01-15', '2024-03-15', 25000.00, 'completed', 4),
    (5, 'Budget Analysis', 'Q2 financial planning', '2024-04-01', '2024-06-30', 10000.00, 'active', 5);

    -- Insert sales
    INSERT OR IGNORE INTO sales (id, employee_id, product_name, quantity, unit_price, total_amount, sale_date, region) VALUES
    (1, 4, 'Laptop Pro', 5, 1299.99, 6499.95, '2024-01-15', 'North'),
    (2, 4, 'Wireless Mouse', 20, 29.99, 599.80, '2024-01-20', 'North'),
    (3, 5, 'Monitor 27"', 10, 399.99, 3999.90, '2024-02-01', 'South'),
    (4, 5, 'Keyboard', 15, 79.99, 1199.85, '2024-02-10', 'South'),
    (5, 10, 'Office Chair', 8, 249.99, 1999.92, '2024-02-15', 'East'),
    (6, 10, 'Standing Desk', 3, 599.99, 1799.97, '2024-02-20', 'East'),
    (7, 4, 'Laptop Pro', 2, 1299.99, 2599.98, '2024-03-01', 'North'),
    (8, 5, 'Webcam HD', 25, 89.99, 2249.75, '2024-03-05', 'West'),
    (9, 10, 'Desk Lamp', 30, 45.99, 1379.70, '2024-03-10', 'East'),
    (10, 4, 'Monitor 27"', 7, 399.99, 2799.93, '2024-03-15', 'North');
    """

    with db.engine.connect() as conn:
        conn.connection.executescript(insert_data_sql)
        conn.commit()

    return db
