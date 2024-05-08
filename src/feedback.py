"""Feedback loop system for improving SQL translations."""

import json
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional
import hashlib

from src.config import settings


@dataclass
class FeedbackEntry:
    """A single feedback entry."""
    id: Optional[int] = None
    natural_query: str = ""
    original_sql: str = ""
    corrected_sql: str = ""
    was_helpful: bool = True
    user_notes: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    query_hash: str = ""

    HASH_LENGTH = 12

    def __post_init__(self):
        if not self.query_hash:
            self.query_hash = self._compute_hash(self.natural_query)

    @classmethod
    def from_database_row(cls, row: tuple) -> "FeedbackEntry":
        """Create a FeedbackEntry from a database row."""
        return cls(
            id=row[0],
            natural_query=row[1],
            original_sql=row[2],
            corrected_sql=row[3],
            was_helpful=bool(row[4]),
            user_notes=row[5],
            timestamp=row[6],
            query_hash=row[7]
        )

    @staticmethod
    def _compute_hash(query: str) -> str:
        """Compute a normalized hash for query matching."""
        normalized = " ".join(query.lower().split())
        return hashlib.md5(normalized.encode()).hexdigest()[:FeedbackEntry.HASH_LENGTH]


@dataclass
class FeedbackStats:
    """Statistics about feedback collection."""
    total_queries: int = 0
    total_corrections: int = 0
    helpful_count: int = 0
    unhelpful_count: int = 0
    improvement_rate: float = 0.0


class FeedbackStore:
    """Persistent storage for feedback data."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.feedback_db_path
        self._ensure_db()

    def _ensure_db(self) -> None:
        """Ensure the database and tables exist."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                natural_query TEXT NOT NULL,
                original_sql TEXT NOT NULL,
                corrected_sql TEXT,
                was_helpful BOOLEAN DEFAULT TRUE,
                user_notes TEXT,
                timestamp TEXT NOT NULL,
                query_hash TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_query_hash
            ON feedback(query_hash)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp
            ON feedback(timestamp)
        """)

        conn.commit()
        conn.close()

    def add_feedback(self, entry: FeedbackEntry) -> int:
        """Add a feedback entry and return its ID."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO feedback
            (natural_query, original_sql, corrected_sql, was_helpful, user_notes, timestamp, query_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            entry.natural_query,
            entry.original_sql,
            entry.corrected_sql,
            entry.was_helpful,
            entry.user_notes,
            entry.timestamp,
            entry.query_hash
        ))

        entry_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return entry_id

    def get_feedback_by_hash(self, query_hash: str) -> Optional[FeedbackEntry]:
        """Get the most recent feedback for a query hash."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, natural_query, original_sql, corrected_sql, was_helpful, user_notes, timestamp, query_hash
            FROM feedback
            WHERE query_hash = ?
            ORDER BY timestamp DESC
            LIMIT 1
        """, (query_hash,))

        row = cursor.fetchone()
        conn.close()

        return FeedbackEntry.from_database_row(row) if row else None

    def get_all_corrections(self) -> list[FeedbackEntry]:
        """Get all entries with corrections."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, natural_query, original_sql, corrected_sql, was_helpful, user_notes, timestamp, query_hash
            FROM feedback
            WHERE corrected_sql IS NOT NULL AND corrected_sql != ''
            ORDER BY timestamp DESC
        """)

        rows = cursor.fetchall()
        conn.close()

        return [FeedbackEntry.from_database_row(row) for row in rows]

    def get_stats(self) -> FeedbackStats:
        """Get feedback statistics."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM feedback")
        total_queries = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM feedback WHERE corrected_sql IS NOT NULL AND corrected_sql != ''")
        total_corrections = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM feedback WHERE was_helpful = 1")
        helpful_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM feedback WHERE was_helpful = 0")
        unhelpful_count = cursor.fetchone()[0]

        conn.close()

        improvement_rate = (helpful_count / total_queries * 100) if total_queries > 0 else 0.0

        return FeedbackStats(
            total_queries=total_queries,
            total_corrections=total_corrections,
            helpful_count=helpful_count,
            unhelpful_count=unhelpful_count,
            improvement_rate=improvement_rate
        )

    def clear_all(self) -> None:
        """Clear all feedback data."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM feedback")
        conn.commit()
        conn.close()


