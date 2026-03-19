import asyncio
import json
import logging
from collections import defaultdict
from fastapi import WebSocket

logger = logging.getLogger(__name__)

# Global event loop reference (set once uvicorn starts)
_loop: asyncio.AbstractEventLoop | None = None


def set_event_loop(loop: asyncio.AbstractEventLoop):
    global _loop
    _loop = loop


class ConnectionManager:
    """Thread-safe WebSocket manager.

    Background threads must call broadcast_sync() which schedules the
    coroutine on the event loop captured at startup.
    """

    def __init__(self):
        # incident_id → list[WebSocket]
        self._incident_conns: dict[str, list[WebSocket]] = defaultdict(list)
        # global notification subscribers
        self._notif_conns: list[WebSocket] = []

    # ── incident channels ─────────────────────────────────────────────────────
    async def connect_incident(self, ws: WebSocket, incident_id: str):
        await ws.accept()
        self._incident_conns[incident_id].append(ws)

    def disconnect_incident(self, ws: WebSocket, incident_id: str):
        self._incident_conns[incident_id] = [
            c for c in self._incident_conns[incident_id] if c is not ws
        ]

    async def broadcast_incident(self, incident_id: str, message: dict):
        payload = json.dumps(message)
        dead = []
        for ws in list(self._incident_conns.get(incident_id, [])):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect_incident(ws, incident_id)

    # ── notification channel ──────────────────────────────────────────────────
    async def connect_notifications(self, ws: WebSocket):
        await ws.accept()
        self._notif_conns.append(ws)

    def disconnect_notifications(self, ws: WebSocket):
        self._notif_conns = [c for c in self._notif_conns if c is not ws]

    async def broadcast_notification(self, message: dict):
        payload = json.dumps(message)
        dead = []
        for ws in list(self._notif_conns):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect_notifications(ws)

    # ── thread-safe helpers (called from background threads) ──────────────────
    def broadcast_incident_sync(self, incident_id: str, message: dict):
        if _loop is None:
            logger.warning("Event loop not set — cannot broadcast WS message")
            return
        asyncio.run_coroutine_threadsafe(
            self.broadcast_incident(incident_id, message), _loop
        )

    def broadcast_notification_sync(self, message: dict):
        if _loop is None:
            return
        asyncio.run_coroutine_threadsafe(
            self.broadcast_notification(message), _loop
        )


manager = ConnectionManager()
