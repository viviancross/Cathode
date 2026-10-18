# ErsatzTV and Tunarr as Cathode sources

Research date: 2026-10-17. Current releases: ErsatzTV **v26.11.3** (2026-10-13), Tunarr **v2026.10.3** (2026-10-16). The user's own Tunarr (10.0.0.215:8000) reports `2026.10.1` and was probed read-only to confirm paths and shapes.

Goal: first-run asks for ONE base URL (scheme + host + port, optional path base), Cathode derives playlist + guide URLs and picks a stream mode that mpv plays reliably.

Legend: [src] = project source on GitHub `main`, [doc] = official docs, [mirror] = unofficial doc mirror, [issue] = GitHub issue/PR, [live] = probed on the user's Tunarr.

---

## 0. One-glance derivation table

| | ErsatzTV | Tunarr |
|---|---|---|
| Default port | `8409` (`ETV_UI_PORT`; `ETV_STREAMING_PORT` optional) | `8000` (`TUNARR_SERVER_PORT`) |
| Path base | `ETV_BASE_URL` (e.g. `/etv`) is honoured via `UsePathBase`; URLs in M3U/XMLTV include it | none |
| Detect + version | `GET {base}/api/version` → `{"apiVersion":3,"appVersion":"v26.11.3"}` (camelCase; `appVersion` from assembly informational version) | `GET {base}/api/version` → `{"tunarr":"2026.10.1","ffmpeg":"n8.1.2-etv.4","nodejs":"22.20.0"}` |
| M3U | `{base}/iptv/channels.m3u` (`?mode=mixed\|ts\|ts-legacy\|hls-direct\|segmenter`, `&access_token=`) | `{base}/api/channels.m3u` (`?forceHttps=1&hostOverride=host:port`) |
| XMLTV | `{base}/iptv/xmltv.xml` (`?access_token=`) | `{base}/api/xmltv.xml` |
| XMLTV channel id | `C{num}.{sum}.ersatztv.org` (+ `.{instanceId}` if `ETV_INSTANCE_ID` set); equals M3U `tvg-id` | `C{num}.{sum}.tunarr.com`; equals M3U `tvg-id` |
| Stream URL in M3U | `{base}/iptv/channel/{num}.m3u8?mode=segmenter` (or `.ts`, `.ts?mode=ts-legacy`, `.m3u8?mode=hls-direct`) | `{base}/stream/channels/{uuid}?streamMode={mode}` → 302 to `.m3u8?mode=` or `.ts?mode=` |
| Recommended mode for mpv | `segmenter` (HLS Segmenter); hybrid `ts` as fallback | `hls` (default); `hls_direct_v2` if no-transcode wanted; avoid `hls_direct` (reset per programme) and `mpegts` |
| HDHR discover | `{base}/discover.json` `FriendlyName:"ErsatzTV"` | `{base}/discover.json` `FriendlyName:"Tunarr"` |

Both servers require **no auth by default**. ErsatzTV can require a JWT `access_token` query param on IPTV routes; Tunarr can enable HTTP basic auth via env vars.

---

## 1. URL layout

### 1.1 ErsatzTV

**Port.** "By default, ErsatzTV listens on port **8409** for all requests." `ETV_UI_PORT` handles everything; `ETV_STREAMING_PORT` can split streaming onto a second port that "will block all management requests". [doc] https://ersatztv.org/docs/networking/ . Docker examples map `8409:8409`. [doc] https://ersatztv.org/docs/installation/docker

**Base path.** `Startup.cs` reads `SystemEnvironment.BaseUrl` (`ETV_BASE_URL`, must start with `/`) and calls `app.UsePathBase(baseUrl)`; `ForwardedHeaders.All` + `app.UseForwardedHeaders()` is on, so `X-Forwarded-Proto/Host` are honoured behind a proxy. [src] https://github.com/ErsatzTV/ErsatzTV/blob/main/ErsatzTV/Startup.cs

