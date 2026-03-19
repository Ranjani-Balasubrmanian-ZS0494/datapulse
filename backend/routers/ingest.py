"""
Universal webhook receiver.

Accepts failure alerts in ANY format from ANY pipeline tool.
Validates the client and bearer token, then triggers the agent chain
in a background thread.
"""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from sqlalchemy.orm import Session

from database import get_db
from models import Client
from services.incident_service import trigger_incident

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ingest"])


def _pipeline_from_dimensions(data: dict) -> str | None:
    """
    Azure Monitor metric alerts bury the pipeline name in:
      data.context.condition.allOf[*].dimensions where name == "Name"
    """
    try:
        ctx = data.get("alertContext", data.get("context", {})) or {}
        condition = ctx.get("condition", {}) or {}
        for rule in condition.get("allOf", []):
            for dim in rule.get("dimensions", []):
                if dim.get("name") == "Name" and dim.get("value"):
                    return dim["value"]
    except Exception:
        pass
    return None


def _extract_fields(body: dict) -> dict:
    """Best-effort field extraction from any webhook payload shape."""

    # Azure Monitor flattening — payload is 2 levels deep under data.properties / data.context
    schema_id = body.get("schemaId", "")
    data = body.get("data", {})
    pipeline_from_dimensions = None

    if isinstance(data, dict) and (
        "properties" in data or "context" in data
        or "alertContext" in data or "essentials" in data
        or "azuremonitor" in schema_id.lower()
    ):
        props = data.get("properties", {}) or {}
        ctx   = data.get("context", {}) or {}

        # Extract pipeline name from resourceId: …/pipelines/{name}/…
        resource_id = ctx.get("resourceId", "")
        pipeline_from_resource = None
        if "/pipelines/" in resource_id:
            pipeline_from_resource = resource_id.split("/pipelines/")[1].split("/")[0]

        # Azure Monitor metric alerts: pipeline name is in condition.allOf[*].dimensions
        pipeline_from_dimensions = _pipeline_from_dimensions(data)

        body = {
            **body,
            **ctx,
            **props,
            **({"pipeline_name": pipeline_from_resource}
               if pipeline_from_resource and not props.get("pipelineName") else {}),
        }

    def _first(*keys):
        for k in keys:
            v = body.get(k)
            if v is not None:
                return v
        # search nested one level
        for v in body.values():
            if isinstance(v, dict):
                for k in keys:
                    if v.get(k) is not None:
                        return v.get(k)
        return None

    pipeline_name = _first(
        "pipeline_name", "pipelineName", "pipeline", "dag_id", "dagId",
        "job_name", "jobName", "workflow_name", "workflowName", "name",
    ) or pipeline_from_dimensions  # fallback to dimensions extraction

    return {
        "pipeline_name": pipeline_name,
        "error_message": _first(
            "error_message", "ErrorMessage", "errorMessage", "error", "message", "msg",
            "failure_message", "failureMessage", "exception", "detail",
        ),
        "error_code": _first(
            "error_code", "errorCode", "code", "status_code", "statusCode",
            "exit_code", "exitCode",
        ),
        "run_id": _first(
            "run_id", "runId", "pipelineRunId", "correlationId",
            "execution_id", "executionId", "dag_run_id", "dagRunId", "job_id", "jobId",
        ),
        "platform_hint": _first(
            "platform", "source", "tool", "integration", "pipeline_tool",
        ),
        "log_snippet": _first(
            "log", "logs", "log_snippet", "logSnippet", "stack_trace",
            "stackTrace", "traceback",
        ),
        "raw_payload": body,
    }


@router.post("/ingest/{client_id}", status_code=202)
async def ingest_webhook(
    client_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    # 1. Validate client exists
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=403, detail="Unknown client")

    # 2. Validate bearer token (optional — missing header accepted for Azure Monitor)
    auth_header = request.headers.get("Authorization", "")
    if auth_header:
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=403, detail="Invalid token")
        token = auth_header.removeprefix("Bearer ").strip()
        if token != client.webhook_secret:
            raise HTTPException(status_code=403, detail="Invalid token")
    else:
        logger.warning(
            "Warning: unauthenticated request accepted from Azure Monitor or trusted source "
            f"(client={client_id})"
        )

    # 3. Parse body — accept any JSON
    try:
        body = await request.json()
        if not isinstance(body, dict):
            body = {"raw": body}
    except Exception:
        body = {}

    # Log raw payload so we can see exactly what Azure Monitor sends
    logger.info(f"Raw webhook body: {json.dumps(body, default=str)}")

    # 4. Best-effort field extraction
    fields = _extract_fields(body)
    logger.info(
        f"Webhook received for client={client_id} "
        f"pipeline={fields.get('pipeline_name')} run_id={fields.get('run_id')}"
    )

    # 5. ADF enrichment — fetch real run details from ADF API before agents run.
    #    Azure Monitor metric alerts have no runId: fall back to querying ADF for
    #    the latest failed run of the named pipeline.
    schema_id = body.get("schemaId", "")
    is_azure_monitor = (
        "azuremonitor" in schema_id.lower()
        or (isinstance(body.get("data"), dict)
            and any(k in body["data"] for k in ("context", "properties", "alertContext", "essentials")))
    )
    if is_azure_monitor:
        run_id      = fields.get("run_id")
        pipeline_nm = fields.get("pipeline_name")
        try:
            from adf_client import fetch_run_details, fetch_latest_failed_run
            if run_id:
                logger.info(f"ADF enrichment: fetching run {run_id}")
                enriched = fetch_run_details(run_id)
            elif pipeline_nm:
                logger.info(f"ADF enrichment: no runId — querying latest failed run for '{pipeline_nm}'")
                enriched = fetch_latest_failed_run(pipeline_nm)
            else:
                logger.warning("ADF enrichment: no runId and no pipeline name — skipping")
                enriched = {}

            if enriched:
                fields = {**fields, **{k: v for k, v in enriched.items() if v is not None}}
                logger.info(
                    f"ADF enrichment applied — pipeline={fields.get('pipeline_name')} "
                    f"error={fields.get('error_message', '')[:100]}"
                )
            else:
                logger.warning("ADF enrichment returned empty result — RCA will have limited context")
        except Exception as exc:
            logger.warning(f"ADF enrichment failed (continuing without it): {exc}")

    # 6. Trigger agent chain in background (non-blocking)
    background_tasks.add_task(trigger_incident, client_id, fields)

    return {"status": "accepted", "client_id": client_id}
