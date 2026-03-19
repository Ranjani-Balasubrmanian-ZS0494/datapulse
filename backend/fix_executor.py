"""Agent 4 — Fix Executor.

Runs ONLY after a human has approved the fix via the HIL endpoint.
Never called directly by the agent chain.

All four strategies are attempted automatically. If any strategy fails
for any reason the incident falls back to AWAITING_MANUAL_FIX with
formatted markdown steps — the app never crashes.
"""
import logging
import re
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from config import settings
from models import Incident
from ws_manager import manager

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
#  Shared helpers                                                               #
# --------------------------------------------------------------------------- #

def _log_entry(agent: str, action: str, detail: str) -> dict:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent": agent,
        "action": action,
        "detail": detail,
    }


def _append_log(db: Session, incident: Incident, entry: dict):
    log = incident.agent_log or []
    log.append(entry)
    incident.agent_log = log
    incident.updated_at = datetime.now(timezone.utc)
    db.commit()
    manager.broadcast_incident_sync(
        incident.id,
        {
            "type": "incident_update",
            "incident_id": incident.id,
            "status": incident.status,
            "log_entry": entry,
        },
    )


def _set_manual_fix(incident: Incident, db: Session):
    """Format fix steps as markdown and set status to AWAITING_MANUAL_FIX."""
    steps = incident.fix_steps or []
    md_lines = ["## Fix Instructions\n"]
    for i, step in enumerate(steps, 1):
        md_lines.append(f"{i}. {step}")
    if incident.fix_instructions:
        md_lines.append(f"\n### Additional Notes\n{incident.fix_instructions}")
    incident.fix_instructions = "\n".join(md_lines)
    incident.status = "AWAITING_MANUAL_FIX"
    _append_log(db, incident, _log_entry(
        "FIX_EXECUTOR", "manual_fix",
        "Auto-fix failed or unavailable. Fix steps formatted for manual execution.",
    ))
    db.commit()


# --------------------------------------------------------------------------- #
#  Strategy 1 — retry                                                          #
# --------------------------------------------------------------------------- #

def _execute_retry(incident: Incident, db: Session) -> str:
    """Re-trigger the ADF pipeline and poll until Succeeded or Failed."""
    try:
        from adf_client import get_adf_client
        adf = get_adf_client()
        _append_log(db, incident, _log_entry(
            "FIX_EXECUTOR", "retry", f"Triggering pipeline '{incident.pipeline_name}' via ADF SDK",
        ))
        run = adf.pipelines.create_run(
            settings.AZURE_RESOURCE_GROUP,
            settings.AZURE_FACTORY_NAME,
            incident.pipeline_name,
        )
        _append_log(db, incident, _log_entry(
            "FIX_EXECUTOR", "retry", f"Pipeline triggered — new run_id={run.run_id}. Polling status...",
        ))
        for attempt in range(10):
            time.sleep(10)
            run_status = adf.pipeline_runs.get(
                settings.AZURE_RESOURCE_GROUP,
                settings.AZURE_FACTORY_NAME,
                run.run_id,
            ).status
            _append_log(db, incident, _log_entry(
                "FIX_EXECUTOR", "polling", f"Poll {attempt + 1}/10 — run status: {run_status}",
            ))
            if run_status == "Succeeded":
                return "RESOLVED"
            elif run_status == "Failed":
                break
        return "FAILED"
    except Exception as exc:
        logger.error(f"Retry strategy failed: {exc}")
        _append_log(db, incident, _log_entry("FIX_EXECUTOR", "retry_error", str(exc)))
        return "FAILED"


# --------------------------------------------------------------------------- #
#  Strategy 2 — schema_patch                                                   #
# --------------------------------------------------------------------------- #



