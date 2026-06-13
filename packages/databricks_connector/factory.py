"""Select the connector implementation from settings."""

from __future__ import annotations

from databricks_connector.interface import DatabricksConnector
from databricks_connector.mock import MockDatabricksConnector
from databricks_connector.real import RealDatabricksConnector


def build_connector(settings) -> DatabricksConnector:
    if settings.databricks_mode == "real":
        return RealDatabricksConnector(
            host=settings.databricks_host,
            token=settings.databricks_token,
            warehouse_id=settings.databricks_warehouse_id,
        )
    return MockDatabricksConnector()
