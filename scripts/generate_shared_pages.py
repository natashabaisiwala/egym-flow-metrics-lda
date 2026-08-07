"""
EGYM Flow Metrics — Space Agent: Shared Pages Generator (v1)
Owns ONLY index.html, global-dashboard.html, and upload.html.
Merges every data-<realm>.json file at repo root and re-renders the 3 shared
pages from the combined result. Never writes into /{realm}/ folders or any
data-*.json file — those are owned exclusively by each realm agent.
Rendering engine (charts, HTML builders) is shared 1:1 with generate_dashboards_live.py
so shared pages stay visually/structurally consistent with realm pages.
"""
import json, base64, re
from agent_tools import call_tool

OWNER   = 'oleksandrabobina'
REPO    = 'egym-flow-metrics-lda'
GH_CONN = None

# ─── GitHub helpers ────────────────────────────────────────────────────────────
def load_data():
    r = call_tool('github_get_file_contents', {
        'connectionId': GH_CONN, 'owner': OWNER, 'repo': REPO, 'path': 'data-machine.json'})
    return json.loads(base64.b64decode(r['content'].replace('\n','')).decode()), r['sha']

def load_shas():
    """Get SHAs for all files via directory listing (fast, no content download)."""
    shas = {}
    def scan(path):
        r = call_tool('github_get_file_contents', {
            'connectionId': GH_CONN, 'owner': OWNER, 'repo': REPO, 'path': path})
        for e in (r if isinstance(r, list) else []):
            if e.get('type') == 'file':
                shas[e['path']] = e['sha']
            elif e.get('type') == 'dir':
                scan(e['path'])
    scan('/')
    return shas

def push(path, content, msg, sha=None):
    a = {'connectionId': GH_CONN, 'owner': OWNER, 'repo': REPO,
         'path': path, 'message': msg, 'content': content}
    if sha: a['sha'] = sha
    return call_tool('github_create_or_update_file', a)

def slugify(name):
    s = name.lower().strip()
    s = re.sub(r'[&/]+', '-', s)
    s = re.sub(r'[^a-z0-9-]+', '-', s)
    s = re.sub(r'-+', '-', s).strip('-')
    return s

# Display window: render only the last DISPLAY_MONTHS months. data.json keeps the
# full history; this trims the in-memory copy used for rendering only.
DISPLAY_MONTHS = 12
def _trim_realm(realm, n=DISPLAY_MONTHS):
    months = realm.get('months') or []
    if len(months) <= n:
        return
    k = len(months) - n
    realm['months'] = months[k:]
    def _trim_container(cont):
        for fl in ('fl1', 'fl2'):
            if fl not in cont:
                continue
            for key in cont[fl]:
                arr = cont[fl][key]
                if isinstance(arr, list) and len(arr) >= k:
                    cont[fl][key] = arr[k:]
    for t in realm['teams'].values():
        _trim_container(t)
    for cd in (realm.get('epic_cards') or {}).values():
        _trim_container(cd)

# ─── Trend engine ──────────────────────────────────────────────────────────────
def trend(vals, lower_is_better=True):
    v = [x for x in vals if x is not None]
    if len(v) < 6: return 'neutral'
    last3 = sum(v[-3:]) / 3
    prev3 = sum(v[-6:-3]) / 3
    if prev3 == 0: return 'neutral'
    change = (last3 - prev3) / abs(prev3)
    if lower_is_better:
        if change < -0.05: return 'good'
        if change >  0.05: return 'bad'
    else:
        if change >  0.05: return 'good'
        if change < -0.05: return 'bad'
    return 'neutral'

def trend_wip(rV, yV, gV):
    triples = [(r,y,g) for r,y,g in zip(rV,yV,gV) if None not in (r,y,g)]
    if not triples: return 'neutral'
    tots = [r+y+g for r,y,g in triples]
    return trend([r/max(t,1) for (r,y,g),t in zip(triples,tots)], lower_is_better=True)

def trend_bugs(bC, bR):
    pairs = [(c,r) for c,r in zip(bC,bR) if None not in (c,r)]
    if not pairs: return 'neutral'
    return trend([c/max(r,1) for c,r in pairs], lower_is_better=False)

def _filter_none(months, d):
    """Return months and data dict with None-valued months removed."""
    keys = list(d.keys())
    valid = [i for i,v in enumerate(d[keys[0]]) if v is not None]
    fm = [months[i] for i in valid]
    fd = {k: [d[k][i] for i in valid] for k in keys}
    return fm, fd

STATUS = {
    'good':    {'border':'#22c55e','text':'#22c55e','bg':'#22c55e18','label':'↑ Good'},
    'bad':     {'border':'#ef4444','text':'#ef4444','bg':'#ef444418','label':'↓ Watch'},
    'neutral': {'border':'#1e2540','text':'#7a87a0','bg':'#ffffff08','label':'→ Stable'},
}

# ─── SVG engine ────────────────────────────────────────────────────────────────
W,H    = 460,240
PL,PR  = 50,20
PT,PB  = 32,42
CW_    = W-PL-PR
CH_    = H-PT-PB
BG_    = '#141828'
GRID_  = '#1e2540'
TXT_   = '#e4eaf5'
MUT_   = '#7a87a0'
FONT_  = "font-family=\"'Segoe UI',system-ui,sans-serif\""

def xi(i,n): return PL + i*CW_/max(n-1,1)
def yi(f):   return PT + CH_*(1-f)

def edge_anchor(i,n):
    """Anchor text at start/end for edge points so labels don't spill past chart bounds."""
    if i==0: return 'start'
    if i==n-1: return 'end'
    return 'middle'

def scale(vals, mn=None, mx=None, pad=0.08):
    nv = [v for v in vals if v is not None]
    lo = min(nv) if mn is None else mn
    hi = max(nv) if mx is None else mx
    if lo==hi: lo,hi = lo*0.9, hi*1.1+1
    hi += (hi-lo)*pad
    return [(None if v is None else (v-lo)/max(hi-lo,1)) for v in vals], lo, hi

def gridlines(lo,hi,n=4):
    s=''
    for i in range(n+1):
        f=i/n; y=yi(f); v=lo+(hi-lo)*f
        s += f'<line x1="{PL}" y1="{y:.1f}" x2="{W-PR}" y2="{y:.1f}" stroke="{GRID_}" stroke-width="0.6"/>'
        s += f'<text x="{PL-4}" y="{y+3:.1f}" fill="{MUT_}" font-size="7" text-anchor="end" {FONT_}>{int(v)}</text>'
    return s

def xlabels(months):
    n=len(months); s=''
    for i,m in enumerate(months):
        s += f'<text x="{xi(i,n):.1f}" y="{H-5}" fill="{MUT_}" font-size="7" text-anchor="middle" {FONT_}>{m}</text>'
    return s

def xlabels_at(months, xs):
    """Month labels at custom x-positions (used by bar-type charts with inset positioning)."""
    n=len(months); s=''
    for i,m in enumerate(months):
        s += f'<text x="{xs[i]:.1f}" y="{H-5}" fill="{MUT_}" font-size="7" text-anchor="middle" {FONT_}>{m}</text>'
    return s

def bar_xpos(n, group_width):
    """X-centers for n bar-groups so the OUTERMOST group edges stay within [PL, W-PR]."""
    if n <= 1: return [W/2]
    span = max(CW_ - group_width, 0)
    return [PL + group_width/2 + i*span/(n-1) for i in range(n)]

def badge(st):
    p=STATUS[st]; bw,bh,rx_=62,18,9
    bx=W-PR-bw-2; by=3; tx=bx+bw/2; ty=by+11.5
    return (f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="{rx_}" '
            f'fill="{p["bg"]}" stroke="{p["border"]}" stroke-width="1"/>'
            f'<text x="{tx:.1f}" y="{ty:.1f}" fill="{p["text"]}" font-size="8.5" '
            f'font-weight="700" text-anchor="middle" {FONT_}>{p["label"]}</text>')

def tsub(title,sub,color):
    return (f'<text x="8" y="16" fill="{color}" font-size="9.5" font-weight="700" {FONT_}>{title}</text>'
            +(f'<text x="8" y="26" fill="{MUT_}" font-size="8" {FONT_}>{sub}</text>' if sub else ''))

def wrap(inner,title,sub,color,st='neutral'):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
            f'style="width:100%;background:{BG_};border-radius:8px;border:1.5px solid {STATUS[st]["border"]};">'
            + tsub(title,sub,color) + badge(st) + inner + '</svg>')

def line_chart(months,vals,color,title,sub='',st='neutral'):
    n=len(vals); sc,lo,hi=scale(vals)
    inner=gridlines(lo,hi)+xlabels(months)
    pts=[(xi(i,n),yi(sc[i])) for i in range(n) if sc[i] is not None]
    if pts:
        inner+=f'<polygon points="{xi(0,n):.1f},{yi(0)} '+' '.join(f'{x:.1f},{y:.1f}' for x,y in pts)+f' {pts[-1][0]:.1f},{yi(0)}" fill="{color}" opacity="0.12"/>'
        inner+=f'<polyline points="'+' '.join(f'{x:.1f},{y:.1f}' for x,y in pts)+f'" fill="none" stroke="{color}" stroke-width="2"/>'
    for i,(v,s) in enumerate(zip(vals,sc)):
        if s is None: continue
        x,y=xi(i,n),yi(s)
        inner+=f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{color}"/>'
        inner+=f'<text x="{x:.1f}" y="{y-7:.1f}" fill="{TXT_}" font-size="7.5" text-anchor="{edge_anchor(i,n)}" {FONT_}>{v}</text>'
    return wrap(inner,title,sub,color,st)

