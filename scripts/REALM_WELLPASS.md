# Wellpass Realm (LDA space) — How this agent works
_Reference doc for the Wellpass realm agent in the parallel `egym-flow-metrics-lda`
repo. Unlike a from-scratch realm, Wellpass has 13 months of Nave-verified
history (May 25 – Jun 26) that was seeded into the older `egym-flow-metrics-live`
repo on 2026-07-19 but never wired to any automation there — it sat frozen at
Jun 26. That history has been migrated into this realm's own `data-wellpass.json`
(schema-converted, old team keys remapped). This agent's first live-computed
month is therefore the true "manual-seed → engine" boundary for Wellpass — see
Data provenance below before writing any Corrections narrative._

## Status
- Onboarded to the LDA space (parallel repo `oleksandrabobina/egym-flow-metrics-lda`,
  independent of the live repo `egym-flow-metrics-live`, which stays untouched).
- Own data file: **`data-wellpass.json`** at repo root — contains ONLY
  `{"realms": {"wellpass": {...}}}`. Seeded with **13 months of migrated,
  Nave-verified history (May 25 – Jun 26)**, sourced from the older
  `egym-flow-metrics-live` repo's one-time 2026-07-19 seed commit (which was
  never wired to any ongoing automation for Wellpass — see Data provenance).
  Schema-converted to match `data-core.json`/`data-apps.json` (deprecated
  `wipAge`/`tpYTD` fields dropped, old team keys remapped 1:1 to
  `WELLPASS_TEAMS`). Never write to `data-core.json`, `data-apps.json`, or
  `data-machine.json`.
- Own dashboard pages: **`wellpass/`** folder (`wellpass/index.html`,
  `wellpass/realm-dashboard.html`, one page per team). Never write to `core/`,
  `apps/`, `machine/`, or the 3 shared cross-realm pages (`index.html`,
  `global-dashboard.html`, `upload.html` at repo root) — those are owned
  exclusively by the Space agent.
- Schedule: cadence day **15** (rolled to next business day on weekends).
  No schedule trigger is auto-created by this doc; whoever sets up this agent
  configures it explicitly, and it should stay **disabled** until a supervised
  dry run is reviewed.

## Teams (8) — `WELLPASS_TEAMS` in `compute_jira.py` (shared, already present)
| key | Jira project key | display |
|---|---|---|
| cgr | WPCGR | WP Company Growth |
| acq | WPACQ | WP Offer & Acquisition |
| aex | WPAEX | WP Access Experience |
| dis | WPDIS | WP Discovery |
| pex | WPPEX | WP Partner Experience |
| int | WPINT | WP Partner Integrations |
| mot | WPMOT | WP Motivation |
| act | WPACT | WP Activation |

All 8 confirmed as real Wellpass delivery teams by Alexa Bobina (2026-08-08). All
are plain project scopes (`worked_only=False`, `done_extra=None`) — standard
fl1+fl2 schema, same shape as `CORE_TEAMS`/`APPS_TEAMS`.

## Engine (standard schema — same as Core/Apps; see FLOW_METRICS_SPEC.md)
- `data-wellpass.json` follows the exact same fl1+fl2-per-team structure as
  `data-core.json`/`data-apps.json`.
- Do NOT add `"wellpass"` to `WELLPASS_REALMS` in `generate_dashboards_live.py` —
  that set must stay EMPTY. It is dead code from a deprecated special KPI layout
  (WIP/WIP-age/Epic-WIP) that Wellpass no longer uses.
- **Known methodology divergence**: per FLOW_METRICS_SPEC.md, the FL2 cycle-time
  dev-cycle status list "excludes Canary" for Wellpass. Implemented via
  `REALM_FL2_DOING_EXCLUDE = {"wellpass": {"10450"}}` ("In Canary" excluded) and
  a `realm` parameter threaded through `_fl2()`/`_compute_team()`/`_compute()`/
  `compute_team_values()` in `compute_jira.py`. This is a methodology change to
  the shared engine — it went live only after Alexa Bobina's explicit sign-off
  on the exact diff (see commit history). Every other realm defaults to
  `realm="core"`, for which `REALM_FL2_DOING_EXCLUDE` has no entry, so their
  behavior is byte-identical to before.
