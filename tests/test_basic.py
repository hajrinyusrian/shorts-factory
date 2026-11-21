import re, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.constants import PROP_KEYS, PALETTES
from pipeline.facts import Fact, verify_fact
from pipeline.script_writer import ScriptOut, SceneOut, validate
from pipeline.subtitles import make_chunks, build_ass
from pipeline.tts import WordTime, speak_text, _align
from pipeline.utils import load_config, number_tokens

ARTICLE = ("Researchers at MIT unveiled a new chip on Monday. The chip uses 48% less energy than the previous "
           "design while running image models, according to the team. It was fabricated at 3 nanometers and "
           "tested on 1,200 images. The work was published in Nature Electronics.")


class FactTests(unittest.TestCase):
    def test_exact_evidence_passes(self):
        f = Fact(1, "Chipnya memakai energi 48% lebih sedikit.", "The chip uses 48% less energy than the previous design while running image models", "number")
        self.assertTrue(verify_fact(f, ARTICLE)[0])

    def test_invented_evidence_fails(self):
        f = Fact(2, "Chipnya 10 kali lebih cepat.", "The chip is ten times faster than any competitor on the market today", "number")
        self.assertFalse(verify_fact(f, ARTICLE)[0])

    def test_number_not_in_evidence_fails(self):
        f = Fact(3, "Chipnya memakai energi 60% lebih sedikit.", "The chip uses 48% less energy than the previous design while running image models", "number")
        ok, why = verify_fact(f, ARTICLE)
        self.assertFalse(ok); self.assertIn("numbers", why)

    def test_number_formats_equal(self):
        self.assertEqual(number_tokens("1,200"), number_tokens("1.200"))
        f = Fact(4, "Diuji pada 1.200 gambar.", "tested on 1,200 images. The work was published in Nature Electronics", "number")
        self.assertTrue(verify_fact(f, ARTICLE)[0])


class ScriptTests(unittest.TestCase):
    cfg = load_config()
    facts = [Fact(1, "Chip memakai energi 48% lebih sedikit.", "e", "number"), Fact(2, "Dibuat pada 3 nanometer.", "e", "number"),
             Fact(3, "Diuji pada 1.200 gambar.", "e", "number")]

    def scene(self, text, prop, ids=(1,), label="Label"):
        return SceneOut(narration=text, label=label, prop=prop, emotion="happy", fact_ids=list(ids))

    def test_rejects_invented_number(self):
        w = lambda n: " ".join(["kata"] * n)
        sc = [self.scene(w(10), "chip"), self.scene(w(20) + " 99", "battery"), self.scene(w(20), "gear", (2,)),
              self.scene(w(20), "atom", (3,)), self.scene(w(12), "globe", ())]
        errs = validate(ScriptOut(title="Judul", summary="s", tags=["a"], scenes=sc), self.facts, self.cfg)
        self.assertTrue(any("99" in e for e in errs), errs)

    def test_valid_script_passes(self):
        w = lambda n: " ".join(["kata"] * n)
        sc = [self.scene(w(20), "chip"),
              self.scene("Chip memakai energi 48 persen lebih sedikit " + w(29), "battery"),
              self.scene("Dibuat pada 3 nanometer " + w(29), "gear", (2,)),
              self.scene("Diuji pada 1200 gambar " + w(29), "atom", (3,)),
              self.scene(w(34), "shield", (1,)),
              self.scene(w(34), "planet", (2,)),
              self.scene(w(34), "rocket", (3,)),
              self.scene(w(34), "neural", (1,)),
              self.scene("Analisis kami: Indonesia mungkin memperoleh manfaat jika kesiapan industri, pekerja, dan pengguna berkembang seiring perubahan teknologi yang sedang berlangsung", "bulb", (1,)),
              self.scene(w(22), "globe", ())]
        errs = validate(ScriptOut(title="Judul", summary="s", tags=["a"], scenes=sc), self.facts, self.cfg)
        self.assertEqual(errs, [])


class SubtitleTests(unittest.TestCase):
    def test_chunks_respect_line_length(self):
        ws = [WordTime(w, i * .3, i * .3 + .25) for i, w in enumerate("satu dua tiga empat lima enam tujuh delapan sembilan sepuluh".split())]
        for ch in make_chunks(ws, 17, 2):
            line = 0
            for x in ch:
                line = 0 if x is None else line + len(x.text) + 1
                self.assertLessEqual(line, 19)

    def test_pronunciation_and_alignment(self):
        txt, counts = speak_text("Chip AI baru", {"AI": "A I"})
        self.assertEqual(counts, [1, 2, 1])
        bounds = [{"type": "WordBoundary", "offset": i * 3e6, "duration": 2.5e6, "text": t} for i, t in enumerate(["Chip", "A", "I", "baru"])]
        w = _align("Chip AI baru".split(), counts, bounds, 2.0)
        self.assertEqual([x.text for x in w], ["Chip", "AI", "baru"])
        self.assertAlmostEqual(w[1].start, 0.3, 2); self.assertAlmostEqual(w[1].end, 0.85, 2)


class SyncTests(unittest.TestCase):
    def test_prop_keys_match_blender(self):
        src = (Path(__file__).resolve().parent.parent / "blender" / "props.py").read_text()
        keys = re.search(r'PROP_KEYS = \[(.*?)\]', src, re.S).group(1)
        self.assertEqual(re.findall(r'"(\w+)"', keys), PROP_KEYS)


    def test_palettes_match_blender(self):
        src = (Path(__file__).resolve().parent.parent / "blender" / "render_scene.py").read_text()
        block = src[src.index("PALETTES = {"):src.index("PROP_POS")]
        self.assertEqual(re.findall(r'^\s+"(\w+)":\s+dict', block, re.M), PALETTES)


if __name__ == "__main__":
    unittest.main()
