# SHDP — Self-Healing Data Pipeline: Architecture

---

## Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-03-10 | Multi-client webhook model, universal ingest, 4-agent healing loop, HIL approval gate, in-app notifications, real-time WebSocket agent log, React dashboard |

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Client Pipeline Platforms                        │
│                                                                         │
│  Azure Data Factory    Apache Airflow    dbt    AWS Glue    Any tool    │
│       │                     │              │       │             │      │
│       └─────────────────────┴──────────────┴───────┴─────────────┘     │
│                             │  HTTP POST on pipeline failure            │
└─────────────────────────────┼───────────────────────────────────────────┘
                              │
                    Authorization: Bearer {webhook_secret}
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       Backend  (FastAPI :8000)                          │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────┐      │
│  │  Ingestion Layer                                              │      │
│  │  POST /ingest/{client_id}                                     │      │
│  │  ├── Lookup client by id                                      │      │
│  │  ├── Validate Bearer token against webhook_secret             │      │
│  │  ├── Accept any JSON payload (no fixed schema)                │      │
│  │  ├── Best-effort field extraction                             │      │
│  │  └── Return 202 immediately → BackgroundTask                  │      │
│  └──────────────────────────┬────────────────────────────────────┘      │
│                             │  background thread (IncidentService)      │
│                             ▼                                           │
│  ┌───────────────────────────────────────────────────────────────┐      │
│  │  4-Agent Healing Loop  (agents.py + fix_executor.py)          │      │
│  │                                                               │      │
│  │  Agent 1 — SignalFusion                                       │      │
│  │    Dedup check → GPT-4o priority P0–P3 + summary              │      │
│  │    Creates incident  →  status = DETECTING                    │      │
│  │           │                                                   │      │
│  │  Agent 2 — RCA                                                │      │
│  │    GPT-4o: hypothesis, confidence, evidence[], error_category │      │
│  │    Updates incident  →  status = RCA_IN_PROGRESS              │      │
│  │           │                                                   │      │
│  │  Agent 3 — Playbook                                           │      │
│  │    GPT-4o: fix_strategy, fix_steps[], dry_run PASS/FAIL       │      │
│  │    Updates incident  →  status = AWAITING_HIL                 │      │
│  │    ── HARD STOP. No fix executes without engineer approval ──  │      │
│  │           │  (after HIL approve)                              │      │
│  │  Agent 4 — Fix Executor                                       │      │
│  │    retry strategy  → POST to trigger_endpoint if available    │      │
│  │    other strategy  → markdown instructions                    │      │
│  │    →  status = RESOLVED | FIX_FAILED | AWAITING_MANUAL_FIX   │      │
│  │                                                               │      │
│  │  Each agent broadcasts WS event + creates notification        │      │
│  └──────────────────────────┬────────────────────────────────────┘      │
│                             │                                           │
│  ┌──────────────────────────▼────────────────────────────────────┐      │
│  │  Azure SQL  (via SQLAlchemy + pyodbc)                         │      │
│  │  clients · shdp_incidents · shdp_notifications                │      │
│  └──────────────────────────┬────────────────────────────────────┘      │
│                             │  REST + WebSocket                         │
└─────────────────────────────┼───────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   Frontend  (React 18 + Tailwind :5173)                 │
│                                                                         │
│  ClientList   IncidentList   IncidentDetail   AgentLog (WS live)        │
│  HILPanel ──► POST /hil/decision ──► Fix Executor                       │
│  NotificationBell ──► WS /ws/notifications ──► unread badge             │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Agent Flow

