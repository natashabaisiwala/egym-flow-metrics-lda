# -*- coding: utf-8 -*-
"""
Machine cadence "is a report due today?" detector.  [reusable]
================================================================================
The Machine cadence day is the 30th, clamped to month-end and rolled forward to
the next business day. When the 30th lands on a weekend at/near month-end it can
roll into the 1st/2nd of the FOLLOWING month (e.g. Jan-2027 cadence -> Mon 1 Feb;
Feb-2027 cadence -> Mon 1 Mar). A naive "is today == report_anchor(this month)?"
check misses those, and labelling by the anchor's calendar month causes collisions
(two cadences sharing e.g. "Mar 27").

This detector fixes both:
  * it checks the PREVIOUS month's cadence as well as the current month's, so a
    cadence that rolled into this month is still caught on its real business day;
  * it labels the report by its CADENCE month (decision: Alexa 2026-07-30), so
    every cadence month yields exactly one distinct label and there are no
    collisions and no missed months.

`report_date` (the data-through date used in the Slack footer) stays the true
rolled anchor date, while `label` / `month_full` name the report by its cadence
month.

CLI:  uv run --with numpy,tzdata python machine_cadence.py [YYYY-MM-DD]
  Prints a JSON object when a report is due today, else prints "NONE".
  JSON keys: anchor (rolled anchor date, ISO), cadence (YYYY-MM), label ("Mon YY"),
             month_full ("Month YYYY"), report_date ("D Mon YYYY").
Omit the date to use today (Europe/Madrid).
"""
import sys, json
from datetime import date, datetime
try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("Europe/Madrid")
except Exception:
    _TZ = None

import compute_jira as cj

REALM = "machine"


def _prev_month(cy, cm):
    return (cy - 1, 12) if cm == 1 else (cy, cm - 1)


def due(today):
    """Return report descriptor dict if `today` is a Machine cadence anchor, else None.
    Checks the previous month's cadence (which may roll into this month) and the
    current month's cadence. Labels by cadence month, not anchor month."""
    for (cy, cm) in (_prev_month(today.year, today.month), (today.year, today.month)):
        a = cj.report_anchor(cy, cm, REALM)
        if a == today:
            return {
                "anchor": a.isoformat(),
                "cadence": f"{cy:04d}-{cm:02d}",
                "label": f"{cj.MONTHS_ABBR[cm - 1]} {cy % 100:02d}",
                "month_full": date(cy, cm, 1).strftime("%B %Y"),
                "report_date": a.strftime("%-d %b %Y"),
            }
    return None


def main():
    argv = sys.argv[1:]
    if argv and not argv[0].startswith("--"):
        y, m, d = map(int, argv[0].split("-"))
        today = date(y, m, d)
    else:
        today = (datetime.now(_TZ).date() if _TZ else datetime.utcnow().date())
    r = due(today)
    print(json.dumps(r) if r else "NONE")


if __name__ == "__main__":
    main()
