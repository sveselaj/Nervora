"""Deterministic mock Databricks connector.

Stands in for the SQL Warehouse / Statement Execution API and the Jobs API so
the entire reference flow (budget variance report + workflow trigger) runs with
no external dependency. Data is synthetic and stable across runs.
"""

from __future__ import annotations

import hashlib
from typing import Any

from databricks_connector.interface import (
    DatabricksConnector,
    JobRunResult,
    SqlStatementResult,
)

# Synthetic departmental budget data keyed by (department_id, period).
_BUDGET_FACTS: dict[tuple[str, str], list[dict[str, Any]]] = {
    ("FIN-100", "2024-Q2"): [
        {"line_item": "Salaries", "budget": 480000, "actual": 502300},
        {"line_item": "Software", "budget": 95000, "actual": 87200},
        {"line_item": "Travel", "budget": 40000, "actual": 51800},
        {"line_item": "Contractors", "budget": 120000, "actual": 98400},
    ],
    ("SALES-200", "2024-Q2"): [
        {"line_item": "Salaries", "budget": 610000, "actual": 598000},
        {"line_item": "Marketing", "budget": 250000, "actual": 301500},
        {"line_item": "Travel", "budget": 80000, "actual": 76200},
    ],
}


def _stmt_id(statement: str, parameters: dict[str, Any] | None) -> str:
    seed = f"{statement}|{sorted((parameters or {}).items())}"
    return "stmt_" + hashlib.sha256(seed.encode()).hexdigest()[:16]


class MockDatabricksConnector(DatabricksConnector):
    def execute_sql(self, statement: str, parameters: dict[str, Any] | None = None) -> SqlStatementResult:
        params = parameters or {}
        dept = str(params.get("department_id", "FIN-100"))
        period = str(params.get("period", "2024-Q2"))
        facts = _BUDGET_FACTS.get((dept, period), [])

        columns = ["line_item", "budget", "actual", "variance", "variance_pct"]
        rows: list[list[Any]] = []
        for f in facts:
            variance = f["actual"] - f["budget"]
            pct = round(variance / f["budget"] * 100, 2) if f["budget"] else 0.0
            rows.append([f["line_item"], f["budget"], f["actual"], variance, pct])

        return SqlStatementResult(
            statement_id=_stmt_id(statement, parameters),
            columns=columns,
            rows=rows,
            row_count=len(rows),
        )

    def run_job(self, workflow_name: str, parameters: dict[str, Any] | None = None) -> JobRunResult:
        # Deterministic run id derived from inputs so retries are recognisable.
        seed = f"{workflow_name}|{sorted((parameters or {}).items())}"
        run_id = "run_" + hashlib.sha256(seed.encode()).hexdigest()[:12]
        return JobRunResult(
            run_id=run_id,
            job_name=workflow_name,
            state="SUCCESS",
            output={
                "workflow": workflow_name,
                "parameters": parameters or {},
                "note": "mock Databricks job completed",
                "rows_processed": 1280,
            },
        )
