"""Tests for Feedback System."""

import pytest
import tempfile
import os
import shutil
from pathlib import Path

from src.feedback import FeedbackSystem, FeedbackStore, FeedbackEntry, FeedbackStats


class TestFeedbackEntry:
    """Test cases for FeedbackEntry."""

    def test_entry_creation(self):
        """Test creating a feedback entry."""
        entry = FeedbackEntry(
            natural_query="show all employees",
            original_sql="SELECT * FROM employees",
            corrected_sql="SELECT * FROM employees LIMIT 100",
            was_helpful=False,
            user_notes="Added limit for safety"
        )
        assert entry.natural_query == "show all employees"
        assert entry.was_helpful is False
        assert len(entry.query_hash) == 12

    def test_hash_consistency(self):
        """Test that similar queries get similar hashes."""
        entry1 = FeedbackEntry(natural_query="show all employees")
        entry2 = FeedbackEntry(natural_query="Show All Employees")  # Case different
        entry3 = FeedbackEntry(natural_query="show  all  employees")  # Extra spaces

        # Normalized should produce same hash
        assert entry1.query_hash == entry2.query_hash
        assert entry1.query_hash == entry3.query_hash

    def test_different_queries_different_hashes(self):
        """Test that different queries get different hashes."""
        entry1 = FeedbackEntry(natural_query="show all employees")
        entry2 = FeedbackEntry(natural_query="count all products")

        assert entry1.query_hash != entry2.query_hash


class TestFeedbackStore:
    """Test cases for FeedbackStore."""

    def setup_method(self):
        """Set up test fixtures with temporary database."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_feedback.db")
        self.store = FeedbackStore(db_path=self.db_path)

    def teardown_method(self):
        """Clean up temporary files."""
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        shutil.rmtree(self.temp_dir)

    def test_add_feedback(self):
        """Test adding feedback to store."""
        entry = FeedbackEntry(
            natural_query="show all employees",
            original_sql="SELECT * FROM employees"
        )
        entry_id = self.store.add_feedback(entry)
        assert entry_id > 0

    def test_get_feedback_by_hash(self):
        """Test retrieving feedback by hash."""
        entry = FeedbackEntry(
            natural_query="show all employees",
            original_sql="SELECT * FROM employees",
            corrected_sql="SELECT * FROM employees LIMIT 100"
        )
        self.store.add_feedback(entry)

        retrieved = self.store.get_feedback_by_hash(entry.query_hash)
        assert retrieved is not None
        assert retrieved.corrected_sql == "SELECT * FROM employees LIMIT 100"

    def test_get_all_corrections(self):
        """Test retrieving all corrections."""
        # Add entries with and without corrections
        self.store.add_feedback(FeedbackEntry(
            natural_query="query1",
            original_sql="SELECT 1",
            corrected_sql="SELECT 1 LIMIT 100"
        ))
        self.store.add_feedback(FeedbackEntry(
            natural_query="query2",
            original_sql="SELECT 2"
            # No correction
        ))
        self.store.add_feedback(FeedbackEntry(
            natural_query="query3",
            original_sql="SELECT 3",
            corrected_sql="SELECT 3 LIMIT 50"
        ))

        corrections = self.store.get_all_corrections()
        assert len(corrections) == 2

    def test_get_stats(self):
        """Test statistics calculation."""
        self.store.add_feedback(FeedbackEntry(
            natural_query="q1",
            original_sql="SELECT 1",
            was_helpful=True
        ))
        self.store.add_feedback(FeedbackEntry(
            natural_query="q2",
            original_sql="SELECT 2",
            corrected_sql="SELECT 2 LIMIT 100",
            was_helpful=False
        ))

        stats = self.store.get_stats()
        assert stats.total_queries == 2
        assert stats.total_corrections == 1
        assert stats.helpful_count == 1
        assert stats.unhelpful_count == 1


class TestFeedbackSystem:
    """Test cases for the FeedbackSystem."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_feedback.db")
        store = FeedbackStore(db_path=self.db_path)
        self.feedback = FeedbackSystem(store=store)

    def teardown_method(self):
        """Clean up."""
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        shutil.rmtree(self.temp_dir)

    def test_record_and_retrieve_feedback(self):
        """Test recording and retrieving feedback."""
        self.feedback.record_feedback(
            natural_query="show all employees",
            original_sql="SELECT * FROM employees",
            corrected_sql="SELECT * FROM employees LIMIT 100",
            was_helpful=False
        )

        correction = self.feedback.get_learned_correction("show all employees")
        assert correction == "SELECT * FROM employees LIMIT 100"

    def test_similar_corrections(self):
        """Test finding similar corrections."""
        self.feedback.record_feedback(
            natural_query="show all employees in engineering",
            original_sql="SELECT * FROM employees",
            corrected_sql="SELECT * FROM employees WHERE department = 'Engineering'",
            was_helpful=False
        )

        similar = self.feedback.get_similar_corrections("show all employees in sales")
        assert len(similar) > 0

    def test_export_import(self):
        """Test exporting and importing feedback."""
        # Add some feedback
        self.feedback.record_feedback(
            natural_query="query1",
            original_sql="SELECT 1",
            corrected_sql="SELECT 1 LIMIT 100"
        )
        self.feedback.record_feedback(
            natural_query="query2",
            original_sql="SELECT 2",
            corrected_sql="SELECT 2 LIMIT 50"
        )

        # Export
        export_path = os.path.join(self.temp_dir, "export.json")
        count = self.feedback.export_learnings(export_path)
        assert count == 2
        assert os.path.exists(export_path)

        # Clear and reimport
        self.feedback.clear_learnings()
        imported = self.feedback.import_learnings(export_path)
        assert imported == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
