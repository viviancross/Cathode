# How the real boxes behaved: boot, channel change, banner, sounds

Researched 2026-10-17 for the Cathode 5 authenticity pass, from manuals
(official PDFs), period forum posts (DBSTalk, SatelliteGuys, AVS Forum,
forums.directv.com) and the few period videos that exist. Each claim is
marked: **[M]** manual, **[F]** forum/owner testimony, **[V]** a video
frame, **[I]** inferred. Full sourced notes per box are in the research
files this was condensed from; the URLs are there.

Everything in Cathode's skins that departs from this should be a decision,
not an accident.

## InDirecTV HD (HR20 / HR21, 2006-2010)

**Boot (only after a power loss or red-button reset; a remote power-on is
standby and goes straight to video [F]).** The screens were static SD
bitmaps on blue, not rendered UI [F]:

1. Blue screen: "hello, DirecTV your receiver is starting up" (2006
   firmware called it "System Is Starting") [F].
2. Blue screen: "Almost there... just a few more seconds" [F].
3. Black, 3-5 minutes on the real hardware [F]. (Cathode compresses this.)
4. "Step 1 of 2  Checking Satellite Settings... This will take a few
   minutes." [F, several owners agree on the wording].
5. "Step 2 of 2  Receiving Satellite Info..." with a percentage [F].
6. Live video with an "Acquiring Guide Data" box and a progress bar over
   it [M: "Acquiring Satellite Info" / "Acquiring Guide Data"; the
   screensaver comes after 5 minutes idle]. Guide data rebuilt from
   scratch after a power loss [F].

No source describes the shade of blue, the text position or the bar's look.
If no signal at step 5: "Searching for Satellite Signal (771)" [M].

**Channel change.** 1.5 s same resolution, ~3 s with Native On [F,
timed]. The picture goes black for several seconds [F]. The banner appears
at once on the key press, before the new picture, and stays while the
screen is black [F]. Typed digits show in the banner; fewer than four
digits waits ~2 s, ENTER tunes now; a dash shows after the third digit
when a leading 0 was typed [M, F]. PREV = previous channel; one live buffer,
lost on change [M].