```
Webhook POST /ingest/{client_id}
         │  (any JSON payload)
         ▼
IncidentService.trigger_incident()  →  background thread
         │
         ▼
Agent 1 — SignalFusion
  • Dedup: active incident for same client_id + pipeline_name? → skip
  • GPT-4o: assign priority P0–P3 and one-line summary
  • Creates incident  →  status = DETECTING
  • broadcast_sync()  →  WebSocket clients notified
  • Creates in-app notification
         │
         ▼
Agent 2 — RCA
  • GPT-4o input: error_message, error_code, pipeline_name, log snippet
  • GPT-4o output: { hypothesis, confidence (0–1), evidence[], error_category }
  • confidence < 0.6  →  LOW_CONFIDENCE tag
  • Updates incident  →  status = RCA_IN_PROGRESS
  • broadcast_sync()  + notification
         │
         ▼
Agent 3 — Playbook
  • GPT-4o input: full RCA result
  • GPT-4o output: { fix_strategy, fix_steps[], fix_instructions,
                     dry_run_result: PASS|FAIL, dry_run_reasoning }
  • Updates incident  →  status = AWAITING_HIL
  • broadcast_sync()  + notification
  • ══ HARD STOP — engineer must approve before anything executes ══
         │
         │  POST /hil/decision  { decision: "approve", engineer_email }
         ▼
Agent 4 — Fix Executor
  • retry strategy + trigger_endpoint configured
      →  POST to re-trigger pipeline
      →  status = RESOLVED
  • any other strategy (or retry without endpoint)
      →  format fix_steps as markdown instructions
      →  status = AWAITING_MANUAL_FIX
  • on any exception  →  status = FIX_FAILED
```

---

## Incident Status Lifecycle

```
DETECTING
  └─► RCA_IN_PROGRESS
        └─► PLAYBOOK_IN_PROGRESS
              └─► AWAITING_HIL
                    ├─► (approve) FIXING ──► RESOLVED
                    │                  └──► FIX_FAILED
                    ├─► (approve, no endpoint) AWAITING_MANUAL_FIX
                    └─► (reject) REJECTED
```

---

## Multi-Client Design

Each client (company / team) gets an isolated identity:

```
clients table
  id               UUID — part of the webhook URL
  name             display name
  industry         NBFC | NGO | ecommerce | other
  webhook_secret   64-char hex token — validated on every ingest call
  created_at

Webhook URL format:  POST /ingest/{client_id}
Auth header:         Authorization: Bearer {webhook_secret}
```

A single SHDP instance manages pipelines for multiple clients simultaneously. Each incident is scoped to exactly one `client_id`. Clients can only see their own incidents (filtered by `client_id` in the dashboard).

---

## Universal Ingest

The `/ingest/{client_id}` endpoint accepts **any JSON payload** — no fixed schema required. Best-effort extraction tries common field names:

| Extracted field | Tried keys in payload |
|---|---|
| `pipeline_name` | `pipeline_name`, `pipeline`, `name`, `dag_id`, `job_name` |
| `error_message` | `error_message`, `error`, `message`, `exception`, `failure_reason` |
| `error_code` | `error_code`, `code`, `errorCode` |
| `run_id` | `run_id`, `runId`, `execution_id`, `run_url` |
| `platform_hint` | `platform`, `source`, `tool` |
| `log` | `log`, `logs`, `log_url`, `details` |

If a field is not found it is stored as `null` — the agents work with whatever is available.

---

## ADF Integration

### Option A — Web Activity on failure path (recommended)

Add a Web Activity connected on the **failure** output of any ADF activity:

```
Activity (e.g. Copy Data)
  └─[failure]─► Web Activity
                  URL:    https://<shdp-host>/ingest/{client_id}
                  Method: POST
                  Header: Authorization = Bearer {webhook_secret}
                  Body:
                  {
                    "pipeline_name": "@pipeline().Pipeline",
                    "run_id":        "@pipeline().RunId",
                    "error_message": "@activity('ActivityName').error.message",
                    "error_code":    "@activity('ActivityName').error.errorCode",
                    "platform_hint": "ADF"
                  }
```

### Option B — Azure Monitor Alert → Webhook

1. Azure Monitor → Alerts → New rule
2. Scope: your ADF instance
3. Condition: `PipelineFailedRuns > 0`
4. Action: Action Group → Webhook → `https://<shdp-host>/ingest/{client_id}`

---

## Real-Time WebSocket

