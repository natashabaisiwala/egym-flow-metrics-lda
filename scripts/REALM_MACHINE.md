# Machine Realm — How the agent works
_Reference doc. Shared baseline in `FLOW_METRICS_SPEC.md`; divergences in `REALM_DIVERGENCES.md`.
Detailed working log/history in `MACHINE_STATUS.md`._

## Status
- **LIVE since 30 Jul 2026 (July 2026 report published & delivered to #sw-team-lda).** Live `data.json`
  Machine realm = FLAT Variant-B shape: 8 task-teams, each carrying BOTH `fl1` + `fl2`; NO `epic_cards`
  key in data.json. 14 months Jun25→Jul26. Auto path = `machine_publish.py` (controlled append → push →
  dashboards → PDF → deliver), idempotent. ⚠️ `machine_monthly.py --publish` is INCOMPATIBLE with the flat
  live structure — NEVER use it on live. Compute still uses `machine_monthly.py --part=...` (staging).
  Schedule: days 1, 2, 28, 29, 30, 31 @ 08:00 Europe/Madrid (`sched_vrch4v3yml8urj6b753x`).
  `machine_cadence.py` is the due-detector: on each fire it prints the due report's `anchor`+`cadence`
  (or `NONE`), handling weekend/month-end rolls INCLUDING rolls into the 1st/2nd of the next month.
  Reports are labeled by CADENCE month (Alexa 2026-07-30) → no label collisions, no missed months
  (e.g. Jan 2027 → anchor 1 Feb, label `Jan 27`). Compute/publish/report/deliver take `--anchor` and
  `--cadence` from the detector. Delivery = DIRECT auto-post to #sw-team-lda (no DM gate, same as Core/Apps). (28–31 catches in-month rolls incl. the
  31st, e.g. Aug 2026 anchor = Aug 31; cross-month rolls to the 1st — Jan/Feb 2027 — need a dated backfill.)
- (history) Engine (FL1 + FL2) FINALIZED & reconciled vs Mar/Apr/May/Jun manual reports.
- **Own orchestrator** `machine_monthly.py` (staged, batch compute) — deliberately NOT added to
  `monthly_run.py`/`LIVE_REALMS` so LIVE Core/Apps stay untouched until Machine is ready.
- Cadence day = **30th** (clamped to month-end, rolled to next business day). ⚠️ day-30 frequently lands on a
  weekend and rolls into the NEXT month (Feb 28 Sat→Mar 2; May 30 Sat→Jun 1), shifting the report's month label —
  handle explicitly at publish and when reconciling.

## Data model (schema) — SPLIT (unique to Machine)
- **8 FL1 task-teams** but **7 FL2 epic-cards.** Teams carry `fl1`; epics live on `epic_cards`.
- Each team maps to its epic series via `fl2_card`. **MI OS + MI Backend both point to the shared
  `minfra` (Machine Infrastructure = whole MI project)** epic series — proven: epics in MI are never
  component-split, so both MI FL1 teams share one MI epic card.
- Dashboard renders as a **single grid** of 8 team cards (`FL1 CT · FL2 CT`), MI OS & MI Backend showing the
  same MI FL2 — exactly like the legacy layout. NO separate "epic cards" grid. (`generate_dashboards_live.py`
  is split-aware via `_team_fl2` / `realm.get('epic_cards')`.)

## FL1 teams (8) — `MACHINE_TEAMS` in compute_jira.py
| key | display | scope | bugs |
|---|---|---|---|
| fh | Fitness Hub | project ASD | project bugs |
| bs | Backstage (ex-MS Rocket) | project BAST | project bugs |
| cr | MSW Core & Retention | project SCOR | project bugs |
| aq | MSW Acquisition & HW | project SMAQ | project bugs |
| be | MSW Backend | **whole project DEBE** (no narrowing) | project bugs |
| mifw | MI Firmware | project FW (counts Release type) | project bugs |
| mios | MI OS | project MI, `component in (OS, Other, Smart Flex, Smart Balance, Smart Strength, Smart Flex Pi Software)` | filter 16309 |
| mibe | MI Backend | project MI, `component = "BE/API"` | filter 16310 |

Dropped from realm: **MS Back-End (ms_be), MS Front-End (ms_fe)** — legacy teams, not predecessors of the MSW split.