def smooth_chart(months,vals,color,title,sub='',st='neutral'):
    n=len(vals)
    nv=[v for v in vals if v is not None]
    if not nv: return wrap('',title,sub,color,st)
    sm=[vals[0] if vals[0] is not None else nv[0]]
    for i in range(1,n-1):
        trio=[v for v in [vals[i-1],vals[i],vals[i+1]] if v is not None]
        sm.append(sum(trio)/len(trio) if trio else None)
    sm.append(vals[-1] if vals[-1] is not None else nv[-1])
    sc_all,lo,hi=scale(nv); lo=min(nv); hi=max(nv)+(max(nv)-min(nv))*0.08 if max(nv)!=min(nv) else max(nv)*1.1+1
    def sca(v): return None if v is None else (v-min(nv))/max(hi-min(nv),1)
    sc_v=[sca(v) for v in vals]; sc_s=[sca(v) for v in sm]
    inner=gridlines(lo,hi)+xlabels(months)
    raw_pts=[(xi(i,n),yi(sc_v[i])) for i in range(n) if sc_v[i] is not None]
    sm_pts =[(xi(i,n),yi(sc_s[i])) for i in range(n) if sc_s[i] is not None]
    if raw_pts:
        inner+=f'<polyline points="'+' '.join(f'{x:.1f},{y:.1f}' for x,y in raw_pts)+f'" fill="none" stroke="{color}" stroke-width="1.2" stroke-dasharray="4,3" opacity="0.35"/>'
    if sm_pts:
        inner+=f'<polyline points="'+' '.join(f'{x:.1f},{y:.1f}' for x,y in sm_pts)+f'" fill="none" stroke="{color}" stroke-width="2.5"/>'
    for x,y in sm_pts:
        inner+=f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5" fill="{color}"/>'
    lx=W-250
    inner+=(f'<line x1="{lx}" y1="13" x2="{lx+16}" y2="13" stroke="{color}" stroke-width="1.2" stroke-dasharray="4,3" opacity="0.35"/>'
            f'<text x="{lx+19}" y="17" fill="{MUT_}" font-size="7.5" {FONT_}>Raw</text>'
            f'<line x1="{lx+45}" y1="13" x2="{lx+61}" y2="13" stroke="{color}" stroke-width="2.5"/>'
            f'<text x="{lx+64}" y="17" fill="{MUT_}" font-size="7.5" {FONT_}>3-mo avg</text>')
    return wrap(inner,title,sub,color,st)

def bar_chart(months,vals,color,title,sub='',st='neutral'):
    n=len(vals); sc,lo,hi=scale(vals,0); bw=max(CW_/n*0.55,4)
    xs=bar_xpos(n,bw)
    inner=gridlines(0,hi)+xlabels_at(months,xs)
    for i,(v,s) in enumerate(zip(vals,sc)):
        if s is None: continue
        x=xs[i]; bh=max(s*CH_,2)
        inner+=f'<rect x="{x-bw/2:.1f}" y="{yi(s):.1f}" width="{bw:.1f}" height="{bh:.1f}" fill="{color}" opacity="0.82" rx="2"/>'
        inner+=f'<text x="{x:.1f}" y="{yi(s)-4:.1f}" fill="{TXT_}" font-size="7" text-anchor="{edge_anchor(i,n)}" {FONT_}>{v}</text>'
    return wrap(inner,title,sub,color,st)

def wip_stacked(months,rV,yV,gV,title,sub='',st='neutral'):
    n=len(rV); tots=[(r+y+g) if None not in (r,y,g) else None for r,y,g in zip(rV,yV,gV)]
    real_tots=[t for t in tots if t is not None]
    hi=(max(real_tots) or 1)*1.18 if real_tots else 1  # extra headroom so tallest bar's label clears the legend row
    bw=max(CW_/n*0.55,4); xs=bar_xpos(n,bw)
    inner=gridlines(0,hi)+xlabels_at(months,xs)
    for i in range(n):
        x=xs[i]; bot=0
        for v,c in [(gV[i],'#22c55e'),(yV[i],'#f59e0b'),(rV[i],'#ef4444')]:
            if v:
                ft=(bot+v)/hi; y_=yi(ft); hh=max((ft-bot/hi)*CH_,1)
                inner+=f'<rect x="{x-bw/2:.1f}" y="{y_:.1f}" width="{bw:.1f}" height="{hh:.1f}" fill="{c}" opacity="0.85" rx="1"/>'
                bot+=v
        t=tots[i]
        if t: inner+=f'<text x="{x:.1f}" y="{yi(t/hi)-4:.1f}" fill="{TXT_}" font-size="7" text-anchor="{edge_anchor(i,n)}" {FONT_}>{t}</text>'
    for k,(lbl,c) in enumerate([('Green','#22c55e'),('Yellow','#f59e0b'),('Red','#ef4444')]):
        lx=PL+k*82
        inner+=f'<rect x="{lx}" y="20" width="8" height="8" fill="{c}" rx="1"/><text x="{lx+11}" y="28" fill="{MUT_}" font-size="7.5" {FONT_}>{lbl}</text>'
    return wrap(inner,title,sub,'#60a5fa',st)

def grouped_bar(months,vA,vB,lA,lB,cA,cB,title,sub='',st='neutral'):
    n=len(vA)
    nall=[v for v in list(vA)+list(vB) if v is not None]
    hi=max(nall) if nall else 1
    bw=max(CW_/n*0.27,3); gap=bw*0.25
    group_w=2*bw+gap; xs=bar_xpos(n,group_w)
    inner=gridlines(0,hi)+xlabels_at(months,xs)
    for i,(a,b) in enumerate(zip(vA,vB)):
        cx=xs[i]
        for v,c,dx in [(a,cA,-(bw+gap)/2),(b,cB,gap/2)]:
            if v is None: continue
            f=v/max(hi,1); y_=yi(f); hh=max(f*CH_,1)
            inner+=f'<rect x="{cx+dx:.1f}" y="{y_:.1f}" width="{bw:.1f}" height="{hh:.1f}" fill="{c}" opacity="0.85" rx="1"/>'
    for k,(lbl,c) in enumerate([(lA,cA),(lB,cB)]):
        lx=PL+k*100
        inner+=f'<rect x="{lx}" y="20" width="8" height="8" fill="{c}" rx="1"/><text x="{lx+11}" y="28" fill="{MUT_}" font-size="7.5" {FONT_}>{lbl}</text>'
    return wrap(inner,title,sub,cA,st)

def area_chart(months,vals,color,title,sub='',st='neutral'):
    n=len(vals); sc,lo,hi=scale(vals,0)
    inner=gridlines(0,hi)+xlabels(months)
    pts=[(xi(i,n),yi(sc[i])) for i in range(n) if sc[i] is not None]
    if pts:
        inner+=f'<polygon points="{xi(0,n):.1f},{yi(0)} '+' '.join(f'{x:.1f},{y:.1f}' for x,y in pts)+f' {pts[-1][0]:.1f},{yi(0)}" fill="{color}" opacity="0.2"/>'
        inner+=f'<polyline points="'+' '.join(f'{x:.1f},{y:.1f}' for x,y in pts)+f'" fill="none" stroke="{color}" stroke-width="2.5"/>'
    for i,s in enumerate(sc):
        if s is None: continue
        inner+=f'<circle cx="{xi(i,n):.1f}" cy="{yi(s):.1f}" r="3" fill="{color}"/>'
    return wrap(inner,title,sub,color,st)

# ─── Chart descriptions ────────────────────────────────────────────────────────
DESC_FL1=[
    ("✅ Lower = better","How long a task takes start-to-done (85th pct). Falling trend = process getting faster."),
    ("✅ Higher = better","Tasks completed per month. Look for stability or gradual growth."),
    ("✅ More green = better","Health of current tasks. Growing red = systemic blockers to fix."),
    ("⚖️ Closed ≥ Reported = healthy","If reported consistently exceeds closed, quality debt accumulates."),
    ("✅ Higher = more tech investment","Share of throughput going to tech improvements. Growing = healthy long-term investment."),
    ("✅ Lower and stable = better","Total tasks in progress. High WIP slows everything — reducing it improves cycle time."),
]
DESC_FL2=[
    ("✅ Lower = better","How long epics take end-to-end (85th pct). Spikes often mean outlier epics in backlogs."),
    ("✅ Higher = better","Epics completed per month. Shows ability to close large initiatives."),
    ("✅ More green = better","Health of in-progress epics. Red epics = strategic blockers."),
    ("✅ Lower and stable = better","Total epics in flight. Too many parallel epics reduce focus."),
    ("✅ Higher = more strategic tech investment","Share of delivered epics that are tech/platform-focused."),
    ("✅ Downward trend = the goal","Solid = 3-mo moving avg; dashed = raw. Clear downward slope = genuine improvement."),
]

def desc_card(good,text,st):
    c=STATUS[st]['border']
    return (f'<div style="background:#0a0e1a;border-left:3px solid {c};border-radius:0 6px 6px 0;padding:8px 12px;margin-top:6px">'
            f'<span style="font-size:.7rem;font-weight:700;color:#60a5fa">{good}</span>'
            f'<p style="font-size:.72rem;color:#7a87a0;line-height:1.55;margin-top:3px">{text}</p></div>')

METHODOLOGY=(
    '<p style="font-size:.7rem;color:#4a5568;margin-bottom:14px">'
    '🔍 <strong style="color:#7a87a0">Status badges</strong> compare the '
    '<strong style="color:#7a87a0">3-month average</strong> vs. the previous 3 months (threshold: 5%). '
    '<span style="color:#22c55e;font-weight:700">↑ Good</span> = improving &nbsp;·&nbsp; '
    '<span style="color:#ef4444;font-weight:700">↓ Watch</span> = declining &nbsp;·&nbsp; '
    '<span style="color:#7a87a0;font-weight:700">→ Stable</span> = no significant change</p>'
)