class FeedbackSystem:
    """System for collecting and learning from user feedback."""

    def __init__(self, store: Optional[FeedbackStore] = None):
        self.store = store or FeedbackStore()
        self._correction_cache: dict[str, str] = {}
        self._load_correction_cache()

    def _load_correction_cache(self) -> None:
        """Load all corrections into memory for fast lookup."""
        corrections = self.store.get_all_corrections()
        for entry in corrections:
            if entry.corrected_sql:
                self._correction_cache[entry.query_hash] = entry.corrected_sql

    def record_feedback(
        self,
        natural_query: str,
        original_sql: str,
        corrected_sql: Optional[str] = None,
        was_helpful: bool = True,
        user_notes: str = ""
    ) -> FeedbackEntry:
        """Record user feedback on a translation."""
        entry = FeedbackEntry(
            natural_query=natural_query,
            original_sql=original_sql,
            corrected_sql=corrected_sql or "",
            was_helpful=was_helpful,
            user_notes=user_notes,
        )

        entry.id = self.store.add_feedback(entry)

        # Update cache if there's a correction
        if corrected_sql:
            self._correction_cache[entry.query_hash] = corrected_sql

        return entry

    def get_learned_correction(self, natural_query: str) -> Optional[str]:
        """Get a previously learned correction for a similar query."""
        query_hash = FeedbackEntry._compute_hash(natural_query)
        return self._correction_cache.get(query_hash)

    def get_similar_corrections(self, natural_query: str, limit: int = 5) -> list[FeedbackEntry]:
        """Get corrections for similar queries."""
        # Simple implementation: get all corrections
        # A more sophisticated version would use semantic similarity
        all_corrections = self.store.get_all_corrections()

        # Filter by keyword overlap
        query_words = set(natural_query.lower().split())
        scored = []

        for entry in all_corrections:
            entry_words = set(entry.natural_query.lower().split())
            overlap = len(query_words & entry_words)
            if overlap > 0:
                scored.append((overlap, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:limit]]

    def get_correction_suggestions(
        self,
        natural_query: str,
        generated_sql: str
    ) -> list[dict]:
        """Get suggestions based on past corrections."""
        similar = self.get_similar_corrections(natural_query)

        suggestions = []
        for entry in similar:
            if entry.corrected_sql and entry.corrected_sql != generated_sql:
                suggestions.append({
                    "sql": entry.corrected_sql,
                    "reason": f"Previously corrected for: '{entry.natural_query}'",
                    "notes": entry.user_notes,
                })

        return suggestions[:3]  # Limit to 3 suggestions

    def get_stats(self) -> FeedbackStats:
        """Get feedback statistics."""
        return self.store.get_stats()

    def export_learnings(self, output_path: str) -> int:
        """Export learned corrections to a JSON file."""
        corrections = self.store.get_all_corrections()

        data = [
            {
                "natural_query": entry.natural_query,
                "original_sql": entry.original_sql,
                "corrected_sql": entry.corrected_sql,
                "notes": entry.user_notes,
                "timestamp": entry.timestamp,
            }
            for entry in corrections
        ]

        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)

        return len(data)

    def import_learnings(self, input_path: str) -> int:
        """Import learned corrections from a JSON file."""
        with open(input_path, 'r') as f:
            data = json.load(f)

        count = 0
        for item in data:
            self.record_feedback(
                natural_query=item["natural_query"],
                original_sql=item["original_sql"],
                corrected_sql=item.get("corrected_sql"),
                was_helpful=True,
                user_notes=item.get("notes", ""),
            )
            count += 1

        return count

    def clear_learnings(self) -> None:
        """Clear all learned feedback."""
        self.store.clear_all()
        self._correction_cache.clear()
