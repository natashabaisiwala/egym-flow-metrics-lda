# -*- coding: utf-8 -*-
"""Generalized flow-metrics PDF generator (any realm), ReportLab only.

Two entry points:
  * build_realm_pdf(realm, realm_id, anchor_iso, month_label, out_path)
      - `realm` is a realm dict {name, months, teams{...}} exactly as stored in
        data.json (full history; this fn trims to the last 12 months internally).
      - used by the live pipeline (monthly_run) after publishing.
  * CLI (preview/dry-run): assembles seed history + a latest-month preview file and
    calls build_realm_pdf. Usage:
        uv run --with reportlab python build_pdf_realm.py <realm_id> <anchor_YYYY-MM-DD> <month_label> <out.pdf> [preview_json] [new_month_key]

Trends (arrow + colour) are computed last-vs-previous month. New teams (team.new)
render as 'no trend' to avoid fake spikes from a reorg. Disclaimers (per-team notes,
new-team notes) render as callout boxes. Realms in NO_DORA_REALMS get no DORA page.
"""
import sys, json, datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import Color
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT

W, H = A4
ORANGE=Color(0.753,0.353,0.157); INK=Color(0.10,0.10,0.10); BLUE=Color(0.109,0.353,0.529)
GREY=Color(0.541,0.561,0.588); CREAM=Color(0.984,0.953,0.827); RED=Color(0.886,0.231,0.180)
YELLOW=Color(0.957,0.706,0.0); GREEN=Color(0.184,0.659,0.309); SUMBG=Color(0.961,0.851,0.420)
CALL=Color(0.988,0.906,0.847)
MARGIN=36; GAP=6
DISP=12
NO_DORA_REALMS={"apps"}  # realms that never had a DORA section

# these are set per-render by build_realm_pdf
NCOLS=5; CW=100.0; NF=8.3; TF=""

def T(y): return H-y
def num(v,d=0): return v if v is not None else d
def last2(arr):
    return (arr[-1] if arr else None, arr[-2] if len(arr)>=2 else None)
def trend(last,prev,lower_better):
    if last is None or prev is None: return ("right",GREY)
    thr=0.15 if abs(prev)<15 else 0.10
    if prev==0:
        if last==0: return ("right",GREY)
        pct=1.0
    else:
        pct=(last-prev)/abs(prev)
    if abs(pct)<=thr: return ("right",GREY)
    up=last>prev
    if lower_better: return ("up",RED) if up else ("down",GREEN)
    return ("up",GREEN) if up else ("down",RED)

def logo(c,x=36,yoff=44):
    c.setFont("Helvetica-Bold",15); y=T(yoff); cx=x
    for ch,col in [("E",ORANGE),("G",INK),("Y",INK),("M",INK)]:
        c.setFillColor(col); c.drawString(cx,y,ch); cx+=c.stringWidth(ch,"Helvetica-Bold",15)+6
def tri(c,cx,yoff,size,direction,col):
    c.setFillColor(col); s=size; p=c.beginPath(); top=T(yoff)
    if direction=="up": p.moveTo(cx,top); p.lineTo(cx-s,top-s*1.4); p.lineTo(cx+s,top-s*1.4)
    elif direction=="down": p.moveTo(cx,top-s*1.4); p.lineTo(cx-s,top); p.lineTo(cx+s,top)
    else: p.moveTo(cx+s,top-s*0.7); p.lineTo(cx-s*0.7,top); p.lineTo(cx-s*0.7,top-s*1.4)
    p.close(); c.drawPath(p,fill=1,stroke=0)
def dot(c,x,yoff,col,r=3.2): c.setFillColor(col); c.circle(x,T(yoff)+r,r,fill=1,stroke=0)
def ctext(c,cx,yoff,text,font,size,col): c.setFont(font,size); c.setFillColor(col); c.drawCentredString(cx,T(yoff),str(text))
def wrap_lines(text,font,size,maxw):
    words=text.split(); lines=[]; cur=""
    for w_ in words:
        t=(cur+" "+w_).strip()
        if canvas.Canvas("/dev/null").stringWidth(t,font,size)<=maxw: cur=t
        else:
            if cur: lines.append(cur)
            cur=w_
    if cur: lines.append(cur)
    return lines