ABOUT_BLOCK=(
    '<div style="margin-bottom:24px;padding:18px 20px;background:#0c1628;border:1px solid #1e2540;border-radius:10px">'
    '<h2 style="font-size:.85rem;font-weight:700;padding-left:10px;border-left:3px solid #60a5fa;margin:0 0 12px">About Flow Metrics</h2>'
    '<p style="font-size:.72rem;color:#7a87a0;line-height:1.6;margin-bottom:12px">'
    '<strong style="color:#e4eaf5">Disclaimer:</strong> All metrics besides WIP and WIP risks are lagging indicators. '
    'WIP and WIP Risk are leading indicators that we can actively manage right now. '
    'Doing so can bring positive trends across all metrics in the future.</p>'
    '<p style="font-size:.72rem;color:#7a87a0;line-height:1.6;margin-bottom:16px">'
    '<strong style="color:#e4eaf5">📊 Rolling 120-day window:</strong> Each report covers the last 4 months, not a single calendar month, '
    'and consecutive reports overlap by ~85 days. This means month-to-month figures are smoothed — a single anomaly can influence '
    '2–3 consecutive data points rather than just one, and real week-to-week swings appear more gradual than they actually are.</p>'
    '<div style="font-size:.72rem;font-weight:700;color:#e4eaf5;margin-bottom:10px">Flight Levels</div>'
    '<div style="display:flex;flex-wrap:wrap;gap:14px">'
      '<div style="flex:1 1 28%;min-width:220px">'
        '<div style="font-size:.71rem;font-weight:700;color:#a78bfa;margin-bottom:4px">FL1 — Operation</div>'
        '<div style="font-size:.7rem;color:#7a87a0;line-height:1.55">Represented by daily-basis team\'s work items where the focus is on delivery, the work is connected with the second level, the Epics.</div>'
      '</div>'
      '<div style="flex:1 1 28%;min-width:220px">'
        '<div style="font-size:.71rem;font-weight:700;color:#60a5fa;margin-bottom:4px">FL2 — Coordination</div>'
        '<div style="font-size:.7rem;color:#7a87a0;line-height:1.55">Where the focus is on coordinate roadmap and tech initiatives, Epics management (Jira FL2 board) and cross-team alignment.</div>'
      '</div>'
      '<div style="flex:1 1 28%;min-width:220px">'
        '<div style="font-size:.71rem;font-weight:700;color:#22c55e;margin-bottom:4px">FL3 — Strategy</div>'
        '<div style="font-size:.7rem;color:#7a87a0;line-height:1.55">At the top EGYM\'s strategy, where the focus is on the goals, direction and priorities of the company.</div>'
      '</div>'
    '</div></div>'
)

# ─── Per-team insights (optional — only for teams with known context) ──────────
INSIGHTS = {
    'core': {
        'cw':[("📉 Cycle Time","Dropped from 40d (Jun'25) to ~11d — strong sustained improvement."),
              ("⚠️ Dec'25 Throughput spike (272)","Nave data sync anomaly — not real delivery."),
              ("🔵 Aug–Sep'25 Epic CT spikes (435d)","Outlier epics; resolved by Q4'25.")],
        'mm':[("📉 Cycle Time","Improved 36d → 16–18d and holding steady."),
              ("⚠️ Feb'26 Epic CT spike (699d)","Batch closure of long-running outlier epics."),
              ("🟢 Nov'25 Epic CT drop (67d)","Strongest epic delivery month in the period.")],
        'ox':[("📉 Cycle Time","52d → 28–29d and stable."),
              ("🔴 Nov'25 WIP spike (3 Red)","Cleared by December."),
              ("🟢 Epic CT improving","324d (Jun'25) → 65d (May'26).")],
        'ul':[("📉 Cycle Time","18d → 10d by May'26."),
              ("⚠️ Dec'25–Mar'26 Epic CT (305d)","Single outlier epic GXY-4979 (1300+ days)."),
              ("📈 Tech % growth","16% (Jun'25) → 70% (May'26).")],
    }
}

# ─── Wellpass-specific schema (different report structure — no clean CT/tech%/
#     red-yellow-green WIP risk numbers exist in the source PDF; only WIP, WIP
#     Age, cumulative-YTD throughput, and cumulative 180-day bugs are reliably
#     extractable) ───────────────────────────────────────────────────────────
WELLPASS_REALMS = set()  # Wellpass switched to the standard schema/template from Aug 25 onward;
                          # reduced-schema code paths kept below (unused, harmless) for reference.

WELLPASS_ABOUT_BLOCK=(
    '<div style="margin-bottom:24px;padding:18px 20px;background:#0c1628;border:1px solid #1e2540;border-radius:10px">'
    '<h2 style="font-size:.85rem;font-weight:700;padding-left:10px;border-left:3px solid #60a5fa;margin:0 0 12px">About Flow Metrics</h2>'
    '<p style="font-size:.72rem;color:#7a87a0;line-height:1.6;margin-bottom:12px">'
    '<strong style="color:#e4eaf5">Disclaimer:</strong> All metrics besides WIP and WIP Age are lagging indicators. '
    'WIP and WIP Age are leading indicators that we can actively manage right now. '
    'Doing so can bring positive trends across all metrics in the future.</p>'
    '<p style="font-size:.72rem;color:#7a87a0;line-height:1.6;margin-bottom:16px">'
    '<strong style="color:#e4eaf5">📊 Cumulative year-to-date tracking:</strong> Wellpass throughput and bug figures are reported '
    'as running totals since the start of the calendar year (not single-month counts), so they only ever grow within a year and '
    'reset each January. WIP and WIP Age are current snapshots at report time. Cycle time percentiles are not consistently '
    'available in the source report for every team, so they are omitted here rather than estimated.</p>'
    '<div style="font-size:.72rem;font-weight:700;color:#e4eaf5;margin-bottom:10px">Flight Levels</div>'
    '<div style="display:flex;flex-wrap:wrap;gap:14px">'
      '<div style="flex:1 1 28%;min-width:220px">'
        '<div style="font-size:.71rem;font-weight:700;color:#a78bfa;margin-bottom:4px">FL1 — Operation</div>'
        '<div style="font-size:.7rem;color:#7a87a0;line-height:1.55">Represented by daily-basis team\'s work items where the focus is on delivery, the work is connected with the second level, the Epics.</div>'
      '</div>'
      '<div style="flex:1 1 28%;min-width:220px">'
        '<div style="font-size:.71rem;font-weight:700;color:#60a5fa;margin-bottom:4px">FL2 — Coordination</div>'
        '<div style="font-size:.7rem;color:#7a87a0;line-height:1.55">Where the focus is on coordinate roadmap and tech initiatives, Epics management (Jira FL2 board) and cross-team alignment.</div>'
      '</div>'
      '<div style="flex:1 1 28%;min-width:220px">'
        '<div style="font-size:.71rem;font-weight:700;color:#22c55e;margin-bottom:4px">FL3 — Strategy</div>'
        '<div style="font-size:.7rem;color:#7a87a0;line-height:1.55">At the top EGYM\'s strategy, where the focus is on the goals, direction and priorities of the company.</div>'
      '</div>'
    '</div></div>'
)

DESC_WELLPASS_FL1=[
    ("✅ Lower and stable = better","Total tasks in progress right now. High or rising WIP slows everything down."),
    ("✅ Lower = better","Average number of days work sits in progress before finishing. Rising = items are aging/stalling."),
    ("ℹ️ Cumulative since Jan","Running total of tasks delivered so far this year. Always rises within a year, resets in January."),
    ("⚖️ Resolved ≥ Created = healthy","Cumulative bugs (last 180 days). If created consistently outpaces resolved, quality debt is accumulating."),
]
DESC_WELLPASS_FL2=[
    ("✅ Lower and stable = better","Total epics in progress right now. Too many in parallel reduces focus."),
    ("✅ Lower = better","Average number of days epics sit in progress before finishing. Rising = epics are aging without closure."),
]

def wellpass_fl1_set(months, d, color):
    months, d = _filter_none(months, d)
    sts=[trend(d['wip'],True), trend(d['wipAge'],True), trend(d['tpYTD'],False), trend_bugs(d['bC'],d['bR'])]
    charts=[
        line_chart (months,d['wip'],   color, 'WIP (items)',      'work items in progress', sts[0]),
        line_chart (months,d['wipAge'],color, 'WIP Average Age',  'days',                    sts[1]),
        area_chart (months,d['tpYTD'], color, 'Throughput',       'cumulative items, YTD',   sts[2]),
        grouped_bar(months,d['bC'],d['bR'],'Resolved','Created','#22c55e','#ef4444','Bugs','cumulative, 180-day window',sts[3]),
    ]
    return list(zip(charts, DESC_WELLPASS_FL1, sts))

def wellpass_fl2_set(months, d, color):
    months, d = _filter_none(months, d)
    sts=[trend(d['wip'],True), trend(d['wipAge'],True)]
    charts=[
        line_chart(months,d['wip'],   '#60a5fa','Epic WIP (items)',     'epics in progress', sts[0]),
        line_chart(months,d['wipAge'],'#60a5fa','Epic WIP Average Age', 'days',               sts[1]),
    ]
    return list(zip(charts, DESC_WELLPASS_FL2, sts))

def wellpass_snapshot(f1, f2):
    def last(a):
        v = [x for x in a if x is not None]
        return v[-1] if v else None
    lwip=last(f1['wip']); lwipAge=last(f1['wipAge']); ltp=last(f1['tpYTD'])
    lbC=last(f1['bC']); lbR=last(f1['bR'])
    lwip2=last(f2['wip']); lwipAge2=last(f2['wipAge'])
    return {
        'wip':     lwip if lwip is not None else '—',
        'wipAge':  f"{lwipAge:g}d" if lwipAge is not None else '—',
        'tp':      ltp if ltp is not None else '—',
        'bugs':    f"{lbR} / {lbC}" if (lbR is not None and lbC is not None) else '—',
        'wip2':    lwip2 if lwip2 is not None else '—',
        'wipAge2': f"{lwipAge2:g}d" if lwipAge2 is not None else '—',
    }

