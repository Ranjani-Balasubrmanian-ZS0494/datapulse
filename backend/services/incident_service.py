"""
incident_service.py
--------------------
Spawns the agent healing chain in a background thread.

trigger_incident() is called from the ingest router (via BackgroundTasks)
and runs Agents 1 → 2 → 3 in sequence.  Every agent is already wrapped
in try/except inside agents.py, so failures are logged but never propagate.
"""
import logging

logger = logging.getLogger(__name__)


def trigger_incident(client_id: str, payload: dict):
    """Entry point called from the ingest router background task."""
    from database import SessionLocal
    if SessionLocal is None:
        logger.warning("Database not initialised — cannot trigger incident")
        return

    db = SessionLocal()
    try:
        _run_chain(client_id, payload, db)
    except Exception as exc:
        logger.exception(f"Unhandled error in healing chain: {exc}")
    finally:
        db.close()


def _run_chain(client_id: str, payload: dict, db):
    from agents import agent_signal_fusion, agent_rca, agent_playbook

    # Agent 1 — Signal Fusion (create or dedup incident)
    incident = agent_signal_fusion(payload, client_id, db)
    if incident is None:
        logger.error("Signal Fusion returned None — aborting chain")
        return

    # Agent 2 — Root Cause Analysis (pass payload so ADF-enriched fields are available)
    incident = agent_rca(incident, db, payload)

    # Agent 3 — Playbook Selection (ends at AWAITING_HIL — hard stop)
    incident = agent_playbook(incident, db)

    logger.info(f"Agent chain complete for incident {incident.id} — status={incident.status}")
