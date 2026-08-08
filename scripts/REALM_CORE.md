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

## Data provenance (inherited from the live repo's history — read before writing any Corrections narrative)
- The live repo's Core history for **Jun 25 → Jun 26 (13 months) was MANUALLY seeded**
  from Nave/manual reports, **NOT recomputed from Jira** (verified 2026-07-28 — see the
  live agent's own `REALM_CORE.md` for the full proof). **Only Jul 26 onward is real
  Jira-engine output** (the live repo's first automated month, run 20 Jul 2026).
- `data-core.json` in THIS repo was seeded **verbatim** from the live repo's full
  history (Jun 25 → Jul 26) at LDA onboarding time (2026-08-07/08), so it **inherits
  the exact same manual-seed-vs-engine discontinuity at the Jun→Jul boundary**. This
  is already historical fact baked into the seed — it needs no new action here.
  **Do NOT** treat a Jun→Jul jump in the historical chart as a fresh anomaly, and
  **do NOT** attempt to "fix" or recompute the manually-seeded months yourself.
- DECISION (Alexa, 2026-07-28, live repo): **Option B** — keep the manually-seeded
  history as-is. The live repo's Jul 2026 report already carried a one-time
  Corrections note about the source switch; that note already happened upstream and
  this LDA agent does not need to repeat it, unless a future report specifically
  references the Jun→Jul step (e.g. someone asks about it directly).
- A full engine backfill of pre-Jul-26 history has **not** been done anywhere
  (deferred backlog item, live repo). If that ever happens upstream, `data-core.json`
  here would need a matching re-seed — flag it to Alexa rather than doing it
  unilaterally.

## Anomaly resolution procedure (standing rule — applies to any evergreen-epic-style outlier)
When a soft anomaly is flagged (large month-over-month FL2 swing), first determine WHICH
kind of anomaly it is before asking Alexa:
1. **Traceable to one or a few specific delivered epics** (not a broad dataset switch):
   look up the exact epic keys in Jira (created date, resolved date, summary). If they
   look like evergreen/umbrella/maintenance-type epics (very old creation date, generic
   "maintenance"/"backlog"-style summary, no bounded delivery scope) rather than real
   time-boxed work, present the specific keys + dates + your assessment to Alexa and
   offer two options: (a) legitimate value, force-publish as-is with a one-time
   Corrections callout, or (b) add the EXACT key(s) to a `FL2_EXCLUDE`-style list in
   `compute_jira.py` for that team. Option (b) is a methodology change — requires
   Alexa's explicit sign-off on the specific key(s), and should be applied consistently
   in BOTH the live repo and this LDA repo for that same team going forward. **Never**
   infer or apply an automatic age/title heuristic yourself — only exact, human-approved
   keys ever go into an exclusion list.
2. **Traceable to a broad, whole-dataset discontinuity** (e.g. a manual-seed-to-engine
   source switch, like the Jun→Jul boundary described above): do NOT propose exclusion.
   Use the Option-B pattern instead — publish as-is with a one-time Corrections note
   about the source switch.
Never self-decide between these paths or silently force-publish through an anomaly —
always surface the specific finding and let Alexa choose.

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
Two separate Corrections topics exist for Core (both already resolved upstream in the
live repo — do not re-litigate either without Alexa):
1. **Bugs-included methodology** (ongoing, still relevant to every report): standard
   methodology includes bugs in throughput. Two Core teams whose past manual reports
   excluded bugs shift up slightly under the automated engine: Core-Workouts (cw) and
   Operator Experience (ox). Users & Locations (ul), Data Science (ds), and API
   Platform (mm) already matched with bugs included, so no change for them. Evergreen/
   umbrella epics are excluded from FL2 delivered/cycle-time counts.
2. **Manual-seed vs. engine data-source switch** (one-time, historical — see the "Data
   provenance" section above): the Jun→Jul 26 boundary in the history is a real
   source/methodology discontinuity, already flagged once upstream (live repo's Jul
   2026 report). Do not re-flag it every run — only mention it if a report or a
   stakeholder question specifically touches the Jun→Jul step.
(Decisions: Alexa, 2026-07-28 — see the live agent's own `REALM_CORE.md` for full
history/provenance context; this LDA agent does not need to re-derive either.)

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