# ─── Realm-level aggregation (for the realm dashboard) ─────────────────────────
def aggregate_realm_fl(realm, fl_key, wellpass=False):
    """Aggregate every team's fl1/fl2 arrays in a realm into one realm-level dict,
    for the realm dashboard. Rate-like fields (Cycle Time, Tech %, WIP Age) are
    averaged across teams that have a value that month. Volume-like fields
    (Throughput, WIP counts, Bugs, Epics Delivered) are summed across teams that
    have a value that month. A month's aggregate value is None only if NO team
    has data for that field that month — teams without data that month are
    excluded from the calculation rather than counted as zero, so a team
    launching or retiring mid-series doesn't skew the realm trend.
    """
    if fl_key == 'fl2' and realm.get('epic_cards'):
        # Machine: FL2 is tracked on epic cards, not on the FL1 task teams.
        teams = list(realm['epic_cards'].values())
    else:
        teams = list(realm['teams'].values())
    n = len(realm['months'])
    if wellpass:
        avg_keys = ['wipAge']
        sum_keys = ['wip', 'tpYTD', 'bC', 'bR'] if fl_key == 'fl1' else ['wip']
        weight_key = None
    else:
        avg_keys = ['ct']  # tech is handled separately below as a volume-weighted average
        sum_keys = (['tp', 'wR', 'wY', 'wG', 'bC', 'bR'] if fl_key == 'fl1'
                    else ['del', 'wip', 'wR', 'wY', 'wG'])
        weight_key = 'tp' if fl_key == 'fl1' else 'del'
    out = {}
    for k in avg_keys:
        col = []
        for i in range(n):
            vals = [t[fl_key][k][i] for t in teams
                    if t[fl_key].get(k) and i < len(t[fl_key][k]) and t[fl_key][k][i] is not None]
            col.append(round(sum(vals)/len(vals)) if vals else None)
        out[k] = col
    for k in sum_keys:
        col = []
        for i in range(n):
            vals = [t[fl_key][k][i] for t in teams
                    if t[fl_key].get(k) and i < len(t[fl_key][k]) and t[fl_key][k][i] is not None]
            col.append(sum(vals) if vals else None)
        out[k] = col
    if not wellpass:
        # Tech %: volume-weighted average (weighted by Throughput for FL1, Epics Delivered
        # for FL2) so a team that delivered more work influences the realm figure more than
        # a small team — this approximates "what share of all realm work was tech" rather
        # than treating every team's percentage as equally important regardless of volume.
        tech_col = []
        for i in range(n):
            pairs = [(t[fl_key]['tech'][i], t[fl_key][weight_key][i]) for t in teams
                     if t[fl_key].get('tech') and i < len(t[fl_key]['tech']) and t[fl_key]['tech'][i] is not None
                     and t[fl_key].get(weight_key) and i < len(t[fl_key][weight_key]) and t[fl_key][weight_key][i] is not None]
            if not pairs:
                tech_col.append(None)
            else:
                wsum = sum(w for _, w in pairs)
                tech_col.append(round(sum(v*w for v, w in pairs)/wsum) if wsum > 0
                                 else round(sum(v for v, _ in pairs)/len(pairs)))
        out['tech'] = tech_col
    return out

MACHINE_WIP_CAVEAT = (
    '<p style="font-size:.72rem;color:#7a87a0;line-height:1.6;margin-top:8px">'
    '<strong style="color:#f59e0b">⚠️ Machine WIP Red/Yellow/Green uses percentile-based aging.</strong> '
    'Each in-progress item is colored by how its current age compares to that team\'s recent '
    'completed-work cycle-time distribution (yellow at the ~70th percentile, red at the ~85th), '
    'not a single fixed week threshold. Summed status counts across teams are best read as '
    '"items flagged for attention" rather than one consistent realm-wide risk line.</p>'
)

# ─── Build FL1 / FL2 chart sets ────────────────────────────────────────────────
def fl1_set(months, d, color):
    months, d = _filter_none(months, d)
    wip=[(r+y+g) if None not in (r,y,g) else None for r,y,g in zip(d['wR'],d['wY'],d['wG'])]
    sts=[trend(d['ct'],True), trend(d['tp'],False), trend_wip(d['wR'],d['wY'],d['wG']),
         trend_bugs(d['bC'],d['bR']), trend(d['tech'],False), trend(wip,True)]
    charts=[
        line_chart (months,d['ct'],  color,   'Cycle Time 85th pct',      'days',          sts[0]),
        bar_chart  (months,d['tp'],  color,   'Throughput',               'tasks / month', sts[1]),
        wip_stacked(months,d['wR'],d['wY'],d['wG'],'WIP by Status',       '',              sts[2]),
        grouped_bar(months,d['bC'],d['bR'],'Closed','Reported','#22c55e','#ef4444','Bugs','',sts[3]),
        line_chart (months,d['tech'],'#a78bfa','Tech %',                  'of throughput', sts[4]),
        area_chart (months,wip,      color,   'WIP Snapshot (Report Date)', '',              sts[5]),
    ]
    return list(zip(charts, DESC_FL1, sts))

def fl2_set(months, d, color):
    months, d = _filter_none(months, d)
    sts=[trend(d['ct'],True), trend(d['del'],False), trend_wip(d['wR'],d['wY'],d['wG']),
         trend(d['wip'],True), trend(d['tech'],False), trend(d['ct'],True)]
    charts=[
        line_chart  (months,d['ct'],  color,   'Epic CT 85th pct',        'days',              sts[0]),
        bar_chart   (months,d['del'], color,   'Epics Delivered',          'per month',         sts[1]),
        wip_stacked (months,d['wR'],d['wY'],d['wG'],'Epic WIP by Status', '',                  sts[2]),
        area_chart  (months,d['wip'],'#60a5fa','Epic WIP Snapshot (Report Date)', '',       sts[3]),
        line_chart  (months,d['tech'],'#a78bfa','Tech %',                 'of delivered epics',sts[4]),
        smooth_chart(months,d['ct'],  color,   'Epic CT Trend',           '3-month moving avg',sts[5]),
    ]
    return list(zip(charts, DESC_FL2, sts))

# ─── Snapshot KPIs ─────────────────────────────────────────────────────────────
def snapshot(f1, f2, n):
    def d(c,p,lb=None):
        # Arrow reflects the literal numeric direction of change (↓ = decreased, ↑ = increased),
        # independent of whether that direction is "good" or "bad" for this metric — the lb
        # parameter is accepted for call-site compatibility but intentionally unused here.
        if p is None or c is None or c==p: return ''
        return f' ↓{abs(c-p)}' if c < p else f' ↑{abs(c-p)}'
    def last(a): return next((v for v in reversed(a) if v is not None), None)
    def prev(a):
        nn=[v for v in a if v is not None]
        return nn[-2] if len(nn)>=2 else None
    lct1=last(f1['ct']); ltp=last(f1['tp']); lwR=last(f1['wR']); lwY=last(f1['wY']); lwG=last(f1['wG'])
    lct2=last(f2['ct']); ldel=last(f2['del']); ltech=last(f1['tech']); lwip2=last(f2['wip'])
    return {
        'ct1':  f"{lct1}d{d(lct1,prev(f1['ct']),True)}" if lct1 is not None else '—',
        'tp':   f"{ltp}{d(ltp,prev(f1['tp']),False)}" if ltp is not None else '—',
        'wip1': (lwR or 0)+(lwY or 0)+(lwG or 0),
        'ct2':  f"{lct2}d{d(lct2,prev(f2['ct']),True)}" if lct2 is not None else '—',
        'del_': f"{ldel}{d(ldel,prev(f2['del']),False)}" if ldel is not None else '—',
        'tech': f"{ltech}%" if ltech is not None else '—',
        'wip2': lwip2 if lwip2 is not None else 0,
    }

# ─── HTML builders ─────────────────────────────────────────────────────────────
def chart_grid(triples):
    items=''.join(f'<div style="flex:1 1 44%;min-width:300px">{svg}{desc_card(g,t,st)}</div>'
                  for svg,(g,t),st in triples)
    return f'<div style="display:flex;flex-wrap:wrap;gap:16px">{items}</div>'

def insights_html(realm_id, team_id):
    ins = INSIGHTS.get(realm_id,{}).get(team_id,[])
    if not ins: return ''
    cards=''.join(
        f'<div style="background:#0c1628;border:1px solid #1e2540;border-radius:8px;padding:12px 14px;flex:1 1 28%;min-width:220px">'
        f'<div style="font-size:.78rem;font-weight:700;color:#e4eaf5;margin-bottom:4px">{lbl}</div>'
        f'<div style="font-size:.73rem;color:#7a87a0;line-height:1.5">{body}</div></div>'
        for lbl,body in ins)
    return f'<h2 style="font-size:.95rem;font-weight:700;padding-left:10px;border-left:3px solid {{c}};margin:24px 0 10px">Key Insights</h2><div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:28px">{cards}</div>'

def _banner(inner, color='#f59e0b', icon='⚠️'):
    return (f'<div style="background:{color}14;border:1px solid {color}55;border-left:4px solid {color};'
            f'border-radius:8px;padding:11px 14px;margin:0 0 18px;font-size:.76rem;line-height:1.55;color:#d9e0ee">'
            f'{icon}&nbsp; {inner}</div>')

def _new_badge(team):
    if not team.get('new'):
        return ''
    return ('<span style="background:#16a34a;color:#ffffff;border:1px solid #0f7a37;border-radius:5px;'
            'padding:2px 8px;font-size:.64rem;font-weight:800;margin-left:8px;vertical-align:middle;'
            'letter-spacing:.03em">🆕 NEW TEAM</span>')

def team_notes_html(team):
    if team.get('new'):
        return ('<div style="background:#16a34a;border:1px solid #0f7a37;border-radius:9px;padding:13px 16px;'
                'margin:0 0 18px;font-size:.82rem;line-height:1.55;color:#ffffff">'
                '🆕 <strong>NEW TEAM.</strong> Formed in the 20 Jul 2026 reorg — earlier points reflect '
                'tickets carried over from existing teams (not net-new work), so pre-Jul 2026 history is '
                'partial. At least 3 months of data are needed before trends are reliable.</div>')
    if team.get('note'):
        return _banner(team['note'], '#f59e0b', '📌')
    return ''

