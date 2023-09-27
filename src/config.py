"""Configuration management for Text-to-SQL Interface."""

import os
from dataclasses import dataclass, field
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    """Application settings loaded from environment variables."""

    # OpenAI Configuration
    openai_api_key: Optional[str] = field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview"))

    # Database Configuration
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./data/sample.db"))
    database_type: str = field(default_factory=lambda: os.getenv("DATABASE_TYPE", "sqlite"))

    # Security Settings
    max_rows_returned: int = field(default_factory=lambda: int(os.getenv("MAX_ROWS_RETURNED", "1000")))
    query_timeout_seconds: int = field(default_factory=lambda: int(os.getenv("QUERY_TIMEOUT_SECONDS", "30")))
    allow_destructive_queries: bool = field(
        default_factory=lambda: os.getenv("ALLOW_DESTRUCTIVE_QUERIES", "false").lower() == "true"
    )

    # Feedback System
    feedback_db_path: str = field(default_factory=lambda: os.getenv("FEEDBACK_DB_PATH", "./data/feedback.db"))
    feedback_learning_rate: float = field(default_factory=lambda: float(os.getenv("FEEDBACK_LEARNING_RATE", "0.1")))

    # Application Settings
    debug: bool = field(default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true")
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    def validate(self) -> bool:
        """Validate required settings."""
        if not self.openai_api_key:
            print("Warning: OPENAI_API_KEY not set. Translation features will be limited.")
            return False
        return True

    @classmethod
    def from_env(cls) -> "Settings":
        """Create settings from environment variables."""
        return cls()


# Global settings instance
settings = Settings.from_env()
