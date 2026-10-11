"""Tests for database operations."""
import sys
import os
import tempfile
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from app.models import AuditResult, AuditStatus, RankingEntry
from app.database import init_db, save_audit, get_audit, list_audits, upsert_ranking, get_rankings


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    import app.database as db_module
    original_path = db_module.DB_PATH
    temp_path = tempfile.mktemp(suffix=".db")
    db_module.DB_PATH = temp_path
    init_db()
    # Clear initial ranking data for isolated tests
    import sqlite3
    conn = sqlite3.connect(str(temp_path))
    conn.execute("DELETE FROM rankings")
    conn.commit()
    conn.close()
    yield
    db_module.DB_PATH = original_path
    if os.path.exists(temp_path):
        os.unlink(temp_path)


class TestDatabase:
    def test_init_db_creates_tables(self, temp_db):
        import sqlite3
        from app.database import DB_PATH
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        assert "audits" in tables
        assert "rankings" in tables

    def test_save_and_get_audit(self, temp_db):
        result = AuditResult(
            audit_id="test001",
            status=AuditStatus.COMPLETED,
            model="gpt-4o",
            base_url="https://api.example.com/v1",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            overall_score=85.0,
            trust_level="high",
        )
        save_audit(result)
        retrieved = get_audit("test001")
        assert retrieved is not None
        assert retrieved["audit_id"] == "test001"
        assert retrieved["model"] == "gpt-4o"
        assert retrieved["overall_score"] == 85.0

    def test_get_nonexistent_audit(self, temp_db):
        result = get_audit("nonexistent")
        assert result is None

    def test_list_audits(self, temp_db):
        for i in range(5):
            result = AuditResult(
                audit_id=f"test{i:03d}",
                status=AuditStatus.COMPLETED,
                model="gpt-4o",
                base_url="https://api.example.com/v1",
                started_at=datetime.now(),
                overall_score=float(80 + i),
            )
            save_audit(result)
        audits = list_audits(limit=3)
        assert len(audits) == 3
        # Should be ordered by started_at DESC
        assert audits[0]["overall_score"] >= audits[1]["overall_score"]

    def test_upsert_and_get_ranking(self, temp_db):
        entry = RankingEntry(
            relay_name="Test Relay",
            base_url="https://api.test.com/v1",
            model="gpt-4o",
            avg_trust_score=85.0,
            audit_count=3,
            last_audited=datetime.now(),
            token_inflation_avg=2.5,
            model_authenticity_rate=0.95,
            avg_latency_ms=1200.0,
            uptime_rate=0.99,
        )
        upsert_ranking(entry)
        rankings = get_rankings()
        assert len(rankings) == 1
        assert rankings[0]["relay_name"] == "Test Relay"
        assert rankings[0]["avg_trust_score"] == 85.0

    def test_ranking_upsert_updates_existing(self, temp_db):
        entry1 = RankingEntry(
            relay_name="Test Relay",
            base_url="https://api.test.com/v1",
            model="gpt-4o",
            avg_trust_score=80.0,
            audit_count=1,
            last_audited=datetime.now(),
        )
        upsert_ranking(entry1)

        entry2 = RankingEntry(
            relay_name="Test Relay Updated",
            base_url="https://api.test.com/v1",
            model="gpt-4o",
            avg_trust_score=90.0,
            audit_count=2,
            last_audited=datetime.now(),
        )
        upsert_ranking(entry2)

        rankings = get_rankings()
        assert len(rankings) == 1  # Should update, not insert
        assert rankings[0]["avg_trust_score"] == 90.0
        assert rankings[0]["audit_count"] == 2

    def test_ranking_filter_by_model(self, temp_db):
        entries = [
            ("gpt-4o", "https://api.relay1.com/v1"),
            ("claude-3-opus", "https://api.relay2.com/v1"),
            ("gpt-4o", "https://api.relay3.com/v1"),
        ]
        for model, base_url in entries:
            entry = RankingEntry(
                relay_name=f"Relay {model}",
                base_url=base_url,
                model=model,
                avg_trust_score=85.0,
                audit_count=1,
                last_audited=datetime.now(),
            )
            upsert_ranking(entry)
        gpt_rankings = get_rankings(model="gpt-4o")
        assert len(gpt_rankings) == 2


class TestListAuditsInjection:
    """list_audits filters attacker-controlled ``model``/``base_url`` query
    params. The shipped query is parameterized; these tests pin that invariant
    (mutation M7, string concatenation, used to leave the suite green)."""

    def _seed(self):
        save_audit(AuditResult(
            audit_id="inj001",
            status=AuditStatus.COMPLETED,
            model="gpt-4o",
            base_url="https://api.example.com/v1",
            started_at=datetime.now(),
            overall_score=90.0,
        ))
        save_audit(AuditResult(
            audit_id="inj002",
            status=AuditStatus.COMPLETED,
            model="claude-3-opus",
            base_url="https://relay.example.org/v1",
            started_at=datetime.now(),
            overall_score=80.0,
        ))

    def test_or_payload_treated_as_literal(self, temp_db):
        import sqlite3
        import app.database as db_module
        self._seed()
        # Classic tautology: if concatenated, this would leak EVERY row.
        rows = list_audits(model="gpt-4o' OR '1'='1")
        assert rows == []
        rows = list_audits(model="x%' OR '1'='1")
        assert rows == []
        # The literal-looking value still finds its intended model...
        rows = list_audits(model="gpt-4o")
        assert len(rows) == 1
        # ... and the table is intact afterwards.
        conn = sqlite3.connect(str(db_module.DB_PATH))
        n = conn.execute("SELECT COUNT(*) FROM audits").fetchone()[0]
        conn.close()
        assert n == 2

    def test_drop_table_payload_treated_as_literal(self, temp_db):
        import sqlite3
        import app.database as db_module
        self._seed()
        rows = list_audits(base_url="x'; DROP TABLE audits;--")
        assert rows == []
        rows = list_audits(base_url="https://relay.example.org/v1' --")
        assert rows == []
        # DROP never executed: the table still exists and holds both rows.
        conn = sqlite3.connect(str(db_module.DB_PATH))
        n = conn.execute("SELECT COUNT(*) FROM audits").fetchone()[0]
        conn.close()
        assert n == 2
        rows = list_audits(model="claude-3-opus")
        assert len(rows) == 1

    def test_comment_payload_treated_as_literal(self, temp_db):
        self._seed()
        rows = list_audits(model="gpt-4o'--")
        assert rows == []
        rows = list_audits(model="gpt-4o")
        assert len(rows) == 1
