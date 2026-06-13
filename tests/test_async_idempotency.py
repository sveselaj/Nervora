"""Async path: queue -> worker -> idempotency + retry/DLQ."""

from audit import AuditRepository, session_scope


def _worker(settings):
    from worker import Worker

    return Worker(settings)


def test_async_tool_is_queued_not_run_sync(executor, principal_factory):
    fin = principal_factory("finance_agent")
    out = executor.invoke(principal=fin, tool_name="trigger_databricks_workflow",
                          arguments={"workflow_name": "wf1", "parameters": {}},
                          idempotency_key="k1")
    assert out.decision == "queued"
    assert out.job_id and out.result is None  # no synchronous result


def test_worker_processes_queued_job(executor, principal_factory, settings):
    fin = principal_factory("finance_agent")
    out = executor.invoke(principal=fin, tool_name="trigger_databricks_workflow",
                          arguments={"workflow_name": "wf1", "parameters": {"p": 1}},
                          idempotency_key="k-run")
    processed = _worker(settings).poll_once()
    assert processed == 1

    with session_scope(settings.database_url) as s:
        job = AuditRepository(s).get_job(out.job_id)
    assert job.status == "succeeded"
    assert job.result["state"] == "SUCCESS"


def test_duplicate_idempotency_key_returns_same_job(executor, principal_factory):
    fin = principal_factory("finance_agent")
    a = executor.invoke(principal=fin, tool_name="trigger_databricks_workflow",
                        arguments={"workflow_name": "wf", "parameters": {}},
                        idempotency_key="dupe")
    b = executor.invoke(principal=fin, tool_name="trigger_databricks_workflow",
                        arguments={"workflow_name": "wf", "parameters": {}},
                        idempotency_key="dupe")
    assert a.job_id == b.job_id
    assert "duplicate" in (b.message or "")


def test_idempotency_prevents_duplicate_execution_on_redelivery(executor, principal_factory, settings):
    """A second queue message with the same key must not re-execute the tool."""
    fin = principal_factory("finance_agent")
    out = executor.invoke(principal=fin, tool_name="trigger_databricks_workflow",
                          arguments={"workflow_name": "wf", "parameters": {}},
                          idempotency_key="once")
    worker = _worker(settings)
    assert worker.poll_once() == 1  # first run -> completes

    # Simulate a duplicate delivery by re-publishing the same body.
    worker.queue.publish({
        "job_id": out.job_id, "idempotency_key": "once",
        "tool_name": "trigger_databricks_workflow",
        "trace_id": out.trace_id, "arguments": {"workflow_name": "wf", "parameters": {}},
    })
    assert worker.poll_once() == 1  # message handled...

    with session_scope(settings.database_url) as s:
        events = AuditRepository(s).recent_events(limit=50)
    # ...but recognised as a duplicate, not a second execution.
    assert any(e.event_type == "job.duplicate_skipped" for e in events)


def test_auto_idempotency_key_generated_when_absent(executor, principal_factory):
    fin = principal_factory("finance_agent")
    out = executor.invoke(principal=fin, tool_name="trigger_databricks_workflow",
                          arguments={"workflow_name": "wf", "parameters": {}})
    assert out.decision == "queued" and out.job_id