def para(c,html,x,yoff,width,size=8.2,leading=11,color="#222222",space=5):
    st=ParagraphStyle("n",fontName="Helvetica",fontSize=size,leading=leading,textColor=color,alignment=TA_LEFT,spaceAfter=space)
    p=Paragraph(html,st); w,h=p.wrapOn(c,width,H); p.drawOn(c,x,T(yoff)-h); return h
def _para_h(c,html,width,size,leading,space):
    st=ParagraphStyle("m",fontName="Helvetica",fontSize=size,leading=leading,alignment=TA_LEFT,spaceAfter=space)
    p=Paragraph(html,st); w,h=p.wrapOn(c,width,H); return h
def _callout_h(c,text):
    st=ParagraphStyle("clh",fontName="Helvetica",fontSize=8.0,leading=10.5)
    p=Paragraph(text,st); w,h=p.wrapOn(c,W-2*MARGIN-20,H); return h
def title(c,first,rest,yoff=70,size=30):
    c.setFont("Helvetica-Bold",size); full=first+rest; tw=c.stringWidth(full,"Helvetica-Bold",size); x0=(W-tw)/2
    c.setFillColor(ORANGE); c.drawString(x0,T(yoff),first)
    c.setFillColor(INK); c.drawString(x0+c.stringWidth(first,"Helvetica-Bold",size),T(yoff),rest)
def timeframe(c,yoff=92): c.setFont("Helvetica",10.5); c.setFillColor(INK); c.drawCentredString(W/2,T(yoff),TF)
def callout(c,text,yoff,color=ORANGE,bg=CALL,txt="#222222"):
    st=ParagraphStyle("cl",fontName="Helvetica",fontSize=8.0,leading=10.5,textColor=txt)
    p=Paragraph(text,st); w,h=p.wrapOn(c,W-2*MARGIN-20,H)
    c.setFillColor(bg); c.roundRect(MARGIN,T(yoff)-h-12,W-2*MARGIN,h+14,6,fill=1,stroke=0)
    c.setFillColor(color); c.rect(MARGIN,T(yoff)-h-12,4,h+14,fill=1,stroke=0)
    p.drawOn(c,MARGIN+12,T(yoff)-h-5); return h+20
def card_x(i): return MARGIN+i*(CW+GAP)

def fl1_card(c,i,d,top):
    x=card_x(i); cx=x+CW/2; hgt=282
    c.setFillColor(CREAM); c.roundRect(x,T(top)-hgt,CW,hgt,10,fill=1,stroke=0)
    y=top+15
    NAMEF=NF+2.7
    lines=wrap_lines(d["name"],"Helvetica-Bold",NAMEF,CW-4); c.setFillColor(INK); c.setFont("Helvetica-Bold",NAMEF)
    for ln in lines[:2]: c.drawCentredString(cx,T(y),ln); y+=13
    if len(lines)==1: y+=13
    y+=2
    tri(c,cx,y,5,d["ct_t"][0],d["ct_t"][1]); y+=18
    ctext(c,cx,y,"Cycle time","Helvetica",7.6,INK); y+=13
    ctext(c,cx,y,f'{d["ct"]} days',"Helvetica-Bold",11,BLUE); y+=14
    ctext(c,cx,y,"to complete 85%","Helvetica",6.0,GREY); y+=8
    ctext(c,cx,y,"of the tickets","Helvetica",6.0,GREY); y+=17
    tri(c,cx,y,5,d["tp_t"][0],d["tp_t"][1]); y+=18
    ctext(c,cx,y,"Throughput","Helvetica",7.6,INK); y+=13
    ctext(c,cx,y,d["tp"],"Helvetica-Bold",11.5,BLUE); y+=16
    ctext(c,cx,y,"WIP Aging Risk","Helvetica-Bold",7.2,INK); y+=13
    for col,val in [(RED,d["r"]),(YELLOW,d["y"]),(GREEN,d["g"])]:
        dot(c,cx-24,y,col); ctext(c,cx+3,y,f"{val} item(s)","Helvetica-Bold",7.6,INK); y+=11
    y+=5
    ctext(c,cx,y,"Bugs","Helvetica",7.6,INK); y+=11
    ctext(c,cx,y,d["bugs"],"Helvetica-Bold",10.5,BLUE); y+=11
    ctext(c,cx,y,"created vs resolved","Helvetica",6.0,GREY); y+=16
    ctext(c,cx,y,f'{d["tech"]}%',"Helvetica-Bold",13,BLUE); y+=14
    ctext(c,cx,y,"tech tasks","Helvetica-Bold",8,INK)

