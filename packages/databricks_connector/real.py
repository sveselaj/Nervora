"""Real Databricks connector interface (prepared, not exercised in the demo).

This is intentionally a thin, documented skeleton. It wires the two REST APIs
the gateway uses:

* SQL Statement Execution API:
    POST {host}/api/2.0/sql/statements
    GET  {host}/api/2.0/sql/statements/{statement_id}
* Jobs API 2.1:
    POST {host}/api/2.1/jobs/run-now

Switching to real Databricks is a configuration change (DATABRICKS_MODE=real
plus host/token/warehouse id) — no gateway code changes. Implementations should
add retry/backoff and poll until the statement/job reaches a terminal state.
"""

from __future__ import annotations

from typing import Any

from databricks_connector.interface import (
    DatabricksConnector,
    JobRunResult,
    SqlStatementResult,
)


class RealDatabricksConnector(DatabricksConnector):
    def __init__(self, *, host: str, token: str, warehouse_id: str, timeout: float = 60.0) -> None:
        if not (host and token and warehouse_id):
            raise ValueError(
                "RealDatabricksConnector requires host, token and warehouse_id "
                "(set DATABRICKS_HOST / DATABRICKS_TOKEN / DATABRICKS_WAREHOUSE_ID)."
            )
        self._host = host.rstrip("/")
        self._token = token
        self._warehouse_id = warehouse_id
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    def execute_sql(self, statement: str, parameters: dict[str, Any] | None = None) -> SqlStatementResult:
        # Reference implementation outline — uncomment when httpx + creds present.
        #
        # import httpx
        # body = {
        #     "warehouse_id": self._warehouse_id,
        #     "statement": statement,
        #     "parameters": [{"name": k, "value": str(v)} for k, v in (parameters or {}).items()],
        #     "wait_timeout": "30s",
        # }
        # with httpx.Client(timeout=self._timeout) as c:
        #     r = c.post(f"{self._host}/api/2.0/sql/statements", json=body, headers=self._headers())
        #     r.raise_for_status()
        #     data = r.json()
        #     # poll {host}/api/2.0/sql/statements/{id} until state == SUCCEEDED
        #     ...
        raise NotImplementedError(
            "RealDatabricksConnector is a prepared interface. Implement the SQL "
            "Statement Execution call and result polling, or run with "
            "DATABRICKS_MODE=mock for the reference demo."
        )

    def run_job(self, workflow_name: str, parameters: dict[str, Any] | None = None) -> JobRunResult:
        # body = {"job_id": <resolved-from-name>, "job_parameters": parameters or {}}
        # POST {host}/api/2.1/jobs/run-now -> {"run_id": ...}; then poll runs/get.
        raise NotImplementedError(
            "RealDatabricksConnector.run_job is a prepared interface. Wire the "
            "Jobs 2.1 run-now endpoint, or run with DATABRICKS_MODE=mock."
        )