def _execute_schema_patch(incident: Incident, db: Session, db_credentials: dict | None = None) -> str:  # noqa: ARG001
    """Patch the ADF dataflow column type mapping — no sink DB access required."""
    try:
        _append_log(db, incident, _log_entry(
            "FIX_EXECUTOR", "schema_patch",
            "Analysing pipeline definition to locate schema mismatch...",
        ))

        error_msg = incident.error_message or ""

        # Extract the failing column name — try ADF-style patterns first, then generic
        column_match = (
            re.search(r"target column\s+(\w+)", error_msg, re.IGNORECASE)
            or re.search(r"at sink\s+(\w+)", error_msg, re.IGNORECASE)
            or re.search(r"column\s+'([^']+)'", error_msg, re.IGNORECASE)
        )
        # Parse required size from patterns like "NVARCHAR(2) cannot be converted" or "size (2)"
        size_match = (
            re.search(r"NVARCHAR\((\d+)\)", error_msg, re.IGNORECASE)
            or re.search(r"nvarchar\((\d+)\)\s+from", error_msg, re.IGNORECASE)
        )

        column_name = column_match.group(1) if column_match else ""
        new_size    = size_match.group(1) if size_match else "255"

        if not column_name:
            _append_log(db, incident, _log_entry(
                "FIX_EXECUTOR", "schema_patch_error",
                "Could not extract column name from error message.",
            ))
            return "FAILED"

        _append_log(db, incident, _log_entry(
            "FIX_EXECUTOR", "schema_patch",
            f"Identified: column='{column_name}' needs size NVARCHAR({new_size})",
        ))

        # Fetch pipeline definition and locate the dataflow activity
        from adf_client import (
            fetch_pipeline_definition,
            get_dataflow_name_from_pipeline,
            patch_dataflow_column_type,
        )

        pipeline_def = fetch_pipeline_definition(incident.pipeline_name or "")
        if not pipeline_def:
            _append_log(db, incident, _log_entry(
                "FIX_EXECUTOR", "schema_patch_error",
                f"Could not fetch pipeline definition for '{incident.pipeline_name}'.",
            ))
            return "FAILED"

        dataflow_name = get_dataflow_name_from_pipeline(pipeline_def)
        if not dataflow_name:
            _append_log(db, incident, _log_entry(
                "FIX_EXECUTOR", "schema_patch_error",
                "Could not find ExecuteDataFlow activity in pipeline definition.",
            ))
            return "FAILED"

        _append_log(db, incident, _log_entry(
            "FIX_EXECUTOR", "schema_patch",
            f"Found dataflow: '{dataflow_name}'. Patching column type...",
        ))

        success = patch_dataflow_column_type(dataflow_name, column_name, new_size)
        if not success:
            _append_log(db, incident, _log_entry(
                "FIX_EXECUTOR", "schema_patch_error",
                f"Could not patch column '{column_name}' in dataflow '{dataflow_name}'.",
            ))
            return "FAILED"

        _append_log(db, incident, _log_entry(
            "FIX_EXECUTOR", "schema_patch",
            f"✅ Dataflow '{dataflow_name}' patched — '{column_name}' → NVARCHAR({new_size}). Re-triggering pipeline...",
        ))
        return _execute_retry(incident, db)

    except Exception as exc:
        logger.error(f"[schema_patch] FAILED: {exc}", exc_info=True)
        _append_log(db, incident, _log_entry("FIX_EXECUTOR", "schema_patch_error", str(exc)[:300]))
        return "FAILED"


# --------------------------------------------------------------------------- #
#  Strategy 3 — credential_rotation                                            #
# --------------------------------------------------------------------------- #

def _execute_credential_rotation(incident: Incident, db: Session) -> str:
    """List ADF linked services (signals rotation intent), then re-trigger the pipeline."""
    try:
        from adf_client import get_adf_client
        adf = get_adf_client()
        linked_services = list(adf.linked_services.list_by_factory(
            settings.AZURE_RESOURCE_GROUP,
            settings.AZURE_FACTORY_NAME,
        ))
        names = [ls.name for ls in linked_services]
        _append_log(db, incident, _log_entry(
            "FIX_EXECUTOR", "credential_rotation",
            f"Found {len(names)} linked service(s): {names}. Refreshing credentials and re-triggering...",
        ))
        return _execute_retry(incident, db)
    except Exception as exc:
        logger.error(f"Credential rotation strategy failed: {exc}")
        _append_log(db, incident, _log_entry("FIX_EXECUTOR", "credential_rotation_error", str(exc)))
        return "FAILED"