**Routes** (all `[HttpGet]` and `[HttpHead]`, under `ConditionalIptvAuthorizeFilter`): [src] https://github.com/ErsatzTV/ErsatzTV/blob/main/ErsatzTV/Controllers/IptvController.cs
- `GET /iptv/channels.m3u?mode={mixed|ts|ts-legacy|hls-direct|segmenter}[&access_token=]` — default `mixed` = each channel's configured mode. Handler passes `Request.Scheme`, `Request.Host`, `Request.PathBase`, UA, token to `GetChannelPlaylist`.
- `GET /iptv/xmltv.xml[?access_token=]` → `GetChannelGuide` with the same scheme/host/pathbase.
- `GET /iptv/channel/{n}.ts?mode={ts|ts-legacy|mixed}` — `video/mp2t`, ffmpeg stdout piped. 404 if channel missing/disabled. With `mixed`: channel mode TransportStream → `ts-legacy`, TransportStreamHybrid → `ts`, anything else → **302 to `/iptv/channel/{n}.m3u8`**. Next-engine channels: `ts-legacy` is upgraded to `ts`. `ts-legacy` logs "will be removed in ErsatzTV 26.12".
- `GET /iptv/channel/{n}.m3u8?mode={segmenter|segmenter-v2|segmenter-fmp4|hls-direct|mixed}&subtitles=true` — `application/vnd.apple.mpegurl`. With `mixed`: HttpLiveStreamingDirect → `hls-direct`, HttpLiveStreamingSegmenter → `segmenter`, else **302 to `.ts`**. Next-engine channels with a non-segmenter mode are forced to `segmenter`. Segmenter: starts (or joins) a session and returns the **multi-variant playlist**; if a session start fails → 404 with a warning.
- `GET /iptv/session/{n}/hls.m3u8` — the media playlist, "trimmed to 30 seconds ago"; if no worker exists it **302s to `/iptv/channel/{n}.m3u8`** to start one; 404 if trim fails. (A closed PR #2963 proposed 503 + `Retry-After: 1` instead of 404 because "404 tells a player the stream is gone"; not merged, "might no longer be needed after PR #3002". [issue] https://github.com/ErsatzTV/ErsatzTV/pull/2963)
- Segments are static files: the transcode folder is mounted at `/iptv/session` with `.m3u8`→`application/vnd.apple.mpegurl`, `.ts`→`video/mp2t`, `ServeUnknownFileTypes=true` for `.m4s`; every served file writes `TouchFFmpegSession(path)` (keeps the session alive). [src] Startup.cs
- `GET /iptv/hls-direct/{n}[.ts|.mkv|.mp4]?index=N` — the single item of HLS Direct mode.
- `GET /iptv/logos/{hex}[.jpg]`, `GET /iptv/logos/gen?text=...` — logos; `GET /iptv/artwork/{posters|thumbnails}/{path}.jpg` programme art.
- `GET /iptv/hdhr/channel/{n}.ts` — HDHR variant, forces `ts`.

**Multi-variant playlist** returned by `.m3u8?mode=segmenter`: `#EXTM3U`, `#EXT-X-VERSION:3`, one `#EXT-X-STREAM-INF:BANDWIDTH=...[,RESOLUTION=,CODECS=]` then `{Scheme}://{Host}{PathBase}/iptv/session/{n}/hls.m3u8{?access_token}`. [src] https://github.com/ErsatzTV/ErsatzTV/blob/main/ErsatzTV.Application/Streaming/Commands/StartFFmpegSessionHandler.cs

**M3U entry shape** (`ChannelPlaylist.ToM3U`): [src] https://github.com/ErsatzTV/ErsatzTV/blob/main/ErsatzTV.Core/Iptv/ChannelPlaylist.cs
```
#EXTM3U url-tvg="{scheme}://{host}{base}/iptv/xmltv.xml" x-tvg-url="...same..."
#EXTINF:0 tvg-id="C1.149.ersatztv.org" channel-id="{shortUniqueId}" channel-number="1" CUID="{shortUniqueId}" tvg-chno="1" tvg-name="Channel 1" tvg-logo="{scheme}://{host}{base}/iptv/logos/{artwork}.jpg" group-title="Entertainment" tvc-stream-vcodec="h264" tvc-stream-acodec="aac", Channel 1
{scheme}://{host}{base}/iptv/channel/1.m3u8?mode=segmenter
```
- Channels sorted numerically by `decimal.Parse(Number)`; numbers may have one decimal (`500.5`). [doc] https://ersatztv.org/docs/channels/
- `tvg-id` = `ChannelIdentifier.FromNumber(number)`; `channel-id`/`CUID` = URL-safe base64 of the channel GUID.
- `tvg-logo`: external `http(s)://` artwork passed through verbatim; local → `/iptv/logos/{path}.jpg`; none → `/iptv/logos/gen?text={urlencoded name}`.
- Stream URL per channel mode: Segmenter → `.m3u8?mode=segmenter`; Direct → `.m3u8?mode=hls-direct`; Hybrid → `.ts`; legacy → `.ts?mode=ts-legacy`. Scheme/host/pathbase come from the request, so the M3U "follows" whatever address Cathode used to fetch it.
- If the User-Agent starts with `kodi`, three `#KODIPROP:` lines (`inputstream=inputstream.ffmpegdirect`, `mimetype`, `open_mode=ffmpeg`) precede each entry. Cathode's UA should not start with "kodi".
- The doc-mirror example of the same format: [mirror] https://mintlify.wiki/ErsatzTV/ErsatzTV/streaming/iptv

**Channel id algorithm** (`ChannelIdentifier.FromNumber`): parse number as decimal ×100 to an int, sum `(digit + 48)` over its digits, produce `C{number}.{sum}[.{instanceId}].ersatztv.org`. Channel 5 → `C5.149.ersatztv.org`; `1.5` → `C1.5.150.ersatztv.org`. Legacy form `{number}.etv` is also written into programme data (`ChannelIdLegacy`). [src] https://github.com/ErsatzTV/ErsatzTV/blob/main/ErsatzTV.Core/Iptv/ChannelIdentifier.cs . The legacy mirror docs still describe `100.ersatztv.org` / `100.home.ersatztv.org` with `ETV_INSTANCE_ID`; trust the source. [mirror] https://mintlify.wiki/ErsatzTV/ErsatzTV/guides/epg-customization

**JSON API worth knowing:** `GET /api/version` (see §4), `GET /api/channels` (`GetAllChannelsForApi`), `GET /api/sessions` (active HLS sessions; fixed for Next engine in v26.10.0), `GET /api/ffmpeg/profiles`, etc. Controllers: https://github.com/ErsatzTV/ErsatzTV/tree/main/ErsatzTV/Controllers/Api . MVC JSON uses Newtonsoft with `CustomNamingStrategy : CamelCaseNamingStrategy`, so keys are camelCase. [src] https://github.com/ErsatzTV/ErsatzTV/blob/main/ErsatzTV/Serialization/CustomNamingStrategy.cs

### 1.2 Tunarr

**Port.** "listens on" `8000` by default (`TUNARR_SERVER_PORT=8000`, `TUNARR_BIND_ADDR=0.0.0.0`, `TUNARR_SERVER_TRUST_PROXY=false`, `TUNARR_SESSION_CLEANUP_DELAY_SECONDS=15`). [doc] https://tunarr.com/getting-started/run/ ; `DefaultServerSettings.port = 8000` [src] https://github.com/chrisbenincasa/tunarr/blob/main/types/src/SystemSettings.ts ; Fastify listens on `process.env.TUNARR_BIND_ADDR ?? '0.0.0.0'` and mounts `apiRouter` at `prefix: '/api'`, stream and HDHR routers at root. [src] https://github.com/chrisbenincasa/tunarr/blob/main/server/src/Server.ts . No path-base setting exists.

**Routes registered in `server/src/api/index.ts`** (under `/api`): [src] https://github.com/chrisbenincasa/tunarr/blob/main/server/src/api/index.ts
- `GET|HEAD /api/channels.m3u` → `text/plain`; `host = ${protocol}://${req.host}`, overridable with `?forceHttps=true` (protocol) and `?hostOverride=host[:port]`. `DELETE /api/channels.m3u` clears the cache.
- `GET|HEAD /api/xmltv.xml` → `application/xml`, `Cache-Control: no-store`; reads the on-disk file and replaces `{{host}}` with `${req.protocol}://${req.host}` (no override params).
- `GET /api/version` → `{ tunarr, ffmpeg }` (live server also returns `nodejs`).
- `GET /api/xmltv-last-refresh` → `{ value }` timestamp; `POST /api/xmltv/refresh`.
- `GET /api/ffmpeg-info`.
- Sub-routers: `/api/system/health`, `/api/system/state`, `/api/system/settings`, `/api/channels`, `/api/channels/:id` (UUID **or** channel number), `/api/channels/:id/now_playing`, `/api/channels/:id/lineup?from&to`, `/api/guide/channels`, `/api/sessions`, ... [src] systemApi.ts, channelsApi.ts, guideApi.ts in https://github.com/chrisbenincasa/tunarr/tree/main/server/src/api

**Docs discrepancy (verified live):** https://tunarr.com/configure/clients/ prints `http://your-tunarr-ip:8000/api/channels/m3u` and `/api/xmltv`. Those paths **404** on the user's 2026.10.1 server; `/api/channels.m3u` (200 `text`) and `/api/xmltv.xml` (200 `application/xml`) are real. No alias exists in `Server.ts` or `channelsApi.ts`. Use the dotted forms. [live]

**Stream routes** (`server/src/api/streamApi.ts`, mounted at root): [src] https://github.com/chrisbenincasa/tunarr/blob/main/server/src/api/streamApi.ts
- `GET /stream/channels/{idOrNumber}?streamMode=&token=` → **302** to `/stream/channels/{uuid}.m3u8?mode=...` for `hls|hls_slower|hls_direct|hls_direct_v2`, or to `.ts?mode=mpegts` for `mpegts`.
- `GET|HEAD /stream/channels/{id}.m3u8?mode=&variant=` — master playlist (`application/vnd.apple.mpegurl`); `variant=true` returns the media playlist directly. `mode=mpegts` → 400.
- `GET /stream/channels/{id}.ts?streamMode=&audioOnly=&token=` — continuous `video/MP2T` concat session (token generated if absent).
- `GET /stream/channels/{id}/{sessionType}/{file}` — HLS session files (segments `.ts`, `.vtt`, playlists). If the session is stopping/stopped → **404 "No session found"** so clients re-tune.
- `GET /stream/channels/{id}/item-stream.ts?t=` — finite TS of one lineup item (used by hls_direct-style playlists). `GET /streams/` static.

**M3U entry shape** (`M3UService`): [src] https://github.com/chrisbenincasa/tunarr/blob/main/server/src/services/M3UService.ts , confirmed [live]:
```
#EXTM3U url-tvg="http://10.0.0.215:8000/api/xmltv.xml" x-tvg-url="http://10.0.0.215:8000/api/xmltv.xml"
#EXTINF:-1 tvg-id="C3.51.tunarr.com" channel-id="C3.51.tunarr.com" CUID="C3.51.tunarr.com" tvg-chno="3" tvg-name="ABCNBCBSFOX" tvg-logo="http://10.0.0.215:8000/images/uploads/b1803c8e-...-icon.png" group-title="TBBTV",ABCNBCBSFOX
http://10.0.0.215:8000/stream/channels/b1803c8e-ad0f-41e5-b2ae-f0fa88f5ec0a?streamMode=hls
```
- Sorted by `number`; `stealth` channels omitted. `tvg-id`/`channel-id`/`CUID` = `getChannelId(number)`; `tvg-chno` = number; `tvg-logo` only when the channel has an icon (fallback `{{host}}/images/tunarr.png`); values are **not escaped** (a `"` in a name breaks the line).
- Empty lineup → a placeholder entry `tvg-name="tunarr"` pointing at `{{host}}/setup`. Cathode should treat `tvg-id="1"` + URL ending `/setup` as "server has no channels".
- The template is cached in the file cache with literal `{{host}}` and substituted per request; cache regenerates on channel create/update/delete and via `ClearM3uCacheTask`.

**Channel id algorithm** (`getChannelId`): sum `(digit + 48)` over the integer digits, `C${num}.${sum}.tunarr.com`. 1 → `C1.49.tunarr.com`, 3 → `C3.51.tunarr.com`. Non-integer numbers produce odd ids (`1.5` → `C1.5.49.5.tunarr.com`). [src] https://github.com/chrisbenincasa/tunarr/blob/main/server/src/util/channels.ts

---

## 2. Stream modes

### 2.1 ErsatzTV

Official channel docs (Legacy docs page, still current for mode names): HLS Segmenter "offers the best performance at program boundaries" and supports watermarks; MPEG-TS is "a light wrapper over HLS Segmenter" for HDHomeRun-type clients; HLS Direct does not transcode but "some clients will have issues at program boundaries"; MPEG-TS (Legacy) "will be removed with a future release". [doc] https://ersatztv.org/docs/channels/

Engine change (important for 2026 servers): v26.11.0 "All channels migrated to the Next engine, which is now the default for new channels"; "`HLS Direct` was migrated to `HLS Segmenter`, which now transcodes continuously unless Normalize Video or Normalize Audio is disabled, in which case it copies"; cached `ts-legacy`/`hls-direct` URLs "continue to work and now stream through the Next engine". v26.11.2: legacy streaming engine "will be removed in ErsatzTV 26.12". v26.11.3: MPEG-TS sends the first 6 s as a burst (`-readrate_initial_burst 6`). [release] https://github.com/ErsatzTV/ErsatzTV/releases . So on a current server the only modes that really exist are **segmenter** (HLS) and **ts** (hybrid TS wrapper around the same segmenter); the IptvController rewrites the others.

Per-request selection: `?mode=` on `channels.m3u` (rewrites every stream URL) or on the per-channel `.m3u8`/`.ts` URL. [src] IptvController.cs

**`segmenter` (HLS Segmenter)** — one `HlsSessionWorker` per channel, shared by all clients: [src] https://github.com/ErsatzTV/ErsatzTV/blob/main/ErsatzTV.Application/Streaming/HlsSessionWorker.cs , https://github.com/ErsatzTV/ErsatzTV/blob/main/ErsatzTV.Application/Streaming/Commands/StartFFmpegSessionHandler.cs
- First `.m3u8?mode=segmenter` request creates the worker (`SessionStartCoordinator.Start`, 30 s start deadline) and waits for enough segments; later requests join the existing session ("If a session is already active, the existing playlist is returned").
- One **ffmpeg process per playout item**; on item end the next process starts with `-output_ts_offset` derived from `GetLastPtsTime` so PTS continue, and the playlist is rewritten with `hls_flags append_list+discont_start` (second process on). ffmpeg args: `-f hls -hls_time 4 -hls_list_size 0 -hls_flags program_date_time+omit_endlist+append_list[+discont_start]+independent_segments -hls_segment_type mpegts|fmp4 -segment_list_flags +live`, GOP forced to 2 s. [src] https://github.com/ErsatzTV/ErsatzTV/blob/main/ErsatzTV.FFmpeg/OutputFormat/OutputFormatHls.cs
- Served playlist = `live.m3u8` trimmed by `HlsPlaylistFilter` to a window (controller: segments newer than now-30 s, max 10 segments), `#EXT-X-MEDIA-SEQUENCE` from the first kept segment's filename, `#EXT-X-DISCONTINUITY-SEQUENCE:n` when n>1, a bare `#EXT-X-DISCONTINUITY` right after `#EXT-X-INDEPENDENT-SEGMENTS` when n==1, `#EXT-X-PROGRAM-DATE-TIME` per segment, and **`#EXT-X-DISCONTINUITY` between items**; `#EXT-X-ENDLIST` is never written. [src] https://github.com/ErsatzTV/ErsatzTV/blob/main/ErsatzTV.Core/FFmpeg/HlsPlaylistFilter.cs
- **Idle timeout:** default `TimeSpan.FromMinutes(1)` (setting `FFmpegSegmenterTimeout`); disabled when the channel's `IdleBehavior` is `KeepRunning`. Any served segment/init file touches the session; after 60 s without touches the worker logs "Stopping idle HLS session" and exits. Old segments are deleted at most every 30 s. [src] StartFFmpegSessionHandler.cs, HlsSessionWorker.cs, Startup.cs
- **Error:** non-zero ffmpeg exit → no retry; `GetErrorProcess` renders an error slate (offline/error stream) and the session continues if that process succeeds; otherwise the worker ends and the next client request (302 from `/iptv/session/{n}/hls.m3u8`) starts a fresh session. Clients see a 404 from the session playlist in between. [src] HlsSessionWorker.cs, IptvController.cs
- Next engine (`NextSessionWorker`): launches the separate `ersatztv-next` channel binary (`run --output-folder ... --number N -`), waits for a `.ready` file, writes to the same transcode folder; heartbeat via `.heartbeat` file; same `/iptv/session/{n}/hls.m3u8` route. [src] https://github.com/ErsatzTV/ErsatzTV/blob/main/ErsatzTV.Application/Streaming/NextSessionWorker.cs

**`ts` (MPEG-TS Hybrid)** — `WrapSegmenter`: ffmpeg reads `http://localhost:{StreamingPort}/iptv/channel/{n}.m3u8?mode=segmenter&subtitles=false` (comment: "Empty subtitle streams delay MPEG-TS output by about 10 seconds") and remuxes to `video/mp2t` on stdout (`FFmpegState.Concat`); a user MPEG-TS script can replace the command. One ffmpeg **per client connection**, on top of the shared segmenter session; ends when the client disconnects (`HttpContext.RequestAborted`) or ffmpeg dies. [src] https://github.com/ErsatzTV/ErsatzTV/blob/main/ErsatzTV.Core/FFmpeg/FFmpegLibraryProcessService.cs , IptvController.cs, StreamingControllerBase.cs. Docs mirror: "Hybrid Transport Stream (wrapped segmenter)... better handling of transitions, compatible with HDHomeRun clients". [mirror] https://mintlify.wiki/ErsatzTV/ErsatzTV/streaming/iptv

**`ts-legacy`** — concat process per client, "Continuous Transport Stream (legacy concat mode)"; removal announced for 26.12. Avoid.

**`hls-direct`** — no session. `GET .m3u8?mode=hls-direct` returns a 1-item playlist: `#EXTM3U / #EXT-X-VERSION:3 / #EXT-X-TARGETDURATION:10 / #EXT-X-MEDIA-SEQUENCE:{index} / #EXT-X-DISCONTINUITY / #EXTINF:{secondsRemaining:F2}, / {scheme}://{host}/iptv/hls-direct/{n}.ts?index={index}`; no `ENDLIST`; the index increments once per playout item (1-day cache). The item URL is a finite remux of the current file from the current offset. The player must re-poll and reset at each item. [src] https://github.com/ErsatzTV/ErsatzTV/blob/main/ErsatzTV.Application/Streaming/Queries/GetHlsPlaylistByChannelNumberHandler.cs . On 26.11+ this is migrated to segmenter-copy anyway.

**Known client gotchas (ErsatzTV):**
- #348 "Does not play next episode in JF/Emby" (HLS Direct): maintainer traced to an ffmpeg HLS-demuxer bug (ffmpeg trac 5419), added the hybrid TS mode as a workaround; Plex only does MPEG-TS and "has more trouble switching between items when source content varies in resolution or codec". [issue] https://github.com/ErsatzTV/ErsatzTV/issues/348
- #1241 "HLS Direct play issues" (TiviMate `PlaylistStuckException`, IPTV Smarters looping): a regression fixed in PR #1242. [issue] https://github.com/ErsatzTV/ErsatzTV/issues/1241
- No open or closed issue mentions mpv as a failing client (GitHub search "mpv" returns only subtitle/HDR/transcoding tickets). [issue] https://github.com/ErsatzTV/ErsatzTV/issues?q=mpv
- Discontinuity work: PR #2548 "properly track discontinuity sequences with fmp4" (merged); PR #2963 (404→503 on missing live playlist, closed). [issue] https://github.com/ErsatzTV/ErsatzTV/issues?q=discontinuity

**Implications for mpv/Cathode (ErsatzTV):**
1. Use `{base}/iptv/channel/{n}.m3u8?mode=segmenter` (or just the M3U URL with `?mode=segmenter` so every entry is segmenter). mpv's hls demuxer (libavformat) handles `EXT-X-DISCONTINUITY` with a timestamp reset; ErsatzTV also keeps PTS continuous across items via the pts offset, so boundaries are usually seamless.
2. First tune on a cold channel takes until the segmenter has enough segments (30 s start deadline); the controller blocks until ready, so a 10–20 s HTTP wait is normal. Cathode's existing retry backoff (2/5/10/20 s) fits.
3. Stop polling for >60 s and the session dies; next request restarts it (expect a 302 + fresh start, segment numbers restart). Keep mpv's `--cache` modest so it keeps fetching segments.
4. A 404 from `/iptv/session/{n}/hls.m3u8` means the session ended (error or idle); re-request `/iptv/channel/{n}.m3u8?mode=segmenter` to restart rather than giving up.
5. Hybrid `ts` is the fallback if mpv ever trips on playlist rewrites: a continuous TS, no playlist state, costs one extra ffmpeg per viewer.

### 2.2 Tunarr

Official docs: "HLS" is the default and recommended ("Use HLS for virtually all new channel setups"); "HLS alt" (`hls_slower`) two-process fallback needing software encoding; "HLS Direct" (`hls_direct`) "requires clients to essentially 'reset' themselves between each program", known to work with "Jellyfin and MPV"; "HLS Direct v2" (`hls_direct_v2`) "produces a continuous, segmented HLS playlist like standard HLS mode, but remuxes source content into segments without codec conversion"; "MPEG-TS" (`mpegts`) "closest to the DizqueTV experience... There are a lot of potential issues with this mode". "clients which require an MPEG-TS stream will still work" (container conversion is internal). [doc] https://tunarr.com/configure/channels/transcoding/ (mirror with the same text: https://mintlify.wiki/chrisbenincasa/tunarr/configure/channels/transcoding)

`streamMode` enum: `hls | hls_slower | mpegts | hls_direct | hls_direct_v2`. Selected per channel (stored on the channel, emitted as `?streamMode=` in the M3U) or per request via `?streamMode=` on `/stream/channels/{id}` and `/stream/channels/{id}.ts`, or `?mode=` on `/stream/channels/{id}.m3u8`. [src] streamApi.ts; [mirror] https://mintlify.wiki/chrisbenincasa/tunarr/api/channels

**`hls` / `hls_direct_v2`** — one `HlsSession` per channel per mode (`sessionCacheKey = ${channelId}_${sessionType}`), shared by all clients; each client gets a `token` connection on the session. [src] https://github.com/chrisbenincasa/tunarr/blob/main/server/src/stream/SessionManager.ts
- One ffmpeg per lineup item; the next starts with `ptsOffset = lastSegmentPts + duration + 1` (0 for `hls_direct_v2`), `-hls_flags program_date_time+append_list+independent_segments[+omit_endlist][+discont_start]`, `-mpegts_flags +initial_discontinuity` on non-first runs, `-hls_time 4 -hls_list_size 0 -hls_segment_type mpegts -master_pl_name playlist.m3u8`, segments `data%06d.ts` in `stream_{uuid}_{instanceId}/`. Buffering: transcode when ≤60 s is buffered, realtime once ≥30 s. [src] https://github.com/chrisbenincasa/tunarr/blob/main/server/src/stream/hls/HlsSession.ts , https://github.com/chrisbenincasa/tunarr/blob/main/server/src/ffmpeg/builder/options/HlsOutputFormat.ts , https://github.com/chrisbenincasa/tunarr/blob/main/server/src/stream/hls/BaseHlsSession.ts
- Readiness: `waitForStreamReady` needs `initialSegmentCount` `.ts` files + `stream.m3u8`, retried 15× at 1 s ("Stream not ready yet. Retry"); then master `playlist.m3u8` is rewritten (variant URL, subtitle/audio `EXT-X-MEDIA`). The "No master playlist found" log the user saw is the master not existing yet (= transcode never produced output). [src] BaseHlsSession.ts, HlsSession.ts
- Served media playlist (`HlsPlaylistMutator`): `#EXT-X-VERSION:6`, `#EXT-X-INDEPENDENT-SEGMENTS`, `#EXT-X-MEDIA-SEQUENCE` from filename, `#EXT-X-DISCONTINUITY-SEQUENCE` always, `#EXT-X-DISCONTINUITY` only between selected groups (header-section ones from ffmpeg restarts are folded into the sequence), `#EXT-X-PROGRAM-DATE-TIME` per segment, keeps ~20 entries and 10 before the client's requested floor, **never `#EXT-X-ENDLIST`**. [src] https://github.com/chrisbenincasa/tunarr/blob/main/server/src/stream/hls/HlsPlaylistMutator.ts
- **Session end:** ffmpeg runtime error → `state='error'` and the run loop exits → `scheduleCleanup()`; error state triggers cleanup immediately ("Received error from session. Shutting down", as seen in the user's log). Normal end-of-item just starts the next item. Setup failure substitutes an error stream first. Cleanup = SIGTERM, 15 s, SIGKILL, directory removed (`ExitWaitTimeoutMs = 30000`). Once stopping, fragment requests get **404 "No session found"**. [src] HlsSession.ts, Session.ts, BaseHlsSession.ts, streamApi.ts
- **Idle:** cleanup is scheduled when `isStale()` (no alive connections) — every minute `CleanupSessionsTask` → `cleanupStaleSessions()`; connection liveness = heartbeat age < `stalenessMs` (default 120 000 ms in `Session.ts`; env `TUNARR_SESSION_STALENESS_MS`); cleanup fires `TUNARR_SESSION_CLEANUP_DELAY_SECONDS` (15 s) later unless a connection re-appears. [src] https://github.com/chrisbenincasa/tunarr/blob/main/server/src/stream/Session.ts , ConnectionTracker.ts, ScheduleJobsStartupTask.ts, env.ts
- Issue #1911 (closed 2026-10-08, "completed"): on `hls_direct_v2` only the master-playlist fetch counted as a heartbeat, so a healthy TiviMate was culled ~61 s after tune → session killed → client re-tuned at a later `-ss` → repeat every ~2 min. Expected fix: "segment and media-playlist requests ... should count as activity". [issue] https://github.com/chrisbenincasa/tunarr/issues/1911 . v2026.10.0 notes: "Each HLS session gets its own directory, and cleanup waits for ffmpeg to finish. Playlists no longer list segments that pruning already deleted"; "Live streams no longer stall during XMLTV writes". [release] https://github.com/chrisbenincasa/tunarr/releases
- Open #2221: `stream.m3u8` on disk is never trimmed, grows ~21 600 entries/day at 4 s segments; perf only, "no playback bug today". [issue] https://github.com/chrisbenincasa/tunarr/issues/2221
- #1066 "Stream stops at the end of a episode" (Emby/Jellyfin via M3U, default hls): maintainer suspected the media server's ffmpeg mishandling HLS discontinuities; closed "not planned"; HDHR tuner path worked. [issue] https://github.com/chrisbenincasa/tunarr/issues/1066
- #339/#334: HLS playlists switched to relative segment paths so remote playback works. [issue] https://github.com/chrisbenincasa/tunarr/issues/339

**`hls_slower`** — `getOrCreateHlsSlowerSession`, two-stage pipeline (per-item rawvideo → single encoder), same playlist mechanics. Fallback only.

**`hls_direct`** — no session; `HlsPlaylistCreator` returns `#EXTM3U / #EXT-X-VERSION:3 / #EXT-X-TARGETDURATION:10 / #EXT-X-MEDIA-SEQUENCE:{index} / #EXT-X-DISCONTINUITY / #EXTINF:{itemSeconds} / {proto}://{host}/stream.{ts|mkv|mp4}?channel={id}&index={n}[&mode=]` with no `ENDLIST`; index bumps per lineup item (1-day cache, v2026.10.2). This is exactly the mode that "made the player reset between programs" for the user. [src] https://github.com/chrisbenincasa/tunarr/blob/main/server/src/stream/hls/HlsPlaylistCreator.ts

**`mpegts`** — `.ts` route → `ConcatSession` (per client token): ffmpeg reads the channel's own HLS **variant** playlist (`/stream/channels/{uuid}.m3u8?mode={childMode}&variant=true`) and remuxes to MPEG-TS on stdout; ends on client disconnect (`removeConnection`) or child error. So it is the HLS session plus one more ffmpeg per viewer; docs call it not recommended. [src] https://github.com/chrisbenincasa/tunarr/blob/main/server/src/stream/ConcatStream.ts , ConcatSession.ts, streamApi.ts

**Implications for mpv/Cathode (Tunarr):**
1. Keep `streamMode=hls` (what the M3U already emits). Point mpv at the **302 target** `/stream/channels/{uuid}.m3u8?mode=hls` directly to skip a redirect per tune, or follow the redirect; both fine.
2. `hls_direct_v2` is the "copy" option if transcoding is the problem, but mixed codecs/resolutions across items then hit mpv directly, and #1911-style heartbeat culling was only fixed in October 2026 builds.
3. Each tune of a cold channel costs `initialSegmentCount` segments (≥ ~8–12 s of encode); re-tuning within the 15 s cleanup delay re-uses the warm session, retuning after it tears down restarts the encode (the surf-hang the user hit). Tune hold/settle logic already in Cathode is the right fix.
4. Treat 404 on a segment/playlist as "session gone, re-tune"; treat a playlist that stops growing for >8 s as a stall (Tunarr's watchdog ends the session on source errors, mpv then sits paused on `keep-open`).
5. Audio glitches at item boundaries are inherent to `discont_start` + ffmpeg restarts; mpv copes because `EXT-X-DISCONTINUITY` resets its timestamp base. Do not enable `--demuxer-lavf-o=...` hacks that disable discontinuity handling.

---

## 3. Guide (XMLTV)

### 3.1 ErsatzTV

- Built from **cached XML fragments** on disk (`ChannelGuideCacheFolder/channels.xml` + `{number}.xml` per channel), concatenated by `GetChannelGuideHandler` at request time with `{RequestBase}` → `{scheme}://{host}{pathBase}` and `{AccessTokenUri}` → `?v={mtimeTicks}[&amp;access_token=...]` substituted; `<etv:...>` helper tags stripped. Root: `<tv generator-info-name="ersatztv">`. [src] https://github.com/ErsatzTV/ErsatzTV/blob/main/ErsatzTV.Application/Channels/Queries/GetChannelGuideHandler.cs , https://github.com/ErsatzTV/ErsatzTV/blob/main/ErsatzTV.Core/Iptv/ChannelGuide.cs
- Channel element (template `_channel.sbntxt`): `<channel id="{{ channel_id }}">` (= `ChannelIdentifier.FromNumber`, i.e. the M3U `tvg-id`), three `<display-name>`s: `"{number} {name}"`, `"{number}"`, `"{name}"`; icon: external artwork verbatim, local `{RequestBase}/iptv/logos/{path}.jpg{AccessTokenUri}`, or generated `{RequestBase}/iptv/logos/gen{AccessTokenUri}&text={name}`. [src] https://github.com/ErsatzTV/ErsatzTV/blob/main/ErsatzTV/Resources/Templates/_channel.sbntxt , RefreshChannelListHandler.cs
- **Icons never come out as `localhost`** unless the client fetched via localhost — the host is injected per request. Only user-entered external logo URLs pass through unchanged. Programme artwork likewise: `{RequestBase}/iptv/artwork/{posters|thumbnails}/{path}.jpg{AccessTokenUri}` (or Plex/Jellyfin/Emby proxy placeholders). [src] https://github.com/ErsatzTV/ErsatzTV/blob/main/ErsatzTV.Application/Channels/Commands/RefreshChannelDataHandler.cs
- **Horizon:** programme fragments include playout items whose `StartOffset <= UtcNow + XmltvDaysToBuild` (setting "XMLTV Days To Build", default **2 days**, must be ≤ "Playout Days To Build"). [src] RefreshChannelDataHandler.cs; [mirror] https://mintlify.wiki/ErsatzTV/ErsatzTV/guides/epg-customization
- **Regeneration:** `RefreshChannelList` (channels.xml) runs in the hourly `SchedulerService.DoWork`; per-channel `{n}.xml` is rewritten by `RefreshChannelData` whenever a playout is built/extended (hourly `BuildPlayout Continue`, daily reset at `DailyRebuildTime`, and on schedule edits — the docs' "Trigger manual rebuild: Edit and save any schedule"). The XML served to clients is assembled on every request (no HTTP caching headers noted). [src] https://github.com/ErsatzTV/ErsatzTV/blob/main/ErsatzTV/Services/SchedulerService.cs
- Programme elements come from Scriban templates (`_movie.sbntxt`, `_episode.sbntxt`, ...); users can customise them, so Cathode's parser must tolerate missing `<desc>`, `<icon>`, `<episode-num>`. Times use "XMLTV Time Zone" setting (Local or UTC) — always parse the `+hhmm` offset.
- `ETV_INSTANCE_ID` changes ids for all channels (`C5.149.home.ersatztv.org`); Cathode should match guide channels by the M3U `tvg-id` string, never by reconstructing the id.

### 3.2 Tunarr

- `XmlTvWriter.write(channels)` serialises the whole guide to `xmlTvSettings.outputPath` (default `{dataDir}/xmltv.xml`) under a mutex, in batches of 100 programmes, with literal `{{host}}` placeholders; `/api/xmltv.xml` substitutes `{{host}}` per request. Header: `generator-info-name="tunarr" source-data-url="{{host}}/api/xmltv.xml"`. [src] https://github.com/chrisbenincasa/tunarr/blob/main/server/src/services/XmlTvWriter.ts , api/index.ts, db/SettingsDB.ts
- Channel element: `<channel id="C{num}.{sum}.tunarr.com">` (same as `tvg-id`), display-names `"{number} {name}"`, `"{number}"`, `"{name}"`, `<icon src="..." width="250"/>`. [src] XmlTvWriter.ts, confirmed [live].
- **Icon `localhost` gotcha — confirmed in the wild.** `resolveIconUrl` returns `icon.path` **unchanged** whenever it is non-empty; the upload endpoint stores an absolute `fileUrl` built from whatever host the browser used. The user's own guide has `<icon src="http://localhost:8000/images/uploads/f29764ad-..._icon.png">` for channel 164 while other channels have `http://10.0.0.215:8000/...`. The same stored path lands in the M3U `tvg-logo`. Cathode should rewrite `http(s)://(localhost|127.0.0.1|\[::1\])(:port)?/` in icon URLs to the configured server base. [src] https://github.com/chrisbenincasa/tunarr/blob/main/server/src/util/iconUtil.ts ; [live]. Docs only mention icons failing under Plex HTTPS. [doc] https://tunarr.com/misc/common-issues/
- Programme artwork: `{{host}}/api/programs/{id}/artwork/{type}` (`icon` + `image size=3 type=poster`), credits `{{host}}/api/credits/{uuid}/artwork/{type}` when enabled; `<category>` genres, `<episode-num system="onscreen">S01E02` and `xmltv_ns`, `<rating system="MPAA|RIAA|VCHIP">`, `<length units="seconds">`. [src] XmlTvWriter.ts; [doc] https://tunarr.com/configure/channels/epg/
- **Horizon:** `programmingHours` default **12** (schema default), build window `startOf('hour')` to `+programmingHours`. **Refresh:** `UpdateXmlTvTask` is cron-scheduled with `hoursCrontab(refreshHours)` (default **4 h**), plus run immediately at startup by `GenerateGuideStartupTask`; also rewritten on channel edits/deletes and `POST /api/xmltv/refresh`. `GET /api/xmltv-last-refresh` tells when. [src] https://github.com/chrisbenincasa/tunarr/blob/main/types/src/schemas/settingsSchemas.ts , tasks/UpdateXmlTvTask.ts, services/startup/ScheduleJobsStartupTask.ts, services/startup/GenerateGuideStartupTask.ts, services/TvGuideService.ts
- So a Tunarr guide typically covers only the next ~12 h; Cathode should refetch at least every 4 h (the `Cache-Control: no-store` on the endpoint agrees) and tolerate the guide ending mid-day. Docs: "clients should always consume it via the API endpoint rather than reading the file directly". [doc] https://tunarr.com/configure/channels/epg/
- Redirect items appear as programmes titled `Redirect to Channel {n}`; flex/filler appears as a programme too.

---

## 4. Detection

Cheapest: one `GET {base}/api/version` — both servers answer JSON on the same path, with disjoint keys.

| Server | Request | 200 body | Notes |
|---|---|---|---|
| ErsatzTV | `GET /api/version` | `{"apiVersion":3,"appVersion":"v26.11.3"}` | `ApiVersion` is the constant 3; `AppVersion` is the assembly informational version (`"unknown"` if missing). camelCase via `CustomNamingStrategy`. Docker tags now carry a `v` prefix (v26.11.0 notes). Not behind JWT (JWT applies to IPTV routes); may be behind OIDC if the admin enabled it. [src] https://github.com/ErsatzTV/ErsatzTV/blob/main/ErsatzTV/Controllers/Api/VersionController.cs |
| Tunarr | `GET /api/version` | `{"tunarr":"2026.10.1","ffmpeg":"n8.1.2-etv.4","nodejs":"22.20.0"}` | Schema `VersionApiResponseSchema = { tunarr: string, ffmpeg: string }`; `nodejs` present on the live server. 500 with empty body if ffmpeg probing fails. [src] https://github.com/chrisbenincasa/tunarr/blob/main/types/src/api/index.ts , api/index.ts; [live] |

Rule: `appVersion` key → ErsatzTV; `tunarr` key → Tunarr; anything else → unknown/generic M3U host.

Fallbacks / secondary probes:
- `GET /discover.json` (HDHomeRun emulation, both at root): ErsatzTV `{"FriendlyName":"ErsatzTV","Manufacturer":"ErsatzTV","ModelNumber":"HDTC-2US","FirmwareName":"hdhomeruntc_atsc","FirmwareVersion":"20190621","DeviceID":"<uuid>","LineupURL":"{scheme}://{host}/lineup.json",...}` [src] https://github.com/ErsatzTV/ErsatzTV/blob/main/ErsatzTV.Core/Hdhr/Discover.cs ; Tunarr `{"FriendlyName":"Tunarr","Manufacturer":"Tunarr - Silicondust","ModelNumber":"HDTC-2US","FirmwareName":"hdhomeruntc_atsc","TunerCount":5,"FirmwareVersion":"20170930","DeviceID":"Tunarr","DeviceAuth":"","BaseURL":"http://10.0.0.215:8000","LineupURL":"http://10.0.0.215:8000/lineup.json"}` [src] https://github.com/chrisbenincasa/tunarr/blob/main/server/src/services/HDHRService.ts ; [live]. ErsatzTV disables HDHR routes when JWT is on; Tunarr's can be disabled in settings.
- Tunarr health: `GET /api/system/health` → `Record<checkName, {"type":"healthy"} | {"type":"info"|"warning"|"error","context":string}>` (e.g. `FfmpegVersion`, `HardwareAcceleration`, `FfmpegTranscodeDirectory`). [src] https://github.com/chrisbenincasa/tunarr/blob/main/types/src/schemas/miscSchemas.ts , services/HealthCheckService.ts; [live]. ErsatzTV has no health endpoint; `HEAD /iptv/channels.m3u` (200) is the liveness check.
- XMLTV `generator-info-name` is `ersatztv` vs `tunarr`; M3U `tvg-id` suffix `.ersatztv.org` vs `.tunarr.com`; M3U `#EXTINF:0` (ErsatzTV) vs `#EXTINF:-1` (Tunarr). Useful for a pasted M3U URL with no base URL.

Suggested first-run flow: normalise input to `scheme://host[:port][/base]`; if no port given try `:8409` and `:8000` in parallel; `GET /api/version` (2 s timeout); on `appVersion` set playlist `/iptv/channels.m3u?mode=segmenter`, guide `/iptv/xmltv.xml`; on `tunarr` set `/api/channels.m3u`, `/api/xmltv.xml`; else fall back to asking for raw M3U/XMLTV URLs. Prefer the `url-tvg` attribute in the fetched M3U over the derived guide URL (both servers emit it).

---

## 5. Confidence

**High (read from current `main` source and, for Tunarr, confirmed live):**
- Paths: ErsatzTV `/iptv/channels.m3u`, `/iptv/xmltv.xml`, `/iptv/channel/{n}.m3u8|.ts`, `/iptv/session/{n}/hls.m3u8`, `/api/version`; Tunarr `/api/channels.m3u`, `/api/xmltv.xml`, `/api/version`, `/api/system/health`, `/stream/channels/{uuid}[.m3u8|.ts]`, `/discover.json`.
- Version response shapes; Tunarr channel id and icon pass-through (localhost case observed); ErsatzTV channel id algorithm; both M3U formats; default ports 8409/8000; Tunarr XMLTV defaults 12 h / 4 h; ErsatzTV XMLTV days default 2.
- Mode mechanics: ErsatzTV segmenter session (60 s idle, 4 s segments, discontinuity + pts offset, 302/404 behaviour); Tunarr hls session (4 s segments, 15 s cleanup, 120 s staleness, 404 after stop, playlist mutator rules); `hls_direct` single-item playlists on both.

**Medium:**
- ErsatzTV 26.11 mode migration details come from release notes (not re-verified in code): "HLS Direct → HLS Segmenter (copy when normalisation off)", "legacy engine removed in 26.12". The IptvController still accepts the old `mode` values and rewrites them.
- ErsatzTV `/api/version` camelCase inferred from Newtonsoft `CamelCaseNamingStrategy` registration; not probed live (no ErsatzTV instance available).
- Tunarr `stalenessMs` default 120 000 ms (from `Session.ts` default) vs. issue #1911's observed ~61 s — the env `TUNARR_SESSION_STALENESS_MS` or factory may set a different value; treat 60 s as the safe assumption.
- ErsatzTV hybrid `ts` output flags (`-c copy -f mpegts -readrate 1.0 -readrate_initial_burst 6`) inferred from release notes + `FFmpegState.Concat`; not read from the pipeline builder.

**Low / not found:**
- No GitHub issue on either project documents mpv-specific HLS failures; mpv notes above are inferred from libavformat behaviour and the user's own logs (memory notes), not from upstream tickets.
- ErsatzTV's hourly `RefreshChannelList` vs. on-playout-build `RefreshChannelData` triggers were read from `SchedulerService.cs` only; other triggers (UI save) are inferred from docs ("Edit and save any schedule").
- Tunarr official docs list `/api/channels/m3u` and `/api/xmltv`; both 404 on 2026.10.1. Possibly a doc typo or a future alias; re-check if a newer Tunarr starts answering them.
