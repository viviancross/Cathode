# Dish Network SD receivers, 2000-2006 (301 / 311 / 322 / DishPVR 501-508-510 / 522-625)

Research notes for a set-top-box emulation. Scope: the EchoStar "OpenTV / Dish Home Interactive" user
interface that shipped on the DishPro-era SD boxes. Every concrete fact carries one source URL.
Things I could not verify are marked **[inference]** or **[unverified]**.

How the text sources map to the boxes (so the citations make sense):

- The **DISH 311 User Guide** (EchoStar, software DP311) is the closest surviving full manual for the 301;
  the 311 "is based on the very successful 301 receiver ... the only real difference between the 301 and
  311 is the absence of a removable smart card"
  (https://www.manualsdir.com/manuals/275677/toner-cable-311-digital-satellite-receiver.html).
  Page refs below are the manualsdir viewer page numbers (`?page=N`); printed page = N - 5.
  Base URL: https://www.manualsdir.com/manuals/78064/dish-network-solo-311.html
- The **DISH Player-DVR 522/625 User Guide** (EchoStar 2005, software DP522/DP625), 179 viewer pages,
  printed page = N - 5. Base URL: https://www.manualsdir.com/manuals/77955/dish-network-duodvr-625.html
- The **DISH 322 User Guide** (2004, software DP322) is mirrored at
  https://www.manualsdir.com/manuals/76865/dish-network-solo-351.html (the title on that mirror is
  wrong; the text inside says it covers the 322). Not read in depth; its text is the same family.
