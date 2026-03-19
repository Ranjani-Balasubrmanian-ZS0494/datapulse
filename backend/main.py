"""
main.py
-------
FastAPI application entry point.
Registers all routers, CORS middleware, WebSocket endpoints, and
initialises the database on startup.
"""
import asyncio
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import init_db
from ws_manager import manager, set_event_loop
from routers import clients, incidents, ingest, hil, notifications

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="SHDP — Self-Healing Data Pipeline",
    version="1.0.0",
    description="AI-powered pipeline failure diagnosis with mandatory human-in-the-loop approval.",
)

# ── CORS ─────────────────────────────────────────────────────────────────────
_cors_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
if settings.DASHBOARD_URL and settings.DASHBOARD_URL not in _cors_origins:
    _cors_origins.append(settings.DASHBOARD_URL)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(clients.router)
app.include_router(incidents.router)
app.include_router(ingest.router)
app.include_router(hil.router)
app.include_router(notifications.router)


# ── Startup ───────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    set_event_loop(asyncio.get_event_loop())
    init_db()
    if settings.is_degraded:
        logger.warning(
            "SHDP starting in DEGRADED MODE — one or more required config values are missing. "
            "Check OPENAI_API_KEY and AZURE_SQL_CONN in your .env file."
        )
    else:
        logger.info("SHDP started successfully.")
    logger.info(
        f"ADF config — client_id={bool(settings.AZURE_CLIENT_ID)} "
        f"secret={bool(settings.AZURE_CLIENT_SECRET)} "
        f"tenant={bool(settings.AZURE_TENANT_ID)}"
    )


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {
        "status": "ok" if not settings.is_degraded else "degraded",
        "degraded": settings.is_degraded,
    }


# ── WebSocket: incident live updates ─────────────────────────────────────────
@app.websocket("/ws/incidents/{incident_id}")
async def ws_incident(websocket: WebSocket, incident_id: str):
    await manager.connect_incident(websocket, incident_id)
    try:
        while True:
            # Keep connection alive; we only push from the server side
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_incident(websocket, incident_id)


# ── WebSocket: global notification bell ──────────────────────────────────────
@app.websocket("/ws/notifications")
async def ws_notifications(websocket: WebSocket):
    await manager.connect_notifications(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_notifications(websocket)