def realm_note_html(realm):
    return _banner(realm['note'], '#f59e0b', '⚠️') if realm.get('note') else ''

def realm_agg_composition_note(realm):
    """Aggregate-only caveat: when a realm has new teams, realm totals step up in the
    month the new teams first appear (composition change, not organic growth)."""
    teams = realm['teams']; months = realm.get('months') or []
    new = [t['name'] for t in teams.values() if t.get('new')]
    est = [t['name'] for t in teams.values() if not t.get('new')]
    if not new:
        return ''
    join = months[-1] if months else 'the latest month'
    for i, m in enumerate(months):
        if any(t['fl1'].get('ct') and i < len(t['fl1']['ct']) and t['fl1']['ct'][i] is not None
               for t in teams.values() if t.get('new')):
            join = m; break
    est_s = ", ".join(est) if est else "the established teams"
    new_s = ", ".join(new)
    return _banner(f'<strong>Composition note.</strong> Realm totals before {join} reflect only the teams with '
                   f'history in each month ({est_s}). The new team(s) — {new_s} — join the totals from '
                   f'<strong>{join}</strong>, which lifts the summed metrics (Throughput, WIP, Delivered, Bugs). '
                   f'This is a change in team composition, not organic growth.', '#f59e0b', '⚠️')

def _team_fl2(realm, team):
    """Resolve a team's FL2 data dict. For split realms (Machine) FL2 lives on
    epic_cards and is referenced from the team via 'fl2_card' (MI OS and MI
    Back-End both point to the shared 'minfra' epic series)."""
    cards = realm.get('epic_cards')
    if cards:
        ck = team.get('fl2_card')
        if ck and ck in cards:
            return cards[ck].get('fl2')
        return None
    return team.get('fl2')