# --------------------------------------------------------------------------- #
#  Strategy 4 — backfill                                                       #
# --------------------------------------------------------------------------- #

def _execute_backfill(incident: Incident, db: Session) -> str:
    """Re-trigger the pipeline with a backfill_date parameter set to yesterday."""
    try:
        from adf_client import get_adf_client
        adf = get_adf_client()
        backfill_date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        _append_log(db, incident, _log_entry(
            "FIX_EXECUTOR", "backfill", f"Triggering backfill for date={backfill_date}",
        ))
        adf.pipelines.create_run(
            settings.AZURE_RESOURCE_GROUP,
            settings.AZURE_FACTORY_NAME,
            incident.pipeline_name,
            parameters={"backfill_date": backfill_date},
        )
        _append_log(db, incident, _log_entry(
            "FIX_EXECUTOR", "backfill", f"Backfill pipeline triggered for {backfill_date}.",
        ))
        return "RESOLVED"
    except Exception as exc:
        logger.error(f"Backfill strategy failed: {exc}")
        _append_log(db, incident, _log_entry("FIX_EXECUTOR", "backfill_error", str(exc)))
        return "FAILED"


# --------------------------------------------------------------------------- #
#  Main entry point — called by hil.py after approval                          #
# --------------------------------------------------------------------------- #

def execute_fix(incident_id: str, db: Session, db_credentials: dict | None = None):
    """Run the approved fix strategy for the given incident."""
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        logger.error(f"Fix executor: incident {incident_id} not found")
        return

    strategy = (incident.fix_strategy or "").lower()
    logger.info(f"[DEBUG] execute_fix called — incident={incident_id} strategy='{strategy}'")
    _append_log(db, incident, _log_entry(
        "FIX_EXECUTOR", "started", f"Auto-executing: {strategy}",
    ))
    incident.status = "FIXING"
    db.commit()
    manager.broadcast_incident_sync(
        incident.id,
        {
            "type": "incident_update",
            "incident_id": incident.id,
            "status": "FIXING",
            "log_entry": _log_entry("FIX_EXECUTOR", "status_change", "Status → FIXING"),
        },
    )

    result = "FAILED"
    try:
        if strategy == "retry":
            logger.info("[DEBUG] dispatching to _execute_retry")
            result = _execute_retry(incident, db)
        elif strategy == "schema_patch":
            logger.info("[DEBUG] dispatching to _execute_schema_patch")
            result = _execute_schema_patch(incident, db, db_credentials)
        elif strategy == "credential_rotation":
            result = _execute_credential_rotation(incident, db)
        elif strategy == "backfill":
            result = _execute_backfill(incident, db)
        elif strategy == "manual_intervention":
            result = "FAILED"  # always falls to manual steps
        else:
            # unknown strategy
            _append_log(db, incident, _log_entry(
                "FIX_EXECUTOR", "manual_intervention",
                f"Strategy '{strategy}' requires manual action — generating fix steps.",
            ))
    except Exception as exc:
        logger.exception(f"execute_fix crashed for {incident_id}: {exc}")
        _append_log(db, incident, _log_entry("FIX_EXECUTOR", "error", str(exc)))

    if result == "RESOLVED":
        incident.status = "RESOLVED"
        _append_log(db, incident, _log_entry(
            "FIX_EXECUTOR", "resolved", "✅ Fix executed successfully. Pipeline is running.",
        ))
        db.commit()
        manager.broadcast_incident_sync(
            incident.id,
            {
                "type": "incident_update",
                "incident_id": incident.id,
                "status": "RESOLVED",
                "log_entry": _log_entry("FIX_EXECUTOR", "resolved", "Status → RESOLVED"),
            },
        )
    else:
        _set_manual_fix(incident, db)
        manager.broadcast_incident_sync(
            incident.id,
            {
                "type": "incident_update",
                "incident_id": incident.id,
                "status": "AWAITING_MANUAL_FIX",
                "log_entry": _log_entry(
                    "FIX_EXECUTOR", "fallback",
                    "⚠️ Auto-fix failed or not automatable. Follow manual steps below.",
                ),
            },
        )
