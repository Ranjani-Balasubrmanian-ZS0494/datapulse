"""
connectors/adf_connector.py
---------------------------
Connector for Azure Data Factory pipelines.

Required tool_credentials fields:
    tenant_id         str  — Azure AD tenant ID
    client_id         str  — Service principal app (client) ID
    client_secret     str  — Service principal secret
    subscription_id   str  — Azure subscription ID
    resource_group    str  — Resource group that contains the ADF instance
    factory_name      str  — ADF factory name
    pipeline_name     str  — ADF pipeline name to re-run

Authentication uses Service Principal (client credentials) against
the Azure REST API.  No Azure SDK required — pure HTTP calls.
"""

from __future__ import annotations

import requests

from .base import PipelineConnector

_ADF_BASE = "https://management.azure.com"
_TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/token"


class ADFConnector(PipelineConnector):
    def _get_token(self) -> str:
        url = _TOKEN_URL.format(tenant_id=self.creds["tenant_id"])
        resp = requests.post(
            url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.creds["client_id"],
                "client_secret": self.creds["client_secret"],
                "resource": "https://management.azure.com/",
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    def rerun_pipeline(self, pipeline_config: dict, run_id: str = "") -> dict:
        """
        Create a new pipeline run in ADF.
        Uses POST .../pipelines/{pipeline_name}/createRun
        """
        try:
            token = self._get_token()
            sub = self.creds["subscription_id"]
            rg = self.creds["resource_group"]
            factory = self.creds["factory_name"]
            pipeline_name = self.creds["pipeline_name"]

            url = (
                f"{_ADF_BASE}/subscriptions/{sub}/resourceGroups/{rg}"
                f"/providers/Microsoft.DataFactory/factories/{factory}"
                f"/pipelines/{pipeline_name}/createRun"
                f"?api-version=2018-06-01"
            )
            resp = requests.post(
                url,
                headers={"Authorization": f"Bearer {token}"},
                json={},
                timeout=30,
            )
            resp.raise_for_status()
            new_run_id = resp.json().get("runId", "")
            return {
                "success": True,
                "run_id": new_run_id,
                "detail": f"ADF pipeline '{pipeline_name}' triggered. Run ID: {new_run_id}",
            }
        except Exception as exc:
            return {"success": False, "run_id": None, "detail": str(exc)}

    def get_run_logs(self, run_id: str) -> str:
        """Fetch activity runs for a given pipeline run."""
        try:
            token = self._get_token()
            sub = self.creds["subscription_id"]
            rg = self.creds["resource_group"]
            factory = self.creds["factory_name"]

            url = (
                f"{_ADF_BASE}/subscriptions/{sub}/resourceGroups/{rg}"
                f"/providers/Microsoft.DataFactory/factories/{factory}"
                f"/pipelineRuns/{run_id}/activityRuns"
                f"?api-version=2018-06-01"
            )
            resp = requests.post(url, headers={"Authorization": f"Bearer {token}"}, json={}, timeout=30)
            resp.raise_for_status()
            return str(resp.json())
        except Exception as exc:
            return f"Could not fetch ADF logs: {exc}"

    def discover_pipelines(self) -> list[dict]:
        """List all pipelines in the ADF factory."""
        try:
            token = self._get_token()
            sub = self.creds["subscription_id"]
            rg = self.creds["resource_group"]
            factory = self.creds["factory_name"]

            url = (
                f"{_ADF_BASE}/subscriptions/{sub}/resourceGroups/{rg}"
                f"/providers/Microsoft.DataFactory/factories/{factory}"
                f"/pipelines?api-version=2018-06-01"
            )
            resp = requests.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=30,
            )
            resp.raise_for_status()
            pipelines = []
            for item in resp.json().get("value", []):
                name = item.get("name", "")
                pipelines.append({
                    "name": name,
                    "tool_pipeline_id": name,
                })
            return pipelines
        except Exception as exc:
            raise RuntimeError(f"ADF discovery failed: {exc}") from exc
