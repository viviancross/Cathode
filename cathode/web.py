"""Cathode's web page and its outputs, served beside sync (sync.py's server).

- The page (/): a remote for your phone, the channels with what's on and
  next (tap one to tune), and the lineup and channel settings: hide, rename,
  renumber; a library or YouTube channel's sort method, hours and breaks.
- The API under /api/ that page uses: state, remote keys, tuning, edits.
- Outputs for other apps, when sharing is on: the timeline channels as an
  M3U playlist (/lineup.m3u), their guide (/xmltv.xml), and an HDHomeRun
  tuner's answers (/discover.json, /lineup.json, /lineup_status.json); each
  channel's /stream/<id> sends the player to the programme on the air, from
  where it's up to (through Plex's transcoder).

Only addresses on your own network are answered."""

from __future__ import annotations

import ipaddress
import json
import socket
from datetime import datetime, timezone
from xml.sax.saxutils import escape

from . import remote as R

KEYS = {"up": R.UP, "down": R.DOWN, "left": R.LEFT, "right": R.RIGHT, "ok": R.SELECT, "back": R.BACK,
        "guide": R.GUIDE, "menu": R.MENU, "info": R.INFO, "options": R.OPTIONS, "chup": R.CH_UP,
        "chdown": R.CH_DOWN, "last": R.PREV, "volup": R.VOL_UP, "voldown": R.VOL_DOWN, "mute": R.MUTE,
        "play": R.PLAY, "pause": R.PAUSE, "fav": R.FAV, "exit": R.EXIT}


def local(addr: str) -> bool:
    """Whether a client is on this network (or this machine)."""
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local


def my_address() -> str:
    """This machine's address on the network (no packet is sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def _when(dt) -> str:
    return dt.astimezone().strftime("%I:%M %p").lstrip("0") if dt else ""


def state(app) -> dict:
    """What the page shows: the channel on, every channel with now and next."""
    now = datetime.now(timezone.utc)
    epg = app.epg
    live = getattr(app, "live", None)
    on = live.channel if live is not None else None
    rows = []
    for ch in list(app.channels):
        cid = epg.resolve_channel_id(ch.epg_id, ch.name) if ch.epg_id or ch.name else None
        cur = epg.current_program(cid, now) if cid else None
        nxt = epg.next_program(cid, now) if cid else None
        rows.append({"number": ch.number, "name": ch.name, "url": ch.url,
                     "now": {"title": cur.title, "start": _when(cur.start), "stop": _when(cur.stop)} if cur else None,
                     "next": {"title": nxt.title, "start": _when(nxt.start)} if nxt else None})
    shown = {id(c) for c in app.channels}
    hidden = [{"number": c.number, "name": c.name, "url": c.url} for c in getattr(app, "lineup_all", [])
              if id(c) not in shown]
    return {"on": {"number": on.number, "name": on.name} if on else None, "channels": rows, "hidden": hidden,
            "edits": app.config.channel_edits, "made": made(app)}


def made(app) -> list:
    """The timeline channels' settings the page can change."""
    from . import libchannels as lc
    out = []
    for kind, lst in (("library", app.config.library_channels), ("video", app.config.video_channels)):
        for c in lst:
            out.append({"kind": kind, "id": c["id"], "name": c.get("name") or "", "order": c.get("order") or
                        ("mix" if kind == "video" else "cyclic_shuffle"), "hours": c.get("hours"),
                        "breaks": bool(lc.breaks_of(c, app.library)),
                        "mid": lc.breaks_of(c, app.library).get("mid", "off"),
                        "orders": lc.ORDERS, "hourses": lc.HOURS, "mids": lc.MIDS})
    return out


def act(app, body: dict) -> str:
    """A request from the page, done on the UI thread: a key, a channel, an
    edit. Returns what to say back."""
    what = body.get("do")
    if what == "key":
        key = KEYS.get(str(body.get("key")))
        if key is None:
            return "no such key"
        app.post(app.press, key)
        return "ok"
    if what == "tune":
        try:
            number = float(body.get("number"))
        except (TypeError, ValueError):
            return "no such channel"
        app.post(_tune, app, number)
        return "ok"
    if what == "edit":
        app.post(_edit, app, str(body.get("url", "")), body)
        return "ok"
    if what == "channel":
        app.post(_channel, app, str(body.get("id", "")), body)
        return "ok"
    return "not understood"


