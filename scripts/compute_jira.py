"""
EGYM Flow Metrics — Jira compute engine  (reusable automation module)
========================================
Computes ONE monthly data point (team_values) directly from live Jira, using the
FL1/FL2 definitions validated 1:1 against the Nave June-2026 Core report and the
official Notion methodology.

Currently LIVE-VALIDATED for exactly one team:
    Users & Locations  ->  Jira project GXY  ->  realm 'core', team key 'ul'

Other teams must NOT be added here until their project mapping + status buckets are
human-confirmed and reconciled against a real Nave PDF (standing rule: never guess
team->project mappings).

Public API
----------
    compute_team_values(jira_conn, anchor)  -> {"ul": {"fl1": {...}, "fl2": {...}}}
    report_anchor(year, month, day=20)       -> datetime.date  (next business day if weekend)
    month_label(anchor)                       -> "Jun 26"   (data.json month string)

The returned team_values dict is exactly what update_data(_live).update() expects.

Window
------
Rolling 120 calendar days ending at the report anchor. The exact Nave cutoff instant
is still to be confirmed by the user; residual ±1–3 on Throughput / Epics Delivered is
accepted "boundary noise". Tune WINDOW_DAYS / the end bound here once the exact cutoff
is known — nothing else needs to change.
"""
import asyncio, time
from datetime import datetime, timezone, timedelta, date
import numpy as np
from agent_tools import call_tool, async_call_tool

WINDOW_DAYS = 120
CONCURRENCY = 16

def _req(name, args, tries=5):
    """Synchronous Jira call with retry/backoff on transient errors (ConnectError etc.)."""
    for i in range(tries):
        try:
            return call_tool(name, args)
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(1.5 * (i + 1))

async def _areq(name, args, tries=5):
    """Async Jira call with retry/backoff on transient errors."""
    for i in range(tries):
        try:
            return await async_call_tool(name, args)
        except Exception:
            if i == tries - 1:
                raise
            await asyncio.sleep(1.5 * (i + 1))

# ─── Core realm team -> Jira project mapping (all confirmed) ───────────────────
# ul  = GXY  (Users & Locations)     cw = CW   (Core-Workouts)
# ox  = OX   (Operator Experience)   ds = DS   (Data Science)
# mm  = CONN (API Platform, ex-MMS Connect)
CORE_TEAMS = {"ul": "GXY", "cw": "CW", "ox": "OX", "ds": "DS", "mm": "CONN"}

# ─── Machine realm team mapping (8 teams, confirmed with Taner Pereira, Jul 2026) ─
# A team scope may be a plain project string (like Core) OR a rich dict when the team
# is NOT a whole project. Rich dict fields:
#   status_project : project key used to derive FL1 status buckets (statusCategory)
#   fl1 / fl2      : base JQL clause for tasks / epics
#   bugs           : base JQL clause already restricted to bug issues
# MI OS / MI Backend live inside ONE project (MI) split by component; their bug counts
# come from dedicated saved filters (16309 / 16310), NOT project-wide bug queries.
MACHINE_TEAMS = {
    "fh":   "ASD",     # Fitness Hub
    "bs":   "BAST",    # Backstage (ex-MS Rocket)
    "cr":   "SCOR",    # MSW Core & Retention  (split from old MSW)
    "aq":   "SMAQ",    # MSW Acquisition & HW  (split from old MSW)
    "be":   "DEBE",    # MSW Backend           (split from old MSW)
    "mifw": "FW",      # MI Firmware
    "mios": {"status_project": "MI",
             "fl1": 'project = MI AND component in (OS, Other, "Smart Flex", "Smart Balance", "Smart Strength", "Smart Flex Pi Software")',
             "fl2": 'project = MI AND component in (OS, Other, "Smart Flex", "Smart Balance", "Smart Strength", "Smart Flex Pi Software")',
             "bugs": "filter = 16309"},
    "mibe": {"status_project": "MI", "fl1": 'project = MI AND component = "BE/API"',
             "fl2": 'project = MI AND component = "BE/API"', "bugs": "filter = 16310"},
}

