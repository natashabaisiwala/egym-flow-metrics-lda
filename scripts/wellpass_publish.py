# -*- coding: utf-8 -*-
"""
EGYM Flow Metrics — WELLPASS realm publish/report/deliver (LDA space)  [reusable]
==================================================================================
Wellpass realm equivalent of core_publish.py. Direct, single-shot analogue of the
live repo's monthly_run.py Core path, adapted for Wellpass's 8 teams
(cgr/acq/aex/dis/pex/int/mot/act), cadence day 15 (rolled to next business day —
handled generically by compute_jira.py's REALM_CADENCE/report_anchor(), no extra
code needed here), same rolling 120-day window, same validation/anomaly gates.
It is adapted only for the LDA repo's independent data-wellpass.json (via
update_data_live.py's data_path param) and independent wellpass/ dashboard pages
(via generate_dashboards_live.py's data_path param), so Wellpass can run fully
independently of every other realm's data file.

Unlike Core, Wellpass is NOT starting from zero: data-wellpass.json already
carries 13 months of migrated, Nave-verified manual-seed history (May 25 - Jun
26). This agent's first live-computed month is therefore the true
manual-seed-to-engine boundary for Wellpass (see REALM_WELLPASS.md's Data
provenance section). build_report() detects that boundary automatically (the
month immediately after the 13 seeded months) and attaches a one-time
Corrections note to that month's PDF only — never on any other run.

Unlike Core, Wellpass has NO single fixed escalation contact. Decision
authority for anomalies/methodology sits with whichever of the 4 tagged
Wellpass LDAs is currently engaged (see REALM_WELLPASS.md). So when a soft
anomaly holds a publish, this script (given a --slack connection) posts the
anomaly summary straight to #sw-team-lda tagging all 4 LDAs and ends quietly —
it does NOT wait for a reply and does NOT write any data.

No engine/methodology changes. No changes to data-core.json/data-apps.json/
data-machine.json.

USAGE (run in sequence on the Wellpass cadence day, 15th, rolled to next
business day on weekends):
  # 1. compute + append + push data-wellpass.json + regenerate wellpass/ dashboards
  #    (idempotent: skips the recompute+push if the month is already live)
  #    Pass --slack so a soft anomaly can be auto-escalated to #sw-team-lda.
  uv run --with numpy,tzdata python wellpass_publish.py <jira> <gh> <YYYY-MM-DD> --publish \
      [--force-anomalies] [--slack=<slack_conn>]
  # 2. build the report PDF (pass the agent-authored notes file)
  uv run --with numpy,tzdata,reportlab python wellpass_publish.py <jira> <gh> <YYYY-MM-DD> \
      --report --notes=notes_wellpass.json --out=/agent/home/Wellpass_Realm_flow_metrics_YYYY_MM.pdf
  # 3. post to the LDA channel (only after the tagged LDAs approve the DM/preview)
  uv run --with numpy,tzdata python wellpass_publish.py <jira> <gh> <YYYY-MM-DD> \
      --deliver --slack=<slack_conn> --pdf=/agent/home/Wellpass_Realm_flow_metrics_YYYY_MM.pdf

Omit the date to use today (Europe/Madrid). --publish is idempotent: if the month
is already present in data-wellpass.json it does nothing but still regenerates
the dashboards (safe to re-run). --report/--deliver can be re-run safely too
(report just rebuilds the PDF; deliver renames the manifest to
delivery_wellpass_sent_<month>.json on success so a re-run reports "nothing
pending" instead of double-posting).
"""
import sys, os, json, copy
from datetime import date, datetime
try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("Europe/Madrid")
except Exception:
    _TZ = None

import compute_jira as cj
import update_data_live as upd
import generate_dashboards_live as gen
import report_checks as rc
import build_pdf_realm as bp
from agent_tools import call_tool

REALM = "wellpass"
DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = "data-wellpass.json"
OWNER = "oleksandrabobina"
REPO = "egym-flow-metrics-lda"
DASH = f"https://{OWNER}.github.io/{REPO}/{REALM}/index.html"

