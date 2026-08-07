"""
EGYM Flow Metrics — MACHINE realm monthly orchestrator (PTC, STAGED)  [reusable]
================================================================================
Machine is a SPLIT realm: 8 FL1 task teams (data.json realm["teams"]) + 7 FL2 epic
cards (realm["epic_cards"]). It also has the largest compute (15 heavy Jira jobs), so
computing it all in one process is both slow and fragile (long single runs occasionally
get a transient non-dict Jira response). Per our standing rule we therefore compute in
SMALL BATCHES, persisting each batch to staging files, then assemble + publish in a
final cheap step. Core/Apps automation (monthly_run.py) is untouched.

Reused building blocks: compute_jira (engine), update_data_live (split-aware),
generate_dashboards_live (split-aware), report_checks (guardrails).

USAGE (the schedule / agent runs these in sequence on the Machine cadence day):
  # 1..N: compute batches (each < 300s, resilient, idempotent-merge into staging)
  uv run --with numpy,tzdata python machine_monthly.py <jira> <gh> <YYYY-MM-DD> --part=fl1a
  ... --part=fl1b   ... --part=fl2a   ... --part=fl2b
  # final: assemble staged values, validate, anomaly-gate, write data.json, publish, manifest
  uv run --with numpy,tzdata python machine_monthly.py <jira> <gh> <YYYY-MM-DD> --publish
      [--force-anomalies]

Ad-hoc overrides: --teams=fh,bs  --cards=mifw,minfra  (compute an explicit subset).
Omit the date to use today (Europe/Madrid). A compute part only runs if the given date
is the Machine cadence anchor UNLESS --any-day is passed (used for manual backfills).
"""
import sys, os, json
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

REALM = "machine"
DIR = os.path.dirname(os.path.abspath(__file__))

# Conservative compute batches (keep each well under the 300s command cap).
PARTS = {
    "fl1a": {"teams": ["fh", "bs", "cr", "aq"]},
    "fl1b": {"teams": ["be", "mifw", "mios", "mibe"]},
    "fl2a": {"cards": ["mifw", "minfra", "fh", "bs"]},
    "fl2b": {"cards": ["mswbe", "mswcore", "mswacq"]},
}
ALL_TEAMS = list(cj.MACHINE_TEAMS.keys())   # 8
ALL_CARDS = list(cj.MACHINE_FL2.keys())     # 7

DELIVERY = {
    "channel": "C9CBU5S3C",                 # #sw-team-lda
    "tag_names": ["Anna Herpel", "Todor Todorov", "Fabiano Freire"],
    "escalate_to": "UG3UBQWDP",             # Alexa Bobina
}

def _today(override):
    if override:
        y, m, d = map(int, override.split("-"))
        return date(y, m, d)
    return (datetime.now(_TZ).date() if _TZ else datetime.utcnow().date())

def _stage_paths(month):
    m = month.replace(" ", "_")
    return (os.path.join(DIR, f"machine_stage_teams_{m}.json"),
            os.path.join(DIR, f"machine_stage_cards_{m}.json"))

def _load_stage(path):
    return json.load(open(path)) if os.path.exists(path) else {}

def _merge_stage(path, add):
    cur = _load_stage(path)
    cur.update(add)
    with open(path, "w") as f:
        json.dump(cur, f)
    return cur

def _arg(argv, name):
    return next((a.split("=", 1)[1] for a in argv if a.startswith(name + "=")), None)

def _compute_teams(jira_conn, anchor, team_keys):
    subset = {k: cj.MACHINE_TEAMS[k] for k in team_keys}
    raw = cj.compute_team_values(jira_conn, anchor, subset)
    return {k: {"fl1": raw[k]["fl1"]} for k in team_keys}

def _compute_cards(jira_conn, anchor, card_keys):
    subset = {k: cj.MACHINE_FL2[k] for k in card_keys}
    raw = cj.compute_fl2_cards(jira_conn, anchor, subset)
    return {k: {"fl2": raw[k]} for k in card_keys}

