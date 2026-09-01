"""CATHODE_FONTS_DIR: find the bundled fonts when the package isn't on disk.

theme.py normally locates assets/fonts by walking up from its own __file__.
That assumption breaks wherever the package is served from an archive rather
than a directory — on Android, Chaquopy keeps the .py files inside the APK and
extracts data files elsewhere, so the two are not siblings. Without the
override the retro pixel fonts silently fall back to a system sans, which looks
like a styling bug rather than a packaging one.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode.ui import theme


class TestFontDirOverride(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._saved = os.environ.get("CATHODE_FONTS_DIR")

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("CATHODE_FONTS_DIR", None)
        else:
            os.environ["CATHODE_FONTS_DIR"] = self._saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_unset_leaves_the_normal_search_untouched(self):
        os.environ.pop("CATHODE_FONTS_DIR", None)
        self.assertEqual(theme._font_search_dirs(), theme._FONT_DIRS)

    def test_the_override_is_searched_first(self):
        os.environ["CATHODE_FONTS_DIR"] = self.tmp
        dirs = theme._font_search_dirs()
        self.assertEqual(dirs[0], self.tmp)
        # and must not lose the built-in locations
        self.assertEqual(dirs[1:], list(theme._FONT_DIRS))

    def test_a_font_in_the_override_dir_is_found(self):
        # Any file with a registry name will do; _find_font only matches names.
        open(os.path.join(self.tmp, "VCR_OSD_MONO.ttf"), "wb").close()
        os.environ["CATHODE_FONTS_DIR"] = self.tmp
        self.assertEqual(theme._find_font("VCR_OSD_MONO.ttf"),
                         os.path.join(self.tmp, "VCR_OSD_MONO.ttf"))

    def test_the_override_is_read_per_call_not_at_import(self):
        # theme was imported long before this test set the variable; if the
        # lookup were cached at import, a packager setting it later would be
        # silently ignored — which is exactly the bug this guards against.
        open(os.path.join(self.tmp, "VCR_OSD_MONO.ttf"), "wb").close()
        os.environ.pop("CATHODE_FONTS_DIR", None)
        before = theme._font_search_dirs()
        os.environ["CATHODE_FONTS_DIR"] = self.tmp
        self.assertNotEqual(theme._font_search_dirs(), before)


class TestAssetsDirOverride(unittest.TestCase):
    """CATHODE_ASSETS_DIR: the same problem, one directory up.

    The home screen's logo is found by the same walk-up from __file__, and fails
    the same way — the screen just came up without it, which reads as a missing
    asset rather than a packaging one.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._saved = os.environ.get("CATHODE_ASSETS_DIR")

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("CATHODE_ASSETS_DIR", None)
        else:
            os.environ["CATHODE_ASSETS_DIR"] = self._saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_the_logo_is_found_in_the_override_dir(self):
        from cathode.ui import mainmenu
        logo = os.path.join(self.tmp, "cathode.png")
        open(logo, "wb").close()
        os.environ["CATHODE_ASSETS_DIR"] = self.tmp
        self.assertEqual(mainmenu._logo_path(), logo)

    def test_the_override_is_read_per_call_not_at_import(self):
        from cathode.ui import mainmenu
        logo = os.path.join(self.tmp, "cathode.png")
        open(logo, "wb").close()
        os.environ.pop("CATHODE_ASSETS_DIR", None)
        self.assertNotEqual(mainmenu._logo_path(), logo)
        os.environ["CATHODE_ASSETS_DIR"] = self.tmp
        self.assertEqual(mainmenu._logo_path(), logo)

    def test_an_override_without_the_logo_falls_through(self):
        os.environ["CATHODE_ASSETS_DIR"] = self.tmp
        from cathode.ui import mainmenu
        # The repo's own assets/cathode.png is still there to be found.
        self.assertNotEqual(mainmenu._logo_path(),
                            os.path.join(self.tmp, "cathode.png"))


if __name__ == "__main__":
    unittest.main()