# ─── Machine realm FL2 (epics) card grouping (7 cards, validated May 2026) ─────────
# Epics are NOT split by component, so the epic-level cards DIFFER from the 8 FL1 teams:
# MI OS + MI Backend both roll up into ONE card "Machine Infrastructure" = the whole MI
# project (MI literally = Machine Infrastructure). Delivered epics matched the report 1:1
# (7/16/3/2/3/4/4 = 39/39) for May 2026.
# fl2_aging picks the WIP Aging Risk method for the epic traffic lights:
#   "weekly"     -> absolute buckets 🔴>12wk(>84d) / 🟡8-12wk(56-84d) / 🟢<8wk(<56d)
#   "percentile" -> relative to delivered cycle-time distribution (Core-style _ryg)
# NOTE: modes below are PROVISIONAL and set to the best empirical fit vs the May report.
# The report footnote ("MSW/MI=weekly, Fitness Hub=percentile") does NOT fully reproduce it:
# Backstage & MSW Core fit percentile; Machine Infrastructure fits neither (MI-7637 Yocto 5.0
# and MI-8450 GPU RTX 5050, ~100d in Doing, show red but the report shows 0 red).
# AWAITING Luis's confirmation of the exact per-team method — then finalize these.
MACHINE_FL2 = {
    "mifw":    {"display": "MI Firmware",            "fl2": "project = FW",   "fl2_aging": "percentile"},
    "minfra":  {"display": "Machine Infrastructure", "fl2": "project = MI",   "fl2_aging": "percentile"},
    "fh":      {"display": "Fitness Hub",            "fl2": "project = ASD",  "fl2_aging": "percentile"},
    "bs":      {"display": "Backstage",              "fl2": "project = BAST", "fl2_aging": "percentile"},
    "mswbe":   {"display": "MSW Backend",            "fl2": "project = DEBE", "fl2_aging": "percentile"},
    "mswcore": {"display": "MSW Core",               "fl2": "project = SCOR", "fl2_aging": "percentile"},
    "mswacq":  {"display": "MSW Acq",                "fl2": "project = SMAQ", "fl2_aging": "percentile"},
}

# --- Apps realm team mapping (4 teams; boards confirmed by Denys A., Jul 2026) ---
# 2 established teams (Trainer, Workout) + 2 new reorg teams (BMA Core Growth,
# BMA Engagement & Adoption) that spun off old BMA Core/Enterprise ~20 Jul 2026.
# BMA Core (FA) and BMA Enterprise (BMAE) are NO LONGER reported (removed 2026-07-24):
# their work was redistributed to the new boards, so per-team figures no longer
# reflect reality. BMA Platform is intentionally NOT reported yet (team not active).
#   trainer: composite scope across projects/components/labels (status buckets from MA).
APPS_TEAMS = {
    "bma_core_growth": "BMACG",
    "bma_engagement": "BMAEA",
    "trainer": {"status_project": "MA",
                "fl1": '(project in (10033) OR project = 10052 OR component = "iOS TA" OR labels in (pairing, TrainerApp))'},
    "workout": "XT",
}

def _normalize_cfg(val):
    """Normalize a team scope (plain project string or rich dict) to a standard cfg
    with fields: status_project, fl1, fl2, bugs (base JQL clauses)."""
    if isinstance(val, str):
        return {"status_project": val, "fl1": f"project = {val}",
                "fl2": f"project = {val}", "bugs": f"project = {val} AND issuetype = Bug",
                "done_extra": None, "worked_only": False}
    fl1 = val["fl1"]
    return {"status_project": val["status_project"], "fl1": fl1,
            "fl2": val.get("fl2", fl1),
            "fl2_aging": val.get("fl2_aging", "percentile"),
            "bugs": val.get("bugs", f"({fl1}) AND issuetype = Bug"),
            "done_extra": val.get("done_extra"),
            "worked_only": val.get("worked_only", False)}

# ─── Flow Metrics status/workflow definitions (shared EGYM workflow) ───────────
FL1_TYPES = "(Story,Task,Maintenance,Bug,Release)"   # per How-To: only Research/Sub-task
# (and Epic=FL2) are excluded. "Release" IS counted by the manual reports (confirmed by
# Luis Torres, Jul 22 2026). Verified safe for Core: 0 Release-type items resolved in the
# window across all 5 Core projects, so this does not disturb the reconciled Core numbers.
# FL1 status buckets are derived PER-PROJECT from Jira statusCategory, because EGYM
# teams do NOT share one FL1 workflow. Examples validated against Nave June 2026:
#   GXY (Users & Locations) completes at "Released"; OX (Operator Experience) has NO
#   "Released" status and completes at "Done"; stage names differ across projects.
# statusCategory is workflow-agnostic and reconciles for both GXY & OX:
#   indeterminate            -> Doing
#   done                     -> Done  (ends cycle time)
#   done minus "Won't..."    -> Done-Throughput (counts toward throughput/tech%)
# See _fl1_buckets().

