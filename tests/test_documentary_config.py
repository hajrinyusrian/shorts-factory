import unittest
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]


class DocumentaryConfigTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))

    def test_vertical_full_hd_delivery(self):
        self.assertEqual(self.cfg["video"]["width"], 1080)
        self.assertEqual(self.cfg["video"]["height"], 1920)
        self.assertEqual(self.cfg["video"]["fps"], 30)

    def test_documentary_runtime(self):
        self.assertEqual(self.cfg["video"]["min_seconds"], 120)
        self.assertEqual(self.cfg["video"]["max_seconds"], 180)
        self.assertGreaterEqual(self.cfg["script"]["total_words"][0], 300)
        self.assertGreaterEqual(self.cfg["script"]["min_scenes"], 10)

    def test_hybrid_blueprint_mode(self):
        self.assertEqual(self.cfg["render3d"]["mode"], "still")
        self.assertEqual(self.cfg["render3d"]["visual_style"], "documentary_blueprint")


if __name__ == "__main__":
    unittest.main()
