import secrets
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import Client

router = APIRouter(prefix="/clients", tags=["clients"])


class ClientCreate(BaseModel):
    name: str
    industry: str  # NBFC | NGO | ecommerce | other


class ClientOut(BaseModel):
    id: str
    name: str
    industry: str
    webhook_secret: str
    webhook_url: str
    created_at: str

    model_config = {"from_attributes": True}


def _to_out(c: Client) -> ClientOut:
    return ClientOut(
        id=c.id,
        name=c.name,
        industry=c.industry,
        webhook_secret=c.webhook_secret,
        webhook_url=f"/ingest/{c.id}",
        created_at=c.created_at.isoformat(),
    )


@router.post("", response_model=ClientOut, status_code=201)
def create_client(body: ClientCreate, db: Session = Depends(get_db)):
    client = Client(
        id=str(uuid.uuid4()),
        name=body.name,
        industry=body.industry,
        webhook_secret=secrets.token_hex(32),
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    return _to_out(client)


@router.get("", response_model=list[ClientOut])
def list_clients(db: Session = Depends(get_db)):
    clients = db.query(Client).order_by(Client.created_at.desc()).all()
    return [_to_out(c) for c in clients]


@router.delete("/{client_id}", status_code=204)
def delete_client(client_id: str, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    db.delete(client)
    db.commit()
