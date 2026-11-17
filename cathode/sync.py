"""Channels kept the same on every Cathode on the network.

Each Cathode with sync on says hello on the local network every few seconds
(a UDP broadcast) and answers a few read-only questions over HTTP: its
channel lists, each library channel's written-down schedule, the YouTube
lists its video channels were drawn from. Every Cathode asks the others
and takes what's newer, so tuning to the same channel on the PC and on the
Deck shows the same programme at the same point (the clocks are the
computers' own, kept right by the internet).

What's newer, per thing:
- The channel lists (library, video and Cathode's own channels' places):
  the last edited, anywhere. A Cathode that's never been edited takes any
  other's; between two never edited, the one with the higher id wins.
- A library channel's schedule: the oldest schedule of that channel's line
  (the first drawn up, anywhere), then the most worked on (days drawn,
  titles skipped). A title one Cathode skipped and another hadn't is
  skipped on both.
- A YouTube source's list: the most recently fetched.

Nothing secret goes over: no Plex token, no provider password. Nothing is
taken from the network without its shape being checked first."""

from __future__ import annotations

import hashlib
import json
import socket
import threading
import time
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

PORT = 47810                    # the hello (UDP) and the questions (HTTP)
V = 1                           # what's said; a Cathode saying something else is left alone
HELLO = 5.0                     # seconds between hellos
GONE = 20.0                     # a Cathode not heard from this long is gone
ASK = 10.0                      # seconds between asking each one what it has
TICK = 5.0                      # the local picture of things, brought up to date this often
MAX_BYTES = 32 * 1024 * 1024    # an answer bigger than this isn't read
TIMEOUT = 4.0

ME = ""                         # this Cathode's id (config.sync_id), for libchannels' schedules


def channels_digest(cfg) -> str:
    return hashlib.sha1(json.dumps([cfg.library_channels, cfg.video_channels, cfg.own_channels,
                                    getattr(cfg, "content_groups", []), getattr(cfg, "channel_edits", {}),
                                    getattr(cfg, "packs", [])], sort_keys=True).encode()).hexdigest()[:16]


def channels_key(edited: float, editor: str) -> tuple:
    return (float(edited or 0), str(editor or ""))


def _is_channels(d) -> bool:
    """A channel list as another Cathode sends it, its shape checked."""
    if not isinstance(d, dict):
        return False
    lib, vid, own = d.get("library_channels"), d.get("video_channels"), d.get("own_channels")
    if not (isinstance(lib, list) and isinstance(vid, list) and isinstance(own, dict)):
        return False
    for c in lib + vid:
        if not (isinstance(c, dict) and isinstance(c.get("id"), str) and isinstance(c.get("sources", []), list)):
            return False
    return isinstance(d.get("edited", 0), (int, float)) and isinstance(d.get("editor", ""), str)


def _is_listing(d) -> bool:
    return (isinstance(d, dict) and isinstance(d.get("entries"), list) and isinstance(d.get("fetched", 0), (int, float))
            and all(isinstance(e, dict) and isinstance(e.get("id"), str) for e in d["entries"]))


