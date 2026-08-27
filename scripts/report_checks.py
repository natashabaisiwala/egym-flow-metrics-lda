"""
EGYM Flow Metrics — data-quality guardrails  [reusable]
=======================================================
Two layers of protection against bad/hallucinated numbers reaching the dashboards:

  validate(team_values)  -> list of HARD errors (impossible values / broken invariants).
                            If non-empty the caller MUST abort the publish.
  anomalies(prev, new)   -> list of SOFT anomaly strings (suspiciously large month-over-
                            month moves). These do NOT mean the data is wrong, but the
                            caller must route them to a human for approval before
                            publishing rather than shipping silently.

Both operate purely on the computed team_values dict; they never call Jira, so they are
cheap, deterministic and side-effect free.
"""

# ── HARD validation ──────────────────────────────────────────────────────────
def _is_int_or_none(v):
    return v is None or isinstance(v, int)

def _is_num_or_none(v):
    return v is None or (isinstance(v, (int, float)) and not isinstance(v, bool))

# Realms whose FL1 uses Average WIP (a float, key "wipAvg") instead of the
# Red/Yellow/Green report-date WIP snapshot (wR/wY/wG, ints). Wellpass only.
REALM_NO_FL1_WIP_RYG = {"wellpass"}
# wipAvgRoll: the rolling-120-day counterpart of wipAvg, used ONLY for the KPI-headline
# card (never charted per calendar month) on REALM_NO_FL1_WIP_RYG realms -- see
# ctRoll/tpRoll/techRoll below. Confirmed with the user 2026-08-27: a single volatile
# calendar month must not drive the headline number, so KPI cards show a genuine
# rolling-120-day recompute (same window/logic FL1 always used before this redesign)
# instead of an average of the monthly chart points.
_FLOAT_FIELDS = {"wipAvg", "wipAvgRoll"}

def validate(team_values, realm="core"):
    """Return a list of hard error strings. Empty list == data passed all invariants."""
    errs = []
    no_ryg = realm in REALM_NO_FL1_WIP_RYG
    for tk, tv in team_values.items():
        fl1 = tv.get("fl1", {}); fl2 = tv.get("fl2", {})

        # types (skip *_keys fields -- manifest-only issue-key lists added to
        # compute_jira.py on 2026-08-20 for delivery-manifest traceability, e.g.
        # wR_keys/wY_keys/wG_keys on fl1/fl2. These are lists of issue keys, not
        # real int/None metrics, and were never meant to be validated here.)
        for fl_name, fl in (("fl1", fl1), ("fl2", fl2)):
            for k, v in fl.items():
                if k.endswith("_keys"):
                    continue
                ok = _is_num_or_none(v) if k in _FLOAT_FIELDS else _is_int_or_none(v)
                if not ok:
                    errs.append(f"{tk}.{fl_name}.{k} is not int/None: {v!r}")

        # non-negative counts. FL1 realms without WIP RYG (calendar-month Wellpass)
        # have no wR/wY/wG to check; their wipAvg/wipAvgRoll are checked separately
        # below. tpRoll (rolling-120-day KPI-headline throughput) is checked here too.
        fl1_count_keys = (["tp", "tpRoll", "bC", "bR"] if no_ryg
                           else ["tp", "wR", "wY", "wG", "bC", "bR"])
        for fl_name, fl, keys in (
            ("fl1", fl1, fl1_count_keys),
            ("fl2", fl2, ["del", "wip", "wR", "wY", "wG"]),
        ):
            for k in keys:
                v = fl.get(k)
                if isinstance(v, int) and v < 0:
                    errs.append(f"{tk}.{fl_name}.{k} is negative: {v}")

        if no_ryg:
            for k in ("wipAvg", "wipAvgRoll"):
                wa = fl1.get(k)
                if isinstance(wa, (int, float)) and wa < 0:
                    errs.append(f"{tk}.fl1.{k} is negative: {wa}")

        # cycle time non-negative (None allowed = no completions in window). ctRoll
        # (rolling-120-day KPI-headline cycle time, no_ryg realms only) checked too.
        for fl_name, fl in (("fl1", fl1), ("fl2", fl2)):
            for k in (("ct", "ctRoll") if (fl_name == "fl1" and no_ryg) else ("ct",)):
                ct = fl.get(k)
                if isinstance(ct, int) and ct < 0:
                    errs.append(f"{tk}.{fl_name}.{k} is negative: {ct}")

        # tech % must be within 0..100. techRoll (no_ryg realms only) checked too.
        for fl_name, fl in (("fl1", fl1), ("fl2", fl2)):
            for k in (("tech", "techRoll") if (fl_name == "fl1" and no_ryg) else ("tech",)):
                t = fl.get(k)
                if isinstance(t, int) and not (0 <= t <= 100):
                    errs.append(f"{tk}.{fl_name}.{k} out of range 0-100: {t}")

        # FL2 invariant: the red/yellow/green WIP buckets must sum to the WIP count
        wsum = sum(fl2.get(k) or 0 for k in ("wR", "wY", "wG"))
        wip = fl2.get("wip")
        if isinstance(wip, int) and wsum != wip:
            errs.append(f"{tk}.fl2 WIP mismatch: wR+wY+wG={wsum} but wip={wip}")

        # consistency: throughput but no cycle time (or vice versa) is suspicious->hard
        if isinstance(fl1.get("tp"), int) and fl1.get("tp") > 0 and fl1.get("ct") is None:
            errs.append(f"{tk}.fl1 has throughput={fl1['tp']} but ct is None")
        if no_ryg and isinstance(fl1.get("tpRoll"), int) and fl1.get("tpRoll") > 0 and fl1.get("ctRoll") is None:
            errs.append(f"{tk}.fl1 has tpRoll={fl1['tpRoll']} but ctRoll is None")
        if isinstance(fl2.get("del"), int) and fl2.get("del") > 0 and fl2.get("ct") is None:
            errs.append(f"{tk}.fl2 has delivered={fl2['del']} but ct is None")
    return errs

