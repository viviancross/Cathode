"""A QR code on the screen (the phone remote's address): point a phone's
camera at it. Any of OK, BACK, EXIT or MENU puts it away."""

from .. import qr, remote as R
from ..app import Screen


class QrCode(Screen):
    name = "qr"

    def __init__(self, app, text: str, title: str = "", caption: str = ""):
        super().__init__(app)
        self.text, self.title, self.caption = text, title, caption
        self.modules = qr.encode(text)

    def video_box(self):
        return "full"

    def handle(self, a: str) -> bool:
        if a in (R.SELECT, R.BACK, R.EXIT, R.MENU):
            self.app.pop(self)
            return True
        return a not in (R.VOL_UP, R.VOL_DOWN, R.MUTE, R.FULLSCREEN, R.QUIT)