## FL2 epic-cards (7) — `MACHINE_FL2`
mifw=FW · **minfra=whole MI** · fh=ASD · bs=BAST · mswbe=DEBE · mswcore=SCOR · mswacq=SMAQ.
All `fl2_aging="percentile"` (see below).

## Methodology specifics (differs from report footnotes — validated by data, not docs)
- **FL2 epic WIP-aging = percentile P70/P85 for ALL 7 cards** (NOT the "weekly 12wk/8wk" the report footnote
  claims). Reproduces the manual R/Y/G under percentile for every card.
- **FL2 percentile estimator = nearest-rank 'higher'** ("develop 85% of tickets") for both epic CT headline
  and aging thresholds. (This is now the shared `_fl2` behaviour for all realms.) FL1 stays 'linear'.
- FL1: `FL1_TYPES` includes **Release** (realm-wide decision, Luis); tech = 10463 value-in-set; bugs included.
- MI OS scope = the 6-component set above; MI Backend = `BE/API` only; MI bug counts via saved filters 16309/16310.

## History mapping (LOCKED) + seed
`machine_realm_seed.json` = 8 teams + 7 epic_cards, 13-month history (Jun 25→Jun 26):
- FL1: mifw←mi_fw · mios←mi_os · mibe←mi_be · fh←fithub · bs←ms_rk(renamed) · be←msw_be(from Oct25) ·
  cr←msw_cr(Oct25) · aq←msw_acq(Oct25).
- FL2 cards: mifw←mi_fw.fl2 · **minfra←mi_os.fl2 (canonical MI epics, FULL history)** · fh←fithub.fl2 ·
  bs←ms_rk.fl2 · mswbe←msw_be.fl2 · mswcore←msw_cr.fl2 · mswacq←msw_acq.fl2.
- Colors: mifw `#f97316` · mios `#3b82f6` · mibe `#10b981` · fh `#14b8a6` · bs `#ec4899` · be `#6366f1` ·
  cr `#f43f5e` · aq `#84cc16`.

## ⚠️ Provenance (CRITICAL — this caused a real error)
The **CURRENT live Machine dashboard shows the migrated MANUAL (Luis) history, NOT engine/Jira data.**
Only Jul 26 has been engine-computed (staged, not published). Do NOT claim any current live Machine number
"comes from Jira" until publish on the 30th. History carries the manual reports' known discrepancies.
- **DECISION (Alexa, 2026-07-28): Option B** — keep manual history as-is; add a **Corrections** note about the
  source switching to the automated Jira engine from Jul 26 (one-time discontinuity, esp. mifw/mios). Full engine
  backfill of prior months DEFERRED (backlog item for team vote). Applies uniformly to Core, Apps, Machine.

## DORA
- Machine PDF gets a **DORA stub page** (Core-style placeholder). Engine does NOT compute DORA. (Machine is NOT
  in `NO_DORA_REALMS`.) Manual Machine reports had a visible DORA section.

## Delivery (planned)
- **Slack**, channel **#sw-team-lda** `C9CBU5S3C`. TAG at delivery: **Anna Herpel, Todor Todorov, Fabiano Freire**
  (resolve Slack user IDs at delivery time). Escalate: Alexa `UG3UBQWDP`.
- PDF layout fixes REQUIRED when extending `build_pdf_realm.py`: larger base font, generous leading (line
  spacing), fill whitespace better (prior manual Machine PDFs had all three problems).

## Corrections (report "Corrections" section — NEVER "errata")
- MI Firmware old-report throughput bug (used status "In Progress" not "In Development"; Luis fixed board).
- mswacq FL2 aging off-by-one on a tiny sample (P70 boundary; no false reds) — boundary noise.
- Trend discontinuity old-Nave-history ↔ new-engine at Jul 26 (esp. mifw/mios); history kept + self-corrects;
  full engine backfill deferred until after 30 Jul.

