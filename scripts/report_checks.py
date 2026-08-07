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

def validate(team_values):
    """Return a list of hard error strings. Empty list == data passed all invariants."""
    errs = []
    for tk, tv in team_values.items():
        fl1 = tv.get("fl1", {}); fl2 = tv.get("fl2", {})

        # types
        for fl_name, fl in (("fl1", fl1), ("fl2", fl2)):
            for k, v in fl.items():
                if not _is_int_or_none(v):
                    errs.append(f"{tk}.{fl_name}.{k} is not int/None: {v!r}")

        # non-negative counts
        for fl_name, fl, keys in (
            ("fl1", fl1, ["tp", "wR", "wY", "wG", "bC", "bR"]),
            ("fl2", fl2, ["del", "wip", "wR", "wY", "wG"]),
        ):
            for k in keys:
                v = fl.get(k)
                if isinstance(v, int) and v < 0:
                    errs.append(f"{tk}.{fl_name}.{k} is negative: {v}")

        # cycle time non-negative (None allowed = no completions in window)
        for fl_name, fl in (("fl1", fl1), ("fl2", fl2)):
            ct = fl.get("ct")
            if isinstance(ct, int) and ct < 0:
                errs.append(f"{tk}.{fl_name}.ct is negative: {ct}")

        # tech % must be within 0..100
        for fl_name, fl in (("fl1", fl1), ("fl2", fl2)):
            t = fl.get("tech")
            if isinstance(t, int) and not (0 <= t <= 100):
                errs.append(f"{tk}.{fl_name}.tech out of range 0-100: {t}")

        # FL2 invariant: the red/yellow/green WIP buckets must sum to the WIP count
        wsum = sum(fl2.get(k) or 0 for k in ("wR", "wY", "wG"))
        wip = fl2.get("wip")
        if isinstance(wip, int) and wsum != wip:
            errs.append(f"{tk}.fl2 WIP mismatch: wR+wY+wG={wsum} but wip={wip}")

        # consistency: throughput but no cycle time (or vice versa) is suspicious->hard
        if isinstance(fl1.get("tp"), int) and fl1.get("tp") > 0 and fl1.get("ct") is None:
            errs.append(f"{tk}.fl1 has throughput={fl1['tp']} but ct is None")
        if isinstance(fl2.get("del"), int) and fl2.get("del") > 0 and fl2.get("ct") is None:
            errs.append(f"{tk}.fl2 has delivered={fl2['del']} but ct is None")
    return errs

# ── SOFT anomaly detection (month-over-month) ────────────────────────────────
# (pct_threshold, abs_threshold): flag when abs move >= abs_threshold AND
# (previous == 0 OR relative move >= pct_threshold). tech uses pct=0 so any
# absolute swing >= its abs_threshold (in percentage points) is flagged.
_THRESH = {
    "fl1": {"ct": (0.6, 25), "tp": (0.5, 25), "tech": (0.0, 25), "bC": (0.6, 15), "bR": (0.6, 15)},
    "fl2": {"ct": (0.6, 40), "del": (0.6, 3), "wip": (0.6, 5), "tech": (0.0, 25)},
}
_WIP_THRESH = (0.6, 5)  # FL1 total WIP (wR+wY+wG)

def _flag(prev, cur, pctthr, absthr):
    if prev is None or cur is None:
        return prev != cur  # appearing/disappearing data is worth a look
    delta = abs(cur - prev)
    if delta < absthr:
        return False
    if prev == 0:
        return True
    return (delta / abs(prev)) >= pctthr

def anomalies(prev, new):
    """prev/new are {team: {"fl1":{...}, "fl2":{...}}}. Returns list of human-readable
    anomaly strings. prev may be None/empty (first month) -> returns []."""
    if not prev:
        return []
    out = []
    for tk, tv in new.items():
        p = prev.get(tk)
        if not p:
            out.append(f"{tk}: no previous-month data to compare (new team?)")
            continue
        for fl in ("fl1", "fl2"):
            for k, (pctthr, absthr) in _THRESH[fl].items():
                pv = p.get(fl, {}).get(k); cv = tv.get(fl, {}).get(k)
                if _flag(pv, cv, pctthr, absthr):
                    out.append(f"{tk}.{fl}.{k}: {pv} -> {cv} (large change)")
            if fl == "fl1":
                pw = sum(p.get("fl1", {}).get(x) or 0 for x in ("wR", "wY", "wG"))
                cw = sum(tv.get("fl1", {}).get(x) or 0 for x in ("wR", "wY", "wG"))
                if _flag(pw, cw, *_WIP_THRESH):
                    out.append(f"{tk}.fl1.WIP(total): {pw} -> {cw} (large change)")
    return out
