# SHDP — Self-Healing Data Pipeline

SHDP is an internal tool for service companies that manage data pipelines for multiple clients. When a pipeline fails, instead of an engineer manually investigating, the system automatically diagnoses the failure using four chained GPT-4o AI agents and presents a proposed fix for human approval. No fix ever executes without a human approving it first.

---

## Running the Backend

```bash
cd shdp/backend

# 1. Create and activate a virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy and fill in your .env
cp ../.env.example .env
# Edit .env with your OPENAI_API_KEY and AZURE_SQL_CONN

# 4. Start the server
uvicorn main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`.
Interactive docs: `http://localhost:8000/docs`

---

## Running the Frontend

```bash
cd shdp/frontend

# 1. Install dependencies
npm install

# 2. Start the dev server
npm run dev
```

The dashboard will be available at `http://localhost:5173`.

---

## Onboarding a New Client

1. Go to the **Clients** page and click **Add Client**. Enter the client name and industry.
2. Copy their **Webhook URL** (format: `http://your-server/ingest/{client_id}`).
3. Copy their **Webhook Secret**.
4. In the client's pipeline tool (Airflow, Glue, dbt, etc.), add a failure alert that sends an HTTP POST to the webhook URL with the header `Authorization: Bearer <webhook_secret>`.
5. Done — the next pipeline failure will automatically appear in the Incidents page.

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | Yes | — | OpenAI API key used by all four agents |
| `AZURE_SQL_CONN` | Yes | — | SQLAlchemy connection string for Azure SQL (pyodbc) |
| `DASHBOARD_URL` | No | `http://localhost:5173` | Frontend URL — added to CORS allowed origins |
| `FIX_MODE` | No | `auto` | `auto` = attempt automated retry if trigger endpoint exists; `manual` = always produce markdown instructions |

> The app starts in **degraded mode** if `OPENAI_API_KEY` or `AZURE_SQL_CONN` are missing — it will boot and show the dashboard, but agent runs and database operations will fail gracefully.

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check — returns degraded status if config is missing |
| `POST` | `/clients` | Create a new client |
| `GET` | `/clients` | List all clients |
| `DELETE` | `/clients/{id}` | Delete a client |
| `POST` | `/ingest/{client_id}` | Universal webhook receiver (any payload format) |
| `GET` | `/incidents` | List all incidents (filterable by client_id, status) |
| `GET` | `/incidents/{id}` | Get full incident detail |
| `POST` | `/hil/decision` | Submit approve/reject decision |
| `GET` | `/notifications` | Get unread notifications |
| `POST` | `/notifications/{id}/read` | Mark notification as read |
| `WS` | `/ws/incidents/{id}` | Real-time incident updates |
| `WS` | `/ws/notifications` | Real-time notification bell updates |

---

## Incident Status Flow

```
DETECTING → RCA_IN_PROGRESS → PLAYBOOK_IN_PROGRESS → AWAITING_HIL
  → (approve) → FIXING → RESOLVED
                       → FIX_FAILED
  → (reject)  → REJECTED
  → (manual)  → AWAITING_MANUAL_FIX
```
