# egym-flow-metrics-lda

EGYM Flow Metrics — LDA-space agents (parallel to `egym-flow-metrics-live`).

## Why this repo exists

`egym-flow-metrics-live` is owned/operated by a single Dataleap agent (Alexa's).
This repo is the home for a **separate, independent set of Dataleap agents**
living in the LDA space, so the LDA team (Anna, Todor, Fabiano, etc.) can chat
with and adjust the rules of their own realm's agent directly — Alexa is no
longer a bottleneck. It does not replace or modify the live repo/agent; both
run in parallel until/unless a cutover decision is made later.

Public site: https://oleksandrabobina.github.io/egym-flow-metrics-lda/

## Architecture: 5 agents, narrow scopes, zero write conflicts

- **4 realm agents** — one per realm (Machine, Core, Apps, Wellpass), built one
  at a time, starting with **Machine**. Each realm agent:
  - Owns Jira compute + report generation for its realm only.
  - Reads/writes **only its own** `data-<realm>.json` and `<realm>/*.html`
    files (own folder). Never touches another realm's files.
  - Posts its own PDF/Slack message on its own schedule (cadence differs per
    realm — see each realm's own docs under `scripts/`).
- **1 Space agent** (build once a 2nd realm agent is added — not needed while
  only Machine exists) — the **only** writer of the shared aggregate pages:
  `index.html` (root), `global-dashboard.html`, `upload.html`. It reads every
  `data-<realm>.json` it finds in the repo (read-only) and rebuilds those 3
  pages from all of them. Runs on its own light schedule (e.g. daily or a
  couple of times a month) — decoupled from any realm's reporting cadence.
  Needs GitHub access only (no Jira/Slack required unless later extended to
  post a cross-realm summary).

This split means: exactly one writer per file, always — no git conflicts,
regardless of how many realm agents run and when.

⚠️ **Known limitation while only Machine exists:** `scripts/generate_dashboards_live.py`
(as adapted for this repo) still regenerates `index.html`/`global-dashboard.html`/
`upload.html` itself on every Machine run, since the Space agent doesn't exist yet.
This is safe today (only Machine's data exists) but **must be changed before a 2nd
realm agent is added** — either move that regeneration into the new Space agent, or
teach the script to preserve other realms it can't see. Don't skip this step when
onboarding realm #2.

## Repo layout

```
/scripts/                     reusable engine + publish scripts (Python)
/data-<realm>.json            one file per realm, owned only by that realm's agent
/<realm>/                     that realm's generated dashboard HTML (team pages,
                               realm-dashboard.html, index.html)
/index.html                   site landing page (all realms) — Space agent only
/global-dashboard.html        cross-realm engineering view — Space agent only
/upload.html                  static helper page — Space agent only
```

## Status

| Realm    | Agent built | Data seeded | Notes |
|----------|-------------|-------------|-------|
| Machine  | in progress | ✅ Jul 2026 (from live repo) | first realm being onboarded |
| Core     | not started | — | |
| Apps     | not started | — | |
| Wellpass | not started | — | next after Machine, per Alexa's plan |
| Space agent | not started | — | build when realm #2 starts |

## scripts/ contents (Machine, reused from egym-flow-metrics-live)

- `compute_jira.py` — engine (Jira queries, FL1/FL2 buckets, percentiles). Unmodified.
- `machine_cadence.py` — cadence-aware due-detector (handles month-end/weekend rolls).
- `machine_monthly.py` — batch Jira compute orchestrator (staged, <300s per batch).
- `machine_publish.py` — controlled-append publish path (data + dashboards + PDF + Slack deliver).
- `generate_dashboards_live.py` — dashboard HTML generator. Adapted: `REPO` →
  `egym-flow-metrics-lda`, data path → `data-machine.json`.
- `update_data_live.py` — safe chronological data.json updater. Same adaptation.
- `build_pdf_realm.py` — PDF report renderer (ReportLab). Unmodified, takes realm dict as input.
- `report_checks.py` — sanity/guardrail checks before publish. Unmodified.
- `REALM_MACHINE.md` — reference doc carried over from the live repo. **Needs a
  rewrite pass** — it still describes the live repo's context (paths, links);
  treat it as background reading only until updated.

## Setup checklist for the new Machine agent (LDA space)

1. Create the agent shell in the LDA space (Dataleap UI).
2. Connect: Jira (read), GitHub (write, same `oleksandrabobina` account — needs
   access to this repo), Slack (post to `#sw-team-lda`), Notion (optional, for
   methodology doc reference).
3. Paste in the drafted ExecutionAgent instructions (prepared separately with
   Alexa).
4. Pull the 9 files above from `scripts/` into the new agent's own sandbox
   (`/agent/home/`) — e.g. via `github_get_file_contents` for each path, or
   `curl` the raw URLs, at first run.
5. Set the schedule trigger (Machine cadence: 1st/2nd/28th–31st, 08:00 Europe/Madrid).
6. Test run, verify dashboard + PDF + Slack post, then enable.
