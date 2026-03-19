from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from database import get_db
from models import Incident, Notification

router = APIRouter(prefix="/incidents", tags=["incidents"])


def _serialize(inc: Incident) -> dict:
    return {
        "id":                 inc.id,
        "client_id":          inc.client_id,
        "client_name":        inc.client.name if inc.client else None,
        "platform_hint":      inc.platform_hint,
        "pipeline_name":      inc.pipeline_name,
        "run_id":             inc.run_id,
        "status":             inc.status,
        "priority":           inc.priority,
        "summary":            inc.summary,
        "error_message":      inc.error_message,
        "error_code":         inc.error_code,
        "rca_hypothesis":     inc.rca_hypothesis,
        "rca_confidence":     inc.rca_confidence,
        "rca_evidence":       inc.rca_evidence or [],
        "rca_error_category": inc.rca_error_category,
        "fix_strategy":       inc.fix_strategy,
        "fix_steps":          inc.fix_steps or [],
        "fix_instructions":   inc.fix_instructions,
        "dry_run_result":     inc.dry_run_result,
        "dry_run_reasoning":  inc.dry_run_reasoning,
        "engineer_email":     inc.engineer_email,
        "decision":           inc.decision,
        "decided_at":         inc.decided_at.isoformat() if inc.decided_at else None,
        "agent_log":          inc.agent_log or [],
        "created_at":         inc.created_at.isoformat(),
        "updated_at":         inc.updated_at.isoformat(),
    }


@router.get("")
def list_incidents(
    client_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Incident)
    if client_id:
        q = q.filter(Incident.client_id == client_id)
    if status:
        q = q.filter(Incident.status == status)
    incidents = q.order_by(Incident.created_at.desc()).all()
    return [_serialize(i) for i in incidents]


@router.get("/{incident_id}")
def get_incident(incident_id: str, db: Session = Depends(get_db)):
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    return _serialize(inc)


@router.delete("/{incident_id}", status_code=204)
def delete_incident(incident_id: str, db: Session = Depends(get_db)):
    db.query(Notification).filter(Notification.incident_id == incident_id).delete()
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    db.delete(incident)
    db.commit()
    return Response(status_code=204)
