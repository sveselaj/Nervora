#!/usr/bin/env python3
"""Generate the Nervora architecture diagram (SVG + PNG).

Data-driven, dependency-light: the layout is described as plain box/arrow data
and emitted as a clean, engineer-style SVG (no stock icons). PNG rendering uses
cairosvg if available.

    python docs/diagrams/generate_diagram.py

Outputs:
    docs/diagrams/nervora-architecture.svg
    docs/diagrams/nervora-architecture.png   (if cairosvg is installed)
"""

from __future__ import annotations

import html
import os

W, H = 1640, 980

# --- palette --------------------------------------------------------------
INK = "#16202b"
MUTED = "#5b6b7b"
BG = "#f7f9fc"
GRID = "#e7edf4"
ARROW = "#5b6b7b"
ARROW_DASH = "#9aa8b6"

C = {
    "agent": "#334155",
    "gateway": "#1f5f9e",
    "auth": "#2563eb",
    "rbac": "#d97706",
    "registry": "#475569",
    "route": "#0e7490",
    "exec": "#0f766e",
    "pii": "#9333ea",
    "bus": "#0891b2",
    "worker": "#7c3aed",
    "databricks": "#c2410c",
    "dlq": "#dc2626",
    "audit": "#2d6a8e",
    "otel": "#64748b",
}

FONT = "'Segoe UI', 'Helvetica Neue', Arial, sans-serif"
MONO = "'SFMono-Regular', 'JetBrains Mono', Consolas, monospace"

parts: list[str] = []


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def box(x, y, w, h, color, title, subs=None, *, mono_title=False, title_size=16):
    """A node: white fill, colored border + left accent tab, colored title."""
    subs = subs or []
    g = [f'<g>']
    g.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="11" ry="11" '
             f'fill="#ffffff" stroke="{color}" stroke-width="2"/>')
    # left accent tab
    g.append(f'<rect x="{x}" y="{y}" width="7" height="{h}" rx="3.5" ry="3.5" fill="{color}"/>')
    tx = x + 20
    ty = y + 26
    tfont = MONO if mono_title else FONT
    g.append(f'<text x="{tx}" y="{ty}" font-family="{tfont}" font-size="{title_size}" '
             f'font-weight="700" fill="{color}">{esc(title)}</text>')
    sy = ty + 21
    for s in subs:
        g.append(f'<text x="{tx}" y="{sy}" font-family="{FONT}" font-size="12.5" '
                 f'fill="{MUTED}">{esc(s)}</text>')
        sy += 18
    g.append('</g>')
    parts.append("".join(g))


def label(x, y, text, *, mono=False, anchor="middle", fill=MUTED, size=12, bg=True):
    f = MONO if mono else FONT
    w = int(len(text) * (size * 0.56)) + 12
    if anchor == "middle":
        rx = x - w / 2
    elif anchor == "start":
        rx = x - 6
    else:
        rx = x - w + 6
    if bg:
        parts.append(f'<rect x="{rx:.0f}" y="{y-size+1}" width="{w}" height="{size+7}" '
                     f'rx="4" fill="{BG}" opacity="0.92"/>')
    parts.append(f'<text x="{x}" y="{y}" font-family="{f}" font-size="{size}" '
                 f'fill="{fill}" text-anchor="{anchor}">{esc(text)}</text>')


def arrow(x1, y1, x2, y2, *, dashed=False, marker="end", curve=None):
    dash = ' stroke-dasharray="6 5"' if dashed else ""
    color = ARROW_DASH if dashed else ARROW
    me = ' marker-end="url(#arrow)"' if marker in ("end", "both") else ""
    ms = ' marker-start="url(#arrowback)"' if marker in ("both",) else ""
    if curve is not None:
        cx, cy = curve
        parts.append(f'<path d="M {x1} {y1} Q {cx} {cy} {x2} {y2}" fill="none" '
                     f'stroke="{color}" stroke-width="2"{dash}{me}{ms}/>')
    else:
        parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" '
                     f'stroke-width="2"{dash}{me}{ms}/>')


def chevron(cx, y, color=ARROW):
    parts.append(f'<path d="M {cx-7} {y} L {cx+7} {y} L {cx} {y+8} Z" fill="{color}"/>')


# ==========================================================================
# Build the SVG
# ==========================================================================
parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
             f'viewBox="0 0 {W} {H}" font-family="{FONT}">')