def team_html(realm_id, realm_name, team_id, team, months, fl2_data=None):
    c = team['color']
    wellpass = realm_id in WELLPASS_REALMS

    if wellpass:
        s = wellpass_snapshot(team['fl1'], team['fl2'])
        fl1 = wellpass_fl1_set(months, team['fl1'], c)
        fl2 = wellpass_fl2_set(months, team['fl2'], c)
        about = WELLPASS_ABOUT_BLOCK
        kpi_cols = 6
        kpi_row = f"""
  <div class="kpi"><div class="lbl">WIP</div><div class="val">{s['wip']}</div></div>
  <div class="kpi"><div class="lbl">WIP Avg Age</div><div class="val">{s['wipAge']}</div></div>
  <div class="kpi"><div class="lbl">Throughput (YTD)</div><div class="val">{s['tp']}</div></div>
  <div class="kpi"><div class="lbl">Bugs Created/Resolved</div><div class="val">{s['bugs']}</div></div>
  <div class="kpi"><div class="lbl">Epic WIP</div><div class="val">{s['wip2']}</div></div>
  <div class="kpi"><div class="lbl">Epic WIP Avg Age</div><div class="val">{s['wipAge2']}</div></div>"""
    else:
        _fl2 = fl2_data if fl2_data is not None else (team.get('fl2') or {})
        s = snapshot(team['fl1'], _fl2, len(months))
        fl1 = fl1_set(months, team['fl1'], c)
        fl2 = fl2_set(months, _fl2, c)
        about = ABOUT_BLOCK
        kpi_cols = 7
        kpi_row = f"""
  <div class="kpi"><div class="lbl">FL1 Cycle Time</div><div class="val">{s['ct1']}</div></div>
  <div class="kpi"><div class="lbl">FL1 Throughput</div><div class="val">{s['tp']}</div></div>
  <div class="kpi"><div class="lbl">FL1 WIP</div><div class="val">{s['wip1']}</div></div>
  <div class="kpi"><div class="lbl">FL2 Cycle Time</div><div class="val">{s['ct2']}</div></div>
  <div class="kpi"><div class="lbl">FL2 Delivered</div><div class="val">{s['del_']}</div></div>
  <div class="kpi"><div class="lbl">FL2 WIP</div><div class="val">{s['wip2']}</div></div>
  <div class="kpi"><div class="lbl">Tech %</div><div class="val">{s['tech']}</div></div>"""

    fl2_section = ('<div style="margin-top:32px"><h2>FL2 — Epics</h2>'
                   + METHODOLOGY + chart_grid(fl2) + '</div>')
    ins = insights_html(realm_id, team_id).replace('{c}', c)
    start = months[0] if months else '—'
    end   = months[-1] if months else '—'
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{team['name']} — Flow Metrics</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0c0f1a;color:#e4eaf5;font-family:'Segoe UI',system-ui,sans-serif;padding:24px 20px;max-width:1100px;margin:0 auto}}
h1{{font-size:1.45rem;font-weight:800;letter-spacing:-.03em}}
.sub{{color:#7a87a0;font-size:.8rem;margin-top:3px;margin-bottom:20px}}
.badge{{background:{c}22;color:{c};border:1px solid {c}44;border-radius:5px;padding:2px 8px;font-size:.7rem;font-weight:600;margin-left:8px}}
.kpi-row{{display:grid;grid-template-columns:repeat({kpi_cols},1fr);gap:10px;margin-bottom:24px}}
.kpi{{background:#141828;border:1px solid #252c45;border-top:3px solid {c};border-radius:10px;padding:12px 14px}}
.kpi .lbl{{font-size:.63rem;color:#7a87a0;text-transform:uppercase;letter-spacing:.07em;margin-bottom:5px}}
.kpi .val{{font-size:1.1rem;font-weight:700}}
h2{{font-size:.95rem;font-weight:700;padding-left:10px;border-left:3px solid {c};margin:24px 0 10px}}
footer{{margin-top:24px;padding-top:14px;border-top:1px solid #1e2540;font-size:.7rem;color:#4a5568;text-align:center}}
a{{color:{c};text-decoration:none}}
</style>
</head>
<body>
<h1>{team['name']} <span class="badge">{realm_name}</span></h1>
<div class="sub">Flow Metrics · {start} → {end} · {len(months)} months of data</div>
{team_notes_html(team)}
{about}
<div class="kpi-row">{kpi_row}
</div>
{ins}
<div><h2>FL1 — Tasks</h2>{METHODOLOGY}{chart_grid(fl1)}</div>
{fl2_section}
<p style="margin-top:20px;font-size:.8rem"><a href="index.html">← {realm_name}</a> &nbsp;·&nbsp; <a href="../index.html">All realms</a></p>
<footer>Auto-generated · Nave + Jira via Notion · {end}</footer>
</body></html>"""

def card_html(realm_id, realm_name, card_id, card, months):
    """Epic-card dashboard page (FL2 only) for split realms such as Machine."""
    c = card['color']
    def _lastv(a): return next((v for v in reversed(a) if v is not None), None)
    f2 = card['fl2']
    _ct=_lastv(f2['ct']); _del=_lastv(f2['del']); _wip=_lastv(f2['wip']); _tech=_lastv(f2['tech'])
    fl2 = fl2_set(months, card['fl2'], c)
    start = months[0] if months else '—'
    end   = months[-1] if months else '—'
    kpi_row = f"""
  <div class="kpi"><div class="lbl">Epic Cycle Time</div><div class="val">{f'{_ct}d' if _ct is not None else '—'}</div></div>
  <div class="kpi"><div class="lbl">Epics Delivered</div><div class="val">{_del if _del is not None else '—'}</div></div>
  <div class="kpi"><div class="lbl">Epic WIP</div><div class="val">{_wip if _wip is not None else 0}</div></div>
  <div class="kpi"><div class="lbl">Tech %</div><div class="val">{f'{_tech}%' if _tech is not None else '—'}</div></div>"""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{card['name']} — Epic Flow Metrics</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0c0f1a;color:#e4eaf5;font-family:'Segoe UI',system-ui,sans-serif;padding:24px 20px;max-width:1100px;margin:0 auto}}
h1{{font-size:1.45rem;font-weight:800;letter-spacing:-.03em}}
.sub{{color:#7a87a0;font-size:.8rem;margin-top:3px;margin-bottom:20px}}
.badge{{background:{c}22;color:{c};border:1px solid {c}44;border-radius:5px;padding:2px 8px;font-size:.7rem;font-weight:600;margin-left:8px}}
.kpi-row{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:24px}}
.kpi{{background:#141828;border:1px solid #252c45;border-top:3px solid {c};border-radius:10px;padding:12px 14px}}
.kpi .lbl{{font-size:.63rem;color:#7a87a0;text-transform:uppercase;letter-spacing:.07em;margin-bottom:5px}}
.kpi .val{{font-size:1.1rem;font-weight:700}}
h2{{font-size:.95rem;font-weight:700;padding-left:10px;border-left:3px solid {c};margin:24px 0 10px}}
footer{{margin-top:24px;padding-top:14px;border-top:1px solid #1e2540;font-size:.7rem;color:#4a5568;text-align:center}}
a{{color:{c};text-decoration:none}}
</style>
</head>
<body>
<h1>{card['name']} <span class="badge">{realm_name} · Epic Card</span></h1>
<div class="sub">Epic (FL2) Flow Metrics · {start} → {end} · {len(months)} months of data</div>
{card_notes_html(card)}
{ABOUT_BLOCK}
<div class="kpi-row">{kpi_row}
</div>
<div><h2>FL2 — Epics</h2>{METHODOLOGY}{chart_grid(fl2)}</div>
<p style="margin-top:20px;font-size:.8rem"><a href="index.html">← {realm_name}</a> &nbsp;·&nbsp; <a href="../index.html">All realms</a></p>
<footer>Auto-generated · Nave + Jira via Notion · {end}</footer>
</body></html>"""

def card_notes_html(card):
    """Optional per-epic-card note banner (mirrors team_notes_html)."""
    note = card.get('note')
    return _banner(note, '#f59e0b', '⚠️') if note else ''

def realm_index_html(realm_id, realm):
    wellpass = realm_id in WELLPASS_REALMS
    split = bool(realm.get('epic_cards'))
    months = realm['months']
    end = months[-1] if months else 'No data yet'
    has_data = bool(months)

    def _card(name, slug, color, metrics_line, badge=''):
        return (f'<a href="{slug}.html" style="background:#141828;border:1px solid #252c45;'
                f'border-top:3px solid {color};border-radius:12px;padding:18px 20px;'
                f'text-decoration:none;color:#e4eaf5;display:block">'
                f'<div style="font-size:1rem;font-weight:700;margin-bottom:8px">{name}{badge}</div>'
                f'<div style="font-size:.75rem;color:#7a87a0">{metrics_line}</div></a>')

    def _grid(inner):
        return (f'<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));'
                f'gap:14px">{inner}</div>')

    cards = ''
    for tid, t in realm['teams'].items():
        slug = slugify(t['name'])
        c = t['color']
        if wellpass:
            wip  = t['fl1']['wip'][-1]  if has_data and t['fl1'].get('wip')  else None
            wip2 = t['fl2']['wip'][-1]  if has_data and t['fl2'].get('wip')  else None
            metrics_line = (f'WIP: <strong style="color:{c}">{wip if wip is not None else "—"}</strong>'
                             f' &nbsp;·&nbsp; Epic WIP: <strong style="color:{c}">{wip2 if wip2 is not None else "—"}</strong>')
        elif split:
            cfl2 = _team_fl2(realm, t) or {}
            ct1v = t['fl1']['ct'][-1] if has_data and t['fl1'].get('ct') else None
            ct2v = cfl2['ct'][-1] if (has_data and cfl2.get('ct')) else None
            ct1 = f"{ct1v}d" if ct1v is not None else '—'
            ct2 = f"{ct2v}d" if ct2v is not None else '—'
            metrics_line = (f'FL1 CT: <strong style="color:{c}">{ct1}</strong>'
                             f' &nbsp;·&nbsp; FL2 CT: <strong style="color:{c}">{ct2}</strong>')
        else:
            ct1v = t['fl1']['ct'][-1] if has_data and t['fl1']['ct'] else None
            ct2v = t['fl2']['ct'][-1] if has_data and t['fl2']['ct'] else None
            ct1 = f"{ct1v}d" if ct1v is not None else '—'
            ct2 = f"{ct2v}d" if ct2v is not None else '—'
            metrics_line = (f'FL1 CT: <strong style="color:{c}">{ct1}</strong>'
                             f' &nbsp;·&nbsp; FL2 CT: <strong style="color:{c}">{ct2}</strong>')
        cards += _card(t["name"], slug, c, metrics_line, _new_badge(t))

    body_grid = _grid(cards)
    teams_line = f'{len(realm["teams"])} teams'

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{realm['name']} — Flow Metrics</title>
<style>*{{box-sizing:border-box;margin:0;padding:0}}body{{background:#0c0f1a;color:#e4eaf5;font-family:'Segoe UI',system-ui,sans-serif;padding:32px 24px;max-width:900px;margin:0 auto}}h1{{font-size:1.4rem;font-weight:800;margin-bottom:6px}}.sub{{color:#7a87a0;font-size:.8rem;margin-bottom:28px}}a.back{{color:#60a5fa;font-size:.8rem;text-decoration:none}}h2.sec{{font-size:.95rem;font-weight:700;border-left:3px solid #60a5fa;padding-left:10px;margin-bottom:12px}}footer{{margin-top:32px;font-size:.7rem;color:#4a5568;text-align:center}}</style>
</head><body>
<a class="back" href="../index.html">← All realms</a>
<h1 style="margin-top:12px">{realm['name']}</h1>
<div class="sub">Flow Metrics · {teams_line} · Latest: {end}</div>
<a href="realm-dashboard.html" style="display:inline-block;margin-bottom:20px;background:#1e2540;border:1px solid #2f3a5f;border-radius:10px;padding:10px 16px;color:#60a5fa;text-decoration:none;font-size:.8rem;font-weight:600">📊 View Realm Dashboard (aggregate across all teams) →</a>
{realm_note_html(realm)}
{body_grid}
<footer>Auto-generated · {end}</footer>
</body></html>"""

def realm_dashboard_html(realm_id, realm):
    wellpass = realm_id in WELLPASS_REALMS
    c = '#60a5fa'
    months = realm['months']
    n_teams = len(realm['teams'])
    start = months[0] if months else '—'
    end = months[-1] if months else '—'

    agg_fl1 = aggregate_realm_fl(realm, 'fl1', wellpass)
    agg_fl2 = aggregate_realm_fl(realm, 'fl2', wellpass)

    if wellpass:
        s = wellpass_snapshot(agg_fl1, agg_fl2)
        fl1 = wellpass_fl1_set(months, agg_fl1, c)
        fl2 = wellpass_fl2_set(months, agg_fl2, c)
        about = WELLPASS_ABOUT_BLOCK
        kpi_cols = 6
        kpi_row = f"""
  <div class="kpi"><div class="lbl">Total WIP</div><div class="val">{s['wip']}</div></div>
  <div class="kpi"><div class="lbl">Avg WIP Age</div><div class="val">{s['wipAge']}</div></div>
  <div class="kpi"><div class="lbl">Total Throughput (YTD)</div><div class="val">{s['tp']}</div></div>
  <div class="kpi"><div class="lbl">Total Bugs Created/Resolved</div><div class="val">{s['bugs']}</div></div>
  <div class="kpi"><div class="lbl">Total Epic WIP</div><div class="val">{s['wip2']}</div></div>
  <div class="kpi"><div class="lbl">Avg Epic WIP Age</div><div class="val">{s['wipAge2']}</div></div>"""
        agg_note = ('<p style="font-size:.72rem;color:#4a5568;margin-bottom:16px">📐 WIP Age is averaged '
                    'across teams with data each month. WIP, Throughput, and Bugs are summed across teams '
                    'with data each month (realm-wide totals). Teams with no data for a given month are '
                    'excluded from that month\'s calculation rather than counted as zero.</p>')
    else:
        s = snapshot(agg_fl1, agg_fl2, len(months))
        fl1 = fl1_set(months, agg_fl1, c)
        fl2 = fl2_set(months, agg_fl2, c)
        about = ABOUT_BLOCK
        kpi_cols = 7
        kpi_row = f"""
  <div class="kpi"><div class="lbl">Avg FL1 Cycle Time</div><div class="val">{s['ct1']}</div></div>
  <div class="kpi"><div class="lbl">Total FL1 Throughput</div><div class="val">{s['tp']}</div></div>
  <div class="kpi"><div class="lbl">Total FL1 WIP</div><div class="val">{s['wip1']}</div></div>
  <div class="kpi"><div class="lbl">Avg FL2 Cycle Time</div><div class="val">{s['ct2']}</div></div>
  <div class="kpi"><div class="lbl">Total FL2 Delivered</div><div class="val">{s['del_']}</div></div>
  <div class="kpi"><div class="lbl">Total FL2 WIP</div><div class="val">{s['wip2']}</div></div>
  <div class="kpi"><div class="lbl">Avg Tech %</div><div class="val">{s['tech']}</div></div>"""
        agg_note = ('<div style="background:#0c1628;border:1px solid #2f261a;border-left:3px solid #f59e0b;'
                    'border-radius:0 8px 8px 0;padding:12px 16px;margin-bottom:16px">'
                    '<p style="font-size:.72rem;color:#7a87a0;line-height:1.6">'
                    '<strong style="color:#e4eaf5">📐 How these numbers are built:</strong> Throughput, WIP counts, '
                    'Epics Delivered, and Bugs are <strong style="color:#e4eaf5">summed</strong> across teams with data '
                    'each month (true realm-wide totals). Tech % is a <strong style="color:#e4eaf5">throughput-weighted '
                    'average</strong> (teams that delivered more work count more), approximating "what share of all '
                    'realm work was tech" rather than treating every team\'s percentage as equally important regardless '
                    'of volume. Teams with no data for a given month are excluded from that month\'s calculation rather '
                    'than counted as zero.</p>'
                    '<p style="font-size:.72rem;color:#7a87a0;line-height:1.6;margin-top:8px">'
                    '<strong style="color:#f59e0b">⚠️ Cycle Time is a simple average of each team\'s reported 85th-'
                    'percentile Cycle Time — not a true realm-wide percentile.</strong> Averaging percentiles across '
                    'teams with very different cycle times can produce a number that doesn\'t reflect any single '
                    'team\'s real experience — use it to spot directional trends, not as a literal "85% of realm work '
                    'finishes within X days" figure. It can also shift simply because the set of active teams changed '
                    'month to month (a team retiring or a new team appearing), not because of a real performance change.</p>'
                    + (MACHINE_WIP_CAVEAT if realm_id == 'machine' else '')
                    + '</div>')

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{realm['name']} — Realm Dashboard</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0c0f1a;color:#e4eaf5;font-family:'Segoe UI',system-ui,sans-serif;padding:24px 20px;max-width:1100px;margin:0 auto}}
h1{{font-size:1.45rem;font-weight:800;letter-spacing:-.03em}}
.sub{{color:#7a87a0;font-size:.8rem;margin-top:3px;margin-bottom:20px}}
.badge{{background:{c}22;color:{c};border:1px solid {c}44;border-radius:5px;padding:2px 8px;font-size:.7rem;font-weight:600;margin-left:8px}}
.kpi-row{{display:grid;grid-template-columns:repeat({kpi_cols},1fr);gap:10px;margin-bottom:24px}}
.kpi{{background:#141828;border:1px solid #252c45;border-top:3px solid {c};border-radius:10px;padding:12px 14px}}
.kpi .lbl{{font-size:.63rem;color:#7a87a0;text-transform:uppercase;letter-spacing:.07em;margin-bottom:5px}}
.kpi .val{{font-size:1.1rem;font-weight:700}}
h2{{font-size:.95rem;font-weight:700;padding-left:10px;border-left:3px solid {c};margin:24px 0 10px}}
footer{{margin-top:24px;padding-top:14px;border-top:1px solid #1e2540;font-size:.7rem;color:#4a5568;text-align:center}}
a{{color:{c};text-decoration:none}}
</style>
</head>
<body>
<h1>{realm['name']} <span class="badge">Realm Dashboard</span></h1>
<div class="sub">Aggregate Flow Metrics across {n_teams} teams · {start} → {end} · {len(months)} months of data</div>
{realm_note_html(realm)}
{realm_agg_composition_note(realm)}
{agg_note}
{about}
<div class="kpi-row">{kpi_row}
</div>
<div><h2>FL1 — Tasks (Realm Total)</h2>{METHODOLOGY}{chart_grid(fl1)}</div>
<div style="margin-top:32px"><h2>FL2 — Epics (Realm Total)</h2>{METHODOLOGY}{chart_grid(fl2)}</div>
<p style="margin-top:20px;font-size:.8rem"><a href="index.html">← {realm['name']} teams</a> &nbsp;·&nbsp; <a href="../index.html">All realms</a></p>
<footer>Auto-generated · Nave + Jira via Notion · {end}</footer>
</body></html>"""

def main_index_html(data):
    realms = data['realms']
    ICONS = {'core':'⚙️','apps':'📱','machine':'🤖','wellpass':'💚'}
    cards = ''
    for rid, r in realms.items():
        months = r['months']
        end = months[-1] if months else 'No data yet'
        n_teams = len(r['teams'])
        icon = ICONS.get(rid,'🏢')
        cards += (f'<a href="{rid}/index.html" style="background:#141828;border:1px solid #252c45;'
                  f'border-radius:14px;padding:22px 24px;text-decoration:none;color:#e4eaf5;display:block;'
                  f'position:relative;overflow:hidden">'
                  f'<div style="font-size:1.8rem;margin-bottom:10px">{icon}</div>'
                  f'<div style="font-size:1.05rem;font-weight:700;margin-bottom:4px">{r["name"]}</div>'
                  f'<div style="font-size:.75rem;color:#7a87a0">{n_teams} teams · Latest: {end}</div></a>')
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>EGYM Flow Metrics</title>
<style>*{{box-sizing:border-box;margin:0;padding:0}}body{{background:#0c0f1a;color:#e4eaf5;font-family:'Segoe UI',system-ui,sans-serif;padding:40px 24px;max-width:800px;margin:0 auto;text-align:center}}h1{{font-size:1.7rem;font-weight:800;letter-spacing:-.03em;margin-bottom:6px}}h1 span{{color:#60a5fa}}.sub{{color:#7a87a0;font-size:.85rem;margin-bottom:40px}}.grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:18px;text-align:left}}footer{{margin-top:40px;font-size:.72rem;color:#4a5568}}</style>
</head><body>
<h1>EGYM <span>Flow Metrics</span></h1>
<div class="sub">Monthly dashboards · FL1 Tasks &amp; FL2 Epics · All realms</div>
<a href="global-dashboard.html" style="display:inline-block;margin-bottom:24px;background:#1e2540;border:1px solid #2f3a5f;border-radius:10px;padding:10px 16px;color:#60a5fa;text-decoration:none;font-size:.8rem;font-weight:600">🌐 Global Engineering View (all realms) →</a>
<div class="grid">{cards}</div>
<footer>Auto-generated · Nave + Jira via Notion</footer>
</body></html>"""

# ─── Upload page — retired (webhook payload size limit blocks real-world PDFs) ─
# History: this used to be a webhook-based upload form as an alternative to Google
# Drive. It was pulled from the UI (button removed from main_index_html) because
# the platform webhook enforces a hard ~1 MiB request body limit, and a base64-encoded
# real monthly PDF report (e.g. 836 KB raw -> ~1.11 MB encoded) reliably exceeds it,
# so uploads silently failed. Kept as a graceful placeholder in case anyone still has
# the old link bookmarked, pointing them back to Google Drive instead of a dead form.
def upload_page_html():
    return """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Upload Report — EGYM Flow Metrics</title>
<style>*{box-sizing:border-box;margin:0;padding:0}body{background:#0c0f1a;color:#e4eaf5;font-family:'Segoe UI',system-ui,sans-serif;padding:40px 24px;max-width:560px;margin:0 auto}
h1{font-size:1.4rem;font-weight:800;letter-spacing:-.03em;margin-bottom:6px}h1 span{color:#60a5fa}
.sub{color:#7a87a0;font-size:.85rem;margin-bottom:20px}
a.back{display:inline-block;margin-bottom:24px;font-size:.78rem;color:#7a87a0;text-decoration:none}
.card{background:#141828;border:1px solid #252c45;border-radius:14px;padding:24px;font-size:.85rem;line-height:1.6;color:#a8b3c9}
.card strong{color:#e4eaf5}
</style></head><body>
<a class="back" href="index.html">← Back to Flow Metrics</a>
<h1>Upload <span>Monthly Report</span></h1>
<div class="sub">This upload form has been retired for now.</div>
<div class="card">
  We tried a direct browser-upload button here, but the underlying webhook has a hard ~1&nbsp;MiB request size limit that most real monthly PDF reports exceed once encoded — so uploads couldn't reliably reach the automation.
  <br><br>
  <strong>Please upload monthly PDF reports to the usual Google Drive folder instead</strong> — that path works exactly the same as before and picks up new reports automatically within a few minutes.
</div>
</body></html>"""

# ─── Global Engineering View (SVP-level, all realms) ───────────────────────────
def badge_chip(st):
    p = STATUS[st]
    return (f'<span style="display:inline-block;background:{p["bg"]};color:{p["text"]};'
            f'border:1px solid {p["border"]};border-radius:6px;padding:2px 7px;'
            f'font-size:.65rem;font-weight:700;margin-left:6px;white-space:nowrap">{p["label"]}</span>')

def _last(a):
    return next((v for v in reversed(a) if v is not None), None)

def _prev(a):
    nn = [v for v in a if v is not None]
    return nn[-2] if len(nn) >= 2 else None

def fmt_last_delta(arr, lower_is_better, suffix=''):
    # Arrow reflects the literal numeric direction of change (↓ = decreased, ↑ = increased);
    # lower_is_better is accepted for call-site compatibility but intentionally unused here.
    c = _last(arr); p = _prev(arr)
    if c is None: return '—'
    if p is None or c == p: return f"{c}{suffix}"
    arrow = '↓' if c < p else '↑'
    return f"{c}{suffix} {arrow}{abs(c-p)}"

def metric_row(label, value, st):
    return (f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:7px 0;border-bottom:1px solid #1e2540">'
            f'<span style="font-size:.73rem;color:#7a87a0">{label}</span>'
            f'<span style="font-size:.82rem;font-weight:600;white-space:nowrap">{value}{badge_chip(st)}</span></div>')

ENG_ICONS = {'core':'⚙️','apps':'📱','machine':'🤖','wellpass':'💚'}

def realm_card(rid, r, agg_fl1, agg_fl2):
    icon = ENG_ICONS.get(rid, '🏢')
    months = r['months']
    end = months[-1] if months else '—'
    s = snapshot(agg_fl1, agg_fl2, len(months))
    rows = (
        metric_row('FL1 Cycle Time', s['ct1'], trend(agg_fl1['ct'], True)) +
        metric_row('FL1 Throughput', s['tp'], trend(agg_fl1['tp'], False)) +
        metric_row('FL2 Cycle Time', s['ct2'], trend(agg_fl2['ct'], True)) +
        metric_row('FL2 Delivered', s['del_'], trend(agg_fl2['del'], False)) +
        metric_row('Tech %', s['tech'], trend(agg_fl1['tech'], False))
    )
    return (f'<div style="background:#141828;border:1px solid #252c45;border-radius:14px;padding:20px 22px">'
            f'<div style="font-size:1.05rem;font-weight:700;margin-bottom:2px">{icon} {r["name"]}</div>'
            f'<div style="font-size:.72rem;color:#7a87a0;margin-bottom:14px">{len(r["teams"])} teams · Latest: {end}</div>'
            f'{rows}'
            f'<div style="margin-top:14px;display:flex;gap:14px">'
            f'<a href="{rid}/realm-dashboard.html" style="font-size:.72rem;color:#60a5fa;text-decoration:none;font-weight:600">📊 Realm Dashboard →</a>'
            f'<a href="{rid}/index.html" style="font-size:.72rem;color:#60a5fa;text-decoration:none;font-weight:600">👥 Teams →</a>'
            f'</div></div>')

def needs_attention_html(active_realms, realm_aggs):
    checks_meta = [
        ('fl1', 'ct',   True,  'FL1 Cycle Time'),
        ('fl1', 'tp',   False, 'FL1 Throughput'),
        ('fl2', 'ct',   True,  'FL2 Cycle Time'),
        ('fl2', 'del',  False, 'FL2 Epics Delivered'),
        ('fl1', 'tech', False, 'Tech %'),
    ]
    items = []
    for rid, r in active_realms.items():
        aggs = realm_aggs[rid]
        for fl_key, field, lower_better, label in checks_meta:
            st = trend(aggs[fl_key][field], lower_better)
            if st == 'bad':
                items.append((r['name'], label))
    if not items:
        return ('<div style="background:#0c1628;border:1px solid #1e2540;border-left:3px solid #22c55e;'
                'border-radius:0 10px 10px 0;padding:14px 18px;font-size:.8rem;color:#22c55e;font-weight:600">'
                '✅ No realms currently flagged — all realm-level trends are stable or improving.</div>')
    rows = ''.join(
        f'<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;'
        f'border-bottom:1px solid #1e2540"><span style="font-size:.8rem"><strong>{name}</strong> — {label}</span>'
        f'{badge_chip("bad")}</div>' for name, label in items)
    return (f'<div style="background:#0c1628;border:1px solid #2f1a1a;border-left:3px solid #ef4444;'
            f'border-radius:0 10px 10px 0;padding:14px 18px">{rows}</div>')

def global_dashboard_html(data):
    realms = data['realms']
    active_realms = {rid: r for rid, r in realms.items() if r['months']}
    canonical = max((r['months'] for r in active_realms.values()), key=len, default=[])

    SUM_FL1 = ['tp','wR','wY','wG','bC','bR']
    SUM_FL2 = ['del','wip','wR','wY','wG']
    realm_aggs = {rid: {'fl1': aggregate_realm_fl(r,'fl1'), 'fl2': aggregate_realm_fl(r,'fl2'), 'months': r['months']}
                  for rid, r in active_realms.items()}

    eng_fl1 = {k: [] for k in SUM_FL1}
    eng_fl2 = {k: [] for k in SUM_FL2}
    for mon in canonical:
        for k in SUM_FL1:
            vals = []
            for ra in realm_aggs.values():
                if mon in ra['months']:
                    j = ra['months'].index(mon)
                    v = ra['fl1'][k][j]
                    if v is not None: vals.append(v)
            eng_fl1[k].append(sum(vals) if vals else None)
        for k in SUM_FL2:
            vals = []
            for ra in realm_aggs.values():
                if mon in ra['months']:
                    j = ra['months'].index(mon)
                    v = ra['fl2'][k][j]
                    if v is not None: vals.append(v)
            eng_fl2[k].append(sum(vals) if vals else None)

    end = canonical[-1] if canonical else '—'
    start = canonical[0] if canonical else '—'

    eng_wip1_series = [(r+y+g) if None not in (r,y,g) else None
                        for r,y,g in zip(eng_fl1['wR'], eng_fl1['wY'], eng_fl1['wG'])]
    wip1_total = _last(eng_wip1_series) or 0
    wip1_badge = trend(eng_wip1_series, True)
    lbC, lbR_ = _last(eng_fl1['bC']), _last(eng_fl1['bR'])
    bugs_str = f"{lbC} / {lbR_}" if (lbC is not None and lbR_ is not None) else '—'

    kpi_row = f"""
  <div class="kpi"><div class="lbl">Total FL1 Throughput</div><div class="val">{fmt_last_delta(eng_fl1['tp'], False)}{badge_chip(trend(eng_fl1['tp'], False))}</div></div>
  <div class="kpi"><div class="lbl">Total FL1 WIP</div><div class="val">{wip1_total}{badge_chip(wip1_badge)}</div></div>
  <div class="kpi"><div class="lbl">Bugs Closed / Reported</div><div class="val">{bugs_str}{badge_chip(trend_bugs(eng_fl1['bC'],eng_fl1['bR']))}</div></div>
  <div class="kpi"><div class="lbl">Total FL2 Epics Delivered</div><div class="val">{fmt_last_delta(eng_fl2['del'], False)}{badge_chip(trend(eng_fl2['del'], False))}</div></div>
  <div class="kpi"><div class="lbl">Total FL2 WIP</div><div class="val">{fmt_last_delta(eng_fl2['wip'], True)}{badge_chip(trend(eng_fl2['wip'], True))}</div></div>"""

    method_note = (
        '<div style="background:#0c1628;border:1px solid #1e2540;border-left:3px solid #60a5fa;'
        'border-radius:0 8px 8px 0;padding:12px 16px;margin-bottom:20px">'
        '<p style="font-size:.72rem;color:#7a87a0;line-height:1.6">'
        '<strong style="color:#e4eaf5">📐 How this page is built:</strong> Engineering-wide totals above are '
        '<strong style="color:#e4eaf5">sums</strong> of each realm\'s own already-aggregated totals — safe, purely '
        'additive metrics (Throughput, WIP, Bugs, Epics Delivered). '
        '<strong style="color:#f59e0b">Cycle Time and Tech % are intentionally NOT blended across realms</strong> — '
        'realms differ in team structure, scale, and (for Machine) WIP-risk thresholds, so a single blended number '
        'would be misleading. Instead, each realm shows its own Cycle Time / Tech % independently below.</p></div>'
    )

    realm_cards = ''.join(realm_card(rid, active_realms[rid], realm_aggs[rid]['fl1'], realm_aggs[rid]['fl2'])
                           for rid in active_realms)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>EGYM Engineering — Global View</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0c0f1a;color:#e4eaf5;font-family:'Segoe UI',system-ui,sans-serif;padding:24px 20px;max-width:1100px;margin:0 auto}}
h1{{font-size:1.5rem;font-weight:800;letter-spacing:-.03em}}
.sub{{color:#7a87a0;font-size:.8rem;margin-top:3px;margin-bottom:20px}}
.badge{{background:#60a5fa22;color:#60a5fa;border:1px solid #60a5fa44;border-radius:5px;padding:2px 8px;font-size:.7rem;font-weight:600;margin-left:8px}}
.kpi-row{{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:20px}}
.kpi{{background:#141828;border:1px solid #252c45;border-top:3px solid #60a5fa;border-radius:10px;padding:12px 14px}}
.kpi .lbl{{font-size:.63rem;color:#7a87a0;text-transform:uppercase;letter-spacing:.07em;margin-bottom:5px}}
.kpi .val{{font-size:1.05rem;font-weight:700;display:flex;align-items:center;flex-wrap:wrap}}
h2{{font-size:.95rem;font-weight:700;padding-left:10px;border-left:3px solid #60a5fa;margin:24px 0 12px}}
.realm-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px}}
footer{{margin-top:28px;padding-top:14px;border-top:1px solid #1e2540;font-size:.7rem;color:#4a5568;text-align:center}}
a{{color:#60a5fa}}
</style>
</head>
<body>
<h1>EGYM Engineering <span class="badge">Global View</span></h1>
<div class="sub">Snapshot across {len(active_realms)} realms · {start} → {end}</div>
{method_note}
<h2>Engineering-Wide Totals</h2>
<div class="kpi-row">{kpi_row}
</div>
<h2>Needs Attention</h2>
{needs_attention_html(active_realms, realm_aggs)}
<div style="margin-top:28px"><h2>By Realm</h2>
<div class="realm-grid">{realm_cards}</div></div>
<p style="margin-top:24px;font-size:.8rem"><a href="index.html">← All realms</a></p>
<footer>Auto-generated · Nave + Jira via Notion · {end}</footer>
</body></html>"""

# ─── Main (Space agent — shared-pages-only entry point) ────────────────────────
# This script owns ONLY index.html, global-dashboard.html, and upload.html.
# It NEVER writes into any /{realm}/ folder and NEVER touches data-*.json files.
# It merges every data-<realm>.json file found at repo root into one in-memory
# {"realms": {...}} structure and re-renders the three shared pages from that.

def discover_data_files():
    """List root-level files matching data-*.json (each realm agent owns exactly one)."""
    r = call_tool('github_get_file_contents', {
        'connectionId': GH_CONN, 'owner': OWNER, 'repo': REPO, 'path': '/'})
    return sorted(e['path'] for e in (r if isinstance(r, list) else [])
                  if e.get('type') == 'file' and e['name'].startswith('data-') and e['name'].endswith('.json'))

def load_realm_file(path):
    r = call_tool('github_get_file_contents', {
        'connectionId': GH_CONN, 'owner': OWNER, 'repo': REPO, 'path': path})
    return json.loads(base64.b64decode(r['content'].replace('\n', '')).decode())

def merge_all_realms(files):
    """Merge every data-<realm>.json's "realms" dict into one combined structure.
    Each realm file is expected to contain exactly one realm key (e.g. data-machine.json
    -> {"realms": {"machine": {...}}}), but this merges however many keys it finds,
    so it's forward-compatible if a file ever carries more than one realm."""
    merged = {"realms": {}}
    for path in files:
        d = load_realm_file(path)
        for rid, r in d.get('realms', {}).items():
            merged['realms'][rid] = r
    return merged

def root_file_shas():
    r = call_tool('github_get_file_contents', {
        'connectionId': GH_CONN, 'owner': OWNER, 'repo': REPO, 'path': '/'})
    return {e['path']: e['sha'] for e in (r if isinstance(r, list) else []) if e.get('type') == 'file'}

def run_space(gh_conn):
    """
    gh_conn — GitHub connection ID.
    Rebuilds index.html, global-dashboard.html, and upload.html from ALL
    data-<realm>.json files currently present at repo root. Does not touch
    anything else in the repo.
    """
    global GH_CONN
    GH_CONN = gh_conn

    print("Discovering data-*.json files at repo root...")
    files = discover_data_files()
    print(f"Found {len(files)} realm data file(s): {files}")
    if not files:
        print("⚠️  No data-*.json files found — nothing to merge, skipping rebuild.")
        return False

    print("Merging realm data files...")
    data = merge_all_realms(files)
    realm_ids = list(data['realms'].keys())
    print(f"Merged realms: {realm_ids}")

    # Trim every realm to the last DISPLAY_MONTHS months for rendering, same as the
    # realm agents do for their own pages — keeps shared-page rendering consistent.
    for _r in data['realms'].values():
        _trim_realm(_r)

    print("Fetching root file SHAs...")
    shas = root_file_shas()

    push('index.html', main_index_html(data),
         "Space agent: update main index", shas.get('index.html'))
    print("✅ index.html updated")

    push('global-dashboard.html', global_dashboard_html(data),
         "Space agent: update global engineering view", shas.get('global-dashboard.html'))
    print("✅ global-dashboard.html updated")

    push('upload.html', upload_page_html(),
         "Space agent: update upload page", shas.get('upload.html'))
    print("✅ upload.html updated")

    print("Done! (realm folders and data-*.json files are owned by the realm agents — not touched here.)")
    return True

if __name__ == '__main__':
    import sys
    run_space(sys.argv[1] if len(sys.argv) > 1 else input("GitHub connectionId: "))
