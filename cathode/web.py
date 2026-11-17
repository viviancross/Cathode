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
            out.append({"kind": kind, "id": c["id"], "name": c.get("name") or "", "raw": c, "order": c.get("order") or
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
    if what == "channel_json":
        try:
            new = json.loads(body.get("json") or "")
        except ValueError as e:
            return f"not JSON: {e}"
        if not isinstance(new, dict):
            return "not a channel"
        app.post(_channel_json, app, str(body.get("id", "")), new)
        return "ok"
    if what == "import":
        return import_doc(app, body.get("doc"), "replace" if body.get("mode") == "replace" else "merge")
    return "not understood"


def _channel_json(app, cid, new):
    """A channel's whole settings, as the browser's editor sent them (its id kept)."""
    from . import libchannels as lc
    for lst in (app.config.library_channels, app.config.video_channels):
        for n, c in enumerate(lst):
            if c["id"] == cid:
                new["id"] = cid
                lst[n] = new
                app.config.save()
                lc.place(app)
                app.place_own_channels()
                return


# ── Export and import ────────────────────────────────────────────────────

EXPORTED = ("library_channels", "video_channels", "content_groups", "channel_edits", "packs", "stream_channels",
            "own_channels")


def export(app) -> dict:
    """The channels as a file another Cathode (or this one, later) takes in:
    library and YouTube channels, content groups, the lineup's edits, packs,
    stream channels. No tokens, no accounts."""
    from . import __version__
    cfg = app.config
    return {"cathode": "channels", "v": 1, "version": __version__,
            **{k: json.loads(json.dumps(getattr(cfg, k, None) or ({} if k in ("channel_edits", "own_channels") else [])))
               for k in EXPORTED}}


def import_doc(app, doc: dict, mode: str = "merge") -> str:
    """Channels taken in from export(): "replace" swaps every list for the
    file's; "merge" adds the file's, one with the same id (a group, a
    channel) or name (a pack) taking the place of what's here."""
    if not isinstance(doc, dict) or doc.get("cathode") != "channels":
        return "not a Cathode channels file"
    cfg = app.config
    n = 0
    for k in EXPORTED:
        theirs = doc.get(k)
        if theirs is None:
            continue
        mine = getattr(cfg, k)
        if isinstance(mine, dict):
            if not isinstance(theirs, dict):
                continue
            setattr(cfg, k, dict(theirs) if mode == "replace" else dict(mine, **theirs))
            n += len(theirs)
            continue
        if not isinstance(theirs, list):
            continue
        if mode == "replace":
            setattr(cfg, k, [x for x in theirs if isinstance(x, dict)])
        else:
            key = "name" if k == "packs" else "url" if k == "stream_channels" else "id"
            have = {x.get(key): i for i, x in enumerate(mine)}
            for x in theirs:
                if not isinstance(x, dict):
                    continue
                if x.get(key) in have:
                    mine[have[x[key]]] = x
                else:
                    mine.append(x)
        n += len(theirs)
    cfg.save()
    from . import libchannels as lc
    app.post(lambda: (app.place_own_channels(), lc.place(app), app.relineup()))
    return f"{n} taken in ({mode})"


# ── What's playing on the servers; the log ───────────────────────────────

def sessions(app) -> list:
    """Plex's dashboard: who is watching what, where, how far through."""
    od = getattr(app, "ondemand", None)
    if od is None or not getattr(od, "signed_in", False):
        return []
    c = od.client()
    if not c.server:
        c.discover_server(prefer=app.config.plex_server_id)
    d = c._get(f"{c.server}/status/sessions", token=c.admin_token or c._server_token)
    out = []
    for m in (d.get("MediaContainer") or {}).get("Metadata") or []:
        title = m.get("title", "")
        if m.get("grandparentTitle"):
            title = f"{m['grandparentTitle']}: {title}"
        dur, off = int(m.get("duration") or 0), int(m.get("viewOffset") or 0)
        out.append({"title": title, "user": (m.get("User") or {}).get("title", ""),
                    "player": (m.get("Player") or {}).get("title") or (m.get("Player") or {}).get("product", ""),
                    "state": (m.get("Player") or {}).get("state", ""), "progress": round(100 * off / dur) if dur else 0,
                    "transcode": "TranscodeSession" in m})
    return out


def log_tail(lines: int = 400) -> str:
    """The end of cathode.log, tokens and keys blanked."""
    import os
    import re
    from . import paths
    try:
        with open(os.path.join(paths.cache_dir(), "cathode.log"), encoding="utf-8", errors="replace") as f:
            text = "".join(f.readlines()[-lines:])
    except OSError:
        return "(no log yet)"
    return re.sub(r"(?i)((?:x-plex-token|token|api_key|key)[=:]\s*)[A-Za-z0-9_\-]{8,}", r"\1<hidden>", text)


# ── The API for other things (Home Assistant) ────────────────────────────

def api_ok(app, headers, query) -> bool:
    """A request to /api/v1 carries the API key (Authorization: Bearer, or
    X-Api-Key, or ?key=); with no key set, that API is off."""
    import hmac
    want = getattr(app.config, "api_key", "")
    if not want:
        return False
    got = (headers.get("Authorization") or "").removeprefix("Bearer ").strip() or headers.get("X-Api-Key") or \
        (query.get("key") or [""])[0]
    return hmac.compare_digest(str(got), want)


def api_v1(app, path: str, query: dict):
    """/api/v1/state | /now | /channels | /tune?number= | /key?k= | /volume?level= -> (code, body)."""
    live = getattr(app, "live", None)
    on = live.channel if live is not None else None
    if path == "/api/v1/state":
        cur = live.programs()[0] if live is not None and on is not None and live.programs() else None
        return 200, {"channel": {"number": on.number, "name": on.name} if on else None,
                     "programme": {"title": cur.title, "episode": cur.episode} if cur else None,
                     "volume": app.video.volume, "muted": app.video.muted, "paused": bool(app.video.paused)}
    if path == "/api/v1/channels":
        return 200, [{"number": c.number, "name": c.name} for c in app.channels]
    if path == "/api/v1/now":
        return 200, state(app)["channels"]
    if path == "/api/v1/tune":
        try:
            number = float((query.get("number") or [""])[0])
        except ValueError:
            return 400, {"error": "number"}
        app.post(_tune, app, number)
        return 200, {"ok": True}
    if path == "/api/v1/key":
        key = KEYS.get((query.get("k") or [""])[0])
        if key is None:
            return 400, {"error": "keys: " + ", ".join(KEYS)}
        app.post(app.press, key)
        return 200, {"ok": True}
    if path == "/api/v1/volume":
        try:
            level = int((query.get("level") or [""])[0])
        except ValueError:
            return 400, {"error": "level"}
        app.post(lambda: setattr(app.video, "volume", max(0, min(100, level))))
        return 200, {"ok": True}
    return 404, {"error": "not found"}


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
        out.append(f"{base}/live/{cid}.ts" if getattr(app.config, "broadcast_stream", False) else f"{base}/stream/{cid}")
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
    live = getattr(app.config, "broadcast_stream", False)
    return [{"GuideNumber": f"{ch.number:g}", "GuideName": ch.name,
             "URL": f"{base}/live/{vc.cid_of(ch)}.ts" if live else f"{base}/stream/{vc.cid_of(ch)}"}
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
<button data-tab="lineup">Lineup</button><button data-tab="made">My channels</button>
<button data-tab="playing">Now playing</button><button data-tab="log">Log</button><button data-tab="admin">Admin</button></nav></header>
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
<section id="playing" hidden><p>What your Plex server is playing, everywhere.</p><div id="sess"></div></section>
<section id="log" hidden><button id="relog">Refresh</button><pre id="logtext" style="white-space:pre-wrap;font-size:12px"></pre></section>
<section id="admin" hidden><h3>Export and import</h3><p><a href="/api/export" download="cathode-channels.json">Download your channels</a>
(library and YouTube channels, groups, lineup edits, packs).</p>
<p><input type="file" id="imp" accept=".json"> <select id="impmode"><option value="merge">Merge</option><option value="replace">Replace</option></select>
<button id="impgo">Import</button> <span id="impsaid"></span></p>
<h3>API</h3><p>Home Assistant and scripts: <code>/api/v1/state</code>, <code>/api/v1/tune?number=</code>, <code>/api/v1/key?k=</code>,
<code>/api/v1/volume?level=</code>, <code>/api/v1/channels</code>, with the key from Settings &gt; Admin &gt; API key as
<code>Authorization: Bearer &lt;key&gt;</code>.</p>
<h3>Streams for other apps</h3><p><a href="/lineup.m3u">lineup.m3u</a> &middot; <a href="/xmltv.xml">xmltv.xml</a> &middot;
with Continuous Streams on (Settings &gt; Admin), each channel continuous, breaks and all, at <code>/live/&lt;channel&gt;.ts</code>.</p></section>
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
function sess(){fetch('/api/sessions').then(r=>r.json()).then(l=>{$('#sess').innerHTML=l.map(s=>`<div class="ch"><span class="t">${esc(s.title)}
 <small>${esc(s.user)} on ${esc(s.player)} &middot; ${esc(s.state)} &middot; ${s.progress}%${s.transcode?' &middot; transcoding':''}</small></span></div>`).join('')||'<p>Nothing playing.</p>';});}
function logs(){fetch('/api/log').then(r=>r.text()).then(t=>{$('#logtext').textContent=t;});}
$('#relog').onclick=logs;
$('#impgo').onclick=()=>{const f=$('#imp').files[0];if(!f)return;f.text().then(t=>{let d;try{d=JSON.parse(t)}catch(e){$('#impsaid').textContent='not JSON';return}
 post({do:'import',doc:d,mode:$('#impmode').value}).then(r=>r.json()).then(j=>{$('#impsaid').textContent=j.said;load();});});};
document.querySelector('[data-tab=playing]').addEventListener('click',sess);document.querySelector('[data-tab=log]').addEventListener('click',logs);
function editors(){document.querySelectorAll('.mc').forEach(d=>{if(d.querySelector('textarea'))return;const c=S.made.find(x=>x.id==d.dataset.id);
 const t=document.createElement('details');t.innerHTML=`<summary>Everything (JSON)</summary><textarea rows="14" style="width:100%;font:12px monospace">${esc(JSON.stringify(c.raw,null,1))}</textarea><button>Save</button> <span></span>`;
 t.querySelector('button').onclick=()=>post({do:'channel_json',id:c.id,json:t.querySelector('textarea').value}).then(r=>r.json()).then(j=>{t.querySelector('span').textContent=j.said;});
 d.appendChild(t);});}
let drawn=false;function load(){fetch('/api/state').then(r=>r.json()).then(s=>{S=s;draw();if(!drawn){lineup();made();editors();drawn=true;}});}
load();setInterval(load,20000);
</script></body></html>
"""
