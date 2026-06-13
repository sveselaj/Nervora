-- Secure MCP Gateway — audit + execution schema (PostgreSQL reference DDL)
--
-- This file documents the schema. At runtime the tables are created by
-- SQLAlchemy (audit.create_all); this DDL is the human-readable source of
-- truth and can be used to bootstrap a database directly.

CREATE TABLE IF NOT EXISTS audit_events (
    id          BIGSERIAL PRIMARY KEY,
    trace_id    VARCHAR(64)  NOT NULL,
    request_id  VARCHAR(64)  NOT NULL,
    event_type  VARCHAR(64)  NOT NULL,
    user_id     VARCHAR(128) NOT NULL DEFAULT '',
    agent_id    VARCHAR(128) NOT NULL DEFAULT '',
    role        VARCHAR(64)  NOT NULL DEFAULT '',
    tool_name   VARCHAR(128) NOT NULL DEFAULT '',
    decision    VARCHAR(32)  NOT NULL DEFAULT '',
    detail      JSONB        NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_audit_events_trace   ON audit_events (trace_id);
CREATE INDEX IF NOT EXISTS ix_audit_events_request ON audit_events (request_id);
CREATE INDEX IF NOT EXISTS ix_audit_events_tool    ON audit_events (tool_name);

CREATE TABLE IF NOT EXISTS tool_calls (
    id               BIGSERIAL PRIMARY KEY,
    trace_id         VARCHAR(64)  NOT NULL,
    request_id       VARCHAR(64)  NOT NULL UNIQUE,
    user_id          VARCHAR(128) NOT NULL DEFAULT '',
    agent_id         VARCHAR(128) NOT NULL DEFAULT '',
    role             VARCHAR(64)  NOT NULL DEFAULT '',
    tool_name        VARCHAR(128) NOT NULL,
    input_hash       VARCHAR(64)  NOT NULL,
    redaction_status VARCHAR(32)  NOT NULL DEFAULT 'none',
    decision         VARCHAR(32)  NOT NULL,  -- allowed|denied|dry_run|queued|executed|failed
    error_code       VARCHAR(64),
    latency_ms       DOUBLE PRECISION NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_tool_calls_trace    ON tool_calls (trace_id);
CREATE INDEX IF NOT EXISTS ix_tool_calls_tool     ON tool_calls (tool_name);
CREATE INDEX IF NOT EXISTS ix_tool_calls_decision ON tool_calls (decision);

CREATE TABLE IF NOT EXISTS tool_policies (
    tool_name          VARCHAR(128) PRIMARY KEY,
    description        TEXT NOT NULL DEFAULT '',
    required_roles     JSONB NOT NULL DEFAULT '[]',
    classification     VARCHAR(32) NOT NULL,  -- read|write|destructive
    execution_mode     VARCHAR(16) NOT NULL,  -- sync|async
    pii_classification VARCHAR(32) NOT NULL,  -- none|low|sensitive
    dry_run_required   BOOLEAN NOT NULL DEFAULT false,
    enabled            BOOLEAN NOT NULL DEFAULT true,
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS async_jobs (
    job_id          VARCHAR(64) PRIMARY KEY,
    trace_id        VARCHAR(64) NOT NULL,
    request_id      VARCHAR(64) NOT NULL,
    tool_name       VARCHAR(128) NOT NULL,
    idempotency_key VARCHAR(96) NOT NULL,
    user_id         VARCHAR(128) NOT NULL DEFAULT '',
    agent_id        VARCHAR(128) NOT NULL DEFAULT '',
    role            VARCHAR(64)  NOT NULL DEFAULT '',
    payload         JSONB NOT NULL DEFAULT '{}',
    status          VARCHAR(32) NOT NULL DEFAULT 'queued', -- queued|running|succeeded|failed|dead_letter
    attempts        INT NOT NULL DEFAULT 0,
    result          JSONB,
    error_code      VARCHAR(64),
    error_detail    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_async_jobs_status ON async_jobs (status);
CREATE INDEX IF NOT EXISTS ix_async_jobs_idk    ON async_jobs (idempotency_key);

CREATE TABLE IF NOT EXISTS approvals (
    approval_id        VARCHAR(64) PRIMARY KEY,
    tool_name          VARCHAR(128) NOT NULL,
    resource_id        VARCHAR(128) NOT NULL,
    proposed_change    JSONB NOT NULL DEFAULT '{}',
    requested_by_agent VARCHAR(128) NOT NULL DEFAULT '',
    requested_by_role  VARCHAR(64)  NOT NULL DEFAULT '',
    status             VARCHAR(32) NOT NULL DEFAULT 'pending', -- pending|approved|rejected|consumed
    approved_by        VARCHAR(128),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    idempotency_key VARCHAR(96) PRIMARY KEY,
    tool_name       VARCHAR(128) NOT NULL,
    job_id          VARCHAR(64),
    input_hash      VARCHAR(64) NOT NULL,
    status          VARCHAR(32) NOT NULL DEFAULT 'reserved', -- reserved|completed
    result          JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
