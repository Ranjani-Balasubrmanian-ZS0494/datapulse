"""
Four AI agents that run in sequence after a webhook is received.

Every agent is wrapped in try/except so one failure never crashes the chain.
All GPT-4o calls use temperature=0.2 and response_format=json_object.
"""
import json
import logging
from datetime import datetime, timezone

from openai import OpenAI
from sqlalchemy.orm import Session

from config import settings
from models import Client, Incident, Notification
from ws_manager import manager

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
#  Shared helpers                                                               #
# --------------------------------------------------------------------------- #

def _gpt(client: OpenAI, system: str, user: str) -> dict:
    resp = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    )
    return json.loads(resp.choices[0].message.content)


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


def _create_notification(db: Session, incident: Incident, message: str):
    notif = Notification(
        incident_id=incident.id,
        client_id=incident.client_id,
        message=message,
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    unread = db.query(Notification).filter(Notification.is_read == False).count()
    manager.broadcast_notification_sync({"type": "notification", "unread_count": unread})
    return notif


# --------------------------------------------------------------------------- #
#  Agent 1 — Signal Fusion                                                      #
# --------------------------------------------------------------------------- #

def agent_signal_fusion(payload: dict, client_id: str, db: Session):
    """Deduplicates incidents and assigns priority P0-P3."""
    try:
        pipeline_name = payload.get("pipeline_name") or "unknown"

        active_statuses = [
            "DETECTING", "RCA_IN_PROGRESS", "PLAYBOOK_IN_PROGRESS", "AWAITING_HIL"
        ]
        existing = (
            db.query(Incident)
            .filter(
                Incident.client_id == client_id,
                Incident.pipeline_name == pipeline_name,
                Incident.status.in_(active_statuses),
            )
            .first()
        )
        if existing:
            logger.info(f"Signal Fusion: dedup — returning existing incident {existing.id}")
            return existing

        oai = OpenAI(api_key=settings.OPENAI_API_KEY)
        result = _gpt(
            oai,
            system=(
                "You are a pipeline incident triage system. "
                "Given failure details, assign a priority (P0=critical, P1=high, P2=medium, P3=low) "
                "and write a one-line summary. "
                'Return JSON: {"priority": "P0|P1|P2|P3", "summary": "..."}'
            ),
            user=json.dumps({
                "pipeline_name": pipeline_name,
                "error_message": payload.get("error_message"),
                "error_code":    payload.get("error_code"),
                "platform_hint": payload.get("platform_hint"),
            }),
        )

        incident = Incident(
            client_id     = client_id,
            platform_hint = payload.get("platform_hint"),
            pipeline_name = pipeline_name,
            run_id        = payload.get("run_id"),
            error_message = payload.get("error_message"),
            error_code    = payload.get("error_code"),
            status        = "DETECTING",
            priority      = result.get("priority", "P2"),
            summary       = result.get("summary", ""),
            agent_log     = [],
        )
        db.add(incident)
        db.commit()
        db.refresh(incident)

        entry = _log_entry("SIGNAL_FUSION", "created",
                           f"Incident created — {incident.priority}: {incident.summary}")
        _append_log(db, incident, entry)
        _create_notification(db, incident,
                             f"[{incident.priority}] New incident: {pipeline_name} — {incident.summary}")
        return incident

    except Exception as exc:
        logger.exception(f"Agent 1 (SignalFusion) failed: {exc}")
        try:
            incident = Incident(
                client_id     = client_id,
                pipeline_name = payload.get("pipeline_name", "unknown"),
                error_message = payload.get("error_message"),
                status        = "DETECTING",
                priority      = "P2",
                summary       = "Signal Fusion failed — manual triage required",
                agent_log     = [_log_entry("SIGNAL_FUSION", "error", str(exc))],
            )
            db.add(incident)
            db.commit()
            db.refresh(incident)
            return incident
        except Exception:
            return None


# --------------------------------------------------------------------------- #
#  Agent 2 — Root Cause Analysis                                                #
# --------------------------------------------------------------------------- #

def agent_rca(incident: Incident, db: Session, payload: dict | None = None) -> Incident:
    """Performs root cause analysis on the incident."""
    try:
        has_adf = bool(payload and payload.get("adf_failed_activities"))
        detail_msg = (
            "Analysing ADF activity run logs and error details."
            if has_adf else
            "Analysing error logs and pipeline definition."
        )
        entry = _log_entry("RCA", "started", detail_msg)
        _append_log(db, incident, entry)

        oai = OpenAI(api_key=settings.OPENAI_API_KEY)

        # Build RCA input — include ADF-enriched fields when available
        rca_input: dict = {
            "pipeline_name": incident.pipeline_name,
            "error_message": incident.error_message,
            "error_code":    incident.error_code,
            "platform_hint": incident.platform_hint,
        }
        if payload:
            if payload.get("log_snippet"):
                rca_input["activity_run_logs"] = payload["log_snippet"]
            if payload.get("adf_failed_activities"):
                rca_input["adf_failed_activities"] = payload["adf_failed_activities"]
            if payload.get("adf_run_status"):
                rca_input["adf_run_status"] = payload["adf_run_status"]

        result = _gpt(
            oai,
            system=(
                "You are a data pipeline reliability engineer. "
                "Analyse the pipeline failure and return a root cause analysis. "
                "If ADF activity-level run logs or failed_activities details are provided, "
                "use them to produce a high-confidence, specific diagnosis. "
                "Return JSON with keys: "
                "hypothesis (string), confidence (float 0.0-1.0), "
                "evidence (list of strings), "
                "error_category (one of: connection_failure, schema_mismatch, timeout, "
                "permission_error, data_quality, unknown)"
            ),
            user=json.dumps(rca_input),
        )

        incident.rca_hypothesis     = result.get("hypothesis", "")
        incident.rca_confidence     = float(result.get("confidence", 0.5))
        incident.rca_evidence       = result.get("evidence", [])
        incident.rca_error_category = result.get("error_category", "unknown")
        incident.status             = "RCA_IN_PROGRESS"
        incident.updated_at         = datetime.now(timezone.utc)
        db.commit()

        confidence = incident.rca_confidence
        low_conf_tag = " [LOW CONFIDENCE — flagged for manual review]" if confidence < 0.6 else ""
        detail = (f"Hypothesis: {incident.rca_hypothesis} "
                  f"(confidence={confidence:.2f}){low_conf_tag}")
        _append_log(db, incident, _log_entry("RCA", "completed", detail))
        _create_notification(db, incident,
                             f"RCA complete for {incident.pipeline_name}: "
                             f"{incident.rca_error_category}{low_conf_tag}")
        return incident

    except Exception as exc:
        logger.exception(f"Agent 2 (RCA) failed for incident {incident.id}: {exc}")
        incident.rca_hypothesis     = "RCA agent received insufficient error context from the webhook — ADF run logs were not available. Manual investigation required."
        incident.rca_confidence     = 0.0
        incident.rca_evidence       = []
        incident.rca_error_category = "unknown"
        incident.status             = "RCA_IN_PROGRESS"
        _append_log(db, incident, _log_entry("RCA", "error", str(exc)))
        db.commit()
        return incident


# --------------------------------------------------------------------------- #
#  Agent 3 — Playbook Selection                                                 #
# --------------------------------------------------------------------------- #

def agent_playbook(incident: Incident, db: Session) -> Incident:
    """Selects a fix strategy and generates step-by-step instructions."""
    try:
        entry = _log_entry("PLAYBOOK", "started", "Selecting fix strategy.")
        _append_log(db, incident, entry)
        incident.status = "PLAYBOOK_IN_PROGRESS"
        db.commit()

        oai = OpenAI(api_key=settings.OPENAI_API_KEY)
        result = _gpt(
            oai,
            system=(
                "You are a data pipeline operations expert. "
                "Given a root cause analysis, select the best fix strategy and generate a remediation plan. "
                "fix_strategy must be one of: retry, schema_patch, credential_rotation, backfill, manual_intervention. "
                "dry_run_result must be PASS or FAIL. "
                "Return JSON with keys: fix_strategy, fix_steps (ordered list of strings), "
                "fix_instructions (markdown string), dry_run_result, dry_run_reasoning"
            ),
            user=json.dumps({
                "pipeline_name":      incident.pipeline_name,
                "rca_hypothesis":     incident.rca_hypothesis,
                "rca_error_category": incident.rca_error_category,
                "rca_confidence":     incident.rca_confidence,
                "error_message":      incident.error_message,
            }),
        )

        incident.fix_strategy      = result.get("fix_strategy", "manual_intervention")
        incident.fix_steps         = result.get("fix_steps", [])
        incident.fix_instructions  = result.get("fix_instructions", "")
        incident.dry_run_result    = result.get("dry_run_result", "FAIL")
        incident.dry_run_reasoning = result.get("dry_run_reasoning", "")

        # HARD STOP — set AWAITING_HIL, nothing executes beyond this point
        incident.status     = "AWAITING_HIL"
        incident.updated_at = datetime.now(timezone.utc)
        db.commit()

        detail = (f"Strategy: {incident.fix_strategy} | "
                  f"Dry run: {incident.dry_run_result} | "
                  f"Awaiting human approval.")
        _append_log(db, incident, _log_entry("PLAYBOOK", "completed", detail))
        _create_notification(db, incident,
                             f"Fix ready for {incident.pipeline_name} — "
                             f"strategy={incident.fix_strategy}. Awaiting your approval.")
        return incident

    except Exception as exc:
        logger.exception(f"Agent 3 (Playbook) failed for incident {incident.id}: {exc}")
        incident.fix_strategy  = "manual_intervention"
        incident.fix_steps     = ["Playbook agent failed — manual investigation required"]
        incident.dry_run_result = "FAIL"
        incident.status        = "AWAITING_HIL"
        _append_log(db, incident, _log_entry("PLAYBOOK", "error", str(exc)))
        db.commit()
        return incident