FL2_START = "10506"                                  # "0 to 25%" == epic cycle start
FL2_DOING = {"10506", "10507", "10508", "10509", "10723",
             "10450", "10724", "10023", "10444"}
#            0-25%, 26-50%, 51-75%, 76-99%, Canary Preparation,
#            In Canary, Phased Rollout, Ready For Release, In Observation
FL2_DELIVERED = "10002"                              # "Done" == epic delivered
FL2_DOING_NAMES = ["0 to 25%", "26 to 50%", "51 to 75%", "76 to 99%",
                   "Canary Preparation", "In Canary", "Phased Rollout",
                   "Ready For Release", "In Observation"]

# Tech = customfield_10463 (Tech Task dropdown) value in {Technical Task, Security Task}.
# customfield_11502 (Tech Roadmap) is intentionally NOT used: verified Jul 2026 that
# value-specific 10463 keeps Core byte-identical and fixes Apps (11502 over-counted).
TECH_FIELDS = ["customfield_10463"]
TECH_VALUES = {"Technical Task", "Security Task"}
def _is_tech(f):
    v = f.get("customfield_10463")
    if not v:
        return False
    if isinstance(v, dict):
        v = [v]
    if isinstance(v, list):
        return any((x.get("value") if isinstance(x, dict) else x) in TECH_VALUES for x in v)
    return v in TECH_VALUES

# ─── FL2 evergreen exclusion list (human-picked, explicit) ─────────────────────
# Some long-lived "umbrella"/evergreen epics were closed as a one-time cleanup in
# July 2026. Per user decision, these specific epics are NOT real deliveries and are
# excluded from FL2 delivered count / cycle time / tech% — now and going forward.
# This is an explicit key list (NOT an age heuristic) so it never affects any other
# epic. Excluding them does NOT change historical months (they never counted before).
# Add a key here only after a human confirms the epic is an evergreen/umbrella closure.
FL2_EXCLUDE = {
    "GXY-4979",   # Product and Support Improvements (created 2021)
    "GXY-4966",   # Tech Improvements and Maintenance 2021-2025 (created 2021)
    "GXY-7159",   # Galaxy Deprecation Research and Implementation Phase 1 (created 2024-06)
    "GXY-7928",   # Speed up UPDS search per gym II (created 2024-09)
    "CONN-885",   # OneMMS maintenance (created 2020-04, evergreen/umbrella; confirmed by Alexa Bobina 2026-08-08)
    "CONN-1389",  # OneMMS v2 backlog (created 2022-01, evergreen/umbrella; confirmed by Alexa Bobina 2026-08-08)
}

MONTHS_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Per-realm report cadence day (official Notion how-to). Reports for different realms
# are generated on different days of the month. The exact time of day is NOT important
# (residual ±1–5 boundary noise is accepted); only the calendar day + weekend roll-forward.
REALM_CADENCE = {"wellpass": 15, "core": 20, "apps": 25, "machine": 30}

# ─── Date helpers ───────────────────────────────────────────────────────────────
def report_anchor(year, month, realm="core"):
    """Report cadence anchor for a realm. Wellpass=15th, Core=20th, Apps=25th,
    Machine=30th. The day is clamped to the last day of the month (e.g. Machine in
    February), then rolled forward to the next business day if it lands on Sat/Sun."""
    import calendar
    day = REALM_CADENCE.get(realm, 20)
    day = min(day, calendar.monthrange(year, month)[1])
    d = date(year, month, day)
    while d.weekday() >= 5:            # 5 = Sat, 6 = Sun
        d += timedelta(days=1)
    return d

def month_label(anchor):
    """data.json month string, e.g. date(2026,6,20) -> 'Jun 26'."""
    return f"{MONTHS_ABBR[anchor.month - 1]} {anchor.strftime('%y')}"

def _window(anchor):
    """Return (start_str, end_excl_str) for JQL. end is exclusive (anchor day fully included)."""
    start = anchor - timedelta(days=WINDOW_DAYS)
    end_excl = anchor + timedelta(days=1)
    return start.isoformat(), end_excl.isoformat()

