# Apps Realm (LDA space) — How this agent works
_Reference doc for the Apps realm agent in the parallel `egym-flow-metrics-lda` repo.
Mirrors the live repo's Apps automation (`monthly_run.py`, see the live orchestrator's
own `REALM_APPS.md`) — same engine, same teams, same cadence, same methodology. Adapted
ONLY for independent per-realm storage so this agent never touches Core/Machine/
Wellpass data or the shared cross-realm pages._

## Status
- Onboarded to the LDA space (parallel repo `oleksandrabobina/egym-flow-metrics-lda`,
  independent of the live repo `egym-flow-metrics-live`, which stays untouched).
- Own data file: **`data-apps.json`** at repo root — contains ONLY
  `{"realms": {"apps": {...}}}`. Seed it with Apps' real history (Jun 25 → Jul 26,
  4 teams) copied verbatim from the live repo's `data.json` at seeding time — byte-diff
  the seed against the live source before trusting it.
  Never write to `data-core.json`, `data-machine.json`, or `data-wellpass.json`.
- Own dashboard pages: **`apps/`** folder (`apps/index.html`, `apps/realm-dashboard.html`,
  one page per team). Never write to `core/`, `machine/`, `wellpass/`, or the 3 shared
  cross-realm pages (`index.html`, `global-dashboard.html`, `upload.html` at repo
  root) — those are owned exclusively by the Space agent.