- Wellpass has NO DORA page override — `build_pdf_realm.py`'s `NO_DORA_REALMS`
  is untouched (only contains `"apps"`), so Wellpass gets the same generic
  "Not included in this automated report" DORA placeholder page as Core. No
  action needed here.

## Data provenance
- Wellpass's Jun 25 → Jun 26 history (13 months) was **manually seeded from
  Nave-verified reports into the older `egym-flow-metrics-live` repo on
  2026-07-19**, in the same one-shot commit that seeded Core/Apps/Machine
  there. Verified by reading that repo's commit history and `data.json`.
- Unlike Core/Apps/Machine in that same repo, **Wellpass's seed was never
  wired to any ongoing automation** — Core/Apps/Machine went on to receive
  monthly "Data (auto)" commits, but Wellpass sat frozen at "Jun 26" with zero
  subsequent updates. This gap is exactly what this LDA agent exists to fill.
- That 13-month history was migrated into THIS repo's `data-wellpass.json`
  (2026-08-08, approved by Alexa Bobina): old team keys were remapped 1:1 to
  `WELLPASS_TEAMS` (e.g. `act1`→`cgr`, `eng1`→`aex`, `acc`→`act`, etc.), and
  deprecated schema fields not used by the standard engine schema (`wip`,
  `wipAge`, `tpYTD` on fl1; `wipAge` on fl2) were dropped. All array lengths
  were verified against the 13-month count during migration.
- Because that history was manually seeded (not recomputed from Jira), it is a
  **manual-seed period**, exactly like Core/Apps had before their own engine
  boundaries. **This agent's first live-computed month is the true
  manual-seed-to-engine boundary for Wellpass** — treat that transition the
  same way `REALM_APPS.md`'s Data provenance section treats the Apps
  Jun→Jul-26 boundary: it is expected historical fact, not a fresh anomaly.
  Do NOT attempt to "fix" or recompute the manually-seeded months yourself.