def _tune(app, number):
    for i, ch in enumerate(app.channels):
        if ch.number == number:
            app.live.tune(i)
            return


def _edit(app, url, body):
    from . import lineup
    ch = next((c for c in app.lineup_all if c.url == url), None)
    if ch is None:
        return
    change = {}
    if "hide" in body:
        change["hide"] = bool(body["hide"]) or None
    if "name" in body:
        change["name"] = str(body["name"]).strip()[:60] or None
    if "number" in body:
        change["number"] = lineup.number(str(body["number"])) if str(body["number"]).strip() else None
    lineup.edit(app.config, ch, **change)
    app.config.save()
    app.relineup()


def _channel(app, cid, body):
    from . import libchannels as lc
    c = next((x for x in list(app.config.library_channels) + list(app.config.video_channels) if x["id"] == cid), None)
    if c is None:
        return
    if body.get("order") in dict(lc.ORDERS):
        c["order"], c["block"] = body["order"], 0
    if "hours" in body and body["hours"] in [k for k, _ in lc.HOURS]:
        c["hours"] = body["hours"]
    if "breaks" in body and bool(body["breaks"]) != bool(lc.breaks_of(c, app.library)):
        if body["breaks"]:
            c.pop("breaks", None)
            if not lc.breaks_of(c, app.library) and app.library:
                c["breaks"] = lc.default_breaks(c, app.library)
        else:
            c["breaks"] = {}
    if body.get("mid") in dict(lc.MIDS) and lc.breaks_of(c, app.library):
        c["breaks"] = dict(lc.breaks_of(c, app.library), mid=body["mid"])
    c["starter"] = False
    app.config.save()
    lc.place(app)


# ── For other apps ───────────────────────────────────────────────────────

def timeline_channels(app) -> list:
    """The channels another app can be given: the library channels (their
    programmes are files on your Plex server)."""
    from . import libchannels as lc
    return [ch for ch in app.channels if lc.is_library(ch)]


def m3u(app, base: str) -> str:
    from . import videochannels as vc
    out = ["#EXTM3U"]
    for ch in timeline_channels(app):
        cid = vc.cid_of(ch)
        out.append(f'#EXTINF:-1 tvg-id="{escape(ch.epg_id)}" tvg-chno="{ch.number:g}" tvg-name="{escape(ch.name)}" '
                   f'group-title="Cathode",{ch.name}')
        out.append(f"{base}/stream/{cid}")
    return "\n".join(out) + "\n"


def xmltv(app) -> str:
    progs = getattr(app, "video_programmes", {}) or {}
    chans = timeline_channels(app)
    out = ['<?xml version="1.0" encoding="UTF-8"?>', '<tv generator-info-name="Cathode">']
    for ch in chans:
        out.append(f'  <channel id="{escape(ch.epg_id)}"><display-name>{escape(ch.name)}</display-name></channel>')
    fmt = "%Y%m%d%H%M%S %z"
    for ch in chans:
        for p in progs.get(ch.epg_id, []):
            out.append(f'  <programme channel="{escape(ch.epg_id)}" start="{p.start.strftime(fmt)}" '
                       f'stop="{p.stop.strftime(fmt)}"><title>{escape(p.title)}</title>'
                       + (f"<desc>{escape(p.description)}</desc>" if p.description else "")
                       + (f"<category>{escape(p.category)}</category>" if p.category else "")
                       + (f'<icon src="{escape(p.icon)}"/>' if p.icon else "") + "</programme>")
    out.append("</tv>")
    return "\n".join(out) + "\n"


