# DirecTV SD receivers 1994-2006: boot, channel change, banner, sounds

Research notes for a retro set-top-box emulation. Three UI generations are covered, because the
"DSS" look changed twice before the D10/D11:

| Gen | Years | Boxes | UI look |
|---|---|---|---|
| **G1 "DSS" (Thomson/RCA)** | 1994-96 | RCA DRD102RW / DRD203RW (first million units), GE, ProScan | Blue grid "Program Guide" with "Norm" list tag; purple/violet translucent channel marker with Start/End lines and "Normal List" |
| **G2 "DSS" (RCA 1997-2000, Sony SAT-A/B, Hughes GAEB0)** | 1997-2003 | RCA DRD202RA/303RA/505RB, Sony SAT-A1..A55, Hughes GAEB0/GCEB0 | Translucent grey/colour-scheme banner with logo tile, icons row, description box; "Program Details" PPV screen with "Buy Program"; Hughes has OneLine Guide + TurboTune |
| **G3 "Advanced Program Guide" (DirecTV-branded)** | 2004-2006+ | D10 (2004, RCA/Thomson), D11 (2005, Humax/LG), D12 (2006), R15 DVR (2005) | DirecTV blue/grey; top banner with date/time, logo+number+call letters, title+start-stop+rating, Favorites list, audio/mail/lock icons; Quick Menu |

Source anchors used repeatedly:
- RCA DRD202RA user manual (1997), scanned pages: https://www.manualsdir.com/manuals/195718/rca-drd202ra.html (page N = `?page=N`; scans at `https://www.manualsdir.com/screens/212744/N.png`)
- RCA DRD203RW user manual (1994-95): https://www.manualslib.com/manual/139379/Rca-Drd203-Rw.html
- RCA DRD102RW/203RW installation manual (1994): https://www.manualslib.com/manual/642972/Rca-Drd102rw.html
- RCA DRD505RB user manual (c. 1998): https://www.manualslib.com/manual/313372/Rca-Drd505rb.html
- Sony SAT-A1 operating instructions (1995): https://www.manualslib.com/manual/162551/Sony-Sat-A1-Operating-Instructions-Primary-Manual.html
- Hughes DIRECTV GAEB0/GCEB0 owner's manual, 119 pp (c. 2000-01): https://www.manualslib.com/manual/40258/Hughes-Directv-Gaeb0.html ; 56 pp draft A.03: https://www.manualslib.com/manual/1289761/Hughes-Gaeb0.html
- DIRECTV D10 user guide, 48 pp (2004): https://www.manualslib.com/manual/40241/Directv-D10.html ; 96 pp edition: https://www.manualslib.com/manual/356950/Directv-D10.html
- DIRECTV D11 user guide, 84 pp (2005): https://www.manualslib.com/manual/40268/Directv-D11.html
- DIRECTV R15 user guide, 69 pp (2005): https://www.manualslib.com/manual/229079/Directv-R15.html
- DIRECTV Non-DVR user guide, 132 pp (later firmware; H20/H21/H23/H24/D10/D11/D12): https://www.manualslib.com/manual/402733/Directv-H20.html
- RCA 1994 "Changing Entertainment Again" brochure (PDF, p.5 has a colour DSS Program Guide screenshot): https://worldradiohistory.com/BOOKSHELF-ARH/Technology/RCA-Books/RCA-1994-Changing-Entertainment-Again.pdf
- Video, G1 box in use on 12/31/94 (banner, guide, menu, channel flipping): "DirecTV and USSB 12/31/94 Channel Flipping and RCA DSS Guide and Menu", Midnight Retro, https://www.youtube.com/watch?v=k8MFpylNnYY (27:21). Part 2: https://www.youtube.com/watch?v=Y0dzuprxnhU (37:19).
- Other period video found but not frame-checked: "RCA DSS System Do-It-Yourself Installation Video Guide" (mid-90s VHS, 55:45, shows "initial configuration") https://www.youtube.com/watch?v=sM9ikB5rnaM ; "RCA DSS Demo Guide (FULL VIDEO!)" (retail demo laserdisc); "1995 RCA DSS infomercial"; "DIRECTV D11-500" (29 s) https://www.youtube.com/watch?v=C21PJxPOqGo ; "DirecTV D12" (grentz, 2010).