```
Frontend (AgentLog.jsx)
  useWebSocket(incidentId)
  ├── connects to  ws://host/ws/incidents/{id}
  ├── exponential back-off reconnect
  └── onMessage: appends live log entries to timeline

Backend (ws_manager.py)
  ConnectionManager
  ├── incident_connections: dict[incident_id, list[WebSocket]]
  ├── notification_connections: list[WebSocket]  (global bell)
  ├── broadcast_incident_sync()     ─┐ thread-safe via
  └── broadcast_notification_sync() ─┘ asyncio.run_coroutine_threadsafe(_loop)

set_event_loop(loop) captured in FastAPI startup event
```

**Incident channel message:**
```json
{
  "type": "incident_update",
  "incident_id": "uuid",
  "status": "RCA_IN_PROGRESS",
  "log_entry": {
    "timestamp": "2026-03-10T09:15:00Z",
    "agent": "RCA",
    "action": "started",
    "detail": "Analysing error logs..."
  }
}
```

**Notification bell message:**
```json
{ "type": "notification", "unread_count": 3 }
```

---

## Database Schema

### Table: `clients`

| Column | Type | Notes |
|--------|------|-------|
| id | NVARCHAR(36) | UUID, primary key, part of webhook URL |
| name | NVARCHAR(255) | Display name |
| industry | NVARCHAR(50) | NBFC / NGO / ecommerce / other |
| webhook_secret | NVARCHAR(255) | 64-char hex, validated on every ingest |
| created_at | DateTime | UTC |

### Table: `shdp_incidents`

| Column | Type | Notes |
|--------|------|-------|
| id | NVARCHAR(36) | UUID, primary key |
| client_id | NVARCHAR(36) | References clients.id (no DB FK) |
| platform_hint | NVARCHAR(100) | "ADF", "Airflow", etc. |
| pipeline_name | NVARCHAR(255) | |
| run_id | NVARCHAR(255) | |
| error_message | Text | |
| error_code | NVARCHAR(100) | |
| status | NVARCHAR(50) | See lifecycle above |
| priority | NVARCHAR(10) | P0–P3 |
| summary | Text | One-line GPT-4o summary |
| rca_hypothesis | Text | GPT-4o output |
| rca_confidence | Float | 0.0–1.0 |
| rca_evidence | NVARCHAR(MAX) | JSON array |
| rca_error_category | NVARCHAR(50) | connection_failure / schema_mismatch / etc. |
| fix_strategy | NVARCHAR(50) | retry / schema_patch / backfill / etc. |
| fix_steps | NVARCHAR(MAX) | JSON array of step strings |
| fix_instructions | Text | Markdown (manual strategies) |
| dry_run_result | NVARCHAR(10) | PASS or FAIL |
| dry_run_reasoning | Text | GPT-4o explanation |
| engineer_email | NVARCHAR(255) | Set at HIL decision |
| decision | NVARCHAR(20) | approve / reject |
| decided_at | DateTime | UTC |
| agent_log | NVARCHAR(MAX) | JSON array of log entries |
| created_at | DateTime | UTC |
| updated_at | DateTime | UTC, auto-updated |

### Table: `shdp_notifications`

| Column | Type | Notes |
|--------|------|-------|
| id | NVARCHAR(36) | UUID, primary key |
| incident_id | NVARCHAR(36) | References shdp_incidents.id (no DB FK) |
| client_id | NVARCHAR(36) | References clients.id (no DB FK) |
| message | NVARCHAR(500) | Human-readable notification text |
| is_read | Boolean | Default false |
| created_at | DateTime | UTC |

> Tables prefixed `shdp_` to avoid collision with any pre-existing `incidents` or `notifications` tables in the shared Azure SQL database.

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Liveness + degraded-mode status |
| POST | `/clients` | Register a new client; returns id + webhook_secret |
| GET | `/clients` | List all clients |
| DELETE | `/clients/{id}` | Remove a client and all their incidents |
| POST | `/ingest/{client_id}` | Universal webhook receiver (any payload format) |
| GET | `/incidents` | List incidents; filter by `?client_id=` or `?status=` |
| GET | `/incidents/{id}` | Full incident detail |
| POST | `/hil/decision` | Submit approve / reject + engineer_email |
| GET | `/notifications` | Last 20 unread notifications |
| POST | `/notifications/{id}/read` | Mark notification as read |
| WS | `/ws/incidents/{id}` | Real-time agent log stream for one incident |
| WS | `/ws/notifications` | Global notification bell updates |