# Slack delivery — same routing as the live Wellpass realm (see REALM_WELLPASS.md).
CHANNEL = "C9CBU5S3C"   # #sw-team-lda
LDA_IDS = ["U07MVKEB3B7", "U059KPZ6M3J", "U092X5N5073", "U06HWLH1H5H"]
# Junior Staudt, Annika Heilmann, Luis Torres, Natasha Baisiwala.
# No single fixed escalation contact by design (see REALM_WELLPASS.md):
# decision authority = whichever of the 4 tagged LDAs is currently engaged.

# Number of manually-seeded history months already in data-wellpass.json
# (May 25 - Jun 26, migrated 2026-08-08). The first month appended AFTER this
# many months already present is, by construction, this agent's first
# live-computed month = the true manual-seed-to-engine boundary for Wellpass.
SEED_MONTH_COUNT = 13

# One-time Corrections narrative — only ever attached to the first live-computed
# month's report (see build_report() below). Never re-flagged afterwards.
CORRECTIONS = (
    "The migrated May 2025 - Jun 2026 history (13 months) was manually seeded from "
    "Nave-verified reports via the older egym-flow-metrics-live repo, not recomputed "
    "from Jira (see Data provenance in REALM_WELLPASS.md). This report is the first "
    "month computed directly by the automated engine -- the real manual-seed-to-engine "
    "boundary for Wellpass. Earlier months on this dashboard are historical fact, not a "
    "fresh anomaly, and are unaffected."
)


def _today(override):
    if override:
        y, m, d = map(int, override.split("-"))
        return date(y, m, d)
    return (datetime.now(_TZ).date() if _TZ else datetime.utcnow().date())


def _labels(today, anchor_override=None, cadence_override=None):
    if anchor_override:
        y, m, d = map(int, anchor_override.split("-"))
        anchor = date(y, m, d)
    else:
        anchor = cj.report_anchor(today.year, today.month, REALM)
    if cadence_override:
        cy, cm = map(int, cadence_override.split("-"))
    else:
        cy, cm = anchor.year, anchor.month
    month = f"{cj.MONTHS_ABBR[cm - 1]} {cy % 100:02d}"
    month_full = date(cy, cm, 1).strftime("%B %Y")
    return anchor, month, month_full, anchor.strftime("%-d %b %Y")


def _arg(argv, name):
    return next((a.split("=", 1)[1] for a in argv if a.startswith(name + "=")), None)


def _write_delivery_manifest(gh_conn, anchor, month, month_full, report_date):
    gen.GH_CONN = gh_conn
    data, _ = gen.load_data(DATA_PATH)
    rd = data["realms"][REALM]

    def snap(fl, i, container):
        return {k: (arr[i] if isinstance(arr, list) and len(arr) >= abs(i) else None)
                for k, arr in container[fl].items()}

    teams_out = {}
    for tid, t in rd["teams"].items():
        teams_out[tid] = {"name": t.get("name", tid),
                           "fl1_now": snap("fl1", -1, t), "fl1_prev": snap("fl1", -2, t),
                           "fl2_now": snap("fl2", -1, t), "fl2_prev": snap("fl2", -2, t)}
    manifest = {
        "realm": REALM, "realm_name": rd["name"], "month_full": month_full,
        "month_key": month, "anchor_iso": anchor.isoformat(), "report_date": report_date,
        "dashboard": DASH, "channel": CHANNEL, "ldas": LDA_IDS,
        "teams": teams_out,
    }
    path = os.path.join(DIR, f"delivery_{REALM}.json")
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2)
    return path


def _escalate_anomalies(slack_conn, month_full, anom):
    """Post the anomaly summary straight to #sw-team-lda tagging all 4 Wellpass
    LDAs, then return. Caller must exit without writing any data. Never waits
    for a reply here — resolution happens later when a tagged LDA chats with
    this agent directly and gives an explicit decision (see REALM_WELLPASS.md)."""
    tags = " ".join(f"<@{u}>" for u in LDA_IDS)
    lines = "\n".join(f"\u2022 {a}" for a in anom)
    msg = (f"\U0001F6A8 *Wellpass Realm \u2014 anomaly review needed \u00b7 {month_full}*\n"
           f"The automated engine flagged the following before publishing (nothing written yet):\n\n"
           f"{lines}\n\n"
           f"{tags} \u2014 please review: summarize your evergreen/methodology assessment and reply "
           f"here or chat with this agent directly with a decision (force-publish as-is, or exclude "
           f"specific epic keys with sign-off). No data was written; this run is ending now.")
    call_tool("slack_post_message", {
        "connectionId": slack_conn, "channelId": CHANNEL, "message": msg,
    })