Note on method limits: the desktop browser pane was hidden for much of the session; frames were
captured from the 12/31/94 video at 0:20, 0:40, 5:00, 6:40, 16:00, 18:00, 21:00, 26:20 plus a
10-second run from 4:57 (all listed in sections 2-3). Web-search budget ran out before sounds could
be chased on forums; see Confidence.

---

## 1. BOOT SEQUENCE

### G1/G2 (1994-2003 DSS boxes)

- **Standby, not "off".** "The DSS receiver is never fully off, but goes into a standby state" (DRD203RW manual p.36, OFF/ON button). So a normal "power on" is instant: picture of the last channel plus the channel marker; no logo or acquisition screen. *(Inference: the instant-on part; the manual only states standby.)*
- **Cold boot (after unplug)** is the only time these boxes "boot". No 1990s RCA, Sony or Hughes manual describes a logo or progress screen; the troubleshooting sections only cover the System Test. Owners on HomeTheaterForum describe "soft boot" = hold DOWN arrow + POWER; "hard boot" = unplug and replug (https://www.hometheaterforum.com/community/threads/hard-and-soft-boot-for-dss-receiver.69797/). *Not verified: what the screen shows during the cold boot. Likely black/blank video with the channel marker when the tuner locks (inference).*
- **Guide not yet loaded** shows in the banner as a missing title. Frame at 16:00 of the 12/31/94 video shows MTV 989 banner reading **"Title not available"** with no Start/End lines (https://www.youtube.com/watch?v=k8MFpylNnYY&t=960s). This is what you see right after a cold boot before guide data for that channel has arrived *(inference that cold-boot and "no data" look the same; the frame itself is fact)*.
- **Hughes GAEB0 (2000):** on signal loss the box shows **"Searching for satellite signal. To access related utilities, press [MENU]"** (Q&A, 119-pp manual p.46 and 56-pp manual p.47; the last word is cut in the OCR but the context is the menu key). Manual recommends unplugging 30 s to reset. No boot screen described.
- **Sony SAT-A1 (1995):** no boot screen described; the Program Banner is manual (DISPLAY button), so after a power-on nothing overlays the picture unless you press DISPLAY (SAT-A1 p.40).
- **First-time setup on G1** is a dish-pointing flow, not a boot: "Pointing Dish using Zip Code", "Signal Strength Menu", on-screen prompt "Rotate the Dish 3 Degrees", and an audio tone (installation manual pp.106-113). Only relevant if the emulator ever shows an out-of-box screen.

### G3 (D10 2004, D11 2005, R15 2005)

Documented sequence from the D10 48-pp guide (https://www.manualslib.com/manual/40241/Directv-D10.html?page=13 and ?page=14):
1. Power on. **"Searching for Satellite Signal"** may appear "briefly at the bottom of the screen" on first power-up; "This is normal. If it stays longer than one minute" check the signal meter.
2. **"Advanced Program Guide Data acquisition screen"** with a **progress bar**, shown "after you turn on the receiver". *"The progress bar disappears after 2 minutes, and the screen goes blank"* (stated as screen-burn protection). *"If the screen stays blank for more than 4 minutes, reset the receiver."* *"When the progress bar reaches 100%, video may take a while to appear."*
3. Then live TV (channel 100/201 after Guided Setup).
- Guided Setup on first run: language screen, Welcome screen, dish pointing, system test, then **"Satellite Data Acquisition"** screen, then phone setup and remote programming (D10 96-pp p.34; D11 p.29; R15 p.24). The R15 adds: after 5 minutes idle on a static image, **a black screen with a moving DIRECTV logo** screen saver appears (R15 p.24).
- Troubleshooting wording, D10 48-pp p.41: *"Blank screen with message: 'Searching for satellite signal. Please standby.'"* and *"Screen goes blank during Satellite Data Acquisition: This is normal. The progress bar times out after two minutes."* D11 p.57 and D10 96-pp p.69 repeat the two-minute progress-bar timeout.
- **Later firmware (same hardware, 2008+ non-DVR guide for D10/D11/D12/H2x):** messages are **"Acquiring Guide Data"** / **"Acquiring Data From Satellite"** with a progress bar; "the screen saver appears after five minutes" if it stalls (p.74). Community posts for this era describe a grey screen "Acquiring Guide Data" after a "Searching for Satellite" status bar (https://forums.directv.com/conversations/directv-equipment/receivers-not-receiving-guide-information-and-searching-for-satellite-issues-please-help/610c0f4adf08a4122a465c9a).
- **Time to live TV:** manuals never promise a number. Bounds from the text: progress bar lasts up to 2 min, then blank, reset if >4 min. Real-world: comparable DirecTV boxes hung at "26% or 28%" during acquisition (WeaKnees, https://www.weaknees.com/directv_problems.php). A reasonable emulation: 30-90 s of progress bar, then picture *(inference)*.
- **771 era note:** the numbered "(771)" suffix is not in any 2004-05 D10/D11/R15 manual; those print "Searching for satellite signal. Please standby." The later 132-pp guide (p.72) says messages are two lines, cause then instruction, "Most messages include a code in parentheses". Forum quotes of the later screen: "Searching for Satellite (771)" (https://forums.directv.com/conversations/directv-equipment/771-problems/64e4b7343759d03c986aaf8f). So: D10/D11 original firmware = no code; post-2008 firmware = "Searching for satellite signal (771)" style *(inference on the exact two-line layout)*.

## 2. CHANNEL CHANGE

### G1 (1994-96, RCA DRD102/203)
- Channel marker appears on every tune, over live video, at the top. Three frames from 12/31/94 (https://www.youtube.com/watch?v=k8MFpylNnYY): 0:20 (DIRECTV 301), 5:00 (MC 510, music channel, black video), 16:00 (MTV 989).
- Between channels: the frames show live video already present under the marker; a channel change on DSS is a re-tune of an MPEG stream so there is a short black/freeze gap *(inference; not measured from the video because frame-by-frame capture was blocked)*.
- A viewer comment on that video: *"The info bar coming in and going out was so cool back then"* (comment by @Queef_Murphy) -- supports an animated slide-in/slide-out of the marker rather than a hard cut *(the comment is fact; "slide" is inference)*.
- Marker is also summoned by SELECT/DISPLAY: *"Also brings up a channel marker showing the time, channel, and other program details"* (DRD203RW p.35-36). No manual gives the marker's timeout and there is no user setting for it.
- **Measured timeout (rough):** a 10-second run from 4:57 (https://www.youtube.com/watch?v=k8MFpylNnYY&t=297s, zooms every ~1.5 s) shows the viewer stepping through Music Choice channels (Jazz Plus -> Contemporary Jazz -> New Age 510 -> Eclectic Rock 511); each change redraws the marker instantly with the new channel (no gap in the marker), the marker is still up ~1.5 s after the last change and gone ~3.5 s after it. So the G1 marker persists roughly **3-4 seconds** after the last channel change *(estimate from 1.5 s sampling; could be 3-5 s)*. Video behind it on these music channels is black.
- Locked channel: at 0:40 the marker for **ADLT 401** reads "Title not available", "Normal List", "7:18pm Sat 12/31/94" with a **padlock icon** left of the clock; video is black (channel blocked by the ratings/channel lock). No separate "locked" message text is shown -- the lock icon in the marker is the only indication (https://www.youtube.com/watch?v=k8MFpylNnYY&t=40s).
- Digits: in the guide, "Enter all digits, such as 1-2-8 for Channel 128 or 0-0-2 for Channel 2" (DRD203RW p.9). *Not verified how typed digits were echoed on screen while watching TV.*
- "Not authorized" look on G1: not found. The G1 box ran DirecTV and USSB on one guide; unsubscribed channels still listed.

### G2 (1997-2003)
- RCA DRD202RA/505RB: the banner appears *"whenever you tune to a channel, exit a guide, or press INFO on the remote"* (DRD505RB p.21; DRD202RA glossary p.62 "Channel Banner"). No timeout value or setting in the manual; the Options > Look and Feel menu only has Default Guide (Grid/Detail/SurfGuide), Color Scheme, Translucency slider, Animation on/off (DRD202RA p.46).
- Sony SAT-A1: **no automatic banner on channel change.** "Press DISPLAY to show it. Press DISPLAY again to hide it" and it stays until dismissed (SAT-A1 p.40). Number keys: "Pressing the 0-9 buttons enters a station number, and the ENTER button changes stations more quickly" (p.30).
- Hughes GAEB0: Channel Banner *"appears at the top of the screen when you press the CHANNEL (CH) button"*; *"Banners disappear from the screen after a few seconds"*; *"Press CLEAR to remove them immediately"* (119-pp p.37). Typing a number does **not** tune directly: *"Enter a channel number with the numeric keypad to open the OneLine Guide for that channel"* (bottom-of-screen one-line guide; SELECT tunes) (56-pp p.13).
- Not-subscribed message, G2: a message *"asking you to call an extension"* -- "To watch the channel showing the message, call DIRECTV at 1-800-531-5000" (GAEB0 Q&A p.46). This is the origin of the ext.-number codes (721 etc.): the on-screen text told you to call 1-800-531-5000 and an extension *(wording of the full sentence not recovered)*. The 132-pp guide p.79 still says "call Customer Service at ext. 721 to refresh receiver information".

### G3 (D10/D11/R15, 2004-06)
- Banner *"appears across the top of the screen whenever you tune to a channel"* (D10 96-pp p.39; D11 p.35; R15 p.31). It also appears on PREV, on the front-panel up/down arrows, and on exiting a menu except via EXIT (D10 48-pp p.22).
- Picture first, banner over it: the banner is drawn over the new channel's video *(inference from the manuals' wording; no gap measured)*.
- **Timeout:** *"it goes away on its own after 'a few seconds'"*; *"Press EXIT to remove the banner immediately"*; adjustable: Quick Menu > Settings > Setup > **Display > Banner: "Sets how long the Channel Banner stays on screen"** (D10 96-pp p.40 and p.50). The option values are not printed in the D10/D11/R15 PDFs' text layer. The later firmware guide calls it **"Banner Time"**: *"Set the channel banner time to determine how quickly the banner disappears after moving to a new channel"* (132-pp p.60). A 2019 forum answer for the same family lists the range as **2-8 seconds** (https://forums.directv.com/conversations/watching-directv/turn-off-the-pop-up-window-on-channel-guide/610c11cddf08a4122a471b79) *(values for 2004-era firmware unverified; 2/4/6/8 s is the best guess)*.
- **Typed digits:** *"Key in the channel's digits on the remote. The channel appears after a few seconds, or you can press ENTER after the digits to show it immediately"* (D10 96-pp p.38). The digits are echoed in the banner area as typed *(inference; the manual does not say where)*.
- **Channel-not-available:** *"You can only access channels included in your DIRECTV programming package"* (D10 96-pp p.38). The 132-pp guide (p.72) shows the "channel you haven't purchased" message as a two-line message with a code in parentheses and "call Customer Service at 1-800-531-5000 and mention the code". AT&T's code table: 711 access card not active, 721 service not authorized, 722 service expired, 731 unable to order IPPV, 771 searching for satellite (https://www.att.com/support/smallbusiness/article-modal/smb-directv/KM1215428/).
- Screen saver: "black screen with a moving logo" after 5 minutes of a static image (R15 p.24).

## 3. BANNER DETAILS

### G1 channel marker (1994-96) -- from video frames
Frames: https://www.youtube.com/watch?v=k8MFpylNnYY at **0:20**, **5:00**, **16:00**.
- A translucent **dark purple/violet band** across the top ~20% of the picture (video shows through).
- **Left column:** service logo tile (DIRECTV "D" logo with the word DIRECTV; MC logo for Music Choice; MTV logo), and beneath it the **channel number in a small light box** ("301", "510", "989").
- **Line 1:** program title in a light sans-serif ("Special Events Calendar", "New Age", or **"Title not available"** when no data).
- **Line 2:** `Start  6:00am    NR(Not Rated)    [icon]    7:14pm`
- **Line 3:** `End    6:00am    Normal List                Sat 12/31/94`
  - Rating is shown as "NR(Not Rated)"; "Normal List" is the active channel list name; the clock is `h:mmpm` lowercase am/pm; date is `Ddd M/D/YY`.
  - At 16:00 the right block also shows a **padlock icon** and a **mail (envelope) icon**, i.e. system locked and mail waiting. The small grey glyph between rating and clock at 0:20, 0:40 and 5:00 is the same **padlock** (open/closed lock state; the manual says "A lock icon in the channel marker shows whether the system is locked or unlocked", DRD203RW glossary p.54).
  - Music channel (6:40): "MC 526 | Contemporary Christi[an] | Start 7:00pm NR(Not Rated) | End 7:00pm Normal List" -- Music Choice channels carry a 24-hour "program" so Start and End both read 7:00pm (https://www.youtube.com/watch?v=k8MFpylNnYY&t=400s).
- **G1 guide as actually used (frames 18:00 and 21:00):** header reads **"Norm   + 8.0 HRS Guide"** when paged eight hours ahead (the title replaces "Program Guide" with the offset), time columns "1:30AM  2:00AM ..." in uppercase AM/PM, channel tiles as abbreviation-over-number ("ACTN 276", "WAM! 274", "CBS 282", "NBC 284", "MC26 526", "MC27 527", "ANC 963", "VH1 965"), grey-violet cells with white rules, titles truncated with "..." ("Man Who Wanted to...", "The Adv entures of...", "HBO Com edy Sh..." -- note the word-wrap breaks mid-word), music channels show the genre as the title ("Contemporary Christian", "Gospel", "For Kids Only"), and unsold slots read "Paid Programming" (https://www.youtube.com/watch?v=k8MFpylNnYY&t=1080s and &t=1260s).
- **G1 "Program Information" screen (26:20):** full-screen purple panel titled **"Program Information"**, first line *"After reading this information, p[ress ...]"*, then stacked lines **"Guarding Tess" / "Date: 12/31" / "Start time: Sat 7:30pm" / "Length: 1 hrs 36 min" / "Channel 111" / "Rating: PG13"** followed by the synopsis ("Shirley MacLaine, Nicholas Cag[e]... secret service agent is assigne[d]..."). This is the G1 expanded-info screen (reached from the guide/INFO); note "Length" rather than an End time, "PG13" without hyphen, and "1 hrs" (https://www.youtube.com/watch?v=k8MFpylNnYY&t=1580s).
- **Program Guide (1994)**, from the RCA brochure page 5 (colour): header bar **"Norm  Program Guide   TUE. 2/15/94  6:00 PM"**, second header line "2/15   6:00 PM   6:30 PM   7:00 PM   7:30 PM", channel column = **logo abbreviation over number** ("HBO 202", "DISN 204", "ESPN", "USA", "NICK 299", "LIFE 402"), grid cells blue with white rules, highlighted cell light cyan, bottom button row **[down-arrow] Movies | Sports | Other | All | Exit**. The DRD203RW manual confirms the labels and that time columns read "7:30PM" style (p.8), five-channel paging, and category sort Movies/Sports/Other (p.8-10). Main menu reached by MENU; CLEAR removes guide/menus.
- **PPV "Program Details" (G1):** title ("Dogzilla Returns"), **start time 10:00 pm, stop time 12:00 am, cost to view $6.00**, buttons **Exit, Buy, Times, Info, Help**; on-screen instruction *"To purchase this program, point to BUY and press SELECT. Then, point to EXIT and press SELECT."* (DRD203RW p.16 and p.19). No separate confirmation screen described.
- **"Purchase Offer":** this exact label was not found in any RCA, Sony, Hughes or DirecTV manual text. The phrase "on-screen pay-per-view purchase offer" is how the Hughes manual refers to the prompt that appears on tuning to a PPV channel ("No on-screen pay-per-view offer" Q&A, p.47), and DirecTV's own in-program prompt is **"Press SELECT to order"** (56-pp p.21). *If the emulated screen needs a title, "Purchase Offer" is plausible for the broadcast-side DirecTV prompt but is unverified.*

### G2 banner (1997-2003)
- **RCA DRD202RA (1997)**, scanned "Anatomy of The Channel Banner" (https://www.manualsdir.com/screens/212744/19.png): translucent grey band at top; left: **network logo tile** (HGTV), under it "Ch 214 / HGTV" and a small icon; centre: **title in bold** ("Outdoor Living"), then **"2:30pm to 3:00pm"**, **"NR-Not Rated"**, **"English"** (audio language); right: **"2:40pm"**, **"Wed 7/9/97"**, **"Family"** (active profile name, one of five). Below those, a **row of icon buttons**: list/menu, padlock (green unlock / yellow unlock / red lock states), "AZ" alphasort, binoculars (Scout), envelope (mail), home-control/data-port. Beneath the banner a **description box** ("Tips for creating a safe and fun playground.") -- that box is the INFO/expanded content. Date format `Ddd M/D/YY`, time `h:mmam/pm` lowercase.
- Program Guide (1997 scan, https://www.manualsdir.com/screens/212744/18.png): header "Program Guide | Family | 5:29pm / Tue 7/22/97", a description paragraph for the highlighted show, date column "7/22" then "5:00pm 5:30pm 6:00pm 6:30pm", channel cells "213 HSN / 251 USA / 275 CNBC / 910 HBO / 966 MTV", bottom icon row EXIT ? [sort icons] [down] [scout] AZ ... Menu. Main menu list: Program Guide..., Mailbox..., Purchases..., Timers..., Profiles..., Options..., Dish Pointing..., Home Control... with Exit/Help tabs.
- **PPV Program Details (1997)** (https://www.manualsdir.com/screens/212744/35.png): left buttons **View Channel / Channel Guide... / Buy Program** (DRD505RB adds Record Program, Buy and Record, Other Times); right block: DIRECT TICKET logo, "Topic: Movies, Theme: Comedy, Rating: PG-13, Start: 10:00pm, Length: 1hr 22min", "DTV Ch 107 7/14/97", then the synopsis. Buying over the spending limit asks for the 4-digit password (DRD202RA p.34). Attractions Guide = preview channel browser (DTV Movies / DTV Events / DTV Previews / USSB) (p.36 scan).
- **Sony SAT-A1 Program Banner:** program title, station name and number, start and end times, current date and time, rating; indicator icons for data services, alternate audio, new mail, lock (p.40). **Purchase Program screen:** title, description, "Channel: 102", "Time: Wed Oct 5 8:00PM - 9:30PM", "Rating: R", "Price/View: $2.99", buttons **RETURN, BUY, TIMES, HELP** (PREVIEW appears only when a free preview exists); then **Confirm Purchase**: title, price, time, channel, **"Do you want to purchase this program?" YES / NO** (p.32). Guide cells for PPV read **"PRESS FOR PURCHASE INFORMATION"** (p.29). If no phone line: **"Purchase information not available"** (p.32).
- **Hughes GAEB0 Channel Banner:** sample shows "Family" (class), "4:00 PM to 5:00 PM", channel 340, "Wed, Mar 28 10:54 AM", "Rated: NR (Not Rated)", "TNN: Automobiles"; status icons ALT AUDIO, NEW, CC, MAIL, $, DOLBY DIGITAL, "CAN'T TAPE" (56-pp p.11). INFO once = banner, INFO twice = **Info Banner** with description beneath. Guide: Large Cell (2 hours, 4 channels with Picture-in-Guide, 6 without, 8 with descriptions off) or Logo Guide; MultiColor categories movies rose / sports green / news brown / other blue; Color Scheme e.g. "Satin", Translucency "Heavy" (pp.13, 30).

### G3 banner (D10 / D11 / R15)
Seven numbered elements, identical text in D10 96-pp p.39, D11 p.35, R15 p.31:
1. **Current date & time** (day, date, time)
2. **DIRECTV Channel:** channel **logo**, number and call letters
3. **Program:** title, **start and stop times**, rating
4. **Current Favorites:** name of the Favorites list in use (default "All Channels" *(inference; the D10 guide sorts "All Channels" in the Guide)*)
5. **Audio options icon** (bright when alternate audio exists)
6. **Messages icon** (bright when new Caller ID & Messages)
7. **Parental Controls icon** (Locked / Unlocked / Temporarily Unlocked)
- D10 48-pp p.22 distinguishes a **medium banner** (date, time, channel, inbox, lock status, title + time) shown on tune, and a **large banner** (adds program description) shown by **INFO**. Later docs: INFO once = details, INFO again clears; **"More Info"** button opens other showings / Buy / Autotune (D10 96-pp p.40).
- Music channels: banner first shows the genre ("Alternative", "Today's Country"), then song title, artist and record company as data arrives (D11 p.35).
- Icons also mark Dolby Digital, letterbox, All Day Ticket replay, autotune, PPV scheduled (D10 96-pp p.95 Icon Reference).
- PPV: guide channels 100+ (100 = previews). Highlight + SELECT or INFO, choose **"Buy"** and "follow the onscreen instructions"; a **reminder** appears a few minutes before start; cancel via Scheduler/To Do List if unwatched (D10 96-pp p.45; D11 p.40). Exact buy-screen text not in the PDFs' text layer.

## 4. SOUNDS

What the sources establish:
- **No key-click, menu or error sound is documented for any 1994-2005 box.** The RCA DRD203RW, DRD202RA, DRD505RB, Sony SAT-A1, Hughes GAEB0 (both editions), D10 (both editions), D11 and R15 manuals have no sound/beep setting and never mention a tone when pressing buttons; their Options/Look and Feel/Preferences/Settings lists are enumerated above and contain only guide style, colour scheme, translucency, animation, audio language, Dolby, banner time, TV ratio and time zone. (DRD202RA p.46; GAEB0 56-pp pp.30-31; D10 96-pp p.50; D11 p.42-43; R15 p.40.)
- The only sound a G1 box makes on its own is the **dish-alignment tone**: *"a continuous tone is received immediately after you enter the signal strength menu"*, which stops when the dish is turned off-signal (installation manual p.113, https://www.manualslib.com/manual/642972/Rca-Drd102rw.html?page=112). Pitch is not stated; it is a steady tone, used only during Dish Pointing.
- **"Sound Effects"** first appears as a setting in the later non-DVR firmware guide covering H20/H21/H23/H24 and D10/D11/D12: Settings > Audio > **"Sound Effects: Select the volume of sound effects"** (132-pp p.62; the value list is not in the text layer -- the HD boxes use Off/Low/Medium/High in the same UI *(inference from HR2x family)*). That means a D11/D12 that received the newer software did gain UI clicks; the 2004-2006 original software did not.
- Period videos: the 12/31/94 recording is a VCR capture, so any receiver-generated tone would be on the tape; none was reported in 142 comments, and the one UI remark is about the banner animating, not a sound. No isolated audio sample was found. *(No clean sample URL to give.)*

Emulation guidance *(inference)*: G1/G2 and 2004-06 G3 should be silent on remote presses; the only candidate sound is a later-firmware D12-style soft click, volume-adjustable, off by default in a 2005 recreation.

## Confidence

| Item | Confidence | Basis |
|---|---|---|
| G1 banner layout (Start/End lines, NR(Not Rated), Normal List, clock/date formats, logo+number tile, purple band) | High | Three frames from the 12/31/94 video |
| G1 guide layout and colours | High | Colour screenshot in RCA 1994 brochure + DRD203RW manual |
| G1 PPV details screen fields and Buy/Exit/Times/Info/Help buttons | High | DRD203RW manual text |
| "Purchase Offer" exact title | Low | Phrase not found; Hughes calls it the "on-screen pay-per-view offer"; prompt text "Press SELECT to order" is documented |
| G1 banner timeout ~3-4 s | Med | Sampled every 1.5 s from 4:57 in the video; coarse |
| G1 banner slide animation | Low | One viewer comment ("coming in and going out"); not captured |
| G1 "+ 8.0 HRS Guide" title and "Program Information" screen fields | High | Frames at 18:00, 21:00, 26:20 |
| G1 boot: instant from standby, nothing shown | Med | Standby stated; screen content on cold boot unverified |
| G2 (1997 RCA) banner anatomy incl. icons row, description box, profile name | High | Scanned manual page |
| Sony SAT-A1 banner is manual-only (DISPLAY) with no timeout | High | Manual text |
| Hughes "Searching for satellite signal. To access related utilities, press [MENU]" | High (last word Med) | Two manual editions |
| D10/D11 boot: "Searching for Satellite Signal" at bottom, progress bar, 2-min timeout to blank, reset after 4 min | High | D10 48-pp and 96-pp, D11, R15 manuals |
| D10/D11 banner seven elements; EXIT dismisses; INFO twice clears; "Display > Banner" setting exists | High | Three manuals agree |
| Banner Time values (2-8 s) on 2004-06 firmware | Low | Only a 2019 forum answer for the later UI |
| "Searching for satellite signal. Please standby." (D10, no code) vs "(771)" later | Med-High | D10 manual vs. forum quotes of later firmware |
| Error-code wording 721/722/771 as two-line message + "(code)" | Med | 132-pp guide p.72 (example only as image) + AT&T table |
| No UI sounds on 1994-2006 boxes | Med-High | Absence across nine manuals; no positive source |
| Sound Effects on later D11/D12 firmware | Med | 132-pp guide lists the setting for D10/D11/D12 |
| Boot time to live TV | Low | Only the 2-minute bar timeout and forum anecdotes |