class Sync:
    def __init__(self, app):
        global ME
        self.app = app
        cfg = app.config
        if not cfg.sync_id:
            cfg.sync_id = uuid.uuid4().hex[:12]
            cfg.save()
        ME = self.me = cfg.sync_id
        self.name = socket.gethostname() or "Cathode"
        self.peers: dict = {}           # id -> {"ip", "port", "name", "seen"}
        self.snapshot = b"{}"           # what this Cathode has, as told to the others
        self._digest = channels_digest(cfg)
        self._stop = threading.Event()
        self._http = None
        self.port = 0
        self._udp = None
        self._timer = None

    # ── Starting and stopping ─────────────────────────────────────────────

    def serve(self, *ports, host: str = "0.0.0.0") -> bool:
        """The questions answered over HTTP, on the first of `ports` free."""
        handler = type("Handler", (_Handler,), {"sync": self})
        for port in ports:
            try:
                self._http = ThreadingHTTPServer((host, port), handler)
                break
            except OSError as e:
                print(f"[sync] port {port}: {e!r}")
        if self._http is None:
            return False
        self._http.daemon_threads = True
        self.port = self._http.server_address[1]
        threading.Thread(target=self._http.serve_forever, daemon=True).start()
        return True

    def start(self):
        self._stop.clear()
        if not self.serve(PORT, 0):         # (the port taken: another one, said in the hello)
            return
        if not self.app.config.lan_sync:    # (serving the web page alone)
            self.tick()
            print(f"[web] on port {self.port}")
            return
        try:
            u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            u.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            u.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            u.bind(("", PORT))
            u.settimeout(1.0)
            self._udp = u
            threading.Thread(target=self._hellos, daemon=True).start()
        except OSError as e:
            print(f"[sync] no hellos on the network ({e!r})")
        threading.Thread(target=self._asking, daemon=True).start()
        self.tick()
        print(f"[sync] on: {self.name} ({self.me}), port {self.port}")

    def stop(self):
        self._stop.set()
        self.app.cancel(self._timer)
        if self._http is not None:
            threading.Thread(target=self._http.shutdown, daemon=True).start()
            self._http = None
        if self._udp is not None:
            try:
                self._udp.close()
            except OSError:
                pass
            self._udp = None
        self.peers.clear()

    def others(self) -> list:
        now = time.monotonic()
        return [p for p in self.peers.values() if now - p["seen"] < GONE]

    # ── On the UI thread: what this Cathode has, and its own edits ────────

    def tick(self):
        """Every few seconds: an edit made here stamped (so it's the newest
        anywhere), and the picture the others ask for brought up to date."""
        self.app.cancel(self._timer)
        if self._stop.is_set():
            return
        cfg = self.app.config
        d = channels_digest(cfg)
        if d != self._digest:
            self._digest = d
            cfg.channels_edited, cfg.channels_editor = time.time(), self.me
            cfg.save()
            print("[sync] channels edited here")
        self.snapshot = json.dumps(self.state()).encode()
        self._timer = self.app.after(TICK, self.tick)

    def quiet(self):
        """A change made by Cathode itself (the starter lineup, another
        Cathode's lists taken): not an edit."""
        self._digest = channels_digest(self.app.config)

    def state(self) -> dict:
        from . import libchannels as lc
        cfg = self.app.config
        return {"cathode": "sync", "v": V, "id": self.me, "name": self.name,
                "channels": [cfg.channels_edited, cfg.channels_editor, self._digest],
                "schedules": {cid: tl.version() for cid, tl in list(lc.SCHEDULES.items())},
                "listings": {u: float(l.get("fetched", 0)) for u, l in list(getattr(self.app, "listings", {}).items())
                             if isinstance(l, dict)}}

    def channels_doc(self) -> dict:
        cfg = self.app.config
        return {"edited": cfg.channels_edited, "editor": cfg.channels_editor or "",
                "library_channels": cfg.library_channels, "video_channels": cfg.video_channels,
                "own_channels": cfg.own_channels, "content_groups": getattr(cfg, "content_groups", []),
                "channel_edits": getattr(cfg, "channel_edits", {}), "packs": getattr(cfg, "packs", [])}

    # ── Hellos ────────────────────────────────────────────────────────────

    def hello(self) -> bytes:
        return json.dumps({"cathode": "sync", "v": V, "id": self.me, "name": self.name, "port": self.port}).encode()

    def heard(self, data: bytes, ip: str):
        try:
            d = json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return
        if not isinstance(d, dict) or d.get("cathode") != "sync" or d.get("v") != V:
            return
        pid, port = d.get("id"), d.get("port")
        if not isinstance(pid, str) or pid == self.me or not isinstance(port, int) or not 0 < port < 65536:
            return
        new = pid not in self.peers
        self.peers[pid] = {"id": pid, "ip": ip, "port": port, "name": str(d.get("name", ""))[:64],
                           "seen": time.monotonic()}
        if new:
            print(f"[sync] found {self.peers[pid]['name']} at {ip}:{port}")

    def _hellos(self):
        last = 0.0
        while not self._stop.is_set() and self._udp is not None:
            if time.monotonic() - last >= HELLO:
                last = time.monotonic()
                try:
                    self._udp.sendto(self.hello(), ("255.255.255.255", PORT))
                except OSError:
                    pass
            try:
                data, (ip, _port) = self._udp.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                return
            self.heard(data, ip)

    # ── Asking the others ─────────────────────────────────────────────────

    def _get(self, peer: dict, path: str):
        url = f"http://{peer['ip']}:{peer['port']}{path}"
        with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
            raw = r.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("too big")
        return json.loads(raw.decode("utf-8"))

    def _asking(self):
        while not self._stop.wait(ASK):
            for peer in self.others():
                try:
                    self.ask(peer)
                except Exception as e:
                    print(f"[sync] {peer['name']}: {e!r}")

    def ask(self, peer: dict):
        """What one other Cathode has that's newer, fetched; taken in on the UI thread."""
        st = self._get(peer, "/cathode/sync")
        if not isinstance(st, dict) or st.get("v") != V or st.get("id") != peer["id"]:
            return
        mine = json.loads(self.snapshot.decode("utf-8") or "{}")
        ch = st.get("channels")
        if isinstance(ch, list) and len(ch) == 3 and mine.get("channels"):
            theirs = channels_key(ch[0], ch[1] or peer["id"])
            here = channels_key(mine["channels"][0], mine["channels"][1] or self.me)
            if theirs > here and ch[2] != mine["channels"][2]:
                doc = self._get(peer, "/cathode/channels")
                if _is_channels(doc):
                    self.app.post(self.take_channels, peer, doc)
        from . import libchannels as lc
        for cid, ver in (st.get("schedules") or {}).items():
            here = (mine.get("schedules") or {}).get(cid)
            if here and isinstance(ver, dict) and lc.beats(ver, here):
                doc = self._get(peer, "/cathode/schedule?" + urllib.parse.urlencode({"id": cid}))
                self.app.post(self.take_schedule, peer, cid, doc)
        wanted = self.wanted_sources()
        for url, fetched in (st.get("listings") or {}).items():
            if url in wanted and isinstance(fetched, (int, float)) and \
                    fetched > (mine.get("listings") or {}).get(url, 0) + 60:
                doc = self._get(peer, "/cathode/listing?" + urllib.parse.urlencode({"url": url}))
                if _is_listing(doc):
                    self.app.post(self.take_listing, peer, url, doc)

    def wanted_sources(self) -> set:
        out = set()
        for c in list(self.app.config.video_channels or []):
            for s in c.get("sources") or []:
                out.add(s.get("url"))
                out.add(f"{s.get('url')}#live")
        return out

    # ── Taking things in (UI thread) ──────────────────────────────────────

    def take_channels(self, peer: dict, doc: dict):
        from . import libchannels as lc, videochannels as vc
        cfg = self.app.config
        if channels_key(doc.get("edited"), doc.get("editor") or peer["id"]) <= \
                channels_key(cfg.channels_edited, cfg.channels_editor or self.me):
            return                                  # an edit here since
        cfg.library_channels = doc["library_channels"]
        cfg.video_channels = [vc.fix(c) for c in doc["video_channels"]]
        cfg.own_channels = doc["own_channels"]
        if isinstance(doc.get("channel_edits"), dict):
            cfg.channel_edits = {k: v for k, v in doc["channel_edits"].items() if isinstance(v, dict)}
        if isinstance(doc.get("packs"), list):
            cfg.packs = [p for p in doc["packs"] if isinstance(p, dict) and isinstance(p.get("name"), str)]
        if isinstance(doc.get("content_groups"), list):
            cfg.content_groups = [g for g in doc["content_groups"] if isinstance(g, dict) and isinstance(g.get("id"), str)]
        cfg.channels_edited, cfg.channels_editor = float(doc.get("edited") or 0), doc.get("editor") or peer["id"]
        cfg.library_starter_done = True             # (theirs stands in for a starter lineup of our own)
        cfg.save()
        self.quiet()
        print(f"[sync] channels taken from {peer['name']}")
        lc.place(self.app)
        self.app.toast(f"Channels brought in line with {peer['name']}.", 5.0)

    def take_schedule(self, peer: dict, cid: str, doc):
        from . import libchannels as lc, videochannels as vc
        tl = lc.SCHEDULES.get(cid)
        if tl is None or not tl.adopt(doc):
            return
        print(f"[sync] {tl.c.get('name')}: schedule taken from {peer['name']}")
        if tl.unknown() and cid.startswith(lc.PREFIX):
            from . import library
            library.load(self.app, lambda idx, err: lc.place(self.app))    # titles this one hasn't read yet
        # (a video channel's: the newer list comes over by itself)
        vc.rebuild(self.app)
        live = getattr(self.app, "live", None)
        p = getattr(live, "vplayer", None) if live else None
        if p is not None and p.cid == cid:
            from datetime import datetime, timezone
            now = tl.at(datetime.now(timezone.utc))
            if now and (p.cur is None or p.cur["entry"]["id"] != now["entry"]["id"]):
                p.start()                           # something else is on now: join it

    def take_listing(self, peer: dict, url: str, doc: dict):
        from . import videochannels as vc, ytdl
        have = getattr(self.app, "listings", {}).get(url) or {}
        if doc.get("fetched", 0) <= have.get("fetched", 0):
            return
        ytdl.keep_listing(url, doc)
        print(f"[sync] {doc.get('title') or url}: list taken from {peer['name']}")
        vc._source_loaded(self.app, url, doc)


