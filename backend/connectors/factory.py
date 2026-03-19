"""
connectors/factory.py
---------------------
Returns the correct PipelineConnector subclass based on the `tool` string
stored in the pipeline registry.

Supported tool values
---------------------
  adf         → ADFConnector         (Azure Data Factory)
  databricks  → DatabricksConnector  (Databricks Jobs)
  synapse     → SynapseConnector     (Azure Synapse Analytics)
  custom      → WebhookConnector     (generic HTTP webhook)
"""

from __future__ import annotations

from .adf_connector import ADFConnector
from .base import PipelineConnector
from .databricks_connector import DatabricksConnector
from .synapse_connector import SynapseConnector
from .webhook_connector import WebhookConnector

_REGISTRY: dict[str, type[PipelineConnector]] = {
    "adf": ADFConnector,
    "databricks": DatabricksConnector,
    "synapse": SynapseConnector,
    "custom": WebhookConnector,
}


def get_connector(tool: str, credentials: dict) -> PipelineConnector:
    """
    Instantiate and return the connector for `tool`.

    Parameters
    ----------
    tool        : one of "adf" | "databricks" | "synapse" | "custom"
    credentials : the tool_credentials dict from the pipeline registry

    Raises
    ------
    ValueError  if the tool name is not recognised.
    """
    cls = _REGISTRY.get(tool.lower())
    if cls is None:
        raise ValueError(
            f"Unknown pipeline tool '{tool}'. "
            f"Supported tools: {', '.join(_REGISTRY)}"
        )
    return cls(credentials)