# ─── Jira helpers ───────────────────────────────────────────────────────────────
def _search_all(conn, jql, fields):
    out = []; tok = None
    while True:
        a = {"connectionId": conn, "jql": jql, "fields": fields, "maxResults": 100}
        if tok:
            a["nextPageToken"] = tok
        r = _req("jira_search_issues", a)
        out.extend(r.get("issues", []))
        if r.get("hasMore"):
            tok = r.get("nextPageToken") or (r.get("truncation") or {}).get("nextPageToken")
            if not tok:
                break
        else:
            break
    return out

def _count(conn, jql):
    return len(_search_all(conn, jql, ["id"]))

def _parse(ts):
    ts = ts.replace("Z", "+0000")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(ts, fmt)
        except ValueError:
            pass
    raise ValueError(f"Unparseable timestamp: {ts}")

async def _transitions(conn, iid, sem):
    """Return sorted list of (time, to_status_id) status transitions for an issue."""
    async with sem:
        hist = []; start = 0
        while True:
            r = await _areq("jira_get_issue_changelog", {
                "connectionId": conn, "issueIdOrKey": str(iid),
                "startAt": start, "maxResults": 100})
            hist.extend(r.get("histories", []))
            if r.get("hasMore"):
                start = r.get("nextStartAt", start + 100)
            else:
                break
    tr = []
    for h in hist:
        t = _parse(h["created"])
        for it in h.get("items", []):
            if it.get("fieldId") == "status" or it.get("field") == "status":
                tr.append((t, it.get("to")))
    tr.sort(key=lambda z: z[0])
    return tr

def _first_enter(tr, bucket, after=None, before=None):
    for t, sid in tr:
        if sid in bucket and (after is None or t >= after) and (before is None or t <= before):
            return t
    return None

def _status_at(tr, when):
    st = None
    for t, sid in tr:
        if t <= when:
            st = sid
    return st

def _ryg(ages, cts, method="linear"):
    """Red/Yellow/Green counts by percentile of the team's own cycle-time distribution:
    Red > p85, Yellow in [p70, p85], Green < p70.
    method: percentile estimator. FL1/Core use 'linear' (unchanged, keeps Core
    byte-identical). FL2 epics pass 'higher' (nearest-rank round-up) to match Nave's
    'to develop 85% of the tickets' definition (verified vs Mar/Apr manual reports)."""
    ages = [a for a in ages if a is not None]
    if not cts:
        return 0, 0, len(ages)
    p70 = np.percentile(cts, 70, method=method)
    p85 = np.percentile(cts, 85, method=method)
    r = sum(1 for a in ages if a > p85)
    y = sum(1 for a in ages if p70 <= a <= p85)
    g = sum(1 for a in ages if a < p70)
    return r, y, g

# ─── FL1 (tasks) ────────────────────────────────────────────────────────────────
def _fl1_buckets(conn, project, done_extra=None):
    """Derive per-project FL1 status buckets from Jira statusCategory (workflow-agnostic).
    Returns (doing_ids, done_ids, done_tp_ids, names) where:
      doing_ids   = statuses in category 'indeterminate' (work in progress)
      done_ids    = statuses in category 'done' (any completion, ends cycle time)
      done_tp_ids = done_ids minus "Won't..." statuses (counts toward throughput/tech%)
    """
    r = call_tool("jira_get_project_statuses", {"connectionId": conn, "projectIdOrKey": project})
    doing = set(); done = set(); done_tp = set(); names = {}
    for it in r:
        for s in it["statuses"]:
            cat = s["statusCategory"]["key"]; sid = s["id"]; nm = s["name"]; names[sid] = nm
            if cat == "indeterminate":
                doing.add(sid)
            elif cat == "done":
                done.add(sid)
                if not nm.lower().startswith("won't"):
                    done_tp.add(sid)
    # Per-team terminal-status override: some projects complete at a status that Jira's
    # statusCategory does NOT mark 'done' (e.g. FA/BMA Core completes at "Released",
    # a status later removed from the scheme). Force these IDs into done + done_tp so
    # throughput / cycle time see them. Core & Machine pass none -> unchanged.
    for sid in (done_extra or []):
        sid = str(sid); done.add(sid); done_tp.add(sid); names.setdefault(sid, sid)
    return doing, done, done_tp, names

