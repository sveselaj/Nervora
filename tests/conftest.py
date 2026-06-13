"""Shared pytest fixtures.

Everything runs against an isolated SQLite database per test so the suite needs
no Postgres, no queue broker and no network — the local queue backend and the
mock Databricks connector make the full async path testable in-process.
"""

from __future__ import annotations

from functools import partial

import pytest

# Ensure the queue table is registered on the shared metadata.
import servicebus.local  # noqa: F401


@pytest.fixture
def settings(tmp_path, monkeypatch):
    db_path = tmp_path / "test.sqlite3"
    monkeypatch.setenv("APP_ENV", "demo")
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_path}")
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("DEV_TOKEN_SIGNING_SECRET", "test-secret")
    monkeypatch.setenv("QUEUE_BACKEND", "local")
    monkeypatch.setenv("DATABRICKS_MODE", "mock")
    monkeypatch.setenv("OTEL_ENABLED", "false")
    monkeypatch.setenv("ADMIN_APPROVAL_TOKEN", "")

    import common.settings as cs

    cs.get_settings.cache_clear()
    s = cs.get_settings()

    from audit import create_all

    create_all(s.database_url)
    yield s
    cs.get_settings.cache_clear()


@pytest.fixture
def session_factory(settings):
    from audit import session_scope

    return partial(session_scope, settings.database_url)


@pytest.fixture
def executor(settings, session_factory):
    from app.executor import Executor
    from databricks_connector import build_connector
    from servicebus import build_queue
    from tool_registry import build_default_registry

    return Executor(
        registry=build_default_registry(demo_mode=settings.is_demo),
        settings=settings,
        queue=build_queue(settings),
        databricks=build_connector(settings),
        session_factory=session_factory,
    )


@pytest.fixture
def principal_factory():
    from auth import Principal

    def make(role: str, subject: str = "u@test", agent_id: str = "agent-test"):
        return Principal(subject=subject, agent_id=agent_id, role=role,
                         scopes=("tools.invoke",))

    return make