# --- PUBLISH: compute (single shot) + append + push + dashboards --------------
def publish(jira_conn, gh_conn, today, anchor_override=None, cadence_override=None,
            force=False, slack_conn=None):
    anchor, month, month_full, report_date = _labels(today, anchor_override, cadence_override)
    print(f"=== Wellpass publish ({month}, anchor {anchor}) ===")

    if upd.month_present(gh_conn, REALM, month, data_path=DATA_PATH):
        print(f"--- {month} already present in {DATA_PATH} \u2014 idempotent skip (no push). ---")
        print("  (Regenerating dashboards anyway to be safe.)")
        gen.run(gh_conn, [REALM], data_path=DATA_PATH)
        return {"status": "skipped", "month": month}

    print(f"  computing {REALM} {month} (8 teams: cgr, acq, aex, dis, pex, int, mot, act) ...")
    tv = cj.compute_team_values(jira_conn, anchor, cj.WELLPASS_TEAMS, realm=REALM)
    for tk in cj.WELLPASS_TEAMS:
        f1 = tv[tk]["fl1"]; f2 = tv[tk]["fl2"]
        print(f"  {tk:>3}: FL1 ct={f1['ct']} tp={f1['tp']} tech={f1['tech']}% "
              f"wip={f1['wR']}/{f1['wY']}/{f1['wG']} bugs={f1['bC']}/{f1['bR']} | "
              f"FL2 ct={f2['ct']} del={f2['del']} wip={f2['wip']} tech={f2['tech']}%")

    hard = rc.validate(tv)
    if hard:
        print("  === VALIDATION ERRORS ===")
        for e in hard:
            print(f"    ! {e}")
        sys.exit(1)

    if not force:
        try:
            prev = upd.latest_values(gh_conn, REALM, data_path=DATA_PATH)
        except Exception as e:
            prev = None
            print(f"  (prev values load failed: {e})")
        anom = rc.anomalies(prev, tv)
        if anom:
            print(f"  === ANOMALIES (review needed) for {REALM} {month} ===")
            for a in anom:
                print(f"    ? {a}")
            if slack_conn:
                _escalate_anomalies(slack_conn, month_full, anom)
                print("  Escalation posted to #sw-team-lda tagging the 4 Wellpass LDAs. "
                      "Held for human approval (no data written). Ending run.")
            else:
                print("  Held for human approval. Re-run with --force-anomalies after approval "
                      "(no data was written). NOTE: no --slack conn was given, so no Slack "
                      "escalation was posted -- pass --slack=<conn> so this can auto-notify the LDAs.")
            sys.exit(3)

    try:
        res = upd.update(gh_conn, REALM, month, tv, commit_prefix="Data (auto)",
                          data_path=DATA_PATH)
    except upd.UpdateAborted as e:
        print(f"  ABORTED (safety check): {e}")
        sys.exit(1)

    print(f"  update_data: {res['status']} (index {res.get('index')})")
    if res["status"] != "updated":
        print(f"  {REALM} {month} already present \u2014 idempotent skip (no push).")
        return {"status": "duplicate", "month": month}

    gen.run(gh_conn, [REALM], data_path=DATA_PATH)
    print(f"  PUBLISHED {REALM} {month} + dashboards regenerated")

    manifest = _write_delivery_manifest(gh_conn, anchor, month, month_full, report_date)
    print(f"  DELIVERY PENDING {REALM} {month} \u2014 wrote {os.path.basename(manifest)}; "
          f"author notes_wellpass.json then run --report and --deliver")
    return {"status": "updated", "month": month}


