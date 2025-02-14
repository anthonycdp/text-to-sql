# Text-to-SQL Interface

A comprehensive Natural Language to SQL translation system with validation, security controls, and a feedback loop for continuous improvement.

## Features

- **Natural Language Translation**: Convert plain English queries to SQL using LLM (OpenAI/LangChain) or rule-based fallback
- **SQL Validation**: Syntax checking and safety validation before execution
- **Security Layer**: Row limits, query timeouts, and injection protection
- **Feedback Loop**: User corrections improve future translations
- **Multiple Interfaces**: CLI and Web UI for different use cases
- **Sample Database**: Pre-populated database for testing and demonstration

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     User Interface                          │
│              (CLI / Web API / Python SDK)                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Text-to-SQL Interface                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ Translator  │  │  Validator  │  │   Security Layer    │ │
│  │ (LLM/Rules) │  │ (Syntax/    │  │ (Limits/Timeouts/   │ │
│  │             │  │  Safety)    │  │  Injection Check)   │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Feedback System                          │
│  ┌─────────────────┐  ┌─────────────────────────────────┐  │
│  │ Feedback Store  │  │     Learning Cache              │  │
│  │ (SQLite)        │  │  (Query -> Corrected SQL)       │  │
│  └─────────────────┘  └─────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Database Layer                           │
│                  (SQLAlchemy / SQLite)                      │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Installation

```bash
# Navigate to the project
cd text-to-sql

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

```bash
# Copy example environment file
cp .env.example .env

# Edit .env and add your OpenAI API key (optional - rule-based fallback available)
# OPENAI_API_KEY=your-api-key-here
```

### 3. Setup Sample Database

```bash
# Create and populate the sample database
python setup_db.py
```

### 4. Run the Interface

**CLI Interface:**
```bash
python -m src.cli
```

**Web Interface:**
```bash
python -m src.web
# Open http://localhost:5000 in your browser
```

## Usage Examples

### CLI Usage

```python
from src.interface import TextToSQLInterface

# Initialize the interface
interface = TextToSQLInterface()

# Translate and execute a natural language query
result = interface.query("Show all employees")

# Check the generated SQL
print(result.sql)
# SELECT * FROM employees LIMIT 100

# Access the results
for row in result.execution_result.data:
    print(row)

# Provide feedback to improve future queries
interface.provide_feedback(
    natural_query="Show all employees",
    original_sql=result.sql,
    corrected_sql="SELECT * FROM employees ORDER BY name LIMIT 100",
    was_helpful=True,
    notes="Added ordering by name"
)
```

### Web API Usage

```bash
# Execute a query
curl -X POST http://localhost:5000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Show average salary by department"}'

# Get database schema
curl http://localhost:5000/api/schema

# Get usage statistics
curl http://localhost:5000/api/stats

# Submit feedback
curl -X POST http://localhost:5000/api/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Show average salary by department",
    "sql": "SELECT department, AVG(salary) FROM employees GROUP BY department",
    "helpful": true
  }'
```

### Python SDK Usage

```python
from src.interface import TextToSQLInterface
from src.validator import SQLValidator
from src.security import SecurityLayer, SecurityConfig

# Create interface with custom configuration
interface = TextToSQLInterface(
    database_url="sqlite:///my_database.db",
    api_key="your-openai-api-key",
    allow_destructive=False,
    max_rows=500
)

# Query without execution (just translation)
result = interface.query("Count employees in each department", execute=False)
print(result.sql)

# Execute raw SQL with security checks
exec_result = interface.execute_sql("SELECT * FROM products WHERE price < 100")
print(f"Found {exec_result.row_count} products")

# Get database schema
schema = interface.get_schema()
for table, info in schema.items():
    print(f"Table: {table}")
    for col in info['columns']:
        print(f"  - {col['name']}: {col['type']}")

# Export learned feedback
interface.export_feedback("learned_corrections.json")

# Import feedback from file
interface.import_feedback("corrections.json")
```

## Sample Queries

The system supports a variety of natural language patterns:

| Natural Language Query | Generated SQL |
|------------------------|---------------|
| "Show all employees" | `SELECT * FROM employees LIMIT 100` |
| "Count employees" | `SELECT COUNT(*) as count FROM employees` |
| "Show all products" | `SELECT * FROM products LIMIT 100` |
| "List departments" | `SELECT * FROM departments LIMIT 100` |

See `examples/sample_queries.json` for more examples.

## Security Features

### SQL Validation

The validator checks for:
- Valid SQL syntax
- Allowed statement types (SELECT only by default)
- Dangerous keywords (DROP, DELETE, TRUNCATE, etc.)
- SQL injection patterns

```python
from src.validator import SQLValidator

validator = SQLValidator(allow_destructive=False)
result = validator.validate("SELECT * FROM users WHERE id = 1; DROP TABLE users")

if not result.is_valid:
    print("Validation failed:", result.errors)
```

### Security Layer

The security layer enforces:
- Maximum row limits (prevents excessive data retrieval)
- Query timeouts (prevents long-running queries)
- Table access control (allowlist/blocklist)
- Automatic LIMIT clause injection

```python
from src.security import SecurityLayer, SecurityConfig

