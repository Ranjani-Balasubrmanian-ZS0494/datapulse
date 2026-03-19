from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Notification

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _serialize(n: Notification) -> dict:
    return {
        "id":           n.id,
        "incident_id":  n.incident_id,
        "client_id":    n.client_id,
        "message":      n.message,
        "is_read":      n.is_read,
        "created_at":   n.created_at.isoformat(),
    }


@router.get("")
def list_notifications(db: Session = Depends(get_db)):
    notifs = (
        db.query(Notification)
        .filter(Notification.is_read == False)
        .order_by(Notification.created_at.desc())
        .limit(20)
        .all()
    )
    return [_serialize(n) for n in notifs]


@router.post("/{notification_id}/read", status_code=200)
def mark_read(notification_id: str, db: Session = Depends(get_db)):
    notif = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
    notif.is_read = True
    db.commit()
    return {"status": "ok"}
