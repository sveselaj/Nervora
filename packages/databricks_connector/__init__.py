"""Databricks integration: mock-first, with the real interface prepared.

The gateway/worker depend only on :class:`DatabricksConnector`. The mock
implementation returns deterministic data for the SQL Statement Execution and
Jobs/Workflows APIs so the whole demo runs offline. The real implementation
documents the exact REST endpoints and is a drop-in once credentials exist.
"""

from databricks_connector.factory import build_connector
from databricks_connector.interface import (
    DatabricksConnector,
    JobRunResult,
    SqlStatementResult,
)
from databricks_connector.mock import MockDatabricksConnector
from databricks_connector.real import RealDatabricksConnector

__all__ = [
    "DatabricksConnector",
    "SqlStatementResult",
    "JobRunResult",
    "MockDatabricksConnector",
    "RealDatabricksConnector",
    "build_connector",
]