## Commands / files
- Compute a batch: `uv run --with numpy,tzdata python machine_monthly.py <JIRA> <GH> 2026-07-30 --part=<fl1a|fl1b|fl2a|fl2b> --any-day`.
- Publish (on the 30th): `... 2026-07-30 --publish [--force-anomalies]`.
- Rebuild drafts: `uv run --with numpy,tzdata python preview_machine.py`.
- Files: `machine_realm_seed.json`, `machine_stage_teams_Jul_26.json`, `machine_stage_cards_Jul_26.json`,
  `machine_monthly.py`, `preview_machine.py`, `MACHINE_STATUS.md` (log), `compute_jira.py` (MACHINE_TEAMS/MACHINE_FL2).

## Still TODO before 30 Jul
PDF (8 FL1 + 7 FL2 pages, layout fixes, DORA stub) · Corrections section · schedule · publish path must seed the
realm into data.json first (updater requires realm present) · then compute/publish/deliver · Notion methodology update.

## Methodology thread decision (2026-07-28) — see FLOW_METRICS_SPEC.md
- WIP aging for Machine FL2 = **percentile 70/85** (NOT weekly thresholds). Confirmed by Luis's live Nave
  Aging Chart for Machine Infrastructure: 85% line at 103d, 70% line at 58d. Engine already uses percentile
  ('higher') for all 7 Machine FL2 → correct. Corrections callout notes the switch from the old weekly belief.
- Throughput = bugs included; FL2 tech % = tech-task field (same single standard as Core/Apps).

## LOCKED REPORT STRUCTURE (from "June 2026 Machines Realm" template) — 2026-07-28, Alexa
Report = build-time VIEW over the per-team data (Variant B). NOTHING extra stored in data.json
(no epic_cards / fl1_groups / corrections keys in live data.json). Teams archived: ms_be, ms_fe →
realm has 8 teams. Both dashboard AND report show 8 teams.

8 FL1 teams (live keys): mi_fw, mi_os, mi_be, ms_rk(Backstage), fithub, msw_be, msw_cr, msw_acq.
7 FL2 epic cards (build-time): MI Firmware←mi_fw.fl2 · Machine Infrastructure←mi_os.fl2 (MI OS+MI BE
merge; mi_os.fl2 canonical) · Fitness Hub←fithub.fl2 · Backstage←ms_rk.fl2 · MSW Backend←msw_be.fl2 ·
MSW Core←msw_cr.fl2 · MSW Acq←msw_acq.fl2.

6 pages, match template EXACTLY (do NOT add anything):
1. Cover: "Machines Realm / monthly / flow metrics / <Month Year>".
2. About flow metrics (bullet definitions).
3. Realm - Tasks, 5 cards: MI Firmware, MI OS, MI Backend, Backstage, Fitness Hub. Narrative above.
   NO cluster subtitle (header is just "Realm - Tasks"). FL1 card fields: Cycle time
   ("to develop 85% of the tickets"), Throughput*, WIP Aging Risk R/Y/G, Bugs (created|resolved), tech tasks %.
4. Realm - Tasks, 3 cards: MSW Backend, MSW Core & Retention, MSW Acquisition & HW. Narrative above. NO subtitle.
5. Machine Realm - Epics — ONE page, 7 cards in a single row (order above). Narrative above. Epic card
   fields: Cycle time ("to complete 85% of the Epics"), Epics delivered, tech roadmap %, current WIP,
   WIP Aging Risk R/Y/G. NO Bugs on epic cards. Summary band: "<wip> in progress · <del> delivered ·
   Cycle time <realm p85>d · Aging R/Y/G · <tech%> Tech Roadmap done". 
   Aging legend REPRODUCED from template (two rules): MSW/MI weekly 🔴>12wk 🟡8-12wk 🟢<8wk ;
   Fitness Hub percentile 🔴>85% 🟡70-85% 🟢<70%. (R/Y/G VALUES computed by percentile per locked
   methodology; legend/method mismatch noted in Corrections, same as manual reports historically.)
   Asterisk footnote for small-sample CT: "*...cycle time of one (2 for MSW BE) epic delivered so far".
6. DORA Metrics — STUB page (Core-style placeholder). Engine does not compute DORA.

Deltas applied to build_pdf_realm.py draft: remove invented cluster subtitles; epics 1 page/7 cards
(not 2 pages); add realm epic Cycle time to Summary band; DORA stub; 8 teams.

RE-READ THIS FILE EVERY ~1 HOUR OF DIALOGUE (Alexa's instruction) to avoid context drift.