def hdhr(app, base: str, what: str):
    from . import videochannels as vc
    if what == "discover":
        return {"FriendlyName": "Cathode", "Manufacturer": "Cathode", "ModelNumber": "HDTC-2US",
                "FirmwareName": "hdhomeruntc_atsc", "FirmwareVersion": "20200101",
                "DeviceID": (app.config.sync_id or "cathode00")[:8].upper(), "DeviceAuth": "cathode",
                "BaseURL": base, "LineupURL": f"{base}/lineup.json", "TunerCount": 4}
    if what == "status":
        return {"ScanInProgress": 0, "ScanPossible": 0, "Source": "Cable", "SourceList": ["Cable"]}
    return [{"GuideNumber": f"{ch.number:g}", "GuideName": ch.name, "URL": f"{base}/stream/{vc.cid_of(ch)}"}
            for ch in timeline_channels(app)]


def stream_url(app, cid: str):
    """Where another app's player goes for a channel now: the programme on
    the air through Plex's transcoder, from where it's up to (the token in
    the address: the player can't send it otherwise). None off the air."""
    from . import libchannels as lc
    tl = lc.SCHEDULES.get(cid)
    cur = tl.at(datetime.now(timezone.utc)) if tl is not None else None
    if not cur or not str(cur["entry"].get("plex", ""))[:1].isdigit():
        return None                     # (Plex's titles only: its transcoder starts where the programme's up to)
    e = cur["entry"]
    c = app.ondemand.client()
    if not c.server:
        c.discover_server(prefer=app.config.plex_server_id)
    quality = app.config.plex_quality if app.config.plex_quality != "Original" else "1080p (20 Mbps)"
    s = c.stream_at(e["plex"], quality, cur["offset"] + e.get("in", 0))
    tok = (s.get("headers") or {}).get("X-Plex-Token", "")
    return s["video"] + (("&" if "?" in s["video"] else "?") + "X-Plex-Token=" + tok if tok else "")


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cathode</title>
<style>
:root{--bg:#0b1020;--panel:#151c33;--ink:#e8ecff;--dim:#9aa4c8;--key:#222c4f;--hot:#f0b429;--line:#2a3560}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px system-ui,sans-serif}
header{display:flex;gap:8px;padding:12px 16px;border-bottom:1px solid var(--line);align-items:center;flex-wrap:wrap}
header b{flex:1;font-size:18px}nav button{background:none;border:0;color:var(--dim);font-size:15px;padding:6px 10px}
nav button.on{color:var(--hot);border-bottom:2px solid var(--hot)}
main{padding:16px;max-width:720px;margin:0 auto}.pad{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;max-width:360px;margin:0 auto}
.pad button,.row button{background:var(--key);color:var(--ink);border:1px solid var(--line);border-radius:12px;padding:16px 8px;font-size:16px}
.pad button:active,.row button:active{background:var(--hot);color:#000}.row{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;max-width:360px;margin:12px auto}
.ch{display:flex;gap:12px;padding:10px 4px;border-bottom:1px solid var(--line);align-items:baseline;cursor:pointer}
.ch .n{min-width:3.5em;color:var(--hot);font-weight:600}.ch .t{flex:1}.ch small{display:block;color:var(--dim)}
.ch.on{background:var(--panel)}input,select{background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:6px;font-size:15px;max-width:100%}
.ed{display:grid;grid-template-columns:4.5em 1fr auto;gap:8px;align-items:center;padding:8px 0;border-bottom:1px solid var(--line)}
.mc{padding:10px 0;border-bottom:1px solid var(--line)}.mc b{display:block;margin-bottom:6px}.mc label{display:inline-block;margin:4px 12px 4px 0;color:var(--dim)}
#on{color:var(--dim);font-size:14px}
</style></head><body>
<header><b>Cathode</b><span id="on"></span><nav>
<button data-tab="remote" class="on">Remote</button><button data-tab="channels">Channels</button>
<button data-tab="lineup">Lineup</button><button data-tab="made">My channels</button></nav></header>
<main>
<section id="remote">
<div class="row"><button data-k="guide">Guide</button><button data-k="menu">Menu</button><button data-k="info">Info</button><button data-k="options">Options</button></div>
<div class="pad"><span></span><button data-k="up">&#9650;</button><span></span>
<button data-k="left">&#9664;</button><button data-k="ok">OK</button><button data-k="right">&#9654;</button>
<span></span><button data-k="down">&#9660;</button><span></span></div>
<div class="row"><button data-k="back">Back</button><button data-k="last">Last</button><button data-k="chup">CH +</button><button data-k="chdown">CH &minus;</button></div>
<div class="row"><button data-k="voldown">Vol &minus;</button><button data-k="volup">Vol +</button><button data-k="mute">Mute</button><button data-k="pause">&#10074;&#10074;</button></div>
</section>
<section id="channels" hidden></section>
<section id="lineup" hidden></section>
<section id="made" hidden></section>
</main>
<script>
let S=null;const $=s=>document.querySelector(s);
const post=b=>fetch('/api/do',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
document.querySelectorAll('[data-k]').forEach(b=>b.onclick=()=>post({do:'key',key:b.dataset.k}));
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{document.querySelectorAll('nav button').forEach(x=>x.classList.toggle('on',x===b));
 document.querySelectorAll('main section').forEach(s=>s.hidden=s.id!==b.dataset.tab);});
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function draw(){if(!S)return;$('#on').textContent=S.on?`On ${S.on.number} ${S.on.name}`:'';
 $('#channels').innerHTML=S.channels.map(c=>`<div class="ch${S.on&&S.on.number==c.number?' on':''}" data-n="${c.number}"><span class="n">${c.number}</span><span class="t">${esc(c.name)}
 <small>${c.now?esc(c.now.title)+' &middot; until '+c.now.stop:'&nbsp;'}</small><small>${c.next?'Next '+c.next.start+' '+esc(c.next.title):''}</small></span></div>`).join('');
 document.querySelectorAll('.ch').forEach(d=>d.onclick=()=>post({do:'tune',number:d.dataset.n}).then(load));}
function lineup(){if(!S)return;$('#lineup').innerHTML='<p>Hide, rename or renumber (10.5 is fine). Saved as you leave each box.</p>'+S.channels.concat(S.hidden||[]).map(c=>{const e=S.edits[c.url]||{};
 return `<div class="ed" data-u="${esc(c.url)}"><input class="num" value="${e.number??c.number}"><input class="nm" value="${esc(e.name??c.name)}"><label><input type="checkbox" class="hd"${e.hide?' checked':''}> hide</label></div>`}).join('');
 document.querySelectorAll('.ed').forEach(d=>{const u=d.dataset.u;d.querySelector('.num').onchange=e=>post({do:'edit',url:u,number:e.target.value});
 d.querySelector('.nm').onchange=e=>post({do:'edit',url:u,name:e.target.value});d.querySelector('.hd').onchange=e=>post({do:'edit',url:u,hide:e.target.checked});});}
function made(){if(!S)return;$('#made').innerHTML=(S.made||[]).map(c=>`<div class="mc" data-id="${c.id}"><b>${esc(c.name||'(unnamed)')} <small>${c.kind}</small></b>
 <label>Sort <select class="o">${c.orders.map(([k,l])=>`<option value="${k}"${k==c.order?' selected':''}>${l}</option>`).join('')}</select></label>
 <label>On the air <select class="h">${c.hourses.map(([k,l],i)=>`<option value="${i}"${JSON.stringify(k)==JSON.stringify(c.hours)?' selected':''}>${l}</option>`).join('')}</select></label>
 <label><input type="checkbox" class="b"${c.breaks?' checked':''}> breaks</label>
 <label>During programmes <select class="m">${c.mids.map(([k,l])=>`<option value="${k}"${k==c.mid?' selected':''}>${l}</option>`).join('')}</select></label></div>`).join('')||'<p>No library or YouTube channels yet.</p>';
 document.querySelectorAll('.mc').forEach(d=>{const id=d.dataset.id,c=S.made.find(x=>x.id==id);
 d.querySelector('.o').onchange=e=>post({do:'channel',id,order:e.target.value});d.querySelector('.h').onchange=e=>post({do:'channel',id,hours:c.hourses[e.target.value][0]});
 d.querySelector('.b').onchange=e=>post({do:'channel',id,breaks:e.target.checked});d.querySelector('.m').onchange=e=>post({do:'channel',id,mid:e.target.value});});}
let drawn=false;function load(){fetch('/api/state').then(r=>r.json()).then(s=>{S=s;draw();if(!drawn){lineup();made();drawn=true;}});}
load();setInterval(load,20000);
</script></body></html>
"""
