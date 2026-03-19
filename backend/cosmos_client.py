"""
cosmos_client.py  (Azure SQL implementation — Cosmos DB removed)
----------------------------------------------------------------
All incident documents are stored as JSON blobs in the `incidents` table
on the Target Azure SQL Database. No extra Azure service needed.

Run sql/incidents_schema.sql once against your Target DB before starting,
OR just start the app — _ensure_table() creates it automatically on first use.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import create_engine, text

from config import settings

# ---------------------------------------------------------------------------
# Lazy engine — reuses TARGET_DB_CONN; incidents sit alongside target sales table
# ---------------------------------------------------------------------------
_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(
            settings.TARGET_DB_CONN,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
        _ensure_table()
    return _engine


def _ensure_table() -> None:
    """Create the incidents table if it does not exist yet (idempotent)."""
    ddl = """
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_NAME = 'incidents'
    )
    BEGIN
        CREATE TABLE incidents (
            id          NVARCHAR(100) NOT NULL PRIMARY KEY,
            data        NVARCHAR(MAX) NOT NULL,
            created_at  DATETIME2     NOT NULL DEFAULT GETUTCDATE()
        );
        CREATE INDEX ix_incidents_created_at
            ON incidents (created_at DESC);
    END
    """
    with _engine.connect() as con:
        con.execute(text(ddl))
        con.commit()


# ---------------------------------------------------------------------------
# Public API  (identical signatures to the original Cosmos version)
# ---------------------------------------------------------------------------

def create_incident(data: dict[str, Any]) -> dict[str, Any]:
    """Insert a new incident row and return the document."""
    data.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    with _get_engine().connect() as con:
        con.execute(
            text(
                "INSERT INTO incidents (id, data, created_at) "
                "VALUES (:id, :data, :created_at)"
            ),
            {
                "id": data["id"],
                "data": json.dumps(data),
                "created_at": data["created_at"],
            },
        )
        con.commit()
    return data


def update_incident(incident_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    """
    Read the existing row, merge *patch* into the JSON, write it back.
    Returns the fully updated document.
    """
    existing = get_incident(incident_id)
    existing.update(patch)
    with _get_engine().connect() as con:
        con.execute(
            text("UPDATE incidents SET data = :data WHERE id = :id"),
            {"id": incident_id, "data": json.dumps(existing)},
        )
        con.commit()
    return existing


def get_incident(incident_id: str) -> dict[str, Any]:
    """Return a single incident document by ID. Raises KeyError if not found."""
    with _get_engine().connect() as con:
        row = con.execute(
            text("SELECT data FROM incidents WHERE id = :id"),
            {"id": incident_id},
        ).fetchone()
    if row is None:
        raise KeyError(f"Incident '{incident_id}' not found")
    return json.loads(row[0])


def list_incidents() -> list[dict[str, Any]]:
    """Return all incidents ordered newest-first."""
    with _get_engine().connect() as con:
        rows = con.execute(
            text("SELECT data FROM incidents ORDER BY created_at DESC")
        ).fetchall()
    return [json.loads(r[0]) for r in rows]