def _snap(series_map, i):
    return {k: (arr[i] if isinstance(arr, list) and len(arr) >= abs(i) else None)
            for k, arr in series_map.items()}

def write_delivery_manifest(anchor, gh_conn):
    gen.GH_CONN = gh_conn
    data, _ = gen.load_data()
    rd = data["realms"][REALM]
    teams_out = {tid: {"name": t.get("name", tid),
                       "fl1_now": _snap(t["fl1"], -1), "fl1_prev": _snap(t["fl1"], -2)}
                 for tid, t in rd["teams"].items()}
    cards_out = {cid: {"name": c.get("name", cid),
                       "fl2_now": _snap(c["fl2"], -1), "fl2_prev": _snap(c["fl2"], -2)}
                 for cid, c in rd.get("epic_cards", {}).items()}
    manifest = {
        "realm": REALM, "realm_name": rd["name"],
        "month_full": anchor.strftime("%B %Y"), "month_key": cj.month_label(anchor),
        "anchor_iso": anchor.isoformat(), "report_date": anchor.strftime("%-d %b %Y"),
        "dashboard": f"https://oleksandrabobina.github.io/egym-flow-metrics-lda/{REALM}/index.html",
        "channel": DELIVERY["channel"], "tag_names": DELIVERY["tag_names"],
        "escalate_to": DELIVERY["escalate_to"], "teams": teams_out, "epic_cards": cards_out,
    }
    path = os.path.join(DIR, f"delivery_{REALM}.json")
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2)
    return path