**Banner.** Across the top. Date and time; channel logo, number and call
letters; title, start-stop times, rating; the favourites list in use (All
Channels / Ch's I Get / Custom 1 / Custom 2); filled/hollow audio icon;
filled/hollow messages icon; three-state padlock; BLUE-key Mini Guide hint
[M, 2006 manual p.24]. INFO opens a description panel with "More Info";
the expanded banner is a menu: Messages, Info, Last 4, Favorites, CC,
Audio/Video, Parental [M]. Icons sit upper right [M]. Progress bar green
for live, orange when recording; orange record icon and "R"; blue "K" [M].
Banner Time setting under Display > Preferences, 2-8 s [F]; default not
documented (3-6 s [I]); EXIT clears it [M]. The "Sat 7:37a" date format
is unverified.

**Sounds.** None at launch (Aug 2006): the Sound Effects tab was greyed
out, because effects can't be mixed into a Dolby Digital bitstream [F]. By
Feb 2008 firmware 0x1FE fixed "No sound effects over optical" and "No
bonk over optical" [F], so by then: key/menu effects and an error sound
DirecTV itself calls the **bonk** (described as "a low honking kind of
sound" [F]). Setting: Audio > "Sound Effects: select the volume" [M];
levels not documented; on by default [I, every how-to is about turning
them off]. Nobody describes pitch or length; the forum shorthand is "beeps
and boops". No clean sample exists online.

## InDirecTV SD (DSS 1994-2003; D10 / D11 / R15 2004-2006)

Three UI generations: G1 RCA DSS 1994-96 (purple marker, "Norm" guide),
G2 RCA/Sony/Hughes 1997-2003 (grey translucent banner with logo tile and
icon row), G3 D10/D11/R15 2004-06 (blue/grey "Advanced Program Guide").
Cathode's skin is the G1/G2 look.

**Boot.** G1/G2: the box "is never fully off, but goes into a standby
state" [M], so power-on is instant to the last channel; no 1990s manual
describes a logo or acquisition screen. An unloaded guide shows in the
banner as "Title not available" with no Start/End lines [V]. G3 (D10):
"Searching for Satellite Signal" briefly at the bottom, then the guide
data acquisition screen with a progress bar; the bar times out to a blank
screen after 2 minutes; reset if blank more than 4 [M]. Blank-screen
message on 2004 firmware: "Searching for satellite signal. Please
standby." (no code; the "(771)" suffix came with later firmware) [M, F].

**Channel change.** G1 marker appears on every tune over live video; each
change redraws it at once; it persists ~3-4 s after the last change [V,
sampled at 1.5 s]. A viewer recalls "the info bar coming in and going out"
[V comment: it animated]. G3: banner on every tune, "a few seconds",
EXIT removes it; Display > Banner sets the time (values not in the PDF;
2-8 s per a later forum answer) [M, F]. Digits tune after a few seconds or
ENTER [M]. Locked channel: padlock in the marker, black video, no message
[V]. Not subscribed: a message to call 1-800-531-5000 and an extension
(ext. 721) [M].

**Banner (G1, from frames).** Translucent dark purple band across the top
~20%. Left: logo tile over the channel number in a light box. Line 1 title
(or "Title not available"). Line 2 "Start 6:00am    NR(Not Rated)  [icon]
7:14pm". Line 3 "End 6:00am    Normal List          Sat 12/31/94".
Padlock and envelope icons at the right when locked / mail waiting [V].
Clock `h:mmpm` lowercase; date `Ddd M/D/YY`.

**PPV.** G1 "Program Details": title, start, stop, "cost to view $6.00",
buttons Exit / Buy / Times / Info / Help, instruction "To purchase this
program, point to BUY and press SELECT." [M]. The title "Purchase Offer"
is not found in any manual (Hughes: "on-screen pay-per-view offer"; the
in-programme prompt is "Press SELECT to order") [M]. Cathode's "Purchase
Offer" is a plausible invention, kept by choice.

**Sounds.** None documented in nine manuals (RCA x3, Sony, Hughes x2,
D10, D11, R15); the only tone is the dish-alignment tone on the signal
screen [M]. Silent UI. "Sound Effects" appears only in the later non-DVR
firmware guide (H2x/D12 era).

## Plate Network SD (Dish 301 / 311 / 322 / 501 / 508 / 522, 2000-2006)

**Boot.** No splash on the OpenTV boxes (the "dish NETWORK / Starting
up..." splash belongs to the later ViP/Linux boxes) [F, I]. Cold boot shows
the grey ATTENTION 015 dialog: "Acquiring satellite signal. Please wait."
[M: cause "the receiver was just plugged in"; two independent code lists
agree on the wording]. A software load (061 "Vital program information
will now be downloaded into your receiver. Do not disturb or unplug it.")
only when flagged [M]. Then straight to live video on the last channel
with the banner [I]. The bouncing DISH logo is the OFF state, not a splash
[M]. The 015 dialog's bar: not described anywhere (fill vs loop unknown).

**Channel change.** UP/DOWN, digits, or GUIDE + SELECT [M]. ~1-2 s black on
the 301/311, 2-5 s on the DVRs [F]. Banner "for a few seconds at the top"
on every change and on VIEW; no duration setting exists on these models
[M, both indexes]. An invalid number tunes to the nearest valid channel,
no dialog [M]. UP/DOWN skips channels outside the active Favorites list
[M]. RECALL toggles between the last two channels [M].

**Dialogs (exact wording).** 013 "This is a subscription channel which
has not been purchased." 025 "The satellite signal has been lost, signal
acquisition is in progress. Please wait, or press the 'UP' or 'DOWN' arrow
button to change channels." 076 "This event is locked: To view, enter your
password." (three tries, then a lockout for minutes) [M, F].

**Banner.** Transparent, at the top: channel number and name capsules,
title, start-end times, a brief description when available [M, feature
sheet]. INFO on the 522 cycles transparent, solid, closed [M]. Browse
Banner: current programme at the top, others at the bottom, RIGHT steps
[M]. Favorites: "All Chan", "All Sub", "List 1-4"; the guide shows the
active list; unsubscribed channels on red [M]. Highlight "lighter" (311) /
amber (522) [M].

**PPV.** Select in the guide, a message, "Yes", a confirmation menu, then
billed and uncancellable [M]. Branded "Dish-On-Demand" [M].

**Sounds.** None: no beep/tone/sound entry in either manual's index, remote
feedback is LED flashes [M]. The one tone is the Point Dish peaking tone
[M]. Silent UI.

## Plate Network HD (ViP622 / ViP722, 2006-2011)

The best-evidenced box: boot and channel change are from video frames.

**Boot [V].** Black, then the DISH logo on black with "Starting up..."
(static; 80+ s on a cold 722k), then black, then the "Acquiring Signal"
dialog: code 535 in a tab at its top right, text "This should take no more
than 5 minutes to complete...", a five-block bar that fills green left to
right in ~10 s and then holds full for ~80 s, then a hard cut to live
video. The guide downloads only when its cache is stale (330 "Program
guide is being downloaded"). The first-run wizard is separate ("Step 2 of
5 Download Software... Status: Testing Switch..." with a green bar).

**Channel change.** ~1 s black (not a freeze), then the new video with the
Program Banner "for a few seconds" [M, F]. No banner timeout setting. RECALL
goes back to the last channel; repeated presses step through recent ones
[M]. A bad channel shows the same Acquiring Signal box (015/002/535);
unsubscribed 013/014; blackout 011/012; locked = a password prompt [M].

**Banner (official diagram, ViP622 manual p.37).** A dark translucent bar
at the top. Left cell: TV icon and receiver number, "TUE 3/19" over
"6:25 pm", "Dual Mode". Middle: the title in bold, "6:00 pm - 9:30 pm",
"301 HBO2E". Right: rating "NR", "Time Left: 0:45", "List: Family" (lists
All Chan / All Sub / All HD). "Next:" lives only in the Browse Banner (a
bottom strip: the current and next programme cells with a > arrow) [M].
Guide text style [V, 2009 photo]: "List: All HD", "10:41am Mon 3/09",
"PG-13 Movie. ... (2000) ... (HD) (CC) (Stereo)", an HD badge, a cyan
selection.

**PPV.** A "Dish-On-Demand" dialog, "Do you wish to purchase this
program?", with Event / Date/Time / Channel / Cost and Yes / Cancel / No,
then a "Confirmation" dialog with the same buttons [M, p.43].

**Sounds.** None: no beep, key click, error tone or lock sound on the ViP
line; three manuals have no sound setting; the remotes have no speaker
[M]. Programme audio mutes during the ~1 s black. Silent UI.

## What this means for Cathode

- **Boot sequences** differ per box and the current ones are all a
  "logo + acquiring + bar" template. HR20: two blue text screens, Step 1 /
  Step 2 wording, then video with an Acquiring Guide Data box. DSS: nothing
  (instant on) with "Title not available" in the first banner; the D10 look
  is a progress bar that times out. Dish SD: the ATTENTION 015 box over
  black, then video.
- **Channel change** on every box: the banner comes up at once on the
  press and stays through the black; the black is 1-3 s; typed digits echo
  in the banner. Nobody freezes the old picture.
- **Banners** carry more than ours: the favourites list name, the lock and
  mail icons, the audio icon; the HR20's expanded banner is a menu.
- **Sounds** exist on exactly one of the five boxes: the HR20 (effects
  and a bonk, from 2007-08 firmware). The DSS, D10, Dish SD and ViP were
  all silent. So UI sounds belong to the InDirecTV HD skin alone; silence
  elsewhere is the accurate choice, and Classic is Cathode's own call.