def fl2_card(c,i,d,top,xpos=None):
    x=xpos if xpos is not None else card_x(i); cx=x+CW/2; hgt=250
    c.setFillColor(CREAM); c.roundRect(x,T(top)-hgt,CW,hgt,10,fill=1,stroke=0)
    y=top+15
    NAMEF=NF+2.7
    lines=wrap_lines(d["name"],"Helvetica-Bold",NAMEF,CW-4); c.setFillColor(INK); c.setFont("Helvetica-Bold",NAMEF)
    for ln in lines[:2]: c.drawCentredString(cx,T(y),ln); y+=13
    if len(lines)==1: y+=13
    y+=2
    tri(c,cx,y,5,d["ct_t"][0],d["ct_t"][1]); y+=18
    ctext(c,cx,y,"Cycle time","Helvetica",7.6,INK); y+=13
    ctext(c,cx,y,f'{d["ct"]} days'+("*" if d.get("caveat") else ""),"Helvetica-Bold",11,BLUE); y+=14
    ctext(c,cx,y,"to complete 85%","Helvetica",6.0,GREY); y+=8
    ctext(c,cx,y,"of the Epics","Helvetica",6.0,GREY); y+=17
    ctext(c,cx,y,d["del"],"Helvetica-Bold",13,BLUE); y+=14
    ctext(c,cx,y,"Epics delivered","Helvetica-Bold",7.6,INK); y+=16
    ctext(c,cx,y,f'{d["tech"]}%',"Helvetica-Bold",12,BLUE); y+=13
    ctext(c,cx,y,"tech roadmap","Helvetica-Bold",7.6,INK); y+=17
    ctext(c,cx,y,"current WIP","Helvetica",7.0,GREY); y+=12
    ctext(c,cx,y,d["wip"],"Helvetica-Bold",11.5,BLUE); y+=15
    ctext(c,cx,y,"WIP Aging Risk","Helvetica-Bold",7.2,INK); y+=13
    for col,val in [(RED,d["r"]),(YELLOW,d["y"]),(GREEN,d["g"])]:
        dot(c,cx-24,y,col); ctext(c,cx+3,y,f"{val} item(s)","Helvetica-Bold",7.6,INK); y+=11

def legend(c,yoff,epics=False,template_aging=False):
    metric="Cycle-time trend" if epics else "Cycle-time and Throughput trend"
    html=(f'{metric}: the triangle shows the metric trend (up, none or down). Grey = no trend. '
          '<font color="#E23B2E"><b>Red</b></font> = worse trend / out of expectations. '
          '<font color="#2FA84F"><b>Green</b></font> = better trend / within expectations. '
          'Criteria: a change &gt;10% vs last month flips the trend; if the value is under 15, 15% is used.')
    para(c,html,MARGIN,yoff,W-2*MARGIN,size=6.5,leading=9,color="#333333")
    if template_aging:
        html2=('WIP Aging Risk for MSW/MI: &nbsp; <font color="#E23B2E">&#9679;</font> WIP cycle time &gt; 12 weeks '
               '&nbsp;&nbsp; <font color="#F4B400">&#9679;</font> &ge; 8 weeks and &lt; 12 weeks '
               '&nbsp;&nbsp; <font color="#2FA84F">&#9679;</font> &lt; 8 weeks')
        para(c,html2,MARGIN,yoff+20,W-2*MARGIN,size=6.5,leading=9,color="#333333")
        html3=('WIP Aging Risk for Fitness Hub: &nbsp; <font color="#E23B2E">&#9679;</font> WIP cycle time &gt; 85% '
               '&nbsp;&nbsp; <font color="#F4B400">&#9679;</font> &ge; 70% and &lt; 85% '
               '&nbsp;&nbsp; <font color="#2FA84F">&#9679;</font> &lt; 70%')
        para(c,html3,MARGIN,yoff+32,W-2*MARGIN,size=6.5,leading=9,color="#333333")
    else:
        html2=('WIP Aging Risk: &nbsp; <font color="#E23B2E">&#9679;</font> WIP cycle time &gt; 85% '
               '&nbsp;&nbsp; <font color="#F4B400">&#9679;</font> &ge; 70% and &lt; 85% '
               '&nbsp;&nbsp; <font color="#2FA84F">&#9679;</font> &lt; 70%')
        para(c,html2,MARGIN,yoff+20,W-2*MARGIN,size=6.5,leading=9,color="#333333")

