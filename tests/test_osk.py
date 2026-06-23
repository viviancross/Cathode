import unittest

from cathode.ui.osk import OnScreenKeyboard


class TestOSKCursor(unittest.TestCase):
    def _k(self, initial=""):
        k = OnScreenKeyboard(1280, 720)
        k.show("prompt", initial)
        return k

    def test_show_puts_caret_at_end(self):
        self.assertEqual(self._k("abc").cursor, 3)

    def test_insert_at_caret(self):
        k = self._k("abc")
        k.cursor_left(); k.cursor_left()   # caret between a and b
        self.assertEqual(k.cursor, 1)
        k.insert("X")
        self.assertEqual(k.text, "aXbc")
        self.assertEqual(k.cursor, 2)

    def test_backspace_at_caret(self):
        k = self._k("abcd")
        k.cursor_left()                    # caret before d
        k.backspace()                      # deletes c
        self.assertEqual(k.text, "abd")
        self.assertEqual(k.cursor, 2)

    def test_cursor_clamps(self):
        k = self._k("ab")
        for _ in range(5):
            k.cursor_left()
        self.assertEqual(k.cursor, 0)
        for _ in range(9):
            k.cursor_right()
        self.assertEqual(k.cursor, 2)

    def test_clr_resets_caret(self):
        k = self._k("abc")
        k._activate("CLR")
        self.assertEqual(k.text, "")
        self.assertEqual(k.cursor, 0)


if __name__ == "__main__":
    unittest.main()
