"""
pipeline.py
-----------
ETL pipeline logic.

run_pipeline()  — the scheduled job that moves data from source → target.
                  Uses the *original* broken query (SELECT total_price) to
                  simulate the column-rename failure that drives the demo.

apply_fix()     — called ONLY after a human approves the HIL decision.
                  Reruns the pipeline with the corrected alias query and
                  validates row counts before marking the incident RESOLVED.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import create_engine, text

from agents import manager_agent
from config import settings
from cosmos_client import get_incident, update_incident
from schema_diff import get_schema_diff

# ---------------------------------------------------------------------------
# Module-level state — read by main.py via the `pipeline` module reference
# ---------------------------------------------------------------------------
_last_run_result: dict | None = None
_last_run_time: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _source_engine():
    return create_engine(settings.SOURCE_DB_CONN)


def _target_engine():
    return create_engine(settings.TARGET_DB_CONN)


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def run_pipeline() -> dict[str, Any]:
    """
    Attempt the nightly ETL.

    The query deliberately uses `total_price` (the old column name) — this
    raises a SQL error because the source DB renamed it to `grand_total`.
    That error triggers the self-healing agent flow.
    """
    global _last_run_result, _last_run_time

    _last_run_time = datetime.now(timezone.utc).isoformat()

    try:
        # ── Step 1: Extract ────────────────────────────────────────────────
        # This SELECT fails: column 'total_price' no longer exists in source.
        with _source_engine().connect() as src:
            rows = src.execute(
                text("SELECT id, product_name, total_price, sale_date FROM sales")
            ).fetchall()

        # ── Step 2: Load ───────────────────────────────────────────────────
        with _target_engine().connect() as tgt:
            for row in rows:
                tgt.execute(
                    text(
                        "INSERT INTO sales (id, product_name, total_price, sale_date) "
                        "VALUES (:id, :product_name, :total_price, :sale_date)"
                    ),
                    {
                        "id": row[0],
                        "product_name": row[1],
                        "total_price": row[2],
                        "sale_date": row[3],
                    },
                )
            tgt.commit()

        result: dict[str, Any] = {
            "status": "success",
            "rows_transferred": len(rows),
        }

    except Exception as exc:
        # ── Step 3: Self-healing ───────────────────────────────────────────
        # Don't create a duplicate incident if one is already open for this pipeline
        from cosmos_client import list_incidents
        active = [
            i for i in list_incidents()
            if i.get("status") not in ("RESOLVED", "REJECTED", "FAILED")
        ]
        if active:
            existing_id = active[0]["id"]
            print(f"[pipeline] Active incident {existing_id} already exists — skipping new incident creation.")
            result = {
                "status": "failed",
                "incident_id": existing_id,
                "error": str(exc),
            }
            _last_run_result = result
            return result

        schema_diff: dict = {}
        try:
            schema_diff = get_schema_diff()
        except Exception as diff_exc:
            print(f"[pipeline] Warning: could not fetch schema diff: {diff_exc}")

        incident_id = manager_agent(exc, schema_diff)

        result = {
            "status": "failed",
            "incident_id": incident_id,
            "error": str(exc),
        }

    _last_run_result = result
    return result


def apply_fix(incident_id: str, pipeline_config: dict | None = None) -> dict[str, Any]:
    """
    Apply the schema_patch fix that was approved by the on-call engineer.

    Uses `grand_total AS total_price` in the SELECT so the INSERT into the
    target table (which still has the old column name) succeeds.

    If pipeline_config is provided and has tool credentials, the connector
    will also trigger a native pipeline rerun after the SQL fix.

    This function must ONLY be called after `hil.decision == 'approve'`.
    """
    incident = get_incident(incident_id)

    if incident.get("status") not in ("AWAITING_HIL",):
        return {
            "success": False,
            "error": (
                f"Incident {incident_id} is not awaiting HIL approval. "
                f"Current status: {incident.get('status')}"
            ),
        }

    # Mark as APPLYING so the UI shows progress
    update_incident(incident_id, {"status": "APPLYING"})

    try:
        # ── Extract with corrected alias ───────────────────────────────────
        with _source_engine().connect() as src:
            rows = src.execute(
                text(
                    "SELECT product_name, grand_total AS total_price, sale_date "
                    "FROM sales"
                )
            ).fetchall()

        source_count = len(rows)

        # ── Load into target ───────────────────────────────────────────────
        with _target_engine().connect() as tgt:
            # Clear first to avoid primary-key duplicates from the failed run
            tgt.execute(text("DELETE FROM sales"))

            for row in rows:
                tgt.execute(
                    text(
                        "INSERT INTO sales (product_name, total_price, sale_date) "
                        "VALUES (:product_name, :total_price, :sale_date)"
                    ),
                    {
                        "product_name": row[0],
                        "total_price": row[1],
                        "sale_date": row[2],
                    },
                )
            tgt.commit()

            target_count: int = tgt.execute(
                text("SELECT COUNT(*) FROM sales")
            ).fetchone()[0]

        # ── Validate ───────────────────────────────────────────────────────
        if target_count == source_count:
            # ── Optional: rerun via native pipeline connector ───────────────
            connector_result: dict | None = None
            if pipeline_config:
                try:
                    from connectors.factory import get_connector
                    tool = pipeline_config.get("tool", "")
                    creds = pipeline_config.get("tool_credentials", {})
                    if tool and creds:
                        connector = get_connector(tool, creds)
                        run_id = incident.get("run_id", "")
                        connector_result = connector.rerun_pipeline(pipeline_config, run_id)
                        print(f"[pipeline] Connector rerun result: {connector_result}")
                except Exception as conn_exc:
                    print(f"[pipeline] Warning: connector rerun failed: {conn_exc}")
                    connector_result = {"success": False, "detail": str(conn_exc)}

            rerun_msg = ""
            if connector_result:
                if connector_result.get("success"):
                    rerun_msg = f" Pipeline rerun triggered: {connector_result.get('detail', '')}."
                else:
                    rerun_msg = f" Pipeline rerun failed: {connector_result.get('detail', '')}."

            update_incident(
                incident_id,
                {
                    "status": "RESOLVED",
                    "resolved_at": datetime.now(timezone.utc).isoformat(),
                    "agent_log": incident.get("agent_log", [])
                    + [
                        {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "agent": "Manager",
                            "message": (
                                f"Fix applied successfully. "
                                f"{target_count} rows transferred. "
                                f"Row-count validation PASSED. Incident resolved."
                                f"{rerun_msg}"
                            ),
                        }
                    ],
                },
            )
            return {
                "success": True,
                "rows_transferred": target_count,
                "validation": "PASS",
                "incident_id": incident_id,
                "connector_rerun": connector_result,
            }

        # Mismatch — mark as FAILED
        mismatch_msg = (
            f"Row-count mismatch: source={source_count}, target={target_count}"
        )
        update_incident(
            incident_id,
            {
                "status": "FAILED",
                "agent_log": incident.get("agent_log", [])
                + [
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "agent": "Manager",
                        "message": f"Validation FAILED: {mismatch_msg}",
                    }
                ],
            },
        )
        return {
            "success": False,
            "error": mismatch_msg,
            "incident_id": incident_id,
        }

    except Exception as exc:
        err_msg = str(exc)
        update_incident(
            incident_id,
            {
                "status": "FAILED",
                "agent_log": incident.get("agent_log", [])
                + [
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "agent": "Manager",
                        "message": f"Fix application failed with exception: {err_msg}",
                    }
                ],
            },
        )
        return {"success": False, "error": err_msg, "incident_id": incident_id}