async def _fl1(conn, cfg, anchor, sem):
    start_s, end_s = _window(anchor)
    win = f'("{start_s}","{end_s}")'
    scope = cfg["fl1"]; bugs_base = cfg["bugs"]
    doing, done, done_tp, names = _fl1_buckets(conn, cfg["status_project"], cfg.get("done_extra"))
    doing_ids = ",".join(sorted(doing))

    # Throughput + tech% (items reaching a Done-throughput status in window). When the
    # team is worked_only, restrict to items that actually passed through a Doing status
    # (excludes administrative straight-to-done closures), matching Nave's throughput.
    tp_ids = ",".join(sorted(done_tp))
    worked = f' AND status WAS IN ({doing_ids})' if cfg.get("worked_only") else ""
    # Count each item's FIRST completion only: it must reach a Done-throughput status
    # DURING the window AND not have been in any terminal status before the window. This
    # immunises throughput against mass re-closures (e.g. FA/BMA Core's 23-Jul-2026 bulk
    # move of legacy "Released" items to "Done", which otherwise injects ~2000 phantom
    # completions). Normal months are unaffected (Core reconciles byte-identical).
    firstonly = f' AND NOT status WAS IN ({tp_ids}) BEFORE "{start_s}"'
    tp = _search_all(conn,
        f'({scope}) AND issuetype in {FL1_TYPES} AND status CHANGED TO ({tp_ids}) DURING {win}{firstonly}{worked}',
        ["issuetype"] + TECH_FIELDS)
    tp_n = len(tp)
    tech_n = sum(1 for i in tp if _is_tech(i["fields"]))
    tech_pct = round(100 * tech_n / tp_n) if tp_n else 0

    # Cycle time p85 (first entry into Doing -> first entry into Done)
    trs = await asyncio.gather(*[_transitions(conn, i["key"], sem) for i in tp])
    cts = []
    for tr in trs:
        d0 = _first_enter(tr, doing)
        dn = _first_enter(tr, done, after=d0)
        if d0 and dn and dn >= d0:
            cts.append((dn - d0).total_seconds() / 86400)
    ct_p85 = round(np.percentile(cts, 85)) if cts else None

    # Bugs (from Jira, NOT Nave): created / resolved within window. bugs_base is already
    # restricted to bug issues (project+issuetype, or a dedicated saved filter).
    bC = _count(conn, f'({bugs_base}) AND created >= "{start_s}" AND created < "{end_s}"')
    bR = _count(conn, f'({bugs_base}) AND resolutiondate >= "{start_s}" AND resolutiondate < "{end_s}"')

    # WIP snapshot at anchor (items in a Doing status at report date)
    wip = _search_all(conn,
        f'({scope}) AND issuetype in {FL1_TYPES} AND status WAS IN ({doing_ids}) ON "{anchor.isoformat()}"',
        ["id"])
    snap = datetime(anchor.year, anchor.month, anchor.day, 23, 59, 59, tzinfo=timezone.utc)
    wtrs = await asyncio.gather(*[_transitions(conn, i["id"], sem) for i in wip])
    ages = []
    for tr in wtrs:
        # Exclude items whose status at the snapshot instant is NOT actually Doing
        # (e.g. items completed on the report day itself must not count as WIP).
        if _status_at(tr, snap) not in doing:
            continue
        d0 = _first_enter(tr, doing, before=snap)
        if d0 is not None:
            ages.append((snap - d0).total_seconds() / 86400)
    wR, wY, wG = _ryg(ages, cts)

    return {"ct": ct_p85, "tp": tp_n, "wR": wR, "wY": wY, "wG": wG,
            "bC": bC, "bR": bR, "tech": tech_pct}

# ─── FL2 (epics) ─────────────────────────────────────────────────────────────────
# Epic WIP Aging Risk buckets, "weekly" (absolute) variant used by Machine MSW/MI cards.
FL2_AGING_GREEN_D = 56    # < 8 weeks  -> green
FL2_AGING_RED_D   = 84    # > 12 weeks -> red ; between (inclusive) -> yellow
def _ryg_weekly(ages):
    R = sum(1 for a in ages if a > FL2_AGING_RED_D)
    Y = sum(1 for a in ages if FL2_AGING_GREEN_D <= a <= FL2_AGING_RED_D)
    G = sum(1 for a in ages if a < FL2_AGING_GREEN_D)
    return R, Y, G

