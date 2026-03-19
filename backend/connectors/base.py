"""
connectors/base.py
------------------
Abstract base class that every pipeline connector must implement.

A connector knows how to:
  1. Trigger a pipeline re-run in its native tool (ADF / Databricks / etc.)
  2. Fetch the last run's logs so they can be fed to the AI agents.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class PipelineConnector(ABC):
    """
    Base interface for all pipeline tool connectors.

    Each concrete connector receives tool_credentials (a dict) from the
    pipeline registry and uses them to authenticate with the external API.
    """

    def __init__(self, tool_credentials: dict) -> None:
        self.creds = tool_credentials

    @abstractmethod
    def rerun_pipeline(self, pipeline_config: dict, run_id: str = "") -> dict:
        """
        Trigger a pipeline re-run via the tool's native API.

        Parameters
        ----------
        pipeline_config : dict
            The full pipeline record from the registry (includes credentials).
        run_id : str
            Optional ID of the failed run to rerun (tool-dependent).

        Returns
        -------
        dict
            {"success": bool, "run_id": str | None, "detail": str}
        """

    @abstractmethod
    def get_run_logs(self, run_id: str) -> str:
        """
        Fetch logs / error details for a given run.

        Returns a plain-text string for the AI agents to analyse.
        """

    @abstractmethod
    def discover_pipelines(self) -> list[dict]:
        """
        Query the pipeline tool and return all available pipelines/jobs.

        Returns
        -------
        list of dicts, each with at minimum:
            {"name": str, "tool_pipeline_id": str}

        Returns [] if the tool does not support discovery.
        """
