import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageChops

from pipeline import infographic as ig


class ExtractStatTest(unittest.TestCase):
    def test_percent_wins_and_keeps_original_text(self):
        s = ig.extract_stat("Chip memakai energi 48 persen lebih sedikit dan dibuat pada 3 nanometer")
        self.assertEqual((s.kind, s.text, s.value), ("percent", "48", 48.0))
        self.assertEqual(s.display, "48%")

    def test_percent_sign(self):
        s = ig.extract_stat("Naik 12,5% dibanding tahun lalu")
        self.assertEqual((s.kind, s.text, s.value, s.decimals), ("percent", "12,5", 12.5, 1))

    def test_plain_quantity_with_unit(self):
        s = ig.extract_stat("Dibuat pada 3 nanometer")
        self.assertEqual((s.kind, s.text, s.unit), ("number", "3", "nanometer"))

    def test_thousands_separator(self):
        s = ig.extract_stat("Diuji pada 1.200 gambar")
        self.assertEqual((s.kind, s.value, s.grouped, s.unit), ("number", 1200.0, True, "gambar"))
        self.assertEqual(s.display_at(0.5), "600")
        self.assertEqual(ig.extract_stat("Ada 12.500 perangkat").display_at(0.5), "6.250")

    def test_year_is_last_resort_and_never_counts_up(self):
        s = ig.extract_stat("Diumumkan pada 2025 lalu")
        self.assertEqual(s.kind, "year")
        self.assertEqual(s.display_at(0.2), "2025")
        s2 = ig.extract_stat("Pada 2025 ada 7 pusat data")
        self.assertEqual((s2.kind, s2.text), ("number", "7"))

    def test_no_number(self):
        self.assertIsNone(ig.extract_stat("Tahukah kamu chip ini bisa berpikir lebih cepat"))

    def test_final_frame_shows_exact_original_text(self):
        s = ig.extract_stat("Hemat 48 persen")
        self.assertEqual(s.display_at(1.0), "48%")
        self.assertEqual(s.display_at(0.0), "0%")


class FramesTest(unittest.TestCase):
    def _still(self, d):
        im = Image.new("RGB", (270, 480), (200, 120, 60))
        for y in range(480):
            for x in range(0, 270, 9):
                im.putpixel((x, y), (200 - y // 4, 120, 60 + y // 5))
        p = Path(d) / "still.png"
        im.save(p)
        return p

    def test_frame_count_size_and_animation(self):
        with tempfile.TemporaryDirectory() as d:
            still = self._still(d)
            out = Path(d) / "s00"
            stat = ig.extract_stat("Hemat 48 persen daya")
            n = ig.render_scene_frames(still, out, 40, 30, "Hemat Daya", stat, lead=0.2, accent="#FFC53D", move="push", workers=1)
            files = sorted(out.glob("f_*.jpg"))
            self.assertEqual((n, len(files)), (40, 40))
            first, mid, last = (Image.open(files[i]) for i in (0, 20, 39))
            self.assertEqual(first.size, (1080, 1920))
            # the card is not there at the very start but is there later -> frames differ in the text zone
            zone = (0, ig.SceneRenderer.ZONE_Y, 1080, ig.SceneRenderer.ZONE_Y + ig.SceneRenderer.ZONE_H)
            self.assertIsNotNone(ImageChops.difference(first.crop(zone), last.crop(zone)).getbbox())
            self.assertIsNotNone(ImageChops.difference(first, last).getbbox())   # Ken-Burns moves too

    def test_keyword_card_and_outro_without_text(self):
        with tempfile.TemporaryDirectory() as d:
            still = self._still(d)
            a = Path(d) / "a"
            ig.render_scene_frames(still, a, 30, 30, "Keamanan siber untuk semua", None, 0.2, "#FFC53D", "orbit", workers=1)
            b = Path(d) / "b"
            ig.render_scene_frames(still, b, 30, 30, "", None, 0.2, "#FFC53D", "pull", workers=1)
            self.assertEqual(len(list(a.glob("*.jpg"))), 30)
            zone = (0, ig.SceneRenderer.ZONE_Y, 1080, ig.SceneRenderer.ZONE_Y + ig.SceneRenderer.ZONE_H)
            ia, ib = Image.open(a / "f_0030.jpg").crop(zone), Image.open(b / "f_0030.jpg").crop(zone)
            self.assertIsNotNone(ImageChops.difference(ia, ib).getbbox())

    def test_multiprocessing_matches_single_worker_count(self):
        with tempfile.TemporaryDirectory() as d:
            still = self._still(d)
            out = Path(d) / "mp"
            ig.render_scene_frames(still, out, 48, 30, "Uji", ig.extract_stat("Diuji 5 kali"), 0.2, "#FFC53D", "push", workers=2)
            self.assertEqual(len(list(out.glob("f_*.jpg"))), 48)


if __name__ == "__main__":
    unittest.main()
