import json
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Float, Boolean, DateTime, Text
from sqlalchemy.types import TypeDecorator, NVARCHAR
from sqlalchemy.orm import relationship
from database import Base


# ── JSON stored as NVARCHAR(MAX) (Azure SQL has no native JSON column) ──────
class JSONColumn(TypeDecorator):
    impl = NVARCHAR(length=None)   # NVARCHAR(MAX)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        try:
            return json.loads(value)
        except Exception:
            return value


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── clients ───────────────────────────────────────────────────────────────────
class Client(Base):
    __tablename__ = "clients"

    id             = Column(NVARCHAR(36), primary_key=True, default=_uuid)
    name           = Column(NVARCHAR(255), nullable=False)
    industry       = Column(NVARCHAR(50),  nullable=False)
    webhook_secret = Column(NVARCHAR(255), nullable=False)
    created_at     = Column(DateTime, default=_now, nullable=False)

    # Relationships — no DB-level FK constraints; foreign_keys tells SQLAlchemy which side is FK
    incidents = relationship(
        "Incident", back_populates="client",
        primaryjoin="Client.id == Incident.client_id",
        foreign_keys="[Incident.client_id]",
        cascade="all, delete-orphan",
    )
    notifications = relationship(
        "Notification", back_populates="client",
        primaryjoin="Client.id == Notification.client_id",
        foreign_keys="[Notification.client_id]",
        cascade="all, delete-orphan",
    )


# ── incidents ─────────────────────────────────────────────────────────────────
class Incident(Base):
    __tablename__ = "shdp_incidents"

    id              = Column(NVARCHAR(36), primary_key=True, default=_uuid)
    client_id       = Column(NVARCHAR(36), nullable=False)   # no DB FK — avoid old-table conflicts

    # ingest payload
    platform_hint   = Column(NVARCHAR(100))
    pipeline_name   = Column(NVARCHAR(255))
    run_id          = Column(NVARCHAR(255))
    error_message   = Column(Text)
    error_code      = Column(NVARCHAR(100))

    # lifecycle
    status          = Column(NVARCHAR(50), default="DETECTING", nullable=False)
    priority        = Column(NVARCHAR(10))
    summary         = Column(Text)

    # RCA
    rca_hypothesis      = Column(Text)
    rca_confidence      = Column(Float)
    rca_evidence        = Column(JSONColumn)
    rca_error_category  = Column(NVARCHAR(50))

    # Playbook
    fix_strategy        = Column(NVARCHAR(50))
    fix_steps           = Column(JSONColumn)
    fix_instructions    = Column(Text)
    dry_run_result      = Column(NVARCHAR(10))
    dry_run_reasoning   = Column(Text)

    # HIL
    engineer_email  = Column(NVARCHAR(255))
    decision        = Column(NVARCHAR(20))
    decided_at      = Column(DateTime)

    # agent log
    agent_log       = Column(JSONColumn)

    created_at      = Column(DateTime, default=_now, nullable=False)
    updated_at      = Column(DateTime, default=_now, onupdate=_now, nullable=False)

    client = relationship(
        "Client", back_populates="incidents",
        primaryjoin="Incident.client_id == Client.id",
        foreign_keys="[Incident.client_id]",
    )
    notifications = relationship(
        "Notification", back_populates="incident",
        primaryjoin="Incident.id == Notification.incident_id",
        foreign_keys="[Notification.incident_id]",
        cascade="all, delete-orphan",
    )


# ── notifications ─────────────────────────────────────────────────────────────
class Notification(Base):
    __tablename__ = "shdp_notifications"

    id          = Column(NVARCHAR(36), primary_key=True, default=_uuid)
    incident_id = Column(NVARCHAR(36), nullable=False)   # no DB FK
    client_id   = Column(NVARCHAR(36), nullable=False)   # no DB FK
    message     = Column(NVARCHAR(500), nullable=False)
    is_read     = Column(Boolean, default=False, nullable=False)
    created_at  = Column(DateTime, default=_now, nullable=False)

    incident = relationship(
        "Incident", back_populates="notifications",
        primaryjoin="Notification.incident_id == Incident.id",
        foreign_keys="[Notification.incident_id]",
    )
    client = relationship(
        "Client", back_populates="notifications",
        primaryjoin="Notification.client_id == Client.id",
        foreign_keys="[Notification.client_id]",
    )