# --- REPORT: build the PDF (agent-authored notes injected) --------------------
def build_report(gh_conn, today, notes_path, out_path, anchor_override=None,
                  cadence_override=None):
    anchor, month, month_full, report_date = _labels(today, anchor_override, cadence_override)
    gen.GH_CONN = gh_conn
    data, _ = gen.load_data(DATA_PATH)
    rd = data["realms"][REALM]
    months = rd.get("months", [])
    if month not in months:
        print(f"  ! {month} not yet in {DATA_PATH} \u2014 run --publish first.")
        sys.exit(1)

    notes = None
    if notes_path and os.path.exists(notes_path):
        try:
            notes = json.load(open(notes_path))
        except Exception as e:
            print(f"  WARNING: could not read notes {notes_path}: {e}; building without narrative.")

    rv = copy.deepcopy(rd)
    # One-time Corrections note: only the month immediately after the
    # SEED_MONTH_COUNT manually-seeded months gets it (the true manual-seed-to
    # -engine boundary). Every later month reports normally with no note.
    if months.index(month) == SEED_MONTH_COUNT:
        rv["corrections"] = CORRECTIONS
    if not out_path:
        out_path = os.path.join(DIR, f"Wellpass_Realm_flow_metrics_{anchor.strftime('%Y_%m')}.pdf")
    bp.build_realm_pdf(rv, REALM, anchor.isoformat(), month_full, out_path, notes=notes)
    print(f"  PDF written: {out_path}")
    return out_path


# --- DELIVER: post to the LDA Slack channel (exact approved template) --------
def deliver(slack_conn, today, pdf_path, anchor_override=None, cadence_override=None):
    anchor, month, month_full, report_date = _labels(today, anchor_override, cadence_override)
    if not (pdf_path and os.path.exists(pdf_path)):
        print(f"  ! PDF not found: {pdf_path}")
        sys.exit(1)
    tags = " ".join(f"<@{u}>" for u in LDA_IDS)
    msg = (f"\U0001F4CA *Wellpass Realm \u2014 Flow Metrics \u00b7 {month_full}*\n"
           f"The {month_full} flow metrics report for the *Wellpass Realm* is ready.\n"
           f"\U0001F4C4 PDF attached \u00b7 \U0001F4C8 Live dashboard: <{DASH}|Wellpass Realm dashboard>\n\n"
           f"{tags} \u2014 please review. If everything looks good, please share onward with your "
           f"Head of Realm \u2014 both the PDF and the link to the dashboard. If anything looks off, "
           f"please reach out to this agent directly.\n\n"
           f"_Automatically generated \u00b7 rolling 120-day window (through {report_date})_")
    call_tool("slack_post_message", {
        "connectionId": slack_conn, "channelId": CHANNEL, "message": msg,
        "attachments": [{"sourcePath": pdf_path, "fileName": os.path.basename(pdf_path),
                          "mimeType": "application/pdf"}],
    })
    print(f"  DELIVERED Wellpass {month_full} -> Slack {CHANNEL}")
    man_path = os.path.join(DIR, f"delivery_{REALM}.json")
    sent_path = os.path.join(DIR, f"delivery_{REALM}_sent_{month.replace(' ', '_')}.json")
    try:
        os.replace(man_path, sent_path)
    except Exception:
        pass


def main():
    argv = sys.argv[1:]
    pos = [a for a in argv if not a.startswith("--")]
    if len(pos) < 2:
        print("usage: wellpass_publish.py <jira_conn> <gh_conn> [YYYY-MM-DD] "
              "[--publish [--force-anomalies] [--slack=..]] | --report --notes=.. --out=.. | "
              "--deliver --slack=.. --pdf=..]")
        sys.exit(2)
    jira_conn, gh_conn = pos[0], pos[1]
    today = _today(pos[2] if len(pos) > 2 and pos[2] else None)
    ao = _arg(argv, "--anchor")
    co = _arg(argv, "--cadence")
    force = "--force-anomalies" in argv
    slack = _arg(argv, "--slack")

    if "--publish" in argv:
        publish(jira_conn, gh_conn, today, ao, co, force, slack)
    elif "--report" in argv:
        build_report(gh_conn, today, _arg(argv, "--notes"), _arg(argv, "--out"), ao, co)
    elif "--deliver" in argv:
        deliver(_arg(argv, "--slack"), today, _arg(argv, "--pdf"), ao, co)
    else:
        print("Nothing to do: pass --publish, --report, or --deliver.")
        sys.exit(2)


if __name__ == "__main__":
    main()