---

## File Reference

```
backend/
  main.py                FastAPI app, CORS, startup, all routers, WS endpoints
  config.py              Pydantic Settings — OPENAI_API_KEY, AZURE_SQL_CONN,
                             DASHBOARD_URL, FIX_MODE; is_degraded property
  database.py            SQLAlchemy engine, SessionLocal, per-table safe init
  models.py              Client, Incident, Notification ORM classes
                             JSONColumn TypeDecorator (NVARCHAR MAX ↔ json)
  agents.py              SignalFusion, RCA, Playbook agents (GPT-4o, temp=0.2)
                             All wrapped in try/except with agent_log recording
  fix_executor.py        Agent 4 — retry or markdown instructions
  ws_manager.py          ConnectionManager, broadcast_incident_sync(),
                             broadcast_notification_sync()
  Dockerfile             Python 3.11-slim + ODBC Driver 17 + uvicorn
  routers/
    clients.py           POST/GET/DELETE /clients
    incidents.py         GET /incidents, GET /incidents/{id}
    ingest.py            POST /ingest/{client_id} — auth + field extraction
    hil.py               POST /hil/decision
    notifications.py     GET /notifications, POST /notifications/{id}/read
  services/
    incident_service.py  trigger_incident() — spawns background thread,
                             runs Agent1 → Agent2 → Agent3 in sequence

frontend/src/
  App.jsx                React Router: / → clients, /incidents, /incidents/:id
  api.js                 fetch wrappers for all backend endpoints
  hooks/
    useWebSocket.js      WS hook with exponential back-off reconnect
  components/
    ClientList.jsx       Client table, Add Client modal, onboarding checklist
    IncidentList.jsx     Filter by client/status, priority badges, time elapsed
    IncidentDetail.jsx   RCA confidence bar, evidence list, fix steps,
                             dry-run result, embedded HILPanel
    HILPanel.jsx         Email input + Approve / Reject (disabled if not AWAITING_HIL)
    AgentLog.jsx         Live timeline from WS, pulsing dot on active agent
    NotificationBell.jsx Bell icon + badge count, dropdown of 20 recent alerts
```

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Human-in-the-loop is mandatory | No fix ever auto-executes. Engineers always review the full RCA + playbook before anything runs. |
| Universal webhook, any payload | Clients use different tools (ADF, Airflow, dbt, Glue). One endpoint accepts all formats; best-effort extraction means onboarding requires zero schema changes on the client side. |
| Per-client webhook secrets | Each client gets an isolated secret so a leaked key cannot spoof incidents for another client. |
| In-app notifications only | No Slack or email dependency. The dashboard is the single pane of glass; the notification bell provides real-time alerts without external service configuration. |
| WebSocket + polling hybrid | AgentLog merges live WS entries with a 3s REST poll as authoritative fallback. Page refresh or WS drop never causes missed updates. |
| Thread-safe WS via stored event loop | Agents run in `threading.Thread`; WS runs in asyncio. `set_event_loop()` at startup + `asyncio.run_coroutine_threadsafe()` bridges the two. |
| Tables named `shdp_*` | Avoids collision with pre-existing `incidents` / `notifications` tables in shared Azure SQL databases. |
| No DB-level FK constraints | Prevents `create_table` from failing when a referenced table already exists with a different schema. Integrity enforced at application level. |
| Per-table safe init | Each table is created individually so a failure on one does not block creation of the others. |
| All agent calls in try/except | A single agent failure (LLM timeout, rate limit) never crashes the healing flow — the error is logged to `agent_log` and the incident moves to a safe state. |
