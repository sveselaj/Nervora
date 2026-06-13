# Nervora — RBAC matrix

The authoritative source is the tool registry
([`packages/tool_registry/tools.py`](../packages/tool_registry/tools.py)); this
document is the human-readable rendering. At runtime the same metadata is
snapshotted into the `tool_policies` table and served at `GET /tools`.

## Roles

| Role | Persona |
|------|---------|
| `hr_agent` | HR domain agent |
| `finance_agent` | Finance domain agent |
| `sales_agent` | Sales / CRM domain agent |
| `admin_agent` | Cross-domain admin (explicitly granted per tool; not a wildcard) |

## Full tool policy matrix

| Tool | Required roles | Class | Mode | PII class | Dry-run req. | Approval token | Enabled (demo) |
|------|----------------|-------|------|-----------|:------------:|:--------------:|:--------------:|
| `get_employee_profile` | hr_agent, admin_agent | read | sync | **sensitive** | no | no | yes |
| `check_leave_balance` | hr_agent, admin_agent | read | sync | low | no | no | yes |
| `get_invoice_status` | finance_agent, admin_agent | read | sync | none | no | no | yes |
| `run_budget_variance_report` | finance_agent, admin_agent | read | sync | none | no | no | yes |
| `trigger_databricks_workflow` | finance_agent, admin_agent | write | **async** | none | no | no | yes |
| `create_crm_update_dry_run` | sales_agent, admin_agent | write | sync | none | **yes** | no | yes |
| `execute_crm_update` | admin_agent | **destructive** | sync | none | no | **yes** | **no** |

## Access grid (who can call what)

| Tool | HR | Finance | Sales | Admin |
|------|:--:|:------:|:-----:|:-----:|
| `get_employee_profile` | ✅ | ❌ | ❌ | ✅ |
| `check_leave_balance` | ✅ | ❌ | ❌ | ✅ |
| `get_invoice_status` | ❌ | ✅ | ❌ | ✅ |
| `run_budget_variance_report` | ❌ | ✅ | ❌ | ✅ |
| `trigger_databricks_workflow` | ❌ | ✅ | ❌ | ✅ |
| `create_crm_update_dry_run` | ❌ | ❌ | ✅ | ✅ |
| `execute_crm_update` | ❌ | ❌ | ❌ | ✅* |

`*` Even for the admin role, `execute_crm_update` is **disabled in demo mode**
and, when enabled, additionally requires a valid approval token plus an
`approved` approval record.

## Enforcement notes

- **Deny by default** — absence from "Required roles" means denied + logged.
- **No implicit admin** — admin appears in "Required roles" only where intended.
- **PII class `sensitive`** triggers field-level redaction by default; in the
  reference config no role is granted raw PII (`raw_pii_roles` is empty).
- **`async` mode** means the gateway will never execute the tool synchronously —
  it is always queued for the worker.
- **`dry_run_required`** tools cannot write; they produce a diff + approval.