async def _fl2(conn, cfg, anchor, sem):
    start_s, end_s = _window(anchor)
    win = f'("{start_s}","{end_s}")'
    scope = cfg["fl2"]

    # Delivered epics (reached Done in window). Nave counts an epic as delivered
    # only if it was actually WORKED — i.e. it passed through a Doing stage at some
    # point. Epics closed straight to Done without ever entering a Doing bucket
    # (administrative closures) are excluded, which also aligns the tech% denominator
    # and the cycle-time population with the delivered count.
    raw = _search_all(conn,
        f'({scope}) AND issuetype=Epic AND status CHANGED TO {FL2_DELIVERED} DURING {win}',
        TECH_FIELDS + ["created"])
    # Drop human-confirmed evergreen/umbrella epics (explicit key list, not a heuristic).
    raw = [i for i in raw if (i.get("key") or i.get("id")) not in FL2_EXCLUDE]
    trs = await asyncio.gather(*[_transitions(conn, i["id"], sem) for i in raw])
    kept = []          # (issue, doing_start, done_time)
    for issue, tr in zip(raw, trs):
        s = _first_enter(tr, FL2_DOING)          # first entry into ANY Doing bucket
        d = None
        for t, sid in tr:
            if sid == FL2_DELIVERED and (s is None or t >= s):
                d = t
                break
        if s and d and d >= s:
            kept.append((issue, s, d))
    n = len(kept)
    tech_n = sum(1 for issue, _, _ in kept if _is_tech(issue["fields"]))
    tech_pct = round(100 * tech_n / n) if n else 0

    # Epic cycle time p85 (first entry into a Doing bucket -> Done). Nave uses the
    # nearest-rank 'higher' estimator ("to develop 85% of the tickets"), verified vs the
    # manual reports (minfra Mar cts P85 higher = 163 == report 163).
    cts = [(d - s).total_seconds() / 86400 for _, s, d in kept]
    ct_p85 = round(np.percentile(cts, 85, method="higher")) if cts else None

    # WIP epics snapshot at anchor
    doing_names = ",".join('"%s"' % s for s in FL2_DOING_NAMES)
    cand = _search_all(conn,
        f'({scope}) AND issuetype=Epic AND status WAS IN ({doing_names}) ON "{anchor.isoformat()}"',
        ["id"])
    snap = datetime(anchor.year, anchor.month, anchor.day, 23, 59, 59, tzinfo=timezone.utc)
    wtrs = await asyncio.gather(*[_transitions(conn, i["id"], sem) for i in cand])
    ages = []
    for tr in wtrs:
        if _status_at(tr, snap) not in FL2_DOING:
            continue
        s = _first_enter(tr, {FL2_START}, before=snap) or _first_enter(tr, FL2_DOING, before=snap)
        if s:
            ages.append((snap - s).total_seconds() / 86400)
    wip_n = len(ages)
    if cfg.get("fl2_aging") == "weekly":
        wR, wY, wG = _ryg_weekly(ages)
    else:
        wR, wY, wG = _ryg(ages, cts, method="higher")

    return {"ct": ct_p85, "del": n, "wip": wip_n, "wR": wR, "wY": wY, "wG": wG, "tech": tech_pct}

# ─── Orchestration ───────────────────────────────────────────────────────────────
async def _compute_team(conn, cfg, anchor, sem):
    # FL1 and FL2 are independent — run them concurrently to cut wall-clock time.
    fl1, fl2 = await asyncio.gather(_fl1(conn, cfg, anchor, sem),
                                    _fl2(conn, cfg, anchor, sem))
    return {"fl1": fl1, "fl2": fl2}

async def _compute(conn, anchor, teams):
    # One shared semaphore caps total in-flight Jira calls across ALL teams, but every
    # team is scheduled concurrently so a multi-team run finishes in roughly the time of
    # the slowest single team instead of the sum (needed to stay under the 300s cmd cap).
    sem = asyncio.Semaphore(CONCURRENCY)
    keys = list(teams.keys())
    results = await asyncio.gather(
        *[_compute_team(conn, _normalize_cfg(teams[k]), anchor, sem) for k in keys])
    return dict(zip(keys, results))