- Schedule: cadence day **25** (rolled to next business day on weekends — same rule
  as the live Apps realm; live's first automated run landed on the 27th). No schedule
  trigger is auto-created by this doc; whoever sets up this agent configures it
  explicitly, and should keep it **disabled** until a supervised dry run is reviewed.

## Teams (4) — `APPS_TEAMS` in `compute_jira.py` (shared, already present, unmodified)
| key | display | Jira scope | note |
|---|---|---|---|
| bma_core_growth | BMA Core Growth | project BMACG | **NEW** (reorg ~20 Jul 2026) |
| bma_engagement | BMA Engagement & Adoption | project BMAEA | **NEW** (reorg) |
| trainer | Trainer App | composite: `(project in (10033) OR project = 10052 OR component = "iOS TA" OR labels in (pairing, TrainerApp))`; status buckets from project MA | established |
| workout | Workout Experience | project XT | established |

- **NOT reported:** BMA Core (FA) and BMA Enterprise (BMAE) — removed 2026-07-24, work
  redistributed to the two new boards above; their old per-team figures no longer
  reflect reality. BMA Platform is intentionally NOT reported yet (team not active).
- New teams (bma_core_growth, bma_engagement) should carry a "new team — needs a few
  months for trends" annotation until they have enough history, same as the live realm.

## Engine (unchanged from live Apps — see FLOW_METRICS_SPEC.md for full methodology)
- Methodology is now **identical to Core**: FL1_TYPES incl Release + Bug (bugs INCLUDED
  in throughput); tech% = `customfield_10463 ∈ {Technical Task, Security Task}` (11502
  NOT used); throughput first-completion-only; FL2 delivered = CHANGED-TO-Done + passed
  a Doing stage; FL2 percentile estimator = nearest-rank 'higher'; evergreen/umbrella
  exclusions applied via the SAME shared `FL2_EXCLUDE` set in `compute_jira.py` (no
  Apps-specific entries exist yet — any future one needs the same explicit human
  sign-off process as Core's).
- **Apps has NO DORA page** — it is in `NO_DORA_REALMS`. Do not add one without an
  explicit request; this is a real methodology difference from Core, not an omission.

## Data provenance (inherited from the live repo's history — read before writing any Corrections narrative)
- The live repo's Apps history for **Jun 25 → Jun 26 (13 months) was MANUALLY seeded**
  from the manual reports, **NOT recomputed from Jira** (verified 2026-07-28 — see the
  live orchestrator's own `REALM_APPS.md` for the full proof, e.g. `workout` Jun-26
  throughput = 63 manually-seeded vs ~80 under the standard engine rule). **Only Jul 26
  onward is real Jira-engine output** (the live repo's first automated Apps run, 27 Jul
  2026).
- `data-apps.json` in THIS repo should be seeded **verbatim** from the live repo's full
  Apps history (Jun 25 → Jul 26) at LDA onboarding time, so it will **inherit the exact
  same manual-seed-vs-engine discontinuity at the Jun→Jul boundary**. This is already
  historical fact baked into the seed — it needs no new action here. **Do NOT** treat a
  Jun→Jul jump in the historical chart as a fresh anomaly, and **do NOT** attempt to
  "fix" or recompute the manually-seeded months yourself.
- DECISION (Alexa, 2026-07-28, live repo): **Option B** — keep the manually-seeded
  history as-is. The live repo's Jul 2026 report already carried a one-time Corrections
  note about the source switch; this LDA agent does not need to repeat it, unless a
  future report or a stakeholder question specifically references the Jun→Jul step.

## Anomaly resolution procedure (standing rule — applies to any evergreen-epic-style outlier)
When a soft anomaly is flagged (large month-over-month FL2 swing), first determine WHICH
kind of anomaly it is before pinging anyone:
1. **Traceable to one or a few specific delivered epics** (not a broad dataset switch):
   look up the exact epic keys in Jira (created date, resolved date, summary). If they
   look like evergreen/umbrella/maintenance-type epics (very old creation date, generic
   "maintenance"/"backlog"-style summary, no bounded delivery scope) rather than real
   time-boxed work, present the specific keys + dates + your assessment and offer two
   options: (a) legitimate value, force-publish as-is with a one-time Corrections
   callout, or (b) add the EXACT key(s) to the shared `FL2_EXCLUDE` set in
   `compute_jira.py`. Option (b) is a methodology change — requires explicit human
   sign-off on the specific key(s), and should be applied consistently in BOTH the live
   repo and this LDA repo going forward. **Never** infer or apply an automatic
   age/title heuristic yourself — only exact, human-approved keys ever go into an
   exclusion list.
2. **Traceable to a broad, whole-dataset discontinuity** (e.g. a manual-seed-to-engine
   source switch, like the Jun→Jul boundary described above): do NOT propose exclusion.
   Use the Option-B pattern instead — publish as-is with a one-time Corrections note
   about the source switch.
Never self-decide between these paths or silently force-publish through an anomaly.

## Anomaly & decision-authority ping (replaces ask_user)
There is no fixed individual who owns anomaly/methodology decisions for this agent —
authority rests with whoever is currently chatting with you, or this realm's
currently-tagged LDAs. When a soft anomaly holds a publish (nothing written yet):
look up (or use directly) this realm's LDA Slack user IDs — **Denys Ambrozhevychius**
`U09HA43RY6L`, **Bruno Farace** `U091T5REN2U` — and post to `#sw-team-lda`
(`C9CBU5S3C`) tagging both, summarizing the realm/month, the full list of flagged
metrics (old -> new), any culprit epic keys/dates/summary and your evergreen
assessment, and the two options from the procedure above. Invite them to reply there
or chat with you directly. Do NOT wait in this run — end quietly after posting; do not
publish, do not touch `data-apps.json`. Resolution happens later when someone with
access chats with you directly: "force-publish" → re-run with `--force-anomalies` then
deliver normally; "exclude key X" → do NOT self-implement, flag it as pending for
whoever edits this agent to make the actual `compute_jira.py` change first.

## Own orchestrator: `apps_publish.py` (build by mirroring `core_publish.py`)
Read `scripts/core_publish.py` in this same repo as your structural reference (same
repo, so directly readable) and build an Apps-specific equivalent with the same three
modes:
```
# 1. compute + append + push data-apps.json + regenerate apps/ dashboards (idempotent)
uv run --with numpy,tzdata python apps_publish.py <jira> <gh> <YYYY-MM-DD> --publish \
    [--force-anomalies]
# 2. build the report PDF (agent-authored notes injected)
uv run --with numpy,tzdata,reportlab python apps_publish.py <jira> <gh> <YYYY-MM-DD> \
    --report --notes=notes_apps.json --out=/agent/home/Apps_Realm_flow_metrics_YYYY_MM.pdf
# 3. post to the LDA channel
uv run --with numpy,tzdata python apps_publish.py <jira> <gh> <YYYY-MM-DD> \
    --deliver --slack=<slack_conn> --pdf=/agent/home/Apps_Realm_flow_metrics_YYYY_MM.pdf
```
`notes_apps.json` shape: `{"tasks": [...], "epics": [...], "epics_callout": "..."}`.

Use the SAME shared reusable modules from `scripts/` as Core does — pass
`data_path='data-apps.json'` to `update_data_live.py` and `generate_dashboards_live.py`
(both already generalized with a `data_path` param), and remember Apps is in
`NO_DORA_REALMS` when building the PDF (`build_pdf_realm.py`). `report_checks.py`
(hard validation + soft anomaly gate) is shared and unmodified.

Before running for real against Jira/GitHub: validate with the SAME isolated
mock-harness pattern used for Core (intercept only the GitHub write tool; real reads
bypassed with canned Apps-shaped data) — confirm `--publish` reads/writes ONLY
`data-apps.json` and writes dashboard HTML ONLY under `apps/`, zero touch of any other
realm's files. Also verify idempotency and the anomaly-hold gate before the first real
run.

## Delivery
- **Slack**, channel **#sw-team-lda** `C9CBU5S3C`.
- Tags: **Denys Ambrozhevychius** `U09HA43RY6L`, **Bruno Farace** `U091T5REN2U` — same
  routing as the live Apps realm. Escalate: Alexa `UG3UBQWDP`.

## Corrections (report section — NEVER "errata")
Two separate Corrections topics exist for Apps (both already resolved upstream in the
live repo — do not re-litigate either without explicit human sign-off):
1. **Bugs-included methodology + tech% field fix** (ongoing, still relevant to every
   report): standard methodology includes bugs in throughput and defines tech% via
   `customfield_10463` (not 11502). Some old manual reports for Workout and (the now
   retired) BMA Enterprise EXCLUDED bugs and/or used a different tech definition — those
   old numbers are **Corrections**, the engine is correct. Evergreen/umbrella epics are
   excluded from FL2 delivered/cycle-time counts via the shared `FL2_EXCLUDE`.
2. **Manual-seed vs. engine data-source switch** (one-time, historical — see "Data
   provenance" above): the Jun→Jul 26 boundary in the history is a real
   source/methodology discontinuity, already flagged once upstream (live repo's Jul
   2026 report). Do not re-flag it every run — only mention it if a report or a
   stakeholder question specifically touches the Jun→Jul step.

## Your own instructions are your source of truth
Answer questions about your own configuration/methodology directly from your own
instructions and this doc — never defer a self-explanation to an external Notion page
or any other doc that could be stale.

## Key files (this repo's `scripts/` folder, shared across realm agents)
`compute_jira.py` (APPS_TEAMS, engine — already present, unmodified),
`update_data_live.py`, `generate_dashboards_live.py`, `report_checks.py`,
`build_pdf_realm.py` — all shared/reusable. `apps_publish.py` — this realm's own
orchestrator (bespoke, build by mirroring `core_publish.py`).

## Hard rules (apply to every realm agent in this repo)
- No engine/methodology changes without explicit human sign-off.
- No changes to `data.json` (live repo) or any other realm's data/dashboard files —
  this agent only ever touches `data-apps.json` and `apps/`.
- After ANY push of a large/generated script or data file: immediately fetch it back
  and byte-diff against the intended source before considering the push done.
- Use the isolated mock-harness pattern (intercept only write tools; real reads
  bypassed with canned data) to validate any script change before running it for real
  against Jira/GitHub.
- Terminology: "Corrections", never "errata".
