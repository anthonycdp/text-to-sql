"""Natural Language to SQL Translator."""

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Protocol

from src.config import settings
from src.database import DatabaseManager


@dataclass
class TranslationResult:
    """Result of a translation request."""
    sql: str
    original_query: str
    confidence: float = 1.0
    explanation: str = ""
    suggested_alternatives: list[str] = field(default_factory=list)
    tables_used: list[str] = field(default_factory=list)
    error: Optional[str] = None


class LLMProvider(Protocol):
    """Protocol for LLM providers."""

    def generate(self, prompt: str) -> str:
        """Generate text from a prompt."""
        ...


class BaseTranslator(ABC):
    """Abstract base class for translators."""

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self._schema_context: Optional[str] = None

    def get_schema_context(self) -> str:
        """Get database schema as context for translation."""
        if self._schema_context is None:
            schema = self.db_manager.get_schema_info()
            self._schema_context = self._format_schema(schema)
        return self._schema_context

    def _format_schema(self, schema: dict) -> str:
        """Format schema information for LLM context."""
        context_parts = ["Database Schema:\n"]

        for table_name, table_info in schema.items():
            context_parts.append(f"\nTable: {table_name}")
            context_parts.append("Columns:")

            for col in table_info["columns"]:
                nullable = "NULL" if col["nullable"] else "NOT NULL"
                pk = " PRIMARY KEY" if col["primary_key"] else ""
                context_parts.append(f"  - {col['name']} ({col['type']}) {nullable}{pk}")

            if table_info["foreign_keys"]:
                context_parts.append("Foreign Keys:")
                for fk in table_info["foreign_keys"]:
                    context_parts.append(
                        f"  - {fk['constrained_columns']} -> {fk['referred_table']}.{fk['referred_columns']}"
                    )

            # Add sample data
            if table_info["sample_rows"]:
                context_parts.append("Sample Data:")
                for i, row in enumerate(table_info["sample_rows"][:2]):
                    context_parts.append(f"  Row {i+1}: {row}")

        return "\n".join(context_parts)

    @abstractmethod
    def translate(self, natural_language_query: str) -> TranslationResult:
        """Translate natural language to SQL."""
        pass


class LangChainTranslator(BaseTranslator):
    """Translator using LangChain with OpenAI."""

    def __init__(self, db_manager: DatabaseManager, api_key: Optional[str] = None):
        super().__init__(db_manager)
        self.api_key = api_key or settings.openai_api_key
        self.model = settings.openai_model
        self._llm = None
        self._chain = None

    def _init_llm(self):
        """Initialize the LLM lazily."""
        if self._llm is None:
            try:
                from langchain_openai import ChatOpenAI
                from langchain.prompts import ChatPromptTemplate

                self._llm = ChatOpenAI(
                    model=self.model,
                    temperature=0,
                    api_key=self.api_key
                )

                # Create prompt template
                template = """You are an expert SQL translator. Convert the natural language query to SQL.

{schema_context}

Important rules:
1. Only use SELECT statements (no INSERT, UPDATE, DELETE, DROP, etc.)
2. Use proper SQL syntax for SQLite
3. Include appropriate JOINs when querying multiple tables
4. Add LIMIT clause when appropriate
5. Use column names exactly as they appear in the schema

Natural Language Query: {query}

Respond in JSON format:
{{
    "sql": "the SQL query",
    "explanation": "brief explanation of the query",
    "tables_used": ["list", "of", "tables"],
    "confidence": 0.0-1.0
}}"""

                self._prompt = ChatPromptTemplate.from_template(template)
                self._chain = self._prompt | self._llm

            except ImportError:
                raise ImportError(
                    "LangChain not installed. Install with: pip install langchain langchain-openai"
                )

    def translate(self, natural_language_query: str) -> TranslationResult:
        """Translate using LangChain and OpenAI."""
        self._init_llm()

        schema_context = self.get_schema_context()

        try:
            response = self._chain.invoke({
                "schema_context": schema_context,
                "query": natural_language_query
            })

            # Parse JSON response
            content = response.content
            # Extract JSON from markdown code blocks if present
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            result_data = json.loads(content.strip())

            return TranslationResult(
                sql=result_data.get("sql", ""),
                original_query=natural_language_query,
                confidence=result_data.get("confidence", 0.8),
                explanation=result_data.get("explanation", ""),
                tables_used=result_data.get("tables_used", []),
            )

        except json.JSONDecodeError as e:
            # Try to extract SQL directly
            sql_match = re.search(r'SELECT.*?(?:;|$)', content, re.IGNORECASE | re.DOTALL)
            if sql_match:
                return TranslationResult(
                    sql=sql_match.group(0).strip(),
                    original_query=natural_language_query,
                    confidence=0.6,
                    explanation="SQL extracted from response",
                )
            return TranslationResult(
                sql="",
                original_query=natural_language_query,
                error=f"Failed to parse LLM response: {str(e)}",
            )
        except Exception as e:
            return TranslationResult(
                sql="",
                original_query=natural_language_query,
                error=f"Translation error: {str(e)}",
            )