def compute_team_values(jira_conn, anchor, teams=None):
    """Compute Core-realm data points for a given report anchor (datetime.date).
    teams: dict {team_key: jira_project}. Defaults to all 5 Core teams (CORE_TEAMS).
    Returns {team_key: {"fl1": {...}, "fl2": {...}}} ready for update_data.update()."""
    return asyncio.run(_compute(jira_conn, anchor, teams or CORE_TEAMS))

async def _compute_fl2(conn, anchor, cards):
    """Compute FL2 (epics) only, for a set of epic-level cards. Each card cfg carries its
    own `fl2` scope and `fl2_aging` mode. Used for the Machine realm where the epic cards
    (7) do not line up with the FL1 teams (8)."""
    sem = asyncio.Semaphore(CONCURRENCY)
    keys = list(cards.keys())
    results = await asyncio.gather(*[_fl2(conn, cards[k], anchor, sem) for k in keys])
    return dict(zip(keys, results))

def compute_fl2_cards(jira_conn, anchor, cards=None):
    """Compute FL2 epic cards for a report anchor. Defaults to the Machine MACHINE_FL2 grouping.
    Returns {card_key: {ct, del, wip, wR, wY, wG, tech}}."""
    return asyncio.run(_compute_fl2(jira_conn, anchor, cards or MACHINE_FL2))

# ─── Self-test / reconciliation ──────────────────────────────────────────────────
if __name__ == "__main__":
    import sys, json
    if len(sys.argv) < 2:
        print("usage: python compute_jira.py <jira_conn> [YYYY-MM-DD] [team_key]")
        sys.exit(1)
    conn = sys.argv[1]
    anchor = None
    teams = CORE_TEAMS
    if len(sys.argv) > 2 and sys.argv[2] not in ("", "-"):
        y, m, d = map(int, sys.argv[2].split("-"))
        anchor = date(y, m, d)
    else:
        anchor = report_anchor(2026, 6)   # Core June report
    if len(sys.argv) > 3:
        teams = {sys.argv[3]: CORE_TEAMS[sys.argv[3]]}

    # June Nave targets (from data_seed.json) for reconciliation
    NAVE = {
        "ul": {"ct":9,"tp":167,"wRYG":"3/2/6","bC":10,"bR":11,"tech":75,"fct":295,"del":5,"fwip":7,"ftech":40},
        "cw": {"ct":12,"tp":172,"wRYG":"2/1/7","bC":27,"bR":24,"tech":63,"fct":166,"del":4,"fwip":5,"ftech":50},
        "mm": {"ct":21,"tp":122,"wRYG":"2/2/6","bC":22,"bR":18,"tech":7,"fct":203,"del":4,"fwip":13,"ftech":0},
        "ox": {"ct":37,"tp":92,"wRYG":"5/1/7","bC":9,"bR":5,"tech":21,"fct":65,"del":2,"fwip":9,"ftech":0},
        "ds": {"ct":23,"tp":113,"wRYG":"1/1/8","bC":41,"bR":29,"tech":0,"fct":134,"del":2,"fwip":7,"ftech":0},
    }
    print(f"Report anchor: {anchor}  ({month_label(anchor)})  window={WINDOW_DAYS}d  teams={list(teams)}")
    tv = compute_team_values(conn, anchor, teams)
    for tk in teams:
        f1 = tv[tk]["fl1"]; f2 = tv[tk]["fl2"]; nv = NAVE.get(tk, {})
        print(f"\n===== {tk}  ({teams[tk]}) =====")
        print(f"  FL1 CT p85 : {f1['ct']:<5} (Nave {nv.get('ct')})")
        print(f"  FL1 TP     : {f1['tp']:<5} (Nave {nv.get('tp')})")
        print(f"  FL1 Tech%  : {f1['tech']:<5} (Nave {nv.get('tech')})")
        print(f"  FL1 Bugs   : C={f1['bC']} R={f1['bR']}  (Nave {nv.get('bC')} / {nv.get('bR')})")
        print(f"  FL1 WIP    : {f1['wR']}/{f1['wY']}/{f1['wG']}  (Nave {nv.get('wRYG')})")
        print(f"  FL2 CT p85 : {f2['ct']:<5} (Nave {nv.get('fct')})")
        print(f"  FL2 Deliv  : {f2['del']:<5} (Nave {nv.get('del')})")
        print(f"  FL2 WIP    : {f2['wip']:<5} (Nave {nv.get('fwip')})")
        print(f"  FL2 Tech%  : {f2['tech']:<5} (Nave {nv.get('ftech')})")
