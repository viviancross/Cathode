"""Selection / on-air text must stay readable on every shipped theme.

Guards the _ink() derivation in theme._build: the selection and on-air fills
track the accent color, so light-accent themes (mono, ice) need dark ink where
fixed white text used to fall below 2:1.
"""

import unittest

from cathode.ui import theme


class TestThemeContrast(unittest.TestCase):
    def test_selection_and_onair_text_contrast(self):
        for name, pal in theme.PALETTES.items():
            for text_key, fill_key in (("SEL_TEXT", "GUIDE_SELECTED"),
                                       ("SEL_TEXT_DIM", "GUIDE_SELECTED"),
                                       ("ONAIR_TEXT", "GUIDE_ONAIR")):
                ratio = theme.contrast(pal[text_key][:3], pal[fill_key][:3])
                self.assertGreaterEqual(
                    ratio, 3.0,
                    f"{name}: {text_key} on {fill_key} is {ratio:.2f}:1")

    def test_muted_ink_is_readable_on_every_surface_it_lands_on(self):
        # INK_MUTED replaced a flat (130,130,140) that measured 3.15:1 on c64
        # and ~4.4:1 on amber and green. It is body-sized text (metadata, hints,
        # captions), so 4.5:1 is the bar, on every ground it is drawn over.
        surfaces = ("SCREEN_BG", "OSD_BG", "GUIDE_ROW_ODD", "GUIDE_ROW_EVEN",
                    "GUIDE_BG")
        for name, pal in theme.PALETTES.items():
            for surf in surfaces:
                ratio = theme.contrast(pal["INK_MUTED"][:3], pal[surf][:3])
                self.assertGreaterEqual(
                    ratio, 4.5,
                    f"{name}: INK_MUTED on {surf} is {ratio:.2f}:1")

    def test_muted_ink_belongs_to_its_theme(self):
        # The point of deriving it: a cool gray in Amber CRT's warm world read
        # as another app's text. No two themes may share the same muted ink.
        inks = {name: pal["INK_MUTED"] for name, pal in theme.PALETTES.items()}
        self.assertEqual(len(set(inks.values())), len(inks), inks)

    def test_primary_button_label_is_readable(self):
        # Button labels shrink to fit their box (_fitted_btn_font can reach
        # ~10px on a six-button row), so they are held to the body bar, not the
        # large-text one.
        for name, pal in theme.PALETTES.items():
            ratio = theme.contrast(pal["BTN_PRIMARY_TEXT"][:3],
                                   pal["BTN_PRIMARY_BG"][:3])
            self.assertGreaterEqual(
                ratio, 4.5, f"{name}: primary label is {ratio:.2f}:1")

    def test_primary_button_is_distinguishable_from_a_secondary_one(self):
        # Primacy is carried by the ground: if it matched the ordinary panel,
        # the primary action would be invisible whenever focus sat elsewhere.
        for name, pal in theme.PALETTES.items():
            ratio = theme.contrast(pal["BTN_PRIMARY_BG"][:3], pal["OSD_BG"][:3])
            self.assertGreaterEqual(
                ratio, 1.2, f"{name}: primary ground is {ratio:.2f}:1 vs panel")

    def test_track_recedes_behind_its_own_fill(self):
        # TRACK is the unfilled part of a progress/volume bar, not an ink. It
        # must stay well under the filled portion or the bar reads as full.
        for name, pal in theme.PALETTES.items():
            track = theme.contrast(pal["TRACK"][:3], pal["OSD_BG"][:3])
            fill = theme.contrast(pal["GREEN"][:3], pal["OSD_BG"][:3])
            self.assertLess(track, fill,
                            f"{name}: TRACK ({track:.2f}) rivals its fill")

    def test_a_custom_palette_gets_the_same_guarantees(self):
        # The theme editor can build arbitrary palettes; the derivations have to
        # hold there too, which is why they are solved rather than tabulated.
        theme.set_custom_palette(bg=(90, 88, 96), accent=(200, 198, 205),
                                 accent2=(210, 205, 180), text=(235, 235, 240))
        pal = theme.PALETTES["custom"]
        for surf in ("SCREEN_BG", "OSD_BG", "GUIDE_BG"):
            ratio = theme.contrast(pal["INK_MUTED"][:3], pal[surf][:3])
            self.assertGreaterEqual(ratio, 4.5,
                                    f"custom: INK_MUTED on {surf} {ratio:.2f}:1")
        self.assertGreaterEqual(
            theme.contrast(pal["BTN_PRIMARY_TEXT"][:3],
                           pal["BTN_PRIMARY_BG"][:3]), 4.5)
        theme.apply_theme("blue")          # leave the default installed

    def test_screen_bg_darker_than_theme_bg(self):
        # SCREEN_BG is the full-page backdrop; it must stay near-black so the
        # OSD_BG panels drawn on it keep their contrast.
        for name, pal in theme.PALETTES.items():
            self.assertLess(theme._lum(pal["SCREEN_BG"][:3]), 0.05,
                            f"{name}: SCREEN_BG too bright")


if __name__ == "__main__":
    unittest.main()
