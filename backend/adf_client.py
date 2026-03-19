"""
adf_client.py
-------------
Fetches pipeline run details and activity-level error logs from Azure Data Factory
using the Azure Service Principal credentials in config.

Called from the ingest router when an Azure Monitor webhook is received,
so the RCA agent gets real run logs instead of just the alert payload.
"""
import json
import logging
from datetime import datetime, timedelta, timezone

import requests as _requests

from config import settings

logger = logging.getLogger(__name__)

_ADF_BASE = "https://management.azure.com"
_ADF_API  = "2018-06-01"


def _rest_token() -> str:
    """Return a short-lived Bearer token for the ADF REST API."""
    from azure.identity import ClientSecretCredential
    cred = ClientSecretCredential(
        tenant_id=settings.AZURE_TENANT_ID,
        client_id=settings.AZURE_CLIENT_ID,
        client_secret=settings.AZURE_CLIENT_SECRET,
    )
    return cred.get_token(f"{_ADF_BASE}/.default").token


def _adf_url(resource: str, name: str) -> str:
    """Build a fully-qualified ADF REST URL for a named resource."""
    return (
        f"{_ADF_BASE}/subscriptions/{settings.AZURE_SUBSCRIPTION_ID}"
        f"/resourceGroups/{settings.AZURE_RESOURCE_GROUP}"
        f"/providers/Microsoft.DataFactory/factories/{settings.AZURE_FACTORY_NAME}"
        f"/{resource}/{name}?api-version={_ADF_API}"
    )


def get_adf_client():
    """
    Return an authenticated DataFactoryManagementClient.
    Raises RuntimeError if credentials are not configured.
    Used by fix_executor for active ADF operations.
    """
    if not settings.has_adf_credentials:
        raise RuntimeError("ADF credentials not configured in .env")
    from azure.identity import ClientSecretCredential
    from azure.mgmt.datafactory import DataFactoryManagementClient

    credential = ClientSecretCredential(
        tenant_id=settings.AZURE_TENANT_ID,
        client_id=settings.AZURE_CLIENT_ID,
        client_secret=settings.AZURE_CLIENT_SECRET,
    )
    return DataFactoryManagementClient(credential, settings.AZURE_SUBSCRIPTION_ID)


def _make_client():
    """Return an authenticated DataFactoryManagementClient, or None if not configured."""
    if not settings.has_adf_credentials:
        return None
    try:
        from azure.identity import ClientSecretCredential
        from azure.mgmt.datafactory import DataFactoryManagementClient

        credential = ClientSecretCredential(
            tenant_id=settings.AZURE_TENANT_ID,
            client_id=settings.AZURE_CLIENT_ID,
            client_secret=settings.AZURE_CLIENT_SECRET,
        )
        return DataFactoryManagementClient(credential, settings.AZURE_SUBSCRIPTION_ID)
    except Exception as exc:
        logger.warning(f"ADF client init failed: {exc}")
        return None


def fetch_sink_table_name(pipeline_name: str) -> str:
    """
    Fetch the sink dataset table name from an ADF pipeline definition.
    Walks copy-activity outputs to find a dataset with table_name or table property.
    Returns "" on any failure so callers can degrade gracefully.
    """
    try:
        adf = get_adf_client()
        pipeline = adf.pipelines.get(
            settings.AZURE_RESOURCE_GROUP,
            settings.AZURE_FACTORY_NAME,
            pipeline_name,
        )
        for activity in pipeline.activities or []:
            if hasattr(activity, "outputs"):
                for output in activity.outputs or []:
                    ref_name = output.reference_name
                    dataset = adf.datasets.get(
                        settings.AZURE_RESOURCE_GROUP,
                        settings.AZURE_FACTORY_NAME,
                        ref_name,
                    )
                    props = getattr(dataset, "type_properties", None)
                    if props:
                        table = (
                            getattr(props, "table_name", None)
                            or getattr(props, "table", None)
                        )
                        if table:
                            return str(table)
    except Exception as exc:
        logger.warning(f"fetch_sink_table_name failed for pipeline='{pipeline_name}': {exc}")
    return ""


