# Core Realm (LDA space) — How this agent works
_Reference doc for the Core realm agent in the parallel `egym-flow-metrics-lda` repo.
Mirrors the live repo's Core automation (`monthly_run.py`, see the live agent's own
`REALM_CORE.md`) — same engine, same teams, same cadence, same methodology. Adapted
ONLY for independent per-realm storage so this agent never touches Machine/Apps/
Wellpass data or the shared cross-realm pages._

## Status
- Onboarded to the LDA space (parallel repo `oleksandrabobina/egym-flow-metrics-lda`,
  independent of the live repo `egym-flow-metrics-live`, which stays untouched).
- Own data file: **`data-core.json`** at repo root — contains ONLY
  `{"realms": {"core": {...}}}`. Seeded with Core's real history (Jun 25 → Jul 26,
  5 teams) copied verbatim from the live repo's `data.json` at seeding time.
  Never write to `data-machine.json`, `data-apps.json`, or `data-wellpass.json`.
- Own dashboard pages: **`core/`** folder (`core/index.html`, `core/realm-dashboard.html`,
  5 team pages). Never write to `machine/`, `apps/`, `wellpass/`, or the 3 shared
  cross-realm pages (`index.html`, `global-dashboard.html`, `upload.html` at repo
  root) — those are owned exclusively by the Space agent
  (`scripts/update_shared_pages.py`).
- Schedule: cadence day **20** (rolled to next business day on weekends — same rule
  as the live Core realm). No schedule trigger is auto-created by this doc; whoever
  sets up this agent configures it explicitly.

## Teams (5) — `CORE_TEAMS` in `compute_jira.py` (shared, unmodified)
| key | display | Jira scope |
|---|---|---|
| ul | Users & Locations | project GXY |
| cw | Core-Workouts | project CW |
| ox | Operator Experience | project OX |
| ds | Data Science | project DS (moved Apps→Core, Jun 2026) |
| mm | API Platform (ex-MMS Connect) | project CONN |

All 5 are plain project scopes (`worked_only=False`, `done_extra=None`). Each team
carries BOTH `fl1` (tasks) and `fl2` (epics) — the "standard realm" schema, so
`update_data_live.py`'s generic `update()`/`latest_values()`/`month_present()`
functions work directly (no MAP/staging layer needed, unlike Machine's split
FL1-team/FL2-card schema).

## Engine (unchanged from live Core — see FLOW_METRICS_SPEC.md for full methodology)
- FL1 issue types include Story/Task/Maintenance/Bug/Release — bugs INCLUDED in
  throughput. Cycle time = p85 linear. WIP aging R/Y/G = p70/p85 linear.
- FL2 delivered = status changed to Done during rolling 120-day window, passed
  through a Doing stage. FL2 percentile estimator = nearest-rank 'higher'.
  Evergreen/umbrella exclusions: `FL2_EXCLUDE = {GXY-4979, GXY-4966, GXY-7159, GXY-7928}`.
- Core has a DORA stub page (placeholder); DORA is not computed by the engine.

## Own orchestrator: `core_publish.py` (reusable, mock-tested)
Direct single-shot analogue of the live repo's `monthly_run.py` Core path (Core is
light — 5 teams, no batching needed, unlike Machine's `machine_monthly.py`/
`machine_publish.py` split). Three modes:
```
# 1. compute + append + push data-core.json + regenerate core/ dashboards (idempotent)
uv run --with numpy,tzdata python core_publish.py <jira> <gh> <YYYY-MM-DD> --publish \
    [--force-anomalies]
# 2. build the report PDF (agent-authored notes injected)
uv run --with numpy,tzdata,reportlab python core_publish.py <jira> <gh> <YYYY-MM-DD> \
    --report --notes=notes_core.json --out=/agent/home/Core_Realm_flow_metrics_YYYY_MM.pdf
# 3. post to the LDA channel (only after Alexa approves the DM/preview)
uv run --with numpy,tzdata python core_publish.py <jira> <gh> <YYYY-MM-DD> \
    --deliver --slack=<slack_conn> --pdf=/agent/home/Core_Realm_flow_metrics_YYYY_MM.pdf
```
`notes_core.json` shape: `{"tasks": [...], "epics": [...], "epics_callout": "..."}`
(same as the live repo's `deliver_report.py` narrative format).

Uses shared reusable modules from `scripts/`: `compute_jira.py` (engine, unmodified),
`update_data_live.py` (v2, generalized with a `data_path` param — Core passes
`data_path='data-core.json'`), `generate_dashboards_live.py` (v8, generalized with a
`data_path`/`path` param — Core passes `data_path='data-core.json'`),
`report_checks.py` (hard validation + soft anomaly gate, unmodified),
`build_pdf_realm.py` (PDF builder, unmodified).

Safety validated via isolated mock-harness test (intercepting only the GitHub write
tool; real reads bypassed with canned Core-shaped data): confirmed `--publish`
reads/writes ONLY `data-core.json` and writes dashboard HTML ONLY under `core/`,
zero touch of `data-machine.json` or `machine/`. Idempotency (re-run same month =
no-op data write) and the anomaly-hold gate were also verified.

## Delivery
- **Slack**, channel **#sw-team-lda** `C9CBU5S3C`.
- Tags: **Alexa Bobina** `UG3UBQWDP`, **Mais Alshadidi** `U0ASNNXD31B` — same routing
  as the live Core realm. Escalate: Alexa `UG3UBQWDP`.
- Once this LDA Core agent has its own stable Agent ID/link, consider swapping the
  escalation mention from `<@UG3UBQWDP>` to a direct link to this agent (the pattern
  the Machine LDA agent already uses in `machine_publish.py`'s `deliver()`) — that
  is the whole point of the LDA-space migration: routing questions to the
  realm agent instead of bottlenecking through Alexa.

## Corrections (report section — NEVER "errata")
Standard methodology includes bugs in throughput. Two Core teams whose past manual
reports excluded bugs shift up slightly under the automated engine: Core-Workouts
(cw) and Operator Experience (ox). Users & Locations (ul), Data Science (ds), and
API Platform (mm) already matched with bugs included, so no change for them.
Evergreen/umbrella epics are excluded from FL2 delivered/cycle-time counts.
(Decision: Alexa, 2026-07-28 — see the live agent's own `REALM_CORE.md` for full
history/provenance context; this LDA agent does not need to re-derive it.)

## Key files (this repo's `scripts/` folder, shared across realm agents)
`compute_jira.py`, `update_data_live.py`, `generate_dashboards_live.py`,
`report_checks.py`, `build_pdf_realm.py` — all reusable, unmodified except the two
`data_path` generalizations noted above (which are backward-compatible for Machine).
`core_publish.py` — Core's own orchestrator (this realm's only bespoke script).

## Hard rules (apply to every realm agent in this repo)
- No engine/methodology changes without explicit human (Alexa) sign-off.
- No changes to `data.json`/`data-machine.json` (live-repo file / other realms'
  files) — this agent only ever touches `data-core.json` and `core/`.
- After ANY push of a large/generated script or data file: immediately fetch it
  back and byte-diff against the intended source before considering the push done.
  A "success" response from the write tool does NOT guarantee the correct content
  was sent — this was learned the hard way during onboarding (see commit history).
- Use the isolated mock-harness pattern (intercept only write tools; real reads
  bypassed with canned data) to validate any script change before running it for
  real against Jira/GitHub.