config = SecurityConfig(
    max_rows=1000,
    query_timeout=30,
    allow_destructive=False,
    allowed_tables=['employees', 'departments', 'products']
)

security = SecurityLayer(config=config)
```

## Feedback System

The feedback system learns from user corrections:

```python
from src.feedback import FeedbackSystem

feedback = FeedbackSystem()

# Record a correction
feedback.record_feedback(
    natural_query="show all active employees",
    original_sql="SELECT * FROM employees",
    corrected_sql="SELECT * FROM employees WHERE is_active = TRUE",
    was_helpful=False,
    notes="Added active filter"
)

# The system will use this correction for similar future queries
correction = feedback.get_learned_correction("show all active employees")
# Returns: "SELECT * FROM employees WHERE is_active = TRUE"
```

### How It Works

1. **Query Hashing**: Natural language queries are normalized and hashed
2. **Correction Storage**: User corrections are stored with the query hash
3. **Retrieval**: When a similar query is asked, the stored correction is retrieved
4. **Suggestions**: Similar past queries provide alternative suggestions

## Configuration Options

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key for LLM translation | Optional (rule-based fallback) |
| `OPENAI_MODEL` | OpenAI model to use | `gpt-4-turbo-preview` |
| `DATABASE_URL` | Database connection string | `sqlite:///./data/sample.db` |
| `DATABASE_TYPE` | Database type | `sqlite` |
| `MAX_ROWS_RETURNED` | Maximum rows in results | `1000` |
| `QUERY_TIMEOUT_SECONDS` | Query timeout in seconds | `30` |
| `ALLOW_DESTRUCTIVE_QUERIES` | Allow INSERT/UPDATE/DELETE | `false` |
| `FEEDBACK_DB_PATH` | Path to feedback database | `./data/feedback.db` |
| `DEBUG` | Enable debug mode | `false` |

## Project Structure

```
text-to-sql/
├── src/
│   ├── __init__.py         # Package exports
│   ├── config.py           # Configuration management
│   ├── database.py         # Database connection and operations
│   ├── validator.py        # SQL validation and syntax checking
│   ├── security.py         # Security layer and query limits
│   ├── translator.py       # Natural language to SQL translation
│   ├── feedback.py         # Feedback system for learning
│   ├── interface.py        # Main interface combining all components
│   ├── cli.py              # Command-line interface
│   └── web.py              # Flask web interface
├── tests/
│   ├── test_validator.py   # Validator tests
│   ├── test_security.py    # Security tests
│   └── test_feedback.py    # Feedback system tests
├── examples/
│   └── sample_queries.json # Example queries and expected outputs
├── data/                   # Database files (created on setup)
│   ├── sample.db           # Sample SQLite database
│   └── feedback.db         # Feedback storage
├── requirements.txt        # Python dependencies
├── pyproject.toml          # Project configuration
├── setup_db.py             # Database setup script
├── .env.example            # Environment template
└── README.md               # This file
```

## Database Schema

The sample database includes:

- **employees**: Employee information with department, salary, hire date
- **departments**: Department details with budget and location
- **products**: Product catalog with categories and pricing
- **sales**: Sales records with regional data
- **projects**: Project information with status and budgets

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Run specific test file
pytest tests/test_validator.py -v
```

## Extending the System

### Adding a New LLM Provider

```python
from src.translator import BaseTranslator, TranslationResult

class CustomTranslator(BaseTranslator):
    def translate(self, natural_language_query: str) -> TranslationResult:
        # Implement your translation logic
        sql = your_llm.translate(natural_language_query)
        return TranslationResult(
            sql=sql,
            original_query=natural_language_query,
            confidence=0.9
        )
```

### Adding Custom Validation Rules

```python
from src.validator import SQLValidator, ValidationLevel

class CustomValidator(SQLValidator):
    def _analyze_statement(self, statement, result):
        super()._analyze_statement(statement, result)
        # Add custom rules
        if "sensitive_table" in str(statement).lower():
            result.add_issue(
                ValidationLevel.WARNING,
                "Querying sensitive_table - ensure proper authorization"
            )
```

## Troubleshooting

### Common Issues

1. **"OPENAI_API_KEY not set"**
   - The system will use rule-based fallback translation
   - For LLM translation, add your API key to `.env`

2. **"Database connection failed"**
   - Run `python setup_db.py` to create the sample database
   - Check the `DATABASE_URL` in your `.env` file

3. **"Query exceeded timeout"**
   - Increase `QUERY_TIMEOUT_SECONDS` in `.env`
   - Optimize your query or add indexes

4. **"Query validation failed"**
   - Check if you're using allowed statement types
   - Review validation errors for specific issues

## License

MIT License - See LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Submit a pull request

## Acknowledgments

- [LangChain](https://github.com/langchain-ai/langchain) for LLM integration
- [SQLParse](https://github.com/andialbrecht/sqlparse) for SQL parsing
- [Rich](https://github.com/Textualize/rich) for CLI formatting
