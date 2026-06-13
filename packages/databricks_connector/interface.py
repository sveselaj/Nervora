"""Abstract Databricks connector contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SqlStatementResult:
    statement_id: str
    columns: list[str]
    rows: list[list[Any]]
    row_count: int

    def as_records(self) -> list[dict[str, Any]]:
        return [dict(zip(self.columns, row, strict=False)) for row in self.rows]


@dataclass
class JobRunResult:
    run_id: str
    job_name: str
    state: str  # PENDING | RUNNING | SUCCESS | FAILED
    output: dict[str, Any] = field(default_factory=dict)


class DatabricksConnector(ABC):
    """Minimal surface the gateway needs: run SQL, trigger a job/workflow."""

    @abstractmethod
    def execute_sql(self, statement: str, parameters: dict[str, Any] | None = None) -> SqlStatementResult: ...

    @abstractmethod
    def run_job(self, workflow_name: str, parameters: dict[str, Any] | None = None) -> JobRunResult: ...
