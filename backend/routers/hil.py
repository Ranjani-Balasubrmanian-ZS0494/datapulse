"""
Human-in-the-Loop (HIL) approval endpoint.

No fix ever executes without a human approving it here.
This rule has no exceptions.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import Incident, Notification
from ws_manager import manager

router = APIRouter(prefix="/hil", tags=["hil"])


class HILDecision(BaseModel):
    incident_id: str
    decision: str           # "approve" | "reject"
    engineer_email: str
    db_credentials: dict | None = None   # only for schema_patch; never stored


@router.post("/decision")
def submit_decision(
    body: HILDecision,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    incident = db.query(Incident).filter(Incident.id == body.incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    if incident.status != "AWAITING_HIL":
        raise HTTPException(
            status_code=400,
            detail=f"Incident is not awaiting approval (current status: {incident.status})",
        )

    if body.decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail='decision must be "approve" or "reject"')

    incident.engineer_email = body.engineer_email
    incident.decision       = body.decision
    incident.decided_at     = datetime.now(timezone.utc)

    if body.decision == "reject":
        incident.status = "REJECTED"
        db.commit()
        _notify(db, incident, f"Fix rejected by {body.engineer_email} for {incident.pipeline_name}")
        _broadcast(incident, "Incident rejected by engineer.")
        return {"status": "rejected", "incident_id": incident.id}

    # approve — run Fix Executor in background
    incident.status = "FIXING"
    db.commit()
    _notify(db, incident, f"Fix approved by {body.engineer_email} — executing for {incident.pipeline_name}")
    _broadcast(incident, f"Fix approved by {body.engineer_email}. Executing...")

    background_tasks.add_task(_run_fix_executor, body.incident_id, body.db_credentials)
    return {"status": "approved", "incident_id": incident.id}


def _notify(db: Session, incident: Incident, message: str):
    notif = Notification(
        incident_id=incident.id,
        client_id=incident.client_id,
        message=message,
    )
    db.add(notif)
    db.commit()
    unread = db.query(Notification).filter(Notification.is_read == False).count()
    manager.broadcast_notification_sync({"type": "notification", "unread_count": unread})


def _broadcast(incident: Incident, detail: str):
    from datetime import datetime, timezone
    manager.broadcast_incident_sync(
        incident.id,
        {
            "type": "incident_update",
            "incident_id": incident.id,
            "status": incident.status,
            "log_entry": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "agent": "HIL",
                "action": "decision",
                "detail": detail,
            },
        },
    )


def _run_fix_executor(incident_id: str, db_credentials: dict | None = None):
    """Runs in a background thread via BackgroundTasks."""
    from database import SessionLocal
    if SessionLocal is None:
        return
    db = SessionLocal()
    try:
        from fix_executor import execute_fix
        execute_fix(incident_id, db, db_credentials)
    finally:
        db.close()
