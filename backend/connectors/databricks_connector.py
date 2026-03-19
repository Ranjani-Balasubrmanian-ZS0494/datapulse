"""
connectors/databricks_connector.py
-----------------------------------
Connector for Databricks Jobs.

Required tool_credentials fields:
    host    str  — Databricks workspace URL  (e.g. https://adb-xxxx.azuredatabricks.net)
    token   str  — Personal Access Token or Service Principal token
    job_id  str  — Databricks Job ID to trigger
"""

from __future__ import annotations

import requests

from .base import PipelineConnector


class DatabricksConnector(PipelineConnector):
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.creds['token']}"}

    def rerun_pipeline(self, pipeline_config: dict, run_id: str = "") -> dict:
        """
        Trigger a Databricks job run via POST /api/2.1/jobs/run-now.
        """
        try:
            host = self.creds["host"].rstrip("/")
            job_id = self.creds["job_id"]
            url = f"{host}/api/2.1/jobs/run-now"
            resp = requests.post(
                url,
                headers=self._headers(),
                json={"job_id": int(job_id)},
                timeout=30,
            )
            resp.raise_for_status()
            new_run_id = str(resp.json().get("run_id", ""))
            return {
                "success": True,
                "run_id": new_run_id,
                "detail": f"Databricks job {job_id} triggered. Run ID: {new_run_id}",
            }
        except Exception as exc:
            return {"success": False, "run_id": None, "detail": str(exc)}

    def get_run_logs(self, run_id: str) -> str:
        """Fetch run output for a Databricks job run."""
        try:
            host = self.creds["host"].rstrip("/")
            url = f"{host}/api/2.1/jobs/runs/get-output"
            resp = requests.get(
                url,
                headers=self._headers(),
                params={"run_id": run_id},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("error", "") or str(data.get("notebook_output", {}).get("result", ""))
        except Exception as exc:
            return f"Could not fetch Databricks logs: {exc}"

    def discover_pipelines(self) -> list[dict]:
        """List all Databricks jobs in the workspace."""
        try:
            host = self.creds["host"].rstrip("/")
            url = f"{host}/api/2.1/jobs/list"
            pipelines = []
            has_more = True
            page_token = None
            while has_more:
                params = {"limit": 100}
                if page_token:
                    params["page_token"] = page_token
                resp = requests.get(url, headers=self._headers(), params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()
                for job in data.get("jobs", []):
                    job_id = str(job.get("job_id", ""))
                    name = job.get("settings", {}).get("name", f"job-{job_id}")
                    pipelines.append({"name": name, "tool_pipeline_id": job_id})
                has_more = data.get("has_more", False)
                page_token = data.get("next_page_token")
            return pipelines
        except Exception as exc:
            raise RuntimeError(f"Databricks discovery failed: {exc}") from exc