# defs: arrowheads + subtle dot grid
parts.append(
    '<defs>'
    '<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
    f'markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{ARROW}"/></marker>'
    '<marker id="arrowback" viewBox="0 0 10 10" refX="1" refY="5" markerWidth="7" '
    f'markerHeight="7" orient="auto-start-reverse"><path d="M10,0 L0,5 L10,10 z" fill="{ARROW}"/></marker>'
    f'<pattern id="dots" width="26" height="26" patternUnits="userSpaceOnUse">'
    f'<circle cx="1.2" cy="1.2" r="1.2" fill="{GRID}"/></pattern>'
    '</defs>'
)
parts.append(f'<rect width="{W}" height="{H}" fill="{BG}"/>')
parts.append(f'<rect width="{W}" height="{H}" fill="url(#dots)"/>')

# --- header ---------------------------------------------------------------
parts.append(f'<text x="40" y="56" font-family="{FONT}" font-size="40" font-weight="800" '
             f'fill="{INK}">Nervora</text>')
parts.append(f'<text x="44" y="84" font-family="{FONT}" font-size="16.5" fill="{MUTED}">'
             f'Secure MCP Gateway for Enterprise AI Tool Execution</text>')
# badges (top-right)
for i, txt in enumerate(["Internal R&D Reference Architecture", "mock-first · synthetic data"]):
    bx, by = W - 360, 26 + i * 40
    parts.append(f'<rect x="{bx}" y="{by}" width="320" height="32" rx="16" fill="#eef2f7" '
                 f'stroke="#cfd9e4"/>')
    parts.append(f'<text x="{bx+160}" y="{by+21}" font-family="{FONT}" font-size="13" '
                 f'fill="{MUTED}" text-anchor="middle">{esc(txt)}</text>')

# --- AI client / agent ----------------------------------------------------
box(40, 392, 196, 122, C["agent"], "AI Client / Agent",
    ["Autonomous agent or app.", "Holds a bearer token —", "capabilities, not credentials."])

# --- Gateway panel --------------------------------------------------------
gx, gy, gw, gh = 300, 124, 548, 612
parts.append(f'<rect x="{gx}" y="{gy}" width="{gw}" height="{gh}" rx="16" fill="#eef5fb" '
             f'stroke="{C["gateway"]}" stroke-width="2.5"/>')
parts.append(f'<rect x="{gx}" y="{gy}" width="{gw}" height="48" rx="16" fill="{C["gateway"]}"/>')
parts.append(f'<rect x="{gx}" y="{gy+24}" width="{gw}" height="24" fill="{C["gateway"]}"/>')
parts.append(f'<text x="{gx+22}" y="{gy+31}" font-family="{FONT}" font-size="18" '
             f'font-weight="700" fill="#ffffff">Nervora MCP Gateway · FastAPI</text>')
parts.append(f'<text x="{gx+gw-18}" y="{gy+31}" font-family="{MONO}" font-size="12.5" '
             f'fill="#cfe4f6" text-anchor="end">POST /tools/{{tool}}/invoke</text>')

ix, iw = gx + 22, gw - 44
stages = [
    (C["auth"], "1 · OIDC / Entra ID validation", "span: auth.validate · RS256/JWKS (prod) · HS256 (dev)"),
    (C["rbac"], "2 · Tool-Level RBAC", "deny-by-default · admin is not a wildcard · denials logged"),
    (C["registry"], "3 · Tool Registry", "published tools only — no hidden tools · arg validation"),
    (C["route"], "4 · Route by classification", "sync · async · dry-run · destructive (approval-gated)"),
    (C["exec"], "5 · Tool execution (sync)", "read tools run in-process · ToolError → audit"),
]
sy = gy + 64
sh = 56
for color, title, sub in stages:
    box(ix, sy, iw, sh, color, title, [sub], title_size=14.5)
    sy += sh + 14

# PII redaction boundary (dashed band) just above the response
by = sy + 2
parts.append(f'<line x1="{gx+14}" y1="{by}" x2="{gx+gw-14}" y2="{by}" stroke="{C["pii"]}" '
             f'stroke-width="2.5" stroke-dasharray="9 6"/>')
label(gx + gw / 2, by - 7, "PII REDACTION BOUNDARY — nothing crosses un-redacted",
      fill=C["pii"], size=12.5)