def fetch_pipeline_definition(pipeline_name: str) -> dict:
    """
    Fetch full pipeline JSON via ADF REST API.
    The Python SDK strips typeProperties during as_dict() — REST API returns complete JSON.
    """
    try:
        token = _rest_token()
        resp  = _requests.get(
            _adf_url("pipelines", pipeline_name),
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()

        activities = result.get("properties", {}).get("activities", [])
        logger.info(f"[fetch_pipeline] '{pipeline_name}' — {len(activities)} activities found")
        for act in activities:
            logger.info(
                f"[fetch_pipeline] activity name={act.get('name')!r} type={act.get('type')!r}"
            )
        return result
    except Exception as exc:
        logger.error(f"fetch_pipeline_definition failed for '{pipeline_name}': {exc}", exc_info=True)
        return {}


def fetch_dataflow_definition(dataflow_name: str) -> dict:
    """Fetch full dataflow JSON via ADF REST API."""
    try:
        token = _rest_token()
        resp  = _requests.get(
            _adf_url("dataflows", dataflow_name),
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        logger.info(f"[fetch_dataflow] FULL JSON: {json.dumps(result, default=str)[:3000]}")
        return result
    except Exception as exc:
        logger.error(f"fetch_dataflow_definition failed for '{dataflow_name}': {exc}", exc_info=True)
        return {}


def update_dataflow_definition(dataflow_name: str, dataflow_def: dict) -> bool:
    """Update a dataflow definition via ADF REST API (PUT)."""
    try:
        token = _rest_token()
        resp  = _requests.put(
            _adf_url("dataflows", dataflow_name),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type":  "application/json",
            },
            json=dataflow_def,
            timeout=30,
        )
        resp.raise_for_status()
        logger.info(f"[update_dataflow] '{dataflow_name}' updated successfully")
        return True
    except Exception as exc:
        logger.error(f"update_dataflow_definition failed for '{dataflow_name}': {exc}", exc_info=True)
        return False


def get_dataflow_name_from_pipeline(pipeline_def: dict) -> str:
    """
    Extract the dataflow name from a pipeline definition returned by fetch_pipeline_definition().
    Matches any activity type that references a dataflow.
    """
    try:
        activities = pipeline_def.get("properties", {}).get("activities", [])
        logger.info(f"[get_dataflow_name] scanning {len(activities)} activities")

        for activity in activities:
            act_type = activity.get("type", "")
            act_name = activity.get("name", "")

            if "dataflow" in act_type.lower() or "data_flow" in act_type.lower():
                logger.info(
                    f"[get_dataflow_name] found dataflow activity: name={act_name!r} type={act_type!r}"
                )
                type_props = activity.get("typeProperties", {})
                df_ref = (
                    type_props.get("dataflow")
                    or type_props.get("dataFlow")
                    or type_props.get("data_flow")
                    or {}
                )
                name = (
                    df_ref.get("referenceName")
                    or df_ref.get("reference_name")
                    or ""
                )
                if name:
                    logger.info(f"[get_dataflow_name] resolved dataflow name: {name!r}")
                    return name
                logger.warning(
                    f"[get_dataflow_name] dataflow activity found but no referenceName. "
                    f"typeProperties={type_props}"
                )

        logger.warning(
            f"[get_dataflow_name] no dataflow activity found in {len(activities)} activities. "
            f"Types: {[a.get('type') for a in activities]}"
        )
    except Exception as exc:
        logger.error(f"get_dataflow_name_from_pipeline failed: {exc}", exc_info=True)
    return ""


def revert_dataflow_to_valid_state(dataflow_name: str = "Bigbang_df") -> None:
    """
    One-time fix: revert any invalid sized-string types (e.g. string(2))
    back to plain 'string' in ADF DSL scriptLines.

    Run once after a bad patch, then remove the call.
    """
    import re as _re

    df_def = fetch_dataflow_definition(dataflow_name)
    if not df_def:
        logger.error(f"[revert] could not fetch '{dataflow_name}'")
        return

    type_props   = df_def.get("properties", {}).get("typeProperties", {})
    script_lines = type_props.get("scriptLines", [])

    new_lines = []
    changed   = 0
    for line in script_lines:
        fixed = _re.sub(r'\bstring\(\d+\)', 'string', line)
        if fixed != line:
            changed += 1
            logger.info(f"[revert]   {line!r} → {fixed!r}")
        new_lines.append(fixed)

    if not changed:
        logger.info(f"[revert] '{dataflow_name}' — nothing to revert, already clean")
        return

    type_props["scriptLines"] = new_lines
    df_def.pop("etag", None)

    if update_dataflow_definition(dataflow_name, df_def):
        logger.info(f"[revert] '{dataflow_name}' reverted ({changed} lines fixed)")
    else:
        logger.error(f"[revert] PUT failed for '{dataflow_name}'")


_NUMERIC_DSL_TYPES = {
    'short', 'integer', 'int', 'long', 'float', 'double',
    'decimal', 'byte', 'integral', 'number', 'fractional',
}


def _target_dsl_type(current_type: str) -> str:
    """Map any source type to the correct ADF DSL target type.

    ADF DSL does NOT support sized strings like string(2) or nvarchar(50).
    Valid scalar types: integer short long double float decimal boolean
                        timestamp date byte binary string any
    For all type mismatches the safe fix is plain 'string'.
    """
    base = current_type.lower().split("(")[0].strip()
    return "string"   # always widen to plain string — no size in ADF DSL


def patch_dataflow_column_type(dataflow_name: str, column_name: str, new_size: str) -> bool:
    """
    Generic patch for any ADF dataflow column type mismatch.

    Finds every scriptLine containing `column_name as <any_type>`
    and replaces the type with the correct ADF DSL type (always plain 'string').
    ADF DSL does NOT support sized types like string(2) — size is enforced
    at the SQL sink level, not inside the dataflow script.

    Works for ANY column name, ANY current type (short, integer, string,
    decimal(10,2), etc.) — nothing is hardcoded.
    """
    import re as _re
    try:
        df_dict = fetch_dataflow_definition(dataflow_name)
        if not df_dict:
            logger.error(f"[patch_dataflow] could not fetch dataflow '{dataflow_name}'")
            return False

        type_props   = df_dict.get("properties", {}).get("typeProperties", {})
        script_lines = type_props.get("scriptLines", [])

        if not script_lines:
            logger.error(
                f"[patch_dataflow] no scriptLines in dataflow '{dataflow_name}'. "
                f"typeProperties keys: {list(type_props.keys())}"
            )
            return False

        logger.info(
            f"[patch_dataflow] scanning {len(script_lines)} scriptLines "
            f"for column='{column_name}' (new_size hint={new_size})"
        )

        # Generic regex — captures "column_name as " then matches ANY type token
        # \w+(?:\([^)]*\))? covers: short, string, string(1), decimal(10,2), …
        pattern = _re.compile(
            rf'(\b{_re.escape(column_name)}\b\s+as\s+)'
            rf'(\w+(?:\([^)]*\))?)'
        )

        patched   = False
        new_lines = []
        for line in script_lines:
            if column_name in line:
                m = pattern.search(line)
                if m:
                    current_type = m.group(2)
                    target_type  = _target_dsl_type(current_type)
                    if current_type == target_type:
                        # Already correct DSL type — no change needed
                        logger.info(
                            f"[patch_dataflow] '{column_name}' already '{target_type}' — no change"
                        )
                        new_lines.append(line)
                        continue
                    new_line = pattern.sub(rf'\g<1>{target_type}', line)
                    patched = True
                    logger.info(f"[patch_dataflow] patched line:")
                    logger.info(f"[patch_dataflow]   before: {line!r}")
                    logger.info(f"[patch_dataflow]   after:  {new_line!r}")
                    new_lines.append(new_line)
                    continue
            new_lines.append(line)

        if not patched:
            matching = [ln for ln in script_lines if column_name in ln]
            logger.error(
                f"[patch_dataflow] column '{column_name}' not found in any scriptLine "
                f"matching 'column as <type>'"
            )
            logger.info(
                f"[patch_dataflow] lines containing '{column_name}': {matching}"
            )
            return False

        type_props["scriptLines"] = new_lines

        # Remove etag — causes 412 Precondition Failed if left in
        df_dict.pop("etag", None)

        success = update_dataflow_definition(dataflow_name, df_dict)
        if success:
            logger.info(
                f"[patch_dataflow] dataflow '{dataflow_name}' updated in ADF successfully"
            )
        return success

    except Exception as exc:
        logger.error(f"patch_dataflow_column_type failed: {exc}", exc_info=True)
        return False


def fetch_run_details(
    run_id: str,
    resource_group: str | None = None,
    factory_name: str | None = None,
) -> dict:
    """
    Fetch the pipeline run and all activity runs for `run_id` from ADF.

    Returns a dict with enriched fields that are merged into the ingest payload
    before the agent chain runs. Returns {} on any failure so the chain still works.
    """
    if not run_id:
        return {}

    client = _make_client()
    if not client:
        logger.info("ADF credentials not configured — skipping run enrichment.")
        return {}

    rg      = resource_group or settings.AZURE_RESOURCE_GROUP
    factory = factory_name   or settings.AZURE_FACTORY_NAME

    try:
        # 1. Pipeline run summary
        run = client.pipeline_runs.get(rg, factory, run_id)
        logger.info(f"ADF: fetched run {run_id} — status={run.status}")

        # 2. Activity runs — query last 24 h window to cover the run
        from azure.mgmt.datafactory.models import RunFilterParameters

        now = datetime.now(timezone.utc)
        filter_params = RunFilterParameters(
            last_updated_after=now - timedelta(hours=24),
            last_updated_before=now,
        )
        activity_result = client.activity_runs.query_by_pipeline_run(
            rg, factory, run_id, filter_params
        )

        failed_activities = []
        for act in (activity_result.value or []):
            if act.status == "Failed":
                err = act.error or {}
                failed_activities.append({
                    "activity_name": act.activity_name,
                    "activity_type": act.activity_type,
                    "error_code":    err.get("errorCode"),
                    "error_message": err.get("message"),
                    "duration_ms":   act.duration_in_ms,
                })

        # 3. Build enriched payload
        enriched: dict = {
            "pipeline_name": run.pipeline_name or None,
            "run_id":        run.run_id,
            "platform_hint": "ADF",
            "adf_run_status":   run.status,
            "adf_duration_ms":  run.duration_in_ms,
            "adf_failed_activities": failed_activities,
        }

        # Promote the first failed activity's error as the primary error fields
        if failed_activities:
            primary = failed_activities[0]
            if primary.get("error_message"):
                enriched["error_message"] = primary["error_message"]
            if primary.get("error_code"):
                enriched["error_code"] = primary["error_code"]
            # Full activity log as a JSON string for the RCA agent
            enriched["log_snippet"] = json.dumps(failed_activities, indent=2)

        logger.info(
            f"ADF enrichment complete — pipeline={enriched.get('pipeline_name')}, "
            f"failed_activities={len(failed_activities)}"
        )
        return enriched

    except Exception as exc:
        logger.warning(f"ADF run enrichment failed for run_id={run_id}: {exc}")
        return {}


def fetch_latest_failed_run(
    pipeline_name: str,
    resource_group: str | None = None,
    factory_name: str | None = None,
) -> dict:
    """
    Azure Monitor metric alerts have no runId — query ADF for the most recent
    failed run of `pipeline_name` in the last hour and enrich from it.

    Returns {} on any failure so the agent chain still proceeds.
    """
    if not pipeline_name:
        return {}

    client = _make_client()
    if not client:
        logger.info("ADF credentials not configured — skipping latest-run lookup.")
        return {}

    rg      = resource_group or settings.AZURE_RESOURCE_GROUP
    factory = factory_name   or settings.AZURE_FACTORY_NAME

    try:
        from azure.mgmt.datafactory.models import RunFilterParameters, RunQueryFilter, RunQueryOrder, RunQueryOrderBy

        now = datetime.now(timezone.utc)
        filter_params = RunFilterParameters(
            last_updated_after=now - timedelta(hours=1),
            last_updated_before=now,
            filters=[
                RunQueryFilter(operand="PipelineName", operator="Equals", values=[pipeline_name]),
                RunQueryFilter(operand="Status",       operator="Equals", values=["Failed"]),
            ],
            order_by=[RunQueryOrderBy(order_by="RunEnd", order=RunQueryOrder.DESC)],
        )
        result = client.pipeline_runs.query_by_factory(rg, factory, filter_params)

        runs = result.value or []
        if not runs:
            logger.warning(
                f"ADF: no failed runs found for pipeline='{pipeline_name}' in last 1h"
            )
            return {}

        latest_run = runs[0]
        logger.info(
            f"ADF: found latest failed run {latest_run.run_id} for pipeline='{pipeline_name}'"
        )
        return fetch_run_details(latest_run.run_id, rg, factory)

    except Exception as exc:
        logger.warning(f"ADF latest-run lookup failed for pipeline='{pipeline_name}': {exc}")
        return {}