def main():
    argv = sys.argv[1:]
    pos = [a for a in argv if not a.startswith("--")]
    if len(pos) < 2:
        print("usage: machine_monthly.py <jira_conn> <gh_conn> [YYYY-MM-DD] "
              "[--part=fl1a|fl1b|fl2a|fl2b | --teams=.. --cards=..] "
              "[--publish] [--force-anomalies] [--any-day]")
        sys.exit(2)
    jira_conn, gh_conn = pos[0], pos[1]
    today = _today(pos[2] if len(pos) > 2 and pos[2] else None)
    publish = "--publish" in argv
    force = "--force-anomalies" in argv
    any_day = "--any-day" in argv
    part = _arg(argv, "--part")
    teams_csv = _arg(argv, "--teams")
    cards_csv = _arg(argv, "--cards")

    anchor_override = _arg(argv, "--anchor")
    cadence_override = _arg(argv, "--cadence")
    if anchor_override:
        _y, _m, _d = map(int, anchor_override.split("-"))
        anchor = date(_y, _m, _d)
    else:
        anchor = cj.report_anchor(today.year, today.month, REALM)
    if cadence_override:
        _cy, _cm = map(int, cadence_override.split("-"))
        month = f"{cj.MONTHS_ABBR[_cm - 1]} {_cy % 100:02d}"
    else:
        month = cj.month_label(anchor)
    teams_path, cards_path = _stage_paths(month)
    print(f"=== Machine monthly ({month}, anchor {anchor}) · today={today} ===")
    if anchor != today and not any_day and not anchor_override:
        print(f"Not the Machine cadence anchor ({anchor}); pass --any-day to force. No-op exit.")
        return

    # ── COMPUTE MODE ──────────────────────────────────────────────────────────
    if not publish:
        want_teams, want_cards = [], []
        if part:
            want_teams = PARTS.get(part, {}).get("teams", [])
            want_cards = PARTS.get(part, {}).get("cards", [])
        if teams_csv:
            want_teams = [t for t in teams_csv.split(",") if t]
        if cards_csv:
            want_cards = [c for c in cards_csv.split(",") if c]
        if not want_teams and not want_cards:
            print("Nothing to compute: pass --part=.. or --teams=../--cards=.. (or --publish).")
            sys.exit(2)

        if want_teams:
            print(f"  computing FL1 teams: {want_teams}")
            tv = _compute_teams(jira_conn, anchor, want_teams)
            for tk in want_teams:
                f1 = tv[tk]["fl1"]
                print(f"    {tk:>5}: ct={f1['ct']} tp={f1['tp']} tech={f1['tech']}% "
                      f"wip={f1['wR']}/{f1['wY']}/{f1['wG']} bugs={f1['bC']}/{f1['bR']}")
            cur = _merge_stage(teams_path, tv)
            print(f"  staged teams: {sorted(cur)} ({len(cur)}/8)")
        if want_cards:
            print(f"  computing FL2 cards: {want_cards}")
            cv = _compute_cards(jira_conn, anchor, want_cards)
            for ck in want_cards:
                f2 = cv[ck]["fl2"]
                print(f"    {ck:>7}: ct={f2['ct']} del={f2['del']} wip={f2['wip']} "
                      f"({f2['wR']}/{f2['wY']}/{f2['wG']}) tech={f2['tech']}%")
            cur = _merge_stage(cards_path, cv)
            print(f"  staged cards: {sorted(cur)} ({len(cur)}/7)")
        return

    # ── PUBLISH MODE ──────────────────────────────────────────────────────────
    tv_teams = _load_stage(teams_path)
    tv_cards = _load_stage(cards_path)
    missing_t = [t for t in ALL_TEAMS if t not in tv_teams]
    missing_c = [c for c in ALL_CARDS if c not in tv_cards]
    if missing_t or missing_c:
        print(f"  STAGING INCOMPLETE — missing teams {missing_t}, cards {missing_c}. "
              f"Run the compute parts first.")
        sys.exit(2)

    if upd.month_present(gh_conn, REALM, month):
        print(f"--- {REALM} {month}: already present — idempotent skip (no push). ---")
        for p in (teams_path, cards_path):
            if os.path.exists(p):
                os.remove(p)
        return

    hard = rc.validate(tv_teams) + rc.validate(tv_cards)
    if hard:
        print("  === VALIDATION ERRORS ===")
        for e in hard:
            print(f"    ! {e}")
        sys.exit(1)

    if not force:
        try:
            prev_teams = upd.latest_values(gh_conn, REALM)
        except Exception as e:
            prev_teams = None; print(f"  (prev teams load failed: {e})")
        try:
            prev_cards = upd.latest_cards(gh_conn, REALM)
        except Exception as e:
            prev_cards = None; print(f"  (prev cards load failed: {e})")
        anom = rc.anomalies(prev_teams, tv_teams) + rc.anomalies(prev_cards, tv_cards)
        if anom:
            print(f"  === ANOMALIES (review needed) for {REALM} {month} ===")
            for a in anom:
                print(f"    ? {a}")
            print("  Held for human approval. Staging kept; re-run --publish --force-anomalies "
                  "after approval.")
            sys.exit(3)

    try:
        res = upd.update(gh_conn, REALM, month, tv_teams, card_values=tv_cards,
                         commit_prefix="Data (auto)")
    except upd.UpdateAborted as e:
        print(f"  ABORTED (safety check): {e}")
        sys.exit(1)
    except Exception as e:
        print(f"  ERROR updating: {type(e).__name__}: {e}")
        sys.exit(1)

    print(f"  update_data: {res['status']} (index {res.get('index')})")
    if res["status"] == "updated":
        gen.run(gh_conn, [REALM])
        for p in (teams_path, cards_path):
            if os.path.exists(p):
                os.remove(p)
        print(f"  PUBLISHED {REALM} {month}")
        try:
            mpath = write_delivery_manifest(anchor, gh_conn)
            print(f"  DELIVERY PENDING {REALM} {month} — wrote {os.path.basename(mpath)}; "
                  f"author notes_machine.json then run deliver_report.py")
        except Exception as e:
            print(f"  DELIVERY MANIFEST ERROR: {type(e).__name__}: {e}")
            sys.exit(1)
    print("\n=== machine_monthly complete ===")

if __name__ == "__main__":
    main()
