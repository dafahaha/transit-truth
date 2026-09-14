"""Database initialization and operations."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import DB_PATH, DATA_DIR
from .models import AuditResult, RankingEntry


def get_db() -> sqlite3.Connection:
    """Get a database connection."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database tables."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audits (
            audit_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            model TEXT NOT NULL,
            base_url TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            overall_score REAL DEFAULT 0,
            trust_level TEXT DEFAULT 'unknown',
            result_json TEXT,
            error TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rankings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            relay_name TEXT NOT NULL,
            base_url TEXT NOT NULL,
            model TEXT NOT NULL,
            avg_trust_score REAL DEFAULT 0,
            audit_count INTEGER DEFAULT 0,
            last_audited TEXT,
            token_inflation_avg REAL DEFAULT 0,
            model_authenticity_rate REAL DEFAULT 0,
            avg_latency_ms REAL DEFAULT 0,
            uptime_rate REAL DEFAULT 0,
            notes TEXT DEFAULT '',
            UNIQUE(base_url, model)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_audits_model ON audits(model)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_audits_base_url ON audits(base_url)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_rankings_score ON rankings(avg_trust_score DESC)
    """)

    # Load initial ranking data if table is empty
    cursor.execute("SELECT COUNT(*) as cnt FROM rankings")
    if cursor.fetchone()["cnt"] == 0:
        _load_initial_rankings(cursor)

    conn.commit()
    conn.close()


def _load_initial_rankings(cursor):
    """Load initial ranking data from JSON file into database."""
    import json
    from pathlib import Path

    json_path = Path(__file__).parent.parent.parent / "data" / "initial_ranking.json"
    if not json_path.exists():
        return

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        entries = data.get("entries", [])
        for entry in entries:
            notes_parts = []
            if entry.get("contributor"):
                notes_parts.append(f"Contributor: {entry['contributor']}")
            if entry.get("status"):
                notes_parts.append(f"Status: {entry['status']}")
            if entry.get("notes"):
                notes_parts.append(entry["notes"])

            cursor.execute("""
                INSERT OR IGNORE INTO rankings
                (relay_name, base_url, model, avg_trust_score, audit_count,
                 last_audited, token_inflation_avg, avg_latency_ms, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry.get("relay", ""),
                entry.get("base_url", ""),
                entry.get("model", ""),
                entry.get("overall_score", 0),
                1,
                entry.get("timestamp", ""),
                entry.get("token_inflation_pct", 0),
                entry.get("avg_latency_ms", 0),
                " | ".join(notes_parts)[:500],
            ))
    except Exception as e:
        print(f"Warning: Failed to load initial rankings: {e}")


def save_audit(result: AuditResult):
    """Save an audit result to the database."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO audits
        (audit_id, status, model, base_url, started_at, completed_at,
         overall_score, trust_level, result_json, error)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        result.audit_id,
        result.status.value,
        result.model,
        result.base_url,
        result.started_at.isoformat(),
        result.completed_at.isoformat() if result.completed_at else None,
        result.overall_score,
        result.trust_level,
        result.model_dump_json(),
        result.error,
    ))

    conn.commit()
    conn.close()


def get_audit(audit_id: str) -> Optional[dict]:
    """Get an audit result by ID."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM audits WHERE audit_id = ?", (audit_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def list_audits(limit: int = 50, model: str = None, base_url: str = None) -> list[dict]:
    """List audit results."""
    conn = get_db()
    cursor = conn.cursor()
    query = "SELECT audit_id, status, model, base_url, started_at, completed_at, overall_score, trust_level FROM audits WHERE 1=1"
    params = []
    if model:
        query += " AND model = ?"
        params.append(model)
    if base_url:
        query += " AND base_url = ?"
        params.append(base_url)
    query += " ORDER BY started_at DESC LIMIT ?"
    params.append(limit)
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def upsert_ranking(entry: RankingEntry):
    """Insert or update a ranking entry."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO rankings
        (relay_name, base_url, model, avg_trust_score, audit_count, last_audited,
         token_inflation_avg, model_authenticity_rate, avg_latency_ms, uptime_rate, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(base_url, model) DO UPDATE SET
            avg_trust_score = excluded.avg_trust_score,
            audit_count = excluded.audit_count,
            last_audited = excluded.last_audited,
            token_inflation_avg = excluded.token_inflation_avg,
            model_authenticity_rate = excluded.model_authenticity_rate,
            avg_latency_ms = excluded.avg_latency_ms,
            uptime_rate = excluded.uptime_rate,
            notes = excluded.notes
    """, (
        entry.relay_name,
        entry.base_url,
        entry.model,
        entry.avg_trust_score,
        entry.audit_count,
        entry.last_audited.isoformat(),
        entry.token_inflation_avg,
        entry.model_authenticity_rate,
        entry.avg_latency_ms,
        entry.uptime_rate,
        entry.notes,
    ))

    conn.commit()
    conn.close()


def get_rankings(model: str = None, limit: int = 100) -> list[dict]:
    """Get ranking entries, optionally filtered by model."""
    conn = get_db()
    cursor = conn.cursor()
    query = "SELECT * FROM rankings"
    params = []
    if model:
        query += " WHERE model = ?"
        params.append(model)
    query += " ORDER BY avg_trust_score DESC LIMIT ?"
    params.append(limit)
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]
