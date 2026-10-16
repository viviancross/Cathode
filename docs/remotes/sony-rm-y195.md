# Sony RM-Y195 with a FLIRC

The RM-Y195 is the remote of Sony's 2004 FD Trinitron WEGA sets (KV-27FS120,
KV-32FS120 and their siblings). A [FLIRC](https://flirc.tv) USB receiver
learns its buttons and types keys; Cathode reads those keys like a keyboard.

## 1. Pick the remote's mode

Press the remote's **SAT/CABLE** button (one of the FUNCTION buttons at the
top) and leave it there. Everything below is recorded in that mode.

- Not **TV** mode: the Sony TV would answer every button too (its own menu,
  channels, inputs).
- **GUIDE** only sends in SAT/CABLE mode.
- **VOL+ / VOL- / MUTING** keep working the TV in any mode. Don't record
  them; let the TV do the volume.

## 2. Record the buttons

In the FLIRC software, choose **Controllers > Full Keyboard**. For each row,
click the key on the on-screen keyboard, then press the button on the
remote.

| RM-Y195 button | Key to record | What it does in Cathode |
|---|---|---|
| 0-9 | 0-9 | Channel numbers |
| ENTER | Enter | Select; tunes a typed number |
| Centre button | Enter | Select |
| Arrows | Arrow keys | Move. On live TV, up/down change channel |
| CH+ / CH- | `]` / `[` | Channel up/down; page the guide |
| MENU | C | Menu |
| GUIDE | G | Guide |
| DISPLAY | I | Banner; again for the description |
| JUMP | P | Last channel |
| RESET | Backspace | Back |
| TV/VIDEO | Esc | Exit |
| PLAY | Space | Play/pause |
| PAUSE | Space | Play/pause |
| STOP | X | Stop; back to live |
| REW | , (comma) | Back 10 seconds |
| FF | . (period) | Forward 30 seconds |
| REC | L | My Recordings |
| SLEEP | F | Add/remove the channel from Favorites |
| TV/SAT | B | Browse / mini guide |
| PICTURE MODE | A | Picture format |
| MTS/SAP | S | Subtitles |

Watch the TV while you record:

- If a button makes the TV react as well (for example TV/VIDEO switches the
  TV's input, or SLEEP sets its sleep timer), it is still sending a TV code
  in SAT/CABLE mode. Leave it unrecorded, and give its job to a spare button
  under Cathode's **Settings > Remote control > Keyboard keys**.
- The play, stop and search buttons may only send in **VCR/DVD** mode. If
  the FLIRC software doesn't see one in SAT/CABLE mode, you can record it in
  VCR/DVD mode, or skip it. On Demand plays fine without them: the centre
  button pauses, left/right search and RESET stops.
- If one press registers twice, raise the FLIRC's inter-key delay in its
  advanced settings.

## 3. Tell Cathode

**MENU > Settings > Remote control > Remote: Sony RM-Y195.** The hints on
screen then name the Sony's buttons (ENTER, DISPLAY, RESET, TV/VIDEO...)
instead of Cathode's.