class RuleBasedTranslator(BaseTranslator):
    """Rule-based translator using pattern matching for common query types."""

    DEFAULT_LIMIT = 100
    FALLBACK_LIMIT = 10

    QUERY_PATTERNS = [
        {
            "patterns": [
                r"how many (\w+)",
                r"count (?:of|all|the)? ?(\w+)",
                r"total number of (\w+)",
            ],
            "template": "SELECT COUNT(*) as count FROM {table}",
        },
        {
            "patterns": [
                r"(?:list|show|get|display) (?:all )?(\w+)",
                r"all (\w+)",
            ],
            "template": f"SELECT * FROM {{table}} LIMIT {DEFAULT_LIMIT}",
        },
        {
            "patterns": [
                r"average (\w+) (?:of|in|for) (\w+)",
                r"avg (\w+) (?:of|in|for) (\w+)",
            ],
            "template": "SELECT AVG({column}) as average FROM {table}",
        },
        {
            "patterns": [r"(?:maximum|max|highest) (\w+) (?:of|in|for) (\w+)"],
            "template": "SELECT MAX({column}) as maximum FROM {table}",
        },
        {
            "patterns": [r"(?:minimum|min|lowest) (\w+) (?:of|in|for) (\w+)"],
            "template": "SELECT MIN({column}) as minimum FROM {table}",
        },
        {
            "patterns": [
                r"top (\d+) (\w+)",
                r"(\d+) (?:most|best|highest) (\w+)",
            ],
            "template": "SELECT * FROM {table} ORDER BY {column} DESC LIMIT {limit}",
        },
    ]

    SINGULAR_TO_PLURAL = {
        "employee": "employees",
        "department": "departments",
        "product": "products",
        "order": "orders",
        "customer": "customers",
        "category": "categories",
        "sale": "sales",
        "item": "items",
    }

    def __init__(self, db_manager: DatabaseManager):
        super().__init__(db_manager)
        self._available_tables = [t.lower() for t in db_manager.get_table_names()]

    def translate(self, natural_language_query: str) -> TranslationResult:
        """Translate using pattern matching."""
        query_lower = natural_language_query.lower()

        for pattern_group in self.QUERY_PATTERNS:
            for pattern in pattern_group["patterns"]:
                match = re.search(pattern, query_lower)
                if match:
                    return self._build_query_from_template(
                        pattern_group["template"],
                        match.groups(),
                        natural_language_query
                    )

        return self._fallback_translation(query_lower, natural_language_query)

    def _fallback_translation(self, query_lower: str, original_query: str) -> TranslationResult:
        """Attempt simple table-based translation when patterns don't match."""
        for word in query_lower.split():
            table_name = self._resolve_table_name(word)
            if table_name:
                return TranslationResult(
                    sql=f"SELECT * FROM {table_name} LIMIT {self.DEFAULT_LIMIT}",
                    original_query=original_query,
                    confidence=0.5,
                    explanation=f"Simple SELECT from {table_name}",
                    tables_used=[table_name],
                )

        return TranslationResult(
            sql="",
            original_query=original_query,
            error="Could not translate query. Try rephrasing or use more specific terms.",
            confidence=0.0,
        )

    def _resolve_table_name(self, word: str) -> Optional[str]:
        """Resolve a word to a valid table name."""
        word_singular = word.lower().rstrip('s')
        word_plural = word_singular + 's'
        word_ies = word_singular + 'ies'

        for table in self._available_tables:
            if table in (word_singular, word_plural, word_ies):
                return table

        if word_singular in self.SINGULAR_TO_PLURAL:
            mapped = self.SINGULAR_TO_PLURAL[word_singular]
            if mapped.lower() in self._available_tables:
                return mapped

        return None

    def _build_query_from_template(
        self,
        template: str,
        groups: tuple,
        original_query: str
    ) -> TranslationResult:
        """Build a SQL query from template and matched groups."""
        sql = template

        if "{table}" in sql:
            table = self._resolve_table_name(groups[0])
            if not table:
                return TranslationResult(
                    sql="",
                    original_query=original_query,
                    error=f"Could not find table matching '{groups[0]}'",
                )
            sql = sql.replace("{table}", table)

        if "{column}" in sql:
            column = groups[0] if groups else "id"
            sql = sql.replace("{column}", column)

        if "{limit}" in sql:
            limit = next((g for g in groups if g.isdigit()), str(self.FALLBACK_LIMIT))
            sql = sql.replace("{limit}", limit)

        return TranslationResult(
            sql=sql,
            original_query=original_query,
            confidence=0.7,
            explanation="Generated using pattern matching",
        )


class TextToSQLTranslator:
    """Main translator class with fallback support."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        use_llm: bool = True,
        api_key: Optional[str] = None
    ):
        self.db_manager = db_manager
        self.use_llm = use_llm and (api_key or settings.openai_api_key) is not None

        if self.use_llm:
            self._primary_translator = LangChainTranslator(db_manager, api_key)
        else:
            self._primary_translator = None

        self._fallback_translator = RuleBasedTranslator(db_manager)

    def translate(self, natural_language_query: str) -> TranslationResult:
        """Translate natural language to SQL with fallback."""
        # Try LLM first if available
        if self._primary_translator:
            result = self._primary_translator.translate(natural_language_query)
            if result.sql and not result.error:
                return result

        # Fallback to rule-based
        fallback_result = self._fallback_translator.translate(natural_language_query)
        if not fallback_result.error and self._primary_translator:
            fallback_result.explanation += " (using fallback translator)"
            fallback_result.confidence *= 0.8

        return fallback_result

    def refresh_schema(self) -> None:
        """Refresh cached schema information."""
        self._schema_context = None
        if self._primary_translator:
            self._primary_translator._schema_context = None