# ── SOFT anomaly detection (month-over-month) ────────────────────────────────
# (pct_threshold, abs_threshold): flag when abs move >= abs_threshold AND
# (previous == 0 OR relative move >= pct_threshold). tech uses pct=0 so any
# absolute swing >= its abs_threshold (in percentage points) is flagged.
_THRESH = {
    "fl1": {"ct": (0.6, 25), "tp": (0.5, 25), "tech": (0.0, 25), "bC": (0.6, 15), "bR": (0.6, 15),
            "wR": (0.6, 3), "wY": (0.6, 3), "wG": (0.6, 3)},
    "fl2": {"ct": (0.6, 40), "del": (0.6, 3), "wip": (0.6, 5), "tech": (0.0, 25),
            "wR": (0.6, 3), "wY": (0.6, 3), "wG": (0.6, 3)},
}
_WIP_THRESH = (0.6, 5)  # FL1 total WIP (wR+wY+wG)
_WIPAVG_THRESH = (0.5, 5.0)  # FL1 Average WIP, for REALM_NO_FL1_WIP_RYG realms -- signed off 2026-08-27

def _flag(prev, cur, pctthr, absthr):
    if prev is None or cur is None:
        return prev != cur  # appearing/disappearing data is worth a look
    delta = abs(cur - prev)
    if delta < absthr:
        return False
    if prev == 0:
        return True
    return (delta / abs(prev)) >= pctthr

def anomalies(prev, new, realm="core"):
    """prev/new are {team: {"fl1":{...}, "fl2":{...}}}. Returns list of human-readable
    anomaly strings. prev may be None/empty (first month) -> returns []."""
    if not prev:
        return []
    out = []
    no_ryg = realm in REALM_NO_FL1_WIP_RYG
    for tk, tv in new.items():
        p = prev.get(tk)
        if not p:
            out.append(f"{tk}: no previous-month data to compare (new team?)")
            continue
        for fl in ("fl1", "fl2"):
            thresh = _THRESH[fl]
            if fl == "fl1" and no_ryg:
                thresh = {k: v for k, v in thresh.items() if k not in ("wR", "wY", "wG")}
                thresh["wipAvg"] = _WIPAVG_THRESH
            for k, (pctthr, absthr) in thresh.items():
                pv = p.get(fl, {}).get(k); cv = tv.get(fl, {}).get(k)
                if _flag(pv, cv, pctthr, absthr):
                    out.append(f"{tk}.{fl}.{k}: {pv} -> {cv} (large change)")
            if fl == "fl1" and not no_ryg:
                pw = sum(p.get("fl1", {}).get(x) or 0 for x in ("wR", "wY", "wG"))
                cw = sum(tv.get("fl1", {}).get(x) or 0 for x in ("wR", "wY", "wG"))
                if _flag(pw, cw, *_WIP_THRESH):
                    out.append(f"{tk}.fl1.WIP(total): {pw} -> {cw} (large change)")
    return out