box(ix, by + 12, iw, sh, C["pii"], "6 · PII Redaction",
    ["field masking + regex sweep · span: pii.redaction"], title_size=14.5)

# small chevrons between stacked stages
cxs = ix + iw / 2
for k in range(4):
    chevron(cxs, gy + 64 + sh + 1 + k * (sh + 14))

# --- request / response arrows (agent <-> gateway) ------------------------
arrow(236, 430, gx, 200, curve=(280, 300))
label(268, 250, "request", mono=False, anchor="start", size=12)
arrow(gx, by + 38, 236, 478, dashed=True, curve=(280, 540))
label(250, 600, "200 · result (redacted) + X-Trace-Id", anchor="start", size=11.5)

# --- async plane (right) --------------------------------------------------
ax = 920
box(ax, 300, 340, 92, C["bus"], "Azure Service Bus (abstraction)",
    ["local Postgres queue ↔ Azure Service Bus", "message: job_id + idempotency_key"])
box(ax, 452, 340, 92, C["worker"], "Worker Service",
    ["idempotency guard · peek-lock", "span: worker.execute"])
box(ax, 604, 340, 92, C["databricks"], "Databricks Connector",
    ["SQL Warehouse · Jobs / Workflows API", "mock-first · real interface prepared"])
box(1320, 452, 260, 92, C["dlq"], "DLQ / Retry / Idempotency",
    ["retry = abandon → redeliver", "dead-letter @ max delivery count"])

# route(async) -> bus
arrow(gx + gw, 124 + 64 + 3 * (sh + 14) + sh / 2, ax, 346)
label((gx + gw + ax) / 2, 320, "async · 202 queued", size=12)

# bus <-> worker (receive down / retry up, offset)
arrow(ax + 250, 392, ax + 250, 452)
label(ax + 250, 432, "receive", size=11.5)
arrow(ax + 90, 452, ax + 90, 392, dashed=True)
label(ax + 92, 432, "retry", size=11, anchor="end")

# worker -> databricks
arrow(ax + 170, 544, ax + 170, 604)
label(ax + 170, 580, "span: databricks.call", size=11.5)

# worker -> DLQ
arrow(ax + 340, 498, 1320, 498)
label((ax + 340 + 1320) / 2, 489, "max delivery", size=11.5)

# --- bottom cross-cutting lane: audit + otel ------------------------------
box(40, 772, 840, 168, C["audit"], "PostgreSQL — Audit Log (append-only)",
    ["audit_events · tool_calls · tool_policies · async_jobs · approvals · idempotency_keys",
     "one tool_calls + one audit_events row per outcome:",
     "allowed · denied · dry_run · queued · executed · failed",
     "fields: trace_id · request_id · user/agent/role · input_hash · redaction_status · latency_ms"])

box(920, 772, 660, 168, C["otel"], "OpenTelemetry Tracing",
    ["spans: auth · rbac · pii · tool.execute · queue.publish · worker · databricks · audit",
     "trace_id echoed in X-Trace-Id response header + stored on every audit row",
     "exporter → OTel Collector → Grafana (console fallback for local runs)",
     "one id ties an API response → its spans → its audit / job records"])

# gateway -> audit
arrow(gx + 120, gy + gh, 360, 772)
label(300, 758, "audit write (every decision)", anchor="start", size=11.5)
# worker -> audit (dashed, curves left under the async plane)
arrow(ax, 520, 880, 812, dashed=True, curve=(820, 640))
label(792, 690, "audit", anchor="end", size=11.5)
# instrumentation hint: gateway + worker -> otel (dashed, faint)
arrow(848, 700, 1100, 772, dashed=True)
label(980, 742, "instrumented", size=11)

parts.append('</svg>')
svg = "\n".join(parts)

here = os.path.dirname(os.path.abspath(__file__))
svg_path = os.path.join(here, "nervora-architecture.svg")
with open(svg_path, "w", encoding="utf-8") as f:
    f.write(svg)
print(f"wrote {svg_path}")

try:
    import cairosvg

    png_path = os.path.join(here, "nervora-architecture.png")
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=png_path,
                     output_width=W * 2, output_height=H * 2, background_color="#ffffff")
    print(f"wrote {png_path}")
except Exception as exc:  # pragma: no cover
    print(f"PNG not generated ({exc}); install cairosvg to render PNG.")
