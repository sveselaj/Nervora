"""The reference tools + their policy declarations.

Mock data is synthetic and deterministic. The ``run`` callables contain only
the tool's business logic; all governance (auth, RBAC, PII redaction, async
queueing, dry-run/approval handling) lives in the gateway executor and the
worker, never inside the tools themselves.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from telemetry import span

from tool_registry.registry import ToolRegistry
from tool_registry.spec import (
    Classification,
    ExecutionMode,
    PIIClass,
    ToolContext,
    ToolError,
    ToolResult,
    ToolSpec,
)

# --------------------------------------------------------------------------
# Synthetic HR / finance / CRM fixtures
# --------------------------------------------------------------------------
_EMPLOYEES: dict[str, dict[str, Any]] = {
    "E-1001": {
        "employee_id": "E-1001", "name": "Anika Brandt", "title": "Staff Engineer",
        "department_id": "FIN-100", "email": "anika.brandt@example.com",
        "phone": "+49 151 23456789", "national_id": "123-45-6789",
        "salary": 118000, "address": "Hauptstrasse 5, 10115 Berlin",
    },
    "E-2002": {
        "employee_id": "E-2002", "name": "Tomas Vogel", "title": "Account Director",
        "department_id": "SALES-200", "email": "tomas.vogel@example.com",
        "phone": "+49 160 99887766", "national_id": "987-65-4321",
        "salary": 96000, "address": "Ringstrasse 12, 80331 Munich",
    },
}

_LEAVE: dict[str, dict[str, Any]] = {
    "E-1001": {"annual_total": 30, "annual_taken": 12, "annual_remaining": 18, "sick_taken": 3},
    "E-2002": {"annual_total": 28, "annual_taken": 20, "annual_remaining": 8, "sick_taken": 1},
}

_INVOICES: dict[str, dict[str, Any]] = {
    "INV-5001": {"invoice_id": "INV-5001", "vendor": "Cloudworks GmbH", "amount": 24500,
                 "currency": "EUR", "status": "paid", "due_date": "2024-05-30"},
    "INV-5002": {"invoice_id": "INV-5002", "vendor": "DataPipe AG", "amount": 88200,
                 "currency": "EUR", "status": "overdue", "due_date": "2024-04-15"},
}

_CRM_ACCOUNTS: dict[str, dict[str, Any]] = {
    "ACC-300": {"account_id": "ACC-300", "name": "Helvetia Logistics",
                "tier": "silver", "owner": "tomas.vogel", "annual_value": 120000},
    "ACC-301": {"account_id": "ACC-301", "name": "Nordwind Retail",
                "tier": "bronze", "owner": "tomas.vogel", "annual_value": 45000},
}

_CUSTOMERS: dict[str, dict[str, Any]] = {
    "CUST-700": {"customer_id": "CUST-700", "name": "Helvetia Logistics AG",
                 "tier": "silver", "email": "ap@helvetia-logistics.example",
                 "phone": "+41 44 555 0100", "billing_currency": "EUR"},
    "CUST-701": {"customer_id": "CUST-701", "name": "Nordwind Retail GmbH",
                 "tier": "bronze", "email": "finance@nordwind-retail.example",
                 "phone": "+49 30 555 0199", "billing_currency": "EUR"},
}


# --------------------------------------------------------------------------
# Input models
# --------------------------------------------------------------------------
class EmployeeArgs(BaseModel):
    employee_id: str = Field(min_length=1)


class InvoiceArgs(BaseModel):
    invoice_id: str = Field(min_length=1)


class BudgetArgs(BaseModel):
    department_id: str = Field(min_length=1)
    period: str = Field(min_length=1, examples=["2024-Q2"])


class WorkflowArgs(BaseModel):
    workflow_name: str = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)


class CrmDryRunArgs(BaseModel):
    account_id: str = Field(min_length=1)
    proposed_changes: dict[str, Any]


class CrmExecuteArgs(BaseModel):
    account_id: str = Field(min_length=1)
    approved_change_id: str = Field(min_length=1)


class CustomerLookupArgs(BaseModel):
    customer_id: str = Field(min_length=1)


class InvoiceDraftArgs(BaseModel):
    customer_id: str = Field(min_length=1)
    amount: float = Field(gt=0)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    description: str = Field(default="", max_length=200)


# --------------------------------------------------------------------------
# Handlers
# --------------------------------------------------------------------------
def _get_employee_profile(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    emp = _EMPLOYEES.get(args["employee_id"])
    if emp is None:
        raise ToolError(f"employee {args['employee_id']} not found", code="NOT_FOUND")
    return ToolResult(output=dict(emp))


def _check_leave_balance(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    bal = _LEAVE.get(args["employee_id"])
    if bal is None:
        raise ToolError(f"no leave record for {args['employee_id']}", code="NOT_FOUND")
    return ToolResult(output={"employee_id": args["employee_id"], **bal})


def _get_invoice_status(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    inv = _INVOICES.get(args["invoice_id"])
    if inv is None:
        raise ToolError(f"invoice {args['invoice_id']} not found", code="NOT_FOUND")
    return ToolResult(output=dict(inv))


def _run_budget_variance_report(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    # Reads structured data via the Databricks SQL (mock) interface.
    with span("databricks.call", {"api": "sql.statements", "department_id": args["department_id"]}):
        res = ctx.databricks.execute_sql(
            "SELECT line_item, budget, actual FROM finance.budget_facts "
            "WHERE department_id = :department_id AND period = :period",
            parameters={"department_id": args["department_id"], "period": args["period"]},
        )
    records = res.as_records()
    total_budget = sum(r["budget"] for r in records)
    total_actual = sum(r["actual"] for r in records)
    return ToolResult(
        output={
            "department_id": args["department_id"],
            "period": args["period"],
            "statement_id": res.statement_id,
            "line_items": records,
            "total_budget": total_budget,
            "total_actual": total_actual,
            "total_variance": total_actual - total_budget,
        }
    )


def _trigger_databricks_workflow(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    # Executed by the WORKER (this tool is async). Triggers the Jobs API (mock).
    with span("databricks.call", {"api": "jobs.run-now", "workflow": args["workflow_name"]}):
        run = ctx.databricks.run_job(args["workflow_name"], args.get("parameters") or {})
    return ToolResult(
        output={
            "workflow_name": run.job_name,
            "run_id": run.run_id,
            "state": run.state,
            "output": run.output,
        }
    )


def _create_crm_update_dry_run(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    account = _CRM_ACCOUNTS.get(args["account_id"])
    if account is None:
        raise ToolError(f"account {args['account_id']} not found", code="NOT_FOUND")
    proposed = args["proposed_changes"]
    diff = []
    for key, new_value in proposed.items():
        old_value = account.get(key)
        if old_value != new_value:
            diff.append({"field": key, "from": old_value, "to": new_value})
    # NOTE: never mutates _CRM_ACCOUNTS — this is a dry run by construction.
    return ToolResult(
        output={
            "account_id": args["account_id"],
            "diff": diff,
            "human_approval_required": True,
            "writes_applied": False,
            "message": "Dry run only. No changes were written. Human approval is required "
                       "to execute via execute_crm_update with an approval token.",
        },
        metadata={"proposed_change": proposed, "resource_id": args["account_id"]},
    )


def _execute_crm_update(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    # Reached only if the executor's destructive gate passes (admin + valid,
    # approved approval token + tool enabled). Disabled in demo mode.
    account = _CRM_ACCOUNTS.get(args["account_id"])
    if account is None:
        raise ToolError(f"account {args['account_id']} not found", code="NOT_FOUND")
    return ToolResult(
        output={
            "account_id": args["account_id"],
            "approved_change_id": args["approved_change_id"],
            "writes_applied": True,
            "message": "CRM update applied (mock).",
        }
    )


def _crm_lookup_customer(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    cust = _CUSTOMERS.get(args["customer_id"])
    if cust is None:
        raise ToolError(f"customer {args['customer_id']} not found", code="NOT_FOUND")
    return ToolResult(output=dict(cust))


def _billing_create_invoice_draft(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    # A draft is a non-committal artifact by construction: it never issues an
    # invoice. The gateway routes this tool through the dry-run/approval gate, so
    # the draft is returned alongside a pending approval that a human must clear.
    cust = _CUSTOMERS.get(args["customer_id"])
    if cust is None:
        raise ToolError(f"customer {args['customer_id']} not found", code="NOT_FOUND")
    invoice = {
        "customer_id": args["customer_id"],
        "customer_name": cust["name"],
        "amount": args["amount"],
        "currency": args["currency"],
        "description": args["description"],
    }
    # Deterministic draft reference (no randomness — responses stay reproducible).
    draft_id = f"DRAFT-{args['customer_id']}-{int(args['amount'])}-{args['currency']}"
    return ToolResult(
        output={
            "draft_id": draft_id,
            "status": "draft",
            "writes_applied": False,
            "human_approval_required": True,
            "invoice": invoice,
            "message": "Invoice draft created. No invoice was issued. Human approval is "
                       "required to finalize this draft via the approvals endpoint.",
        },
        metadata={"proposed_change": invoice, "resource_id": draft_id},
    )


# --------------------------------------------------------------------------
# Registry assembly
# --------------------------------------------------------------------------
HR_ROLES = ("hr_agent", "admin_agent")
FINANCE_ROLES = ("finance_agent", "admin_agent")
SALES_ROLES = ("sales_agent", "admin_agent")
ADMIN_ONLY = ("admin_agent",)

_EMPLOYEE_SENSITIVE = frozenset({"email", "phone", "national_id", "salary", "address"})
_CUSTOMER_SENSITIVE = frozenset({"email", "phone"})


def build_registry(*, demo_mode: bool = True) -> ToolRegistry:
    reg = ToolRegistry()

    reg.register(ToolSpec(
        name="get_employee_profile",
        description="Return an employee's HR profile. Sensitive PII fields are redacted by default.",
        required_roles=HR_ROLES,
        classification=Classification.READ,
        execution_mode=ExecutionMode.SYNC,
        pii_classification=PIIClass.SENSITIVE,
        dry_run_required=False,
        input_model=EmployeeArgs,
        run=_get_employee_profile,
        sensitive_fields=_EMPLOYEE_SENSITIVE,
        raw_pii_roles=(),  # nobody gets raw PII in the reference config
    ))

    reg.register(ToolSpec(
        name="check_leave_balance",
        description="Return an employee's leave balance (no direct PII).",
        required_roles=HR_ROLES,
        classification=Classification.READ,
        execution_mode=ExecutionMode.SYNC,
        pii_classification=PIIClass.LOW,
        dry_run_required=False,
        input_model=EmployeeArgs,
        run=_check_leave_balance,
    ))

    reg.register(ToolSpec(
        name="get_invoice_status",
        description="Return the status of a finance invoice.",
        required_roles=FINANCE_ROLES,
        classification=Classification.READ,
        execution_mode=ExecutionMode.SYNC,
        pii_classification=PIIClass.NONE,
        dry_run_required=False,
        input_model=InvoiceArgs,
        run=_get_invoice_status,
    ))

    reg.register(ToolSpec(
        name="run_budget_variance_report",
        description="Compute budget vs actual variance for a department/period via Databricks SQL.",
        required_roles=FINANCE_ROLES,
        classification=Classification.READ,
        execution_mode=ExecutionMode.SYNC,
        pii_classification=PIIClass.NONE,
        dry_run_required=False,
        input_model=BudgetArgs,
        run=_run_budget_variance_report,
    ))

    reg.register(ToolSpec(
        name="trigger_databricks_workflow",
        description="Trigger a Databricks workflow/job asynchronously via the job queue.",
        required_roles=FINANCE_ROLES,
        classification=Classification.WRITE,
        execution_mode=ExecutionMode.ASYNC,  # long-running -> queued, never sync
        pii_classification=PIIClass.NONE,
        dry_run_required=False,
        input_model=WorkflowArgs,
        run=_trigger_databricks_workflow,
    ))

    reg.register(ToolSpec(
        name="create_crm_update_dry_run",
        description="Compute a proposed CRM update diff. Never writes; returns 'human approval required'.",
        required_roles=SALES_ROLES,
        classification=Classification.WRITE,
        execution_mode=ExecutionMode.SYNC,
        pii_classification=PIIClass.NONE,
        dry_run_required=True,  # always dry-run by construction
        input_model=CrmDryRunArgs,
        run=_create_crm_update_dry_run,
    ))

    reg.register(ToolSpec(
        name="execute_crm_update",
        description="Apply an approved CRM update. DESTRUCTIVE — disabled in demo mode; "
                    "requires Admin Agent and a valid approval token.",
        required_roles=ADMIN_ONLY,
        classification=Classification.DESTRUCTIVE,
        execution_mode=ExecutionMode.SYNC,
        pii_classification=PIIClass.NONE,
        dry_run_required=False,
        input_model=CrmExecuteArgs,
        run=_execute_crm_update,
        requires_approval_token=True,
        enabled=not demo_mode,  # hard kill-switch in demo
    ))

    # --- Phase 1 demo flow tools ---------------------------------------------
    # A safe read and an approval-gated write, used by the README "Nervora demo
    # flow". Namespaced names (crm.* / billing.*) anticipate MCP tool namespacing.
    reg.register(ToolSpec(
        name="crm.lookup_customer",
        description="Look up a CRM customer record. Contact PII (email, phone) is redacted by default.",
        required_roles=SALES_ROLES,
        classification=Classification.READ,
        execution_mode=ExecutionMode.SYNC,
        pii_classification=PIIClass.SENSITIVE,
        dry_run_required=False,
        input_model=CustomerLookupArgs,
        run=_crm_lookup_customer,
        sensitive_fields=_CUSTOMER_SENSITIVE,
        raw_pii_roles=(),
    ))

    reg.register(ToolSpec(
        name="billing.create_invoice_draft",
        description="Draft an invoice for a customer. Writes nothing; requires human approval "
                    "to finalize (returns a pending approval id).",
        required_roles=FINANCE_ROLES,
        classification=Classification.WRITE,
        execution_mode=ExecutionMode.SYNC,
        pii_classification=PIIClass.NONE,
        dry_run_required=True,  # routed through the dry-run/approval gate
        input_model=InvoiceDraftArgs,
        run=_billing_create_invoice_draft,
    ))

    return reg
