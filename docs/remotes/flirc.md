# Any remote, through a FLIRC

A [FLIRC](https://flirc.tv) USB receiver learns a remote's buttons and types
keys; Cathode reads the keys like a keyboard. Cathode's wizard does the
teaching, button by button, under **MENU > Settings > Remote control >
FLIRC receiver**.

## Before you start

1. Install the Flirc software from flirc.tv on the computer Cathode runs on.
   The wizard drives its command-line tool, `flirc_util`, which the
   installer puts in the usual place (on Windows `C:\Program Files
   (x86)\Flirc`; on Linux on the PATH; on a Mac inside Flirc.app). Somewhere
   else, give its path in `config.json` as `"flirc_util"`.
   In the Flatpak, Cathode runs the host's `flirc_util`: install it on the
   Deck itself (Flirc's Linux download has a plain binary; put it in
   `~/.local/bin`).
2. Plug the FLIRC in.
3. **A TV remote: pick a mode the TV ignores** (SAT/CABLE, DVD, VCR, AUX,
   whatever the remote has) and leave it there. In TV mode the TV answers
   every button along with Cathode: its own menu, channels and inputs. This is
   the "crosstalk" the wizard's test step is for, below.

## The wizard

- **Set up every button**: the walk-through. Cathode names a button
  ("Press the button for Guide"; with a Remote chosen, that remote's own
  name, "Press DISPLAY for Info"), you press it on the remote, and the next
  comes up. The **RIGHT arrow key** (or a pad's right) skips one, **Esc**
  stops. Volume and mute come last: on a TV remote, skip them and let the TV
  do the volume.
- **Record one button**: one of the list, for a button you skipped or want
  moved.
- **Forget a button**: press a button and the FLIRC drops it.
- **Test the buttons**: press anything; the dialog names what Cathode got.
  **Watch the TV while you do.** A button the TV reacts to as well is still
  sending a TV code in the mode you chose (on many TV remotes volume, mute,
  power, input and the picture/sound buttons do, in every mode). Forget it,
  and give its job to a spare button with Record one button.
- **Turn off built-in profiles**: the FLIRC answers a few remotes out of the
  box (Fire TV, Harmony's Flirc profile, Media Center). If stray keys turn up
  from another remote in the room, turn them off; only your recorded buttons
  type then. (`flirc_util profiles enable` brings them back.)
- **Erase the FLIRC**: every button, for starting over.

A button already recorded can't be recorded again; the wizard says so and
waits for another. Forget it first to move it.

## After

If one press registers twice, raise the FLIRC's inter-key delay in the Flirc
software's advanced settings. With a Remote chosen under Settings > Remote
control, the hints on screen use that remote's button names; if you gave a
job to a different button than the profile names, the hint still shows the
profile's name.

The keys the wizard records are the ones under **Settings > Remote control >
Keyboard keys**: change a key there first and the FLIRC learns that key.
