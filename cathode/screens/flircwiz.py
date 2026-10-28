"""The FLIRC wizard: one flirc_util step after another ('Press the button
for Guide'), each waiting for a remote button. RIGHT skips a step, BACK or
EXIT stops. Drawn as the skins' remap dialog. The test screen names each
button the remote types."""

from .. import remote as R
from ..app import Screen
from ..flirc import Flirc

HELP = "RIGHT (the key) skips a button, Esc stops"


class FlircWizard(Screen):
    name = "capture"

    def __init__(self, app, steps, on_done=None):
        """steps: [(prompt, flirc_util args)]."""
        super().__init__(app)
        self.steps, self.i, self.on_done = list(steps), 0, on_done
        self.done_count, self.skipped = 0, []
        self.flirc = Flirc(app)
        self.prompt = ""
        if len(self.steps) > 1:
            app.toast(HELP, 5)
        app.after(0, self._start)           # once pushed: a missing tool ends it at once

    def _start(self):
        if self.i >= len(self.steps):
            self._finish()
            return
        label, args = self.steps[self.i]
        self.prompt = label
        self.app.invalidate()
        self.flirc.run(args, self._got)

    def _got(self, ok, text):
        if self not in self.app.screens:
            return
        label = self.steps[self.i][0]
        if ok:
            self.done_count += 1
            self.app.toast(f"{label.split(' for ', 1)[-1]}: done")
            self.i += 1
        else:
            self.app.toast(text, 4)
            if text.startswith("flirc_util not found"):
                self._finish(report=False)              # no tool: nothing more will work
                return
        self._start()                                   # again on an error (a button already used)

    def _finish(self, report=True):
        self.flirc.cancel()
        self.app.pop(self)
        if self.on_done and report:
            self.on_done(self.done_count, self.skipped)

    def handle(self, a: str) -> bool:
        if a == R.RIGHT and self.i < len(self.steps):
            self.skipped.append(self.steps[self.i][0])
            self.i += 1
            self._start()
        elif a in (R.BACK, R.EXIT):
            self._finish()
        return True


class FlircTest(Screen):
    """Press buttons: each names itself. Watch the TV too."""
    name = "capture"

    def __init__(self, app, names):
        super().__init__(app)
        self.names = names
        self.prompt = "Press the remote's buttons (Esc ends)"
        app.toast("Each button names itself. Watch the TV too: forget a button it answers.", 6)

    def handle(self, a: str) -> bool:
        if a == R.EXIT:
            self.app.pop(self)
        else:
            self.prompt = f"{self.names.get(a, a)}  ({self.app.key_name(a) or '-'})"
            self.app.invalidate()
        return True