- If any team's freshly-computed (post-migration) numbers look surprising
  relative to the migrated history, treat that as a normal anomaly (see
  procedure below) unless it specifically traces to the manual-seed → engine
  boundary itself — in that case, add a one-time Corrections note about the
  source switch (mirroring Apps' Option B) rather than treating it as a
  culprit-epic anomaly.

## Anomaly resolution procedure (evergreen-epic rule)
If an FL2 anomaly traces to one/few specific epics AND manual Jira review
confirms they are evergreen/umbrella/maintenance-type (old creation date,
generic title, unbounded scope):
1. Offer two choices to a human: (a) force-publish as-is + one-time Corrections
   callout, or (b) add the exact epic key(s) to a `FL2_EXCLUDE`-style list.
   Option (b) is a methodology change — requires explicit human sign-off,
   applied consistently going forward. **Never** infer or apply an automatic
   age/title heuristic — only exact, human-approved keys ever go into an
   exclusion list.

If instead it's a broad whole-dataset discontinuity → Corrections note only, no
exclusion. Never self-decide between these paths or silently force-publish
through an anomaly.

## Anomaly & decision-authority ping (replaces ask_user)
There is no single fixed individual who owns anomaly/methodology decisions for
this agent — authority rests with whoever is currently chatting with this
agent, or this realm's currently-tagged LDAs. When a soft anomaly holds a
publish (nothing written yet): post to `#sw-team-lda` (`C9CBU5S3C`) tagging
this realm's LDAs — **Junior Staudt** `<@U07MVKEB3B7>`, **Annika Heilmann**
`<@U059KPZ6M3J>`, **Luis Torres** `<@U092X5N5073>`, **Natasha Baisiwala**
`<@U06HWLH1H5H>` — summarizing the realm/month, the full list of flagged
metrics (old → new), any culprit epic keys/dates/summary and your evergreen
assessment, and the two options from the procedure above. Invite them to reply
there or chat with this agent directly. Do NOT wait in this run — end quietly
after posting; do not publish, do not touch `data-wellpass.json`. Resolution
happens later when one of the tagged LDAs chats with this agent directly and
gives an explicit decision (force-publish re-run, or exclusion + sign-off).
Never hardcode a single individual as "the" escalation contact — decision
authority = current tagged LDAs for this realm.

## Own orchestrator: `wellpass_publish.py` (mirrors `core_publish.py`/`apps_publish.py`)
Direct single-shot analogue of `core_publish.py`, adapted for Wellpass's 8 teams,
cadence day 15, independent `data-wellpass.json`, independent `wellpass/`
dashboard pages. Three modes:
```
# 1. compute + append + push data-wellpass.json + regenerate wellpass/ dashboards (idempotent)
uv run --with numpy,tzdata python wellpass_publish.py <jira> <gh> <YYYY-MM-DD> --publish \
    [--force-anomalies]
# 2. build the report PDF (agent-authored notes injected)
uv run --with numpy,tzdata,reportlab python wellpass_publish.py <jira> <gh> <YYYY-MM-DD> \
    --report --notes=notes_wellpass.json --out=/agent/home/Wellpass_Realm_flow_metrics_YYYY_MM.pdf
# 3. post to the LDA channel
uv run --with numpy,tzdata python wellpass_publish.py <jira> <gh> <YYYY-MM-DD> \
    --deliver --slack=<slack_conn> --pdf=/agent/home/Wellpass_Realm_flow_metrics_YYYY_MM.pdf
```
Uses the SAME shared reusable modules from `scripts/` as Core/Apps: `compute_jira.py`
(engine — additive changes only, see Engine section), `update_data_live.py`,
`generate_dashboards_live.py`, `report_checks.py`, `build_pdf_realm.py`.

Mock-harness-validated before touching real Jira/GitHub (intercept only the
GitHub write tool; real reads bypassed with canned Wellpass-shaped data):
confirmed `--publish` reads/writes ONLY `data-wellpass.json` and writes
dashboard HTML ONLY under `wellpass/`, zero touch of any other realm's files.

## Delivery
- **Slack**, channel **#sw-team-lda** `C9CBU5S3C`.
- Tags: **Junior Staudt** `<@U07MVKEB3B7>`, **Annika Heilmann** `<@U059KPZ6M3J>`,
  **Luis Torres** `<@U092X5N5073>`, **Natasha Baisiwala** `<@U06HWLH1H5H>`.

## Corrections (report section — NEVER "errata")
One standing topic at launch:
1. **Manual-seed vs. engine data-source switch** (one-time, historical — see
   "Data provenance" above): the migrated May 25 – Jun 26 history was manually
   seeded from Nave reports (via the older live repo), not recomputed from
   Jira. This agent's first live-computed month is the real source switch —
   flag it once with a Corrections note the first time it publishes, mirroring
   how `REALM_APPS.md` documents its own Jun→Jul-26 boundary. Do not re-flag it
   on every subsequent run.
Add further entries here only when a new real data/methodology correction is
confirmed and shipped.

## Your own instructions are your source of truth
This document (and this agent's own instructions) are the operational source of
truth for how this agent works. Notion is documentation OUTPUT for humans only —
never consult Notion to explain your own configuration to yourself or anyone
else, and never defer a self-explanation to it (it can be stale). Notion
consolidation for Wellpass is explicitly deferred until all 5 realm agents exist.

## Key files (this repo's `scripts/` folder, shared across realm agents)
`compute_jira.py` (WELLPASS_TEAMS, REALM_CADENCE["wellpass"]=15, Wellpass Canary
dev-cycle exclusion — all additive), `update_data_live.py`,
`generate_dashboards_live.py`, `report_checks.py`, `build_pdf_realm.py` — all
shared/reusable, unmodified except the additive engine changes above.
`wellpass_publish.py` — this realm's own orchestrator (bespoke, mirrors
`core_publish.py`).

## Hard rules (apply to every realm agent in this repo)
- Terminology: "Corrections", never "errata".
- No engine/methodology changes without explicit human (Alexa) sign-off — this
  includes the Canary dev-cycle exclusion and any future FL2_EXCLUDE edits.
- Never touch Core/Machine/Apps files, team dicts, or FL2_EXCLUDE entries
  belonging to other realms.
- After ANY push of a script/data/doc file: immediately fetch it back and
  byte-diff against the intended source before considering the push done.
- Isolated mock-harness testing mandatory before any script touches real
  Jira/GitHub.