class _Handler(BaseHTTPRequestHandler):
    sync: Sync = None

    def log_message(self, *a):
        pass

    def _send(self, body: bytes, code: int = 200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _type(self, body: bytes, kind: str, code: int = 200):
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        from . import web
        s = self.sync
        u = urllib.parse.urlparse(self.path)
        if web.local(self.client_address[0]) and u.path.startswith("/api/v1/"):
            if not web.api_ok(s.app, self.headers, urllib.parse.parse_qs(u.query)):
                return self._send(b'{"error": "key"}', 401)
            code, body = web.api_v1(s.app, u.path, urllib.parse.parse_qs(u.query))
            return self._send(json.dumps(body).encode(), code)
        if not web.local(self.client_address[0]) or not s.app.config.web_remote or self.path != "/api/do":
            return self._send(b"{}", 403 if self.path == "/api/do" else 404)
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(min(n, 4 << 20)).decode("utf-8") or "{}")
        except ValueError:
            return self._send(b"{}", 400)
        said = web.act(s.app, body if isinstance(body, dict) else {})
        self._send(json.dumps({"said": said}).encode())

    def do_GET(self):
        from . import libchannels as lc, web
        s = self.sync
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        cfg = s.app.config
        if not web.local(self.client_address[0]):
            return self._send(b"{}", 403)
        try:
            if cfg.web_remote and u.path in ("/", "/index.html"):
                return self._type(web.PAGE.encode(), "text/html; charset=utf-8")
            if cfg.web_remote and u.path == "/api/state":
                return self._send(json.dumps(web.state(s.app)).encode())
            if cfg.web_remote and u.path == "/api/export":
                return self._type(json.dumps(web.export(s.app), indent=1).encode(), "application/json")
            if cfg.web_remote and u.path == "/api/sessions":
                return self._send(json.dumps(web.sessions(s.app)).encode())
            if cfg.web_remote and u.path == "/api/log":
                return self._type(web.log_tail().encode(), "text/plain; charset=utf-8")
            if u.path.startswith("/api/v1/"):
                if not web.api_ok(s.app, self.headers, q):
                    return self._send(b'{"error": "key"}', 401)
                code, body = web.api_v1(s.app, u.path, q)
                return self._send(json.dumps(body, default=str).encode(), code)
            if cfg.share_channels:
                base = f"http://{self.headers.get('Host') or web.my_address() + ':' + str(s.port)}"
                if u.path in ("/lineup.m3u", "/channels.m3u"):
                    return self._type(web.m3u(s.app, base).encode(), "audio/x-mpegurl")
                if u.path == "/xmltv.xml":
                    return self._type(web.xmltv(s.app).encode(), "application/xml")
                for name, what in (("/discover.json", "discover"), ("/lineup.json", "lineup"),
                                   ("/lineup_status.json", "status")):
                    if u.path == name:
                        return self._send(json.dumps(web.hdhr(s.app, base, what)).encode())
                if u.path.startswith("/live/") and u.path.endswith(".ts"):
                    if not getattr(cfg, "broadcast_stream", False):
                        return self._send(b"{}", 404)
                    from . import broadcast
                    tl = lc.SCHEDULES.get(urllib.parse.unquote(u.path[len("/live/"):-3]))
                    od = getattr(s.app, "ondemand", None)
                    if tl is None or od is None or not od.signed_in:
                        return self._send(b"{}", 404)
                    client = od.client()
                    if not client.server:
                        client.discover_server(prefer=cfg.plex_server_id)
                    self.send_response(200)
                    self.send_header("Content-Type", "video/mp2t")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    broadcast.stream(s.app, tl, self.wfile, client)
                    return
                if u.path.startswith("/stream/"):
                    to = web.stream_url(s.app, urllib.parse.unquote(u.path[len("/stream/"):]))
                    if not to:
                        return self._send(b"{}", 404)
                    self.send_response(302)
                    self.send_header("Location", to)
                    self.end_headers()
                    return
            if not cfg.lan_sync:
                return self._send(b"{}", 404)
            if u.path == "/cathode/sync":
                return self._send(s.snapshot)
            if u.path == "/cathode/channels":
                return self._send(json.dumps(s.channels_doc()).encode())
            if u.path == "/cathode/schedule":
                tl = lc.SCHEDULES.get((q.get("id") or [""])[0])
                if tl is not None:
                    return self._send(json.dumps(tl.doc()).encode())
            if u.path == "/cathode/listing":
                lst = getattr(s.app, "listings", {}).get((q.get("url") or [""])[0])
                if lst:
                    return self._send(json.dumps(lst).encode())
        except Exception as e:                      # (a list changing as it's written out: ask again)
            print(f"[sync] answering {u.path}: {e!r}")
            return self._send(b"{}", 503)
        self._send(b"{}", 404)


def start(app) -> Optional[Sync]:
    """The server, for whichever of sync, the web page and sharing are on."""
    cfg = app.config
    if getattr(app, "sync", None) is not None or not (cfg.lan_sync or cfg.web_remote or cfg.share_channels):
        return getattr(app, "sync", None)
    app.sync = Sync(app)
    app.sync.start()
    return app.sync


def stop(app):
    s = getattr(app, "sync", None)
    if s is not None:
        s.stop()
        app.sync = None


def restart(app):
    """After sync, the web page or sharing is switched on or off."""
    stop(app)
    start(app)


def quiet(app):
    s = getattr(app, "sync", None)
    if s is not None:
        s.quiet()
