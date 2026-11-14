import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import script_writer as sw
from pipeline.facts import Fact
from pipeline.tts import speak_text
from pipeline.utils import load_config


class UnspaceAcronymsTest(unittest.TestCase):
    def test_joins_spaced_capitals(self):
        self.assertEqual(sw.unspace_acronyms("Etika A I sangat penting"), "Etika AI sangat penting")
        self.assertEqual(sw.unspace_acronyms("Chip G P U dan C P U"), "Chip GPU dan CPU")
        self.assertEqual(sw.unspace_acronyms("BELAJAR ETIKA A I"), "BELAJAR ETIKA AI")

    def test_leaves_normal_text_alone(self):
        for t in ["Etika AI sangat penting", "Rencana A atau B", "Ini a i u e o", "Dia pergi ke Bali. I Made ikut."]:
            self.assertEqual(sw.unspace_acronyms(t), t, t)

    def test_prompt_no_longer_asks_for_spaced_letters(self):
        self.assertNotIn('"A I"', sw.SYSTEM)
        self.assertIn("tanpa spasi", sw.SYSTEM)

    def test_voice_still_spells_it_out(self):
        pron = load_config()["tts"]["pronunciation"]
        spoken, counts = speak_text("Etika AI penting", pron)
        self.assertEqual(spoken, "Etika A I penting")     # voice gets "A I", screen keeps "AI"
        self.assertEqual(counts, [1, 2, 1])


class WriteScriptEndToEndTest(unittest.TestCase):
    def test_spaced_acronyms_from_model_end_up_clean(self):
        cfg = load_config()
        facts = [Fact(1, "Chip memakai energi 48% lebih sedikit.", "e", "number"),
                 Fact(2, "Dibuat pada 3 nanometer.", "e", "number"),
                 Fact(3, "Diuji pada 1.200 gambar.", "e", "number")]
        w = lambda n: " ".join(["kata"] * n)
        S = sw.SceneOut
        out = sw.ScriptOut(title="Etika A I di kampus", summary="Ringkasan A I.", tags=["ai"], scenes=[
            S(narration="Apakah etika A I penting " + w(10), label="Etika A I", prop="neural", emotion="surprised", fact_ids=[]),
            S(narration="Chip memakai energi 48 persen lebih sedikit " + w(10), label="Hemat", prop="chip", emotion="happy", fact_ids=[1]),
            S(narration="Dibuat pada 3 nanometer " + w(10), label="Kecil", prop="gear", emotion="happy", fact_ids=[2]),
            S(narration="Diuji pada 1200 gambar " + w(10), label="Uji", prop="atom", emotion="happy", fact_ids=[3]),
            S(narration="Analisis kami: Indonesia berpotensi menikmati manfaatnya jika industri lokal siap beradaptasi dengan teknologi chip hemat daya ini", label="Dampak", prop="bulb", emotion="happy", fact_ids=[1]),
            S(narration="Jadi G P U " + w(8), label="Penutup", prop="globe", emotion="proud", fact_ids=[]),
        ])

        class FakeLLM:
            def json(self, *a, **k):
                return out
        art = SimpleNamespace(title="T", publisher="P", url="u", published="2026-11-13", text="x", date="2026-11-13")
        script = sw.write_script(FakeLLM(), facts, art, cfg)
        texts = [s.narration for s in script.scenes] + [s.label for s in script.scenes] + [script.title, script.summary]
        self.assertFalse(any("A I" in t or "G P U" in t for t in texts), texts)
        self.assertIn("AI", script.title)


if __name__ == "__main__":
    unittest.main()
