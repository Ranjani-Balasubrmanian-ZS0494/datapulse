"""
pipeline_registry.py
--------------------
CRUD for registered pipelines.

The `pipelines` table lives on the same Target Azure SQL DB as `incidents`.
It is auto-created on first use (idempotent IF NOT EXISTS DDL).

Schema
------
pipelines
    id               NVARCHAR(100)  PK
    name             NVARCHAR(200)  NOT NULL
    tool             NVARCHAR(50)   NOT NULL  -- adf | databricks | synapse | custom
    source_db_conn   NVARCHAR(MAX)  nullable  -- client's source DB conn string
    target_db_conn   NVARCHAR(MAX)  nullable  -- client's target DB conn string
    notify_email     NVARCHAR(200)  nullable
    tool_credentials NVARCHAR(MAX)  NOT NULL  -- JSON blob (tool-specific auth fields)
    created_at       DATETIME2      DEFAULT GETUTCDATE()
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import create_engine, text

from config import settings

# ---------------------------------------------------------------------------
# Lazy engine — same TARGET_DB_CONN as cosmos_client
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
    """Create the pipelines table if it does not exist yet (idempotent)."""
    ddl = """
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_NAME = 'pipelines'
    )
    BEGIN
        CREATE TABLE pipelines (
            id               NVARCHAR(100)  NOT NULL PRIMARY KEY,
            name             NVARCHAR(200)  NOT NULL,
            tool             NVARCHAR(50)   NOT NULL,
            source_db_conn   NVARCHAR(MAX)  NULL,
            target_db_conn   NVARCHAR(MAX)  NULL,
            notify_email     NVARCHAR(200)  NULL,
            tool_credentials NVARCHAR(MAX)  NOT NULL DEFAULT '{}',
            created_at       DATETIME2      NOT NULL DEFAULT GETUTCDATE()
        );
    END
    """
    with _engine.connect() as con:
        con.execute(text(ddl))
        con.commit()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def register_pipeline(data: dict[str, Any]) -> dict[str, Any]:
    """Insert a new pipeline registration. Returns the saved document."""
    pipeline_id = data.get("id") or f"PIPE-{int(time.time() * 1000)}"
    created_at = datetime.now(timezone.utc).isoformat()

    record = {
        "id": pipeline_id,
        "name": data["name"],
        "tool": data["tool"],
        "source_db_conn": data.get("source_db_conn", ""),
        "target_db_conn": data.get("target_db_conn", ""),
        "notify_email": data.get("notify_email", ""),
        "tool_credentials": data.get("tool_credentials", {}),
        "created_at": created_at,
    }

    with _get_engine().connect() as con:
        con.execute(
            text(
                "INSERT INTO pipelines "
                "(id, name, tool, source_db_conn, target_db_conn, notify_email, tool_credentials, created_at) "
                "VALUES (:id, :name, :tool, :source_db_conn, :target_db_conn, :notify_email, :tool_credentials, :created_at)"
            ),
            {
                "id": record["id"],
                "name": record["name"],
                "tool": record["tool"],
                "source_db_conn": record["source_db_conn"],
                "target_db_conn": record["target_db_conn"],
                "notify_email": record["notify_email"],
                "tool_credentials": json.dumps(record["tool_credentials"]),
                "created_at": record["created_at"],
            },
        )
        con.commit()

    return record


def get_pipeline(pipeline_id: str) -> dict[str, Any]:
    """Return a single pipeline by ID. Raises KeyError if not found."""
    with _get_engine().connect() as con:
        row = con.execute(
            text(
                "SELECT id, name, tool, source_db_conn, target_db_conn, "
                "notify_email, tool_credentials, created_at "
                "FROM pipelines WHERE id = :id"
            ),
            {"id": pipeline_id},
        ).fetchone()

    if row is None:
        raise KeyError(f"Pipeline '{pipeline_id}' not found")

    return _row_to_dict(row)


def list_pipelines() -> list[dict[str, Any]]:
    """Return all registered pipelines ordered newest-first."""
    with _get_engine().connect() as con:
        rows = con.execute(
            text(
                "SELECT id, name, tool, source_db_conn, target_db_conn, "
                "notify_email, tool_credentials, created_at "
                "FROM pipelines ORDER BY created_at DESC"
            )
        ).fetchall()

    return [_row_to_dict(r) for r in rows]


def delete_pipeline(pipeline_id: str) -> None:
    """Delete a pipeline by ID."""
    with _get_engine().connect() as con:
        con.execute(
            text("DELETE FROM pipelines WHERE id = :id"),
            {"id": pipeline_id},
        )
        con.commit()


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _row_to_dict(row) -> dict[str, Any]:
    return {
        "id": row[0],
        "name": row[1],
        "tool": row[2],
        "source_db_conn": row[3] or "",
        "target_db_conn": row[4] or "",
        "notify_email": row[5] or "",
        "tool_credentials": json.loads(row[6]) if row[6] else {},
        "created_at": str(row[7]),
    }