- The **DishPRO 301 advance feature sheet** (EKB): https://tbh.lerctr.org/~ekb/301features.php
- Timeline: the 301 was released in 2001, the 311 in 2003; both run "the OpenTV Dish Interactive UI ...
  previously rolled out to 3900 and 4900 receivers"; "The UI had the old 1996 Dish Network logo since the
  UI rollout in 1999" (EchostarFan, 24 Dec 2017,
  https://www.satelliteguys.us/xen/threads/the-dish-network-user-interface-thread.373454/page-4).
  Dish Home interactive software was pushed to the 4900 by end of Feb 2002, 3900 from April 2002, and
  "DishPVR models 301 and 501 ... in July" 2002 (NextTV, 12 Feb 2002,
  https://www.nexttv.com/news/dish-starts-interactive-upgrades-156806).

Image sources I located but could NOT open (the desktop browser pane was hidden for the whole session, so
screenshots were impossible; WebFetch cannot return images):

- DP311 main menu screenshot, "Dish 311 main menu.png":
  https://www.satelliteguys.us/xen/attachments/dish-311-main-menu-png.129957/
- OpenTV guide from the Dec-2002 DishPVR 501 user's guide (shows "Remote Control Help" on ch 101):
  https://c1.staticflickr.com/5/4421/36456106316_2f843e93c8_o.jpg
- A customer-site photo of the old UI: https://www.satelliteguys.us/xen/attachments/129910/
- "common early 2000s Dish guide" image cited in the same thread as tech-faq.com/interactive-tv.jpg

Video sources (all by the collector channel "That Dish500_Guy18", @Dish500_Guy18; none has a
description, and I could not screenshot frames, so no timestamps are claimed):

- "DP301 experience" 0:36, https://www.youtube.com/watch?v=u2reTJkXjRo  (a live DP301 being driven)
- "Dish Network DP301 Crashing And Semi-Browsing" 1:52, https://www.youtube.com/watch?v=c38gG1NxRQc
  (description: "unable to get signal from 110 because of the new satellite in it's place" - the box
  is shown failing to lock and browsing the guide)
- "Dish Network ViP722k and DP301 Unboxing" 17:33, https://www.youtube.com/watch?v=yTn-G1KrjFI
  (thumbnail is the DISH Network logo with "Starting up..." - that splash is the ViP722k's, see Boot)
- "DISH Network dp 301 satellite receiver available now" 1:19 (dealer clip, ~2011),
  https://www.youtube.com/watch?v=TuH2ETwrjOk
- Teardown of a 311: https://www.youtube.com/watch?v=kHN9KUwpWd0


## 1. Boot sequence

**What is documented**

- Power-on begins with the receiver locking the satellite. Message 015's cause is "The receiver was just
  plugged in and is acquiring the satellite signal, or it temporarily lost the signal"; the fix is
  "Wait a few minutes" (311 guide ?page=62; same text in 522 guide ?page=142).
- On-screen wording of that dialog, from two independent code lists:
  - 015: "Acquiring Satellite Signal. Please Wait." (2017 list,
    https://removeandreplace.com/2017/09/09/dish-network-receiver-error-code-list-3-and-4-digit-codes/)
  - 015: "Acquring satellite signal. Please wait." [sic] (list posted 12 Feb 2005 by "LK",
    https://www.ecoustics.com/electronics/forum/home-video/122527.html)
  - Bell ExpressVu (same EchoStar firmware) groups "Attention 015 & 025" as "Please standby for satellite
    signal" (https://support.bell.ca/TV/Receivers/Satellite-TV-error-codes-and-troubleshooting).
  - The dialog is an **Attention** box with the three-digit number; the family wording is
    "ATTENTION Acquiring satellite signal" (removeandreplace, code 026).
- A 2004 owner of a (pre-DishPro) 2800 saw "015 acquiring satellite signal" "right after power-on"
  (24 Apr 2004, https://www.satelliteguys.us/xen/threads/015-acquiring-satellite-signal-2800-model.6536/).
- Signal-loss while running uses 025: "The satellite signal has been lost, signal acquisition is in
  progress. Please wait, or press the 'UP' or 'DOWN' arrow button to change channels." and the
  recovery message 027: "The Satellite Signal has been acquired, all Satellite channels are now
  available." (removeandreplace list).
- Software download at boot (not every boot; only when a new image is flagged): 061 "Vital Program
  Information will now be Downloaded into your receiver." (removeandreplace) / "Vital programming will
  now be downloaded into your receiver. Do not disturb or unplug it." (ecoustics 2005 list). The manual:
  "The download may take several minutes, so don't disturb or unplug the receiver" (311 guide ?page=62).
- Guide data: 023 "Unable to Acquire program guide information" is the failure case (removeandreplace).
  On the DVR models the guide is loaded to disk: 329 "Attention Your receiver is scheduled to download the
  latest program guide information to the hard disk." and 330 "ATTENTION The program guide information
  is now being downloaded to the hard disk on your receiver." (removeandreplace). The 522/625 does this
  during "Inactivity Standby" (MENU-8-8, "Activation" Enabled/Disabled, "Inactivity Duration" chosen by
  the user) so it can "fetch the latest guide data" (522 guide ?page=111).
- Check Switch at install: from Point Dish, "select Check Switch to open the Installation Summary screen.
  It shows whether the receiver is getting satellite signals and which multi-dish switches, if any, are
  installed" (311 guide ?page=58). Related dialogs: 057 "Select 'Check' to check switch installation.",
  058 "Please wait while your switch installation is checked.", 059 "You have attempted to exit this
  screen without performing 'Check Switch.'" (removeandreplace). 059's cause: "You may have tried to
  close an installation menu without doing the Check Switch test" (311 guide ?page=62).
- Point Dish screen: "A bar at the bottom shows signal strength. Green indicates a good signal. Red
  indicates the signal is unacceptable or comes from the wrong satellite", and it must read "Locked"
  (311 guide ?page=58). The 301 feature sheet lists "an audio tone used for antenna peaking"
  (https://tbh.lerctr.org/~ekb/301features.php) - see Sounds.
- Standby / "off" screen: "Whenever the receiver's outputs are turned off using the remote control or
  front panel POWER buttons, you will see the DISH Network logo moving around on your TV screen. Press the
  blank POWER or SELECT button on the remote control to resume" (522 guide ?page=10). I.e. the DISH
  Network logo bouncing screensaver is the "off" state, not a boot splash.
- Timing reference points: forum users describe the 015 screen clearing in a minute or two on a healthy
  system; a 2012 Hopper owner stuck at "progress 5 of 5" for 30 minutes was abnormal
  (https://www.satelliteguys.us/xen/threads/acquiring-satellite-signal.280101/). A 061 software load
  that persists beyond ~20 minutes means something was skipped (DBSTalk summary via search of
  https://www.dbstalk.com/threads/sorry-for-the-interruption.131440/).

**Reconstructed power-on sequence [inference, medium confidence]**

1. Plug-in: black screen (no splash on the OpenTV boxes; the "dish NETWORK / Starting up..." splash with a
   progress bar belongs to the later ViP/Linux boxes such as the 722k in the unboxing video, and the
   721/921 showed a Linux penguin - dishdude, 19 Dec 2017, UI thread page 1). The DVR models (501/508/510/
   522/625) spin up the disk first, so their black period is longer (tens of seconds) than the 301/311's.
2. Grey "ATTENTION 015" dialog box, centred, titled ATTENTION with the code, text "Acquiring satellite
   signal. Please wait." and a horizontal progress bar beneath. The bar is a fill-type bar that creeps as
   each stage (tuner lock, CA/smart-card check, data tables) completes; the Hopper's "progress 5 of 5"
   counter is the descendant of this. **[the fill-vs-loop behaviour is unverified; no source describes it
   for the 301-era boxes]**
3. If a software image is flagged: "ATTENTION 061 Vital program information will now be downloaded..."
   with its own progress bar, several minutes, then an automatic reboot back to step 2.
4. Cut straight to live video on the last-watched channel with the Program Banner shown for a few
   seconds (banner shows on every channel change - see section 2). Guide cells for channels whose data has
   not yet arrived are blank/"No information" until the carousel delivers them **[unverified wording]**.
5. On the DVRs the full guide refresh happens later in Inactivity Standby (329/330 above).


## 2. Channel change

- Three ways: UP/DOWN arrow, number pad, or GUIDE then SELECT (311 guide ?page=28; 522 guide ?page=67).
- Typed digits: "Use the remote control number pad buttons to enter the desired channel number" (311
  guide ?page=28). Three-digit channel numbers; the number pad also enters an hour count for guide
  skipping and option numbers in menus (522 guide ?page=60). Digits are echoed in the banner's channel
  capsule as you type **[inference]**; no manual describes a separate digit overlay.
- Invalid number: "You may have mistyped the number or entered an invalid one, so the receiver shows the
  nearest valid channel" (311 guide ?page=67; 522 guide ?page=148 "The channel changes, but the new
  channel is not exactly the channel you entered"). I.e. the box does NOT pop an error for a non-existent
  channel; it rounds to the nearest one in the active list.
- UP/DOWN surfing is restricted to the active Favorites list; channels not in the list are skipped, and
  "If the 'All Chan' list is active, it shows all channels. If 'All Sub' is active, it shows only
  channels in your subscription" (311 guide ?page=33, ?page=38).
- Picture between channels: a short black gap. Forum consensus for MPEG satellite boxes is "at least
  about one second" black while waiting for a keyframe; on pre-DishPro-Plus wiring, "changing between even
  and odd transponders forced the LNB to flip polarization, adding delay" (Michael P, DBSTalk Nov 2009,
  https://www.dbstalk.com/threads/blank-screen-when-changing-channels.158839/). Dish SD boxes were
  reported as taking "2 to 5 seconds sometimes" (DBSTalk Jun 2008,
  https://www.dbstalk.com/threads/delay-when-switching-channels.150879/). Audio returns with the video.
  **[inference: ~1-2 s black on the 301/311, ~2-4 s on the DVRs; no freeze-frame of the old channel]**
- Banner timing: "The receiver displays it for a few seconds at the top of the TV screen when you change
  channels or press the VIEW TV button" (522 guide ?page=69; identical wording in 311 guide ?page=33
  with "VIEW button"). There is **no user setting** for banner duration or disabling on these models: no
  Preferences entry exists in either manual's index (311 index ?page=102-103; 522 index ?page=166-168),
  and a DBSTalk reply about these banners says "These can not be disabled"
  (https://www.dbstalk.com/threads/is-there-a-way-to-remove-those-ridiculous-bottom-banners-on-the-channels.189982/).
  **[inference: ~3-4 s; the later ViP boxes added a 2-s-upward timeout setting, this generation did not]**
- Unavailable (not-subscribed) channel: a grey dialog, code 013: "This is a subscription channel which
  has not been purchased." (removeandreplace; ecoustics 2005). The manual's cause/fix: "You may have
  tuned to a channel you haven't purchased. Buy the channel through the Customer Service Center" (311
  guide ?page=61). The companion purchase prompt is 029: "To purchase, please call the customer service
  center at: 1-800-333-DISH (3474)." (removeandreplace). In the guide, such channels are drawn on a
  **red** background: "A red background behind a channel means you are not subscribed to it, and you
  cannot tune to it" (311 guide ?page=31); subscribed channels "appear in white" (522 guide ?page=12).
- Blacked-out program: 011/012 "This program has been blacked out in your area." (removeandreplace).
- Not-authorized receiver: 022 "Your receiver has not yet been authorized." and 005 "Your Smart Card does
  not currently have authorization to view or purchase this program." (removeandreplace; ecoustics 2005).
- Locked channel/program: 076 "This event is locked: To view, enter your password." (removeandreplace).
  "If you try to access a locked item ... the receiver displays a message prompting you to enter the
  password. The receiver allows you three tries ... If you fail ... the receiver does not allow more
  tries for several minutes" (311 guide ?page=48). Wrong password: 072 "The password you just entered
  was not correct."; retries exceeded: 074 "The number of password entry retries has been exceeded."
  (removeandreplace). Message 074's lockout: "After three failed attempts, it times out and blocks
  further tries for several minutes" (311 guide ?page=62).
- Last channel was locked/blacked out (DVR / PIP context): 690 "Attention the last channel was locked,
  blacked out, or not purchased." (removeandreplace).
- RECALL: "Press the RECALL button to go back to the last satellite receiver channel you were watching.
  Pressing it again switches between the last two channels you watched" (522 guide ?page=59). The 311
  guide's troubleshooting: "Press the remote's 'Recall' button to return to the previous channel" (311
  guide ?page=67). It is a two-channel toggle, not a history list (the history list arrived with the
  Hopper's "Show Last 6 Channels" setting, DBSTalk
  https://www.dbstalk.com/threads/dish-previous-channels.233234/).
- VIEW TV: "close all menus and go to watching programming"; a press while watching shows the Program
  Banner (522 guide ?page=60). CANCEL: "cancel and go back to the previous menu or to watch a program"
  (522 guide ?page=60).


## 3. Banner details

**Program Banner (auto on channel change / VIEW)**

- Position and life: "at the top of the TV screen", "for a few seconds" (311 guide ?page=33; 522 guide
  ?page=69). It "provides information about the program you are watching".
- Transparency: the 311 feature list says "On-screen transparent channel and program information banner"
  (https://www.manualsdir.com/manuals/275677/toner-cable-311-digital-satellite-receiver.html); the 301
  sheet says "Transparent Info Pages - allows continued viewing of a program while information about the
  program is displayed" and "transparent channel banners superimposed across the bottom of the screen"
  for surfing (https://tbh.lerctr.org/~ekb/301features.php).
- Contents (from the INFO description on the 301 sheet and the guide pages): channel number and channel
  call-sign/name capsules, programme title, "start and end times and, when available, a brief
  description" (EKB 301 sheet). The guide (and by extension the banner's clock) shows "current time, date,
  and channel number" (EKB 301 sheet: "1/4 screen current time, date, and channel number" in the
  picture-in-guide view). Clock/date format: **[inference]** 12-hour with am/pm and a short
  weekday/month-day date, matching the guide header of the OpenTV UI; no source states the format.
- Rating: program ratings are used by the Locks ("Rating (Content) Code Locks", 311 guide index ?page=102)
  and so are carried in the event data; the banner shows the rating capsule **[inference, medium]**.
- Favorites name: the active list name is shown on the Browse Banner and guide: the Browse Banner "shows
  only the channels in the active Favorites List, which the banner indicates" (311 guide ?page=33); "The
  Program Guide shows which Favorites List is active" (522 guide ?page=67). Lists are "All Chan",
  "All Sub", and four user lists whose default names are "List 1" to "List 4"; "Each list has its own
  color in the Program Guide and can be renamed" (311 guide ?page=38). Later Dish manuals cap names at
  eight characters (411 guide via search); the 311 guide does not state a limit.
- Ground colour: the OpenTV UI's page ground is grey with blue selection "pills"; the highlight on these
  boxes is described as "lighter than the other options" (311 guide ?page=29) and, on the 522, "The
  highlighted option turns amber" (522 guide ?page=64). **[The grey/blue palette itself is from the
  screenshots I could not open; treat as the requester's premise, consistent with the "transparent"
  descriptions above.]**

**INFO (expanded)**

- "Press the INFO button for more information when you watch a program" (522 guide ?page=59). On the 522:
  "The first time you press the INFO button, the information screen is transparent"; pressing INFO again
  makes it solid, a third press closes it (522 guide ?page=13). On the 311, INFO shows the page and
  CANCEL returns (311 guide ?page=32). Content: title, start/end times, description, and for movies the
  year ("do you want to know when the movie you're about to watch was made? ... press INFO", 522 guide
  ?page=70).

**Browse Banner (RIGHT ARROW)**

- "Press the RIGHT ARROW button to open the Browse Banner for the current program"; "Information about
  your current program appears at the top of the screen. Browse Banner information appears at the
  bottom" (311 guide ?page=33). On the 522 the bottom part shows "information on two other programs"
  (522 guide ?page=13).
- Navigation: UP/DOWN or number pad changes the channel shown in the bottom half; RIGHT ARROW steps to
  the program "on next on the same channel" (one step only on the 311: "It does not display information
  for any other programs in the future"); LEFT returns; INFO expands; SELECT tunes; CANCEL (or VIEW TV)
  closes and "The receiver stays tuned to the program you are watching" (311 guide ?page=34; 522 guide
  ?page=70). Choosing a future program opens "Create An Event Timer" (311) / "a Timers menu" (522).
- The 522's RIGHT ARROW is labelled BROWSE and LEFT ARROW is THEMES (522 guide ?page=59).

**Program Guide (for the banner's sibling colours)**

- Red background = channel not in subscription; white = subscribed (311 guide ?page=31; 522 guide
  ?page=12). Guide shows now + 2 days on the 301/311 ("view programming information 2 full days into the
  future", EKB; 311 guide ?page=31) and "several days" on the 522 (522 guide ?page=67). "Partial Guide
  With Video" (quarter-screen video) or "Full Guide Without Video" (311 guide ?page=31). Guide can be
  ordered ascending/descending under System Setup (311 guide ?page=31). GUIDE pressed repeatedly cycles
  the Favorites list (311 guide ?page=38; 522 guide ?page=58).

**Pay-Per-View purchase page**

- Flow: "Select a Pay-Per-View program in the Program Guide. A message appears"; "To buy, choose the
  'Yes' option. The receiver then shows a confirmation menu"; "Once you confirm, you can't cancel ...
  you will be billed for it" (522 guide ?page=71). The 301 sheet calls it "Impulse Pay-Per-View with
  On-Screen Purchase Summary" (EKB) and the 311 list "pay-per-view on-screen purchase summary" (Toner
  311 page). Related dialogs: 084 "Dish-On-Demand. To purchase, press 'SELECT'.", 085 "You have indicated
  that you wish to purchase a Dish-On-Demand event.", 086 "This is a Dish-On-Demand event which you have
  already purchased.", 007 "Your purchase of this event is in the process of being authorized.", 006
  "Your purchase request cannot be completed.", 018 "The credit limit on your smart card has been
  exceeded.", 028 "Pay Per View Events cannot be purchased until the receiver has downloaded new
  software.", 030 "This is a special event which is not available for purchase." (removeandreplace list).
  Phone-line nags: 079 "Please connect your receiver to your phone line or your ability to purchase PPV
  will be disabled in the future." (removeandreplace). "Dish-On-Demand" was the PPV brand name on these
  boxes before DISH On Demand VOD.
- Locks on PPV: "Locking Pay Per View Programs" (311 guide index, printed p.47).


## 4. Sounds

- **No UI sounds are documented for the OpenTV boxes.** Neither user guide has any entry for beep, tone,
  sound, click or audio feedback in its index (311 index ?page=102-103; 522 index ?page=166-168), the
  remote-setup pages confirm success with "the mode button flashes three times" rather than a beep (311
  guide ?page=15, ?page=16), and the Preferences menu has no sound option (522 guide ?page=18: it only
  "allows you to set up your receiver to make it easier to use"). Forum searches of DBSTalk/SatelliteGuys
  for 301/501/508/522 + beep/chime turned up only remote-pairing and UHF-remote beeps on later Hopper
  hardware. **[inference, high confidence: button presses, menu moves, channel changes, the Attention
  dialogs and the locked/unavailable-channel dialogs are all silent; the only audio is programme audio,
  which mutes during the black gap and on a not-authorized channel.]**
- **The one real tone: Point Dish signal-meter audio.** The 301 feature sheet lists "an audio tone used for
  antenna peaking" (https://tbh.lerctr.org/~ekb/301features.php). On the Point Dish / Signal screen the
  receiver outputs a tone through the audio outputs so an installer can peak the dish by ear; the
  Bell/EchoStar and FTA descendants keep the same "Tone" idea on the signal meter
  (https://www.satelliteguys.us/xen/threads/signal-beeping-sound.288891/, FTA context). Character:
  **[inference from installer practice]** a repeating beep whose rate/pitch rises with the signal-strength
  bar; on only while the Point Dish screen is open; no user setting on the 301/311 (the FTA "Tone <on>"
  setting is not in the Dish manuals).
- **Remote-control beeps**: none on the 301/311/322/501/508/522 IR/UHF remotes (3.0/3.4/4.4/5.x). The
  three-beep pairing confirmation belongs to the 2010s 40.0/50.0/54.x remotes (search summaries only).
- **Modern-day sample**: none found. The DP301 videos above are the only recordings of a live box I
  located; they have no descriptions and I could not play them. If a sample is needed, "DP301 experience"
  (https://www.youtube.com/watch?v=u2reTJkXjRo, 0:36) is the one to scrub for channel-change audio.


## Menu structure facts picked up on the way (useful for the "grey page, blue pill" screens)

- Main Menu is "the key to the menus"; options are numbered and "To quickly go to any menu option with a
  number next to it, just press the numbers on the remote that match that number" (311 guide ?page=22,
  ?page=29). Known numbers: Favorites = 3, System Setup = 6, Installation = 6-1, Point Dish = 6-1-1,
  Preferences = 8, Inactivity Standby = 8-8 (311 guide ?page=58; 522 guide ?page=18, ?page=111).
- Menus auto-close: "The menu closes if you do not do anything in a menu for several minutes" and unsaved
  changes are lost (311 guide ?page=28; 522 guide ?page=64).
- List widgets: single-choice vs multiple-choice lists; changes apply only on Save/OK; "black arrows on
  the list show the possible directions" (311 guide ?page=29).
- Favorites error dialogs (OpenTV wording): 062 "You Cannot Modify the 'All Channels' List", 064
  "Duplicate favorites list names are not allowed", 066 "The favorites list you are attempting to save
  contains no channels." (removeandreplace); manual: "The receiver shows an 'ERROR' message" for both
  cases (311 guide ?page=67).
- DISH button opens "dish home Interactive TV" (522 guide ?page=60); on the 311 "You can order channels,
  check the news and weather, and even play games" (311 guide ?page=37). Dish Home lived on channel 100.
- Caller ID pop-ups on the 322/522 can be disabled at MENU-6-1-6 (DBSTalk thread 189982, above).
- Front panel: the 322/522 show "Mode" Single/Dual LEDs; 522 remote 1 (green) drives TV1, remote 2
  (blue) drives TV2 (522 guide ?page=28, ?page=168).


## Confidence

| Item | Confidence | Why |
|---|---|---|
| Attention-dialog wording for 013/015/022/025/027/061/076/011 | High | Two independent code lists (2005 forum, 2017 list) plus Bell's EchoStar page agree, typos aside |
| 015 shown at every cold boot; "wait a few minutes" | High | Manual text (311 ?page=62, 522 ?page=142) plus owner report |
| Progress bar look/behaviour on the 015 box | Low | No text source describes it; needs a frame from the DP301 videos |
| No boot splash on OpenTV boxes; splash is ViP-era | Medium | Thread evidence only (721 penguin, 722k "Starting up"); no 301 frame seen |
| Banner at top, "a few seconds", shown on change and VIEW | High | Both manuals, identical wording |
| No banner-duration setting on these models | Medium-high | Absent from both indexes; later ViP boxes added one |
| Banner content fields (ch no./name, title, times, description) | Medium | From the 301 feature sheet's INFO description; layout not seen |
| Clock/date format, rating capsule | Low | Inference only |
| Favorites list name shown on banner/guide; "All Chan"/"All Sub"/"List 1-4" | High | 311 guide ?page=33, ?page=38 |
| Browse Banner layout (current at top, next/other at bottom) | High | 311 ?page=33, 522 ?page=13 |
| INFO three-state (transparent, solid, close) | High for 522; Medium for 311 | 522 ?page=13 explicit; 311 only says INFO then CANCEL |
| Invalid number rounds to nearest valid channel, no dialog | High | Both troubleshooting tables |
| Recall = two-channel toggle | High | 522 ?page=59 |
| Black gap ~1-2 s (SD) / 2-5 s (DVR), no freeze | Medium | Forum descriptions, mostly of later HD boxes |
| PPV flow (message, Yes, confirmation menu, cannot cancel) | High | 522 ?page=71 |
| Silent UI | Medium-high | Argument from absence across two manuals and forum searches |
| Point Dish peaking tone exists on the 301 | High | EKB feature sheet |
| Peaking tone character (rate/pitch with signal) | Low | Inference |
| Grey page / blue pill palette | Not independently verified | Screenshots located but not viewable this session |

Research limits this session: DBSTalk and AVS Forum thread bodies are behind a tollbit paywall for the
fetch tool (402/403), so forum facts above come from search-engine summaries or the few threads that
loaded; the browser pane stayed hidden, so no YouTube frames or image attachments could be inspected; the
shared web-search budget ran out before I could search for 2001-2003 magazine reviews of the 501 or for a
clean audio sample. The three screenshot URLs and four video URLs above are the next things to open.