def set_grid(n):
    """Choose columns/rows for n cards. <=5 => one row (Core/Apps unchanged);
    >5 => two rows (Machine 8 FL1 / 7 FL2). Sets NCOLS/CW/NF globals."""
    import math
    global NCOLS,CW,NF
    cols = n if n<=5 else math.ceil(n/2)
    rows = math.ceil(n/cols)
    NCOLS=cols; CW=(W-2*MARGIN-(cols-1)*GAP)/cols; NF=7.3 if cols>=6 else 8.3
    return cols,rows

def _build_fl1_cards(teams):
    fl1={}
    for tid,t in teams.items():
        f=t["fl1"]; is_new=bool(t.get("new"))
        ct,ctp=last2(f["ct"]); tp,tpp=last2(f["tp"])
        ct_t=("right",GREY) if is_new else trend(ct,ctp,True)
        tp_t=("right",GREY) if is_new else trend(tp,tpp,False)
        fl1[tid]={"name":t["name"],"ct":num(ct,"-"),"ct_t":ct_t,
                    "tp":num(tp,"-"),"tp_t":tp_t,
                    "r":num(f["wR"][-1]),"y":num(f["wY"][-1]),"g":num(f["wG"][-1]),
                    "bugs":f"{num(f['bC'][-1])} | {num(f['bR'][-1])}","tech":num(f["tech"][-1])}
    return fl1

def _build_fl2_cards(source):
    fl2=[]
    for tid,t in source.items():
        g=t["fl2"]; is_new=bool(t.get("new"))
        c2,c2p=last2(g["ct"]); c2_t=("right",GREY) if is_new else trend(c2,c2p,True)
        deln=num(g["del"][-1])
        caveat=isinstance(deln,int) and 1<=deln<=2
        fl2.append({"name":t["name"],"ct":num(c2,"-"),"ct_t":c2_t,"caveat":caveat,
                    "del":deln,"tech":num(g["tech"][-1]),"wip":num(g["wip"][-1]),
                    "r":num(g["wR"][-1]),"y":num(g["wY"][-1]),"g":num(g["wG"][-1])})
    return fl2

