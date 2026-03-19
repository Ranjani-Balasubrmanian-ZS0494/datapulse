"""
connectors/webhook_connector.py
--------------------------------
Generic webhook connector — works with any pipeline tool that accepts
an HTTP POST on failure / trigger.

Required tool_credentials fields:
    webhook_url  str   — Full URL to POST to
    headers      dict  — Optional extra HTTP headers (e.g. Authorization)

The connector POSTs a JSON body:
    {
        "action":      "rerun",
        "pipeline_id": "<pipeline_id>",
        "run_id":      "<original_run_id>"
    }

The receiving webhook is expected to return JSON with at least:
    { "success": true, "run_id": "<new_run_id>" }
"""

from __future__ import annotations

import requests

from .base import PipelineConnector


class WebhookConnector(PipelineConnector):
    def rerun_pipeline(self, pipeline_config: dict, run_id: str = "") -> dict:
        try:
            url = self.creds["webhook_url"]
            extra_headers = self.creds.get("headers", {})
            if isinstance(extra_headers, str):
                import json
                extra_headers = json.loads(extra_headers)

            headers = {"Content-Type": "application/json"}
            headers.update(extra_headers)

            payload = {
                "action": "rerun",
                "pipeline_id": pipeline_config.get("id", ""),
                "pipeline_name": pipeline_config.get("name", ""),
                "run_id": run_id,
            }

            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            resp.raise_for_status()

            try:
                data = resp.json()
            except Exception:
                data = {}

            return {
                "success": True,
                "run_id": str(data.get("run_id", "")),
                "detail": f"Webhook called successfully. Response: {data}",
            }
        except Exception as exc:
            return {"success": False, "run_id": None, "detail": str(exc)}

    def get_run_logs(self, run_id: str) -> str:
        """Webhooks do not expose a log endpoint — return a placeholder."""
        return f"Log retrieval not supported for custom webhook pipelines. Run ID: {run_id}"

    def discover_pipelines(self) -> list[dict]:
        """Custom webhooks do not support auto-discovery — return empty list."""
        return []