def _fl1_page(c, REALM_NAME, cards, bullets, subtitle=None, corrections=None, realm_note=None, spacious=False):
    """Render one FL1 (Tasks) page. `cards` is a list of card dicts. Optional
    `subtitle` labels a team cluster; `corrections`/`realm_note` render callouts
    (used only on the first Tasks page); `bullets` is the LLM-authored narrative.
    `spacious` (Machine clusters) uses larger narrative type and vertically distributes
    the single card row so content is not glued to the top."""
    logo(c); title(c,REALM_NAME[0],REALM_NAME[1:]+" - Tasks",yoff=70,size=26); timeframe(c)
    cols,rows=set_grid(len(cards)); RG=16; FH=282
    nsz,nld,nsp,ngap=(9.3,13.4,7,5) if spacious else (8.0,10.3,3,3)
    top=112
    if corrections:
        top+=callout(c,f'<b>Corrections.</b> {corrections}',top,color=BLUE,bg=Color(0.90,0.94,0.99))+6
    if realm_note:
        top+=callout(c,f'<b>Reorg context.</b> {realm_note}',top)+6
    if subtitle:
        c.setFont("Helvetica-Bold",13); c.setFillColor(ORANGE); c.drawString(MARGIN,T(top),subtitle); top+=24
    if bullets:
        for n in bullets:
            top+=para(c,n,MARGIN,top,W-2*MARGIN,size=nsz,leading=nld,color="#1a1a1a",space=nsp)+ngap
    cards_top=top+(18 if spacious else 6)
    for i,d in enumerate(cards): fl1_card(c,i%cols,d,cards_top+(i//cols)*(FH+RG))
    legend(c,cards_top+rows*FH+(rows-1)*RG+16,epics=False)
    c.showPage()

def _fl2_summary(c, src, sy, epic_ct=None):
    """Draw the FL2 aggregate summary band at yoff `sy`; return its bottom yoff. `src` is a
    list of team/epic-card dicts (each with a 'fl2' block). `epic_ct` = realm-level epic cycle
    time (engine p85); if None, falls back to the delivered-weighted mean of the card CTs."""
    bh=74
    tot_del=sum(num(t["fl2"]["del"][-1]) for t in src)
    tot_wip=sum(num(t["fl2"]["wip"][-1]) for t in src)
    tr=sum(num(t["fl2"]["wR"][-1]) for t in src); ty=sum(num(t["fl2"]["wY"][-1]) for t in src); tg=sum(num(t["fl2"]["wG"][-1]) for t in src)
    wsum=sum(num(t["fl2"]["del"][-1])*num(t["fl2"]["tech"][-1]) for t in src); tech_w=round(wsum/tot_del) if tot_del else 0
    if epic_ct is None:
        ctsum=sum(num(t["fl2"]["ct"][-1])*num(t["fl2"]["del"][-1]) for t in src)
        epic_ct=round(ctsum/tot_del) if tot_del else 0
    c.setFillColor(SUMBG); c.roundRect(MARGIN,T(sy)-bh,W-2*MARGIN,bh,14,fill=1,stroke=0)
    segw=(W-2*MARGIN)/5
    def seg(i): return MARGIN+i*segw+segw/2
    ctext(c,seg(0),sy+26,f"{tot_wip} Epics","Helvetica-Bold",14,BLUE); ctext(c,seg(0),sy+40,"currently in progress","Helvetica",7.0,INK)
    ctext(c,seg(1),sy+26,f"{tot_del} Epics","Helvetica-Bold",14,BLUE); ctext(c,seg(1),sy+40,"delivered","Helvetica",7.0,INK)
    ctext(c,seg(2),sy+24,f"{epic_ct} days","Helvetica-Bold",14,BLUE); ctext(c,seg(2),sy+37,"to complete 85%","Helvetica",6.8,INK); ctext(c,seg(2),sy+46,"of the Epics","Helvetica",6.8,INK)
    ctext(c,seg(3),sy+14,"WIP Aging Risk","Helvetica-Bold",7.2,Color(0.36,0.33,0.14)); yy=sy+26
    for col,val in [(RED,tr),(YELLOW,ty),(GREEN,tg)]:
        dot(c,seg(3)-26,yy,col); ctext(c,seg(3)+2,yy,f"{val} item(s)","Helvetica-Bold",7.2,INK); yy+=11
    ctext(c,seg(4),sy+26,f"{tech_w}%","Helvetica-Bold",14,BLUE); ctext(c,seg(4),sy+40,"Tech Roadmap done","Helvetica",7.0,INK)
    return sy+bh

def _epics_caveat(c, y, fl2):
    if any(d.get("caveat") for d in fl2):
        para(c,'* Small sample: the cycle time reflects only the one or two epic(s) delivered in the window, '
               'so it is not a full 85th-percentile distribution.',MARGIN,y,W-2*MARGIN,
               size=6.8,leading=9,color="#333333")

def build_realm_pdf(realm, realm_id, anchor_iso, month_label, out_path, notes=None):
    """Render `realm` (data.json-shaped dict, full history) to a print-ready A4 PDF.

    `notes` (optional) adds LLM-authored narrative to the report:
      {"tasks": [html_bullet, ...],       # rendered above the FL1 cards
       "epics": [html_bullet, ...],        # rendered above the FL2 cards
       "epics_callout": "html"}            # optional highlighted box on the FL2 page
    Bullets are Paragraph HTML (use <b>..</b>, <i>..</i>). Keep them concise so the
    cards still fit on the page (roughly <=6 FL1 bullets, <=4 FL2 bullets)."""
    global NCOLS, CW, NF, TF
    import copy
    realm=copy.deepcopy(realm)
    months=realm["months"]
    def _trimlists(d,k):
        for key in list(d):
            if isinstance(d[key],list) and len(d[key])>=k: d[key]=d[key][k:]
    if len(months)>DISP:
        k=len(months)-DISP; realm["months"]=months[k:]
        for t in realm["teams"].values():
            for fl in ("fl1","fl2"):
                if fl in t: _trimlists(t[fl],k)
        for cc in (realm.get("epic_cards") or {}).values():
            if "fl2" in cc: _trimlists(cc["fl2"],k)
    teams=realm["teams"]; REALM_NAME=realm["name"]
    a=datetime.date.fromisoformat(anchor_iso); s=a-datetime.timedelta(days=120)
    TF=f"Time frame: last 120 days ({s.strftime('%d/%m')} - {a.strftime('%d/%m')})"
    split=bool(realm.get("epic_cards"))
    fl2_source=realm["epic_cards"] if split else teams
    fl1=_build_fl1_cards(teams)
    fl2=_build_fl2_cards(fl2_source)
    core_note=next((t["note"] for t in teams.values() if t.get("note") and not t.get("new")),None)
    new_names=[t["name"] for t in teams.values() if t.get("new")]

    c=canvas.Canvas(out_path,pagesize=A4)
    # P1 cover
    logo(c)
    c.setFont("Helvetica-Bold",54); c.setFillColor(ORANGE); c.drawString(MARGIN,T(430),REALM_NAME)
    c.setFillColor(INK); c.setFont("Helvetica-Bold",46); c.drawString(MARGIN,T(470),"monthly"); c.drawString(MARGIN,T(512),"flow metrics")
    c.setFont("Helvetica-Bold",20); c.drawString(MARGIN,T(540),month_label); c.showPage()
    # P2 about
    logo(c); title(c,"A","bout flow metrics",yoff=74,size=30)
    about=[
     "<b>Cycle time:</b> total elapsed time for a work item to move from in progress until done. For Epics it starts when moved to the 0-25% status.",
     "<b>Throughput:</b> stories, tasks, maintenances and bugs finished in the period. <u>Research and Sub-task issue types are excluded.</u>",
     "<b>Work in Progress (WIP)*:</b> work started but not finished. <u>Statuses before the commitment point (backlog, draft, etc.) are not counted.</u>",
     "<b>WIP Risk*:</b> in-progress items at risk relative to the cycle time.",
     "<b>Bugs:</b> bugs created vs resolved in the period - tracks whether bugs are under control.",
     "<b>Data source:</b> all data points are extracted directly from Jira (automated pipeline).",
     "<b>Flight Level 1 (FL1) - Operation:</b> daily team work items focused on delivery, linked to the Epics.",
     "<b>Flight Level 2 (FL2) - Coordination:</b> roadmap and tech initiatives, Epics management and cross-team alignment.",
     "<b>Flight Level 3 (FL3) - Strategy:</b> company goals, direction and priorities.",
    ]
    y=140
    for it in about: y+=para(c,"&#8226; &nbsp; "+it,MARGIN+4,y,W-2*MARGIN-8,size=13.0,leading=18.5,color="#1a1a1a",space=8)+13
    para(c,"<i><u>Disclaimer*:</u> all metrics besides WIP and WIP Risk are lagging indicators. WIP and WIP Risk are leading "
           "indicators we can manage now; doing so improves the other metrics over time.</i>",MARGIN+4,y+16,W-2*MARGIN-8,size=11.5,leading=15.5,color="#333333")
    c.showPage()
    # P3+ tasks: single page, or one page per FL1 team cluster (realm["fl1_groups"])
    groups=realm.get("fl1_groups")
    corr=realm.get("corrections"); rnote=realm.get("note")
    if groups:
        tg=(notes or {}).get("tasks_groups") or []
        for gi,g in enumerate(groups):
            subset=[fl1[tid] for tid in g["ids"] if tid in fl1]
            bullets=tg[gi] if gi<len(tg) else None
            _fl1_page(c,REALM_NAME,subset,bullets,subtitle=g.get("title"),
                      corrections=(corr if gi==0 else None),
                      realm_note=(rnote if gi==0 else None),spacious=True)
    else:
        _fl1_page(c,REALM_NAME,list(fl1.values()),(notes or {}).get("tasks"),
                  corrections=corr,realm_note=rnote)
    # Epics: single page for <=5 cards (Core/Apps); two pages for the Machine split (>5 cards)
    src=list(fl2_source.values())
    cols,rows=set_grid(len(fl2)); FH=250; RG=16
    def _ehead():
        logo(c); title(c,REALM_NAME[0],REALM_NAME[1:]+" - Epics",yoff=70,size=26); timeframe(c)
    if len(fl2)<=5:
        _ehead(); top=114
        if core_note: top+=callout(c,f'<b>Data note.</b> {core_note}',top)
        if new_names:
            NG=Color(0.086,0.639,0.290)
            top+=callout(c,'<b>NEW TEAMS.</b> '+", ".join(new_names)+" were formed in the 20 Jul 2026 reorg; "
                         "their history reflects carried-over tickets (not net-new), so pre-Jul trends are partial "
                         "and at least 3 months are needed for reliable readings.",top,
                         color=Color(0.06,0.48,0.22),bg=NG,txt="#ffffff")
        if notes and notes.get("epics_callout"):
            top+=callout(c,notes["epics_callout"],top)
        if notes and notes.get("epics"):
            for n in notes["epics"]:
                top+=para(c,n,MARGIN,top,W-2*MARGIN,size=8.0,leading=10.3,color="#1a1a1a",space=3)+3
        cards_top=top+6
        for i,d in enumerate(fl2): fl2_card(c,i%cols,d,cards_top+(i//cols)*(FH+RG))
        sy=cards_top+rows*(FH+RG)+4
        sb=_fl2_summary(c,src,sy); legend(c,sb+12,epics=True); _epics_caveat(c,sb+52,fl2)
        c.showPage()
    else:
        # Machine template: ONE page, all epic cards in a single row (mirrors the manual report).
        _ehead(); top=112
        nsz,nld,nsp,ngap=9.4,13.6,8,6
        narr=(notes or {}).get("epics")
        cout=notes.get("epics_callout") if notes else None
        if cout: top+=callout(c,cout,top)+6
        if narr:
            for n in narr: top+=para(c,n,MARGIN,top,W-2*MARGIN,size=nsz,leading=nld,color="#1a1a1a",space=nsp)+ngap
        n=len(fl2)
        NCOLS=n; CW=(W-2*MARGIN-(n-1)*GAP)/n; NF=6.2
        cards_top=top+16
        for i,d in enumerate(fl2): fl2_card(c,i,d,cards_top)
        sy=cards_top+FH+18
        sb=_fl2_summary(c,src,sy,epic_ct=realm.get("epic_ct"))
        legend(c,sb+14,epics=True,template_aging=True); _epics_caveat(c,sb+66,fl2)
        c.showPage()
    # P5 DORA (skipped for realms that never had it)
    if realm_id not in NO_DORA_REALMS:
        logo(c); title(c,"D","ORA Metrics",yoff=74,size=30)
        callout(c,'<b>Not included in this automated report.</b> The DORA section (MTTD / MTTR, root-cause severity, '
                  'change-failure rate and deployment counts) is sourced from incident and deployment data, <b>not</b> from '
                  'the Jira flow-metrics pipeline that generates pages 1-4.',132)
        c.showPage()
    c.save()
    return out_path

# ---------- CLI (preview/dry-run): assemble seed + latest-month preview ----------
if __name__=="__main__":
    REALM_ID   = sys.argv[1] if len(sys.argv)>1 else "apps"
    ANCHOR     = sys.argv[2] if len(sys.argv)>2 else "2026-07-27"
    MONTH_LABEL= sys.argv[3] if len(sys.argv)>3 else "July 2026"
    OUT        = sys.argv[4] if len(sys.argv)>4 else "Apps_Realm_flow_metrics_July_2026.pdf"
    PREVIEW_JSON = sys.argv[5] if len(sys.argv)>5 else "preview_apps_july.json"
    NEW_MONTH_KEY= sys.argv[6] if len(sys.argv)>6 else "Jul 26"
    seed=json.load(open("data_seed.json")); latest=json.load(open(PREVIEW_JSON))
    realm=seed["realms"][REALM_ID]
    realm["months"]=realm["months"]+[NEW_MONTH_KEY]
    for tid,t in realm["teams"].items():
        jv=latest.get(tid)
        for fl in ("fl1","fl2"):
            for k in t[fl]:
                t[fl][k]=t[fl][k]+[(jv[fl].get(k) if jv else None)]
    build_realm_pdf(realm, REALM_ID, ANCHOR, MONTH_LABEL, OUT)
    print("PDF written:",OUT)
