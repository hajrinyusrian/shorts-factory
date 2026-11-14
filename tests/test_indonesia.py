import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import facts as facts_mod
from pipeline import script_writer as sw
from pipeline import sources
from pipeline.facts import Fact
from pipeline.sources import Candidate, indonesia_score
from pipeline.utils import load_config


def rss(items):
    now = time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime())
    body = "".join(f"<item><title>{t}</title><link>https://x.test/{i}</link><pubDate>{now}</pubDate>"
                   f"<description>{d}</description></item>" for i, (t, d) in enumerate(items))
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>f</title>{body}</channel></rss>'.encode()


class IndonesiaScoreTest(unittest.TestCase):
    def test_scores(self):
        self.assertGreaterEqual(indonesia_score("Pusat data baru dibangun di Jakarta", ""), 3)
        self.assertGreaterEqual(indonesia_score("Chip baru", "", region="id"), 3)
        self.assertEqual(indonesia_score("New chip cuts power", "A lab result"), 0)
        self.assertEqual(indonesia_score("Undersea cable project announced", ""), 1)   # topic only: weak signal
        self.assertEqual(indonesia_score("Indonesia data center nickel", "", region="id"), 6)  # capped


class CandidateOrderTest(unittest.TestCase):
    def _fetch(self, prefer):
        feeds = [{"name": "MIT News", "url": "https://mit.test/rss", "tier": 1},
                 {"name": "ANTARA", "url": "https://antara.test/rss", "tier": 2, "region": "id"}]
        pages = {"https://mit.test/rss": rss([("Lab builds faster chip", "result")]),
                 "https://antara.test/rss": rss([("Komdigi siapkan aturan AI", "regulasi")])}

        def fake_get(url, **kw):
            return SimpleNamespace(content=pages[url], raise_for_status=lambda: None)
        cfg = {"selection": {"max_age_days": 6, "prefer_indonesia": prefer}, "feeds": feeds}
        with mock.patch.object(sources.requests, "get", fake_get):
            return sources.fetch_candidates(cfg, history=[])

    def test_indonesia_first_when_enabled(self):
        c = self._fetch(True)
        self.assertEqual([x.publisher for x in c], ["ANTARA", "MIT News"])
        self.assertGreaterEqual(c[0].idn_score, 3)

    def test_old_order_when_disabled(self):
        self.assertEqual([x.publisher for x in self._fetch(False)], ["MIT News", "ANTARA"])


class PickPromptTest(unittest.TestCase):
    def test_marker_and_rule_only_when_enabled(self):
        prompts = []

        class LLM:
            def json(self, prompt, schema, **kw):
                prompts.append(prompt)
                return schema(index=0, reason="x")
        now = time.time()
        cands = [Candidate("Komdigi AI", "u1", "ANTARA", 2, now, "s", idn_score=3),
                 Candidate("Chip", "u2", "MIT News", 1, now, "s", idn_score=0)]
        facts_mod.pick_candidates_order(LLM(), cands, prefer_indonesia=True)
        facts_mod.pick_candidates_order(LLM(), cands, prefer_indonesia=False)
        self.assertIn("(ID) (ANTARA", prompts[0])
        self.assertIn("Prioritaskan teknologi yang berdampak", prompts[0])
        self.assertNotIn("Prioritaskan teknologi yang berdampak", prompts[1])


GOOD = "Analisis kami: Indonesia berpotensi menikmati manfaatnya jika industri lokal siap beradaptasi dengan teknologi chip hemat daya ini"


class AnalysisValidatorTest(unittest.TestCase):
    cfg = load_config()["script"]
    facts = [Fact(1, "Chip dari MIT memakai energi 48 persen lebih sedikit.", "e", "number")]

    def errs(self, text):
        return sw.analysis_errors(text, "Dampak", " ".join(f.claim for f in self.facts), self.cfg, 5)

    def test_good_passes(self):
        self.assertEqual(self.errs(GOOD), [])

    def test_each_rule(self):
        cases = {
            "diawali": GOOD.replace("Analisis kami:", "Menurut kami"),
            "Indonesia": GOOD.replace("Indonesia", "negeri ini"),
            "hati-hati": "Analisis kami: Indonesia akan menikmati manfaatnya karena industri lokal siap beradaptasi dengan teknologi chip hemat daya",
            "angka": GOOD + " sebesar 30 persen",
            "pasti": GOOD.replace("berpotensi", "pasti"),
            "nama": GOOD.replace("industri lokal", "industri lokal seperti Samsung"),
        }
        for key, text in cases.items():
            e = self.errs(text)
            self.assertTrue(any(key in x for x in e), (key, e))

    def test_name_from_facts_is_allowed(self):
        self.assertEqual(self.errs(GOOD.replace("industri lokal", "industri lokal yang meniru MIT")), [])

    def test_new_names_ignores_sentence_start_and_acronyms(self):
        self.assertEqual(sw.new_names("Bagus sekali. Teknologi AI dan GPU membantu Indonesia.", "", {"Indonesia"}), set())
        self.assertEqual(sw.new_names("Ini dipakai oleh Google di Bandung.", "", {"Indonesia"}), {"Google", "Bandung"})


class ValidateIntegrationTest(unittest.TestCase):
    def _script(self, analysis_text, hook_extra=""):
        w = lambda n: " ".join(["kata"] * n)
        S = sw.SceneOut
        return sw.ScriptOut(title="Chip hemat energi", summary="Ringkasan.", tags=["chip"], scenes=[
            S(narration="Tahukah kamu chip ini hemat " + w(7) + hook_extra, label="Hook", prop="chip", emotion="surprised", fact_ids=[1]),
            S(narration="Chip memakai energi 48 persen lebih sedikit " + w(10), label="Hemat", prop="battery", emotion="happy", fact_ids=[1]),
            S(narration=w(14), label="Detail", prop="gear", emotion="happy", fact_ids=[1]),
            S(narration=w(14), label="Detail dua", prop="atom", emotion="happy", fact_ids=[1]),
            S(narration=analysis_text, label="Dampak", prop="bulb", emotion="thinking", fact_ids=[1]),
            S(narration="Menurutmu seberapa jauh kita bisa hemat " + w(5), label="Penutup", prop="globe", emotion="proud", fact_ids=[]),
        ])

    facts = [Fact(1, "Chip dari MIT memakai energi 48 persen lebih sedikit.", "e", "number")]

    def test_valid_and_position_is_second_to_last(self):
        cfg = load_config()
        errs = sw.validate(self._script(GOOD), self.facts, cfg)
        self.assertEqual([e for e in errs if "total" not in e and "minimal 3" not in e], [])
        self.assertEqual(sw.analysis_index(cfg["script"], 6), 4)
        self.assertIsNone(sw.analysis_index({"analysis": False}, 6))

    def test_analysis_rules_are_enforced_in_validate(self):
        cfg = load_config()
        bad = GOOD.replace("Analisis kami:", "Menurut kami")
        errs = sw.validate(self._script(bad), self.facts, cfg)
        self.assertTrue(any("diawali kata 'Analisis'" in e for e in errs), errs)

    def test_forbidden_words_blocked_everywhere_unless_in_facts(self):
        cfg = load_config()
        errs = sw.validate(self._script(GOOD, hook_extra=" terbukti"), self.facts, cfg)
        self.assertTrue(any("'terbukti'" in e for e in errs), errs)
        facts2 = [Fact(1, "Chip dari MIT terbukti memakai energi 48 persen lebih sedikit.", "e", "number")]
        errs2 = sw.validate(self._script(GOOD, hook_extra=" terbukti"), facts2, cfg)
        self.assertFalse(any("'terbukti'" in e for e in errs2), errs2)

    def test_analysis_disabled_restores_old_rules(self):
        cfg = load_config(); cfg["script"]["analysis"] = False
        errs = sw.validate(self._script("kata " * 14), self.facts, cfg)
        self.assertFalse(any("Analisis" in e for e in errs), errs)


class WriteScriptKindTest(unittest.TestCase):
    def test_second_to_last_scene_is_marked_analysis_and_description_discloses(self):
        from pipeline.main import description_text
        cfg = load_config()
        facts = [Fact(1, "Chip dari MIT memakai energi 48 persen lebih sedikit.", "e", "number"),
                 Fact(2, "Dibuat pada 3 nanometer.", "e", "number"),
                 Fact(3, "Diuji pada 1.200 gambar.", "e", "number")]
        t = ValidateIntegrationTest()
        w = lambda n: " ".join(["kata"] * n)
        S = sw.SceneOut
        out = sw.ScriptOut(title="Chip hemat energi", summary="Ringkasan.", tags=["chip"], scenes=[
            S(narration="Tahukah kamu chip ini hemat " + w(7), label="Hook", prop="chip", emotion="surprised", fact_ids=[1]),
            S(narration="Chip memakai energi 48 persen lebih sedikit " + w(10), label="Hemat", prop="battery", emotion="happy", fact_ids=[1]),
            S(narration="Dibuat pada 3 nanometer " + w(10), label="Kecil", prop="gear", emotion="happy", fact_ids=[2]),
            S(narration="Diuji pada 1200 gambar " + w(10), label="Uji", prop="atom", emotion="happy", fact_ids=[3]),
            S(narration=GOOD, label="Dampak", prop="bulb", emotion="thinking", fact_ids=[1]),
            S(narration="Menurutmu seberapa jauh kita bisa hemat " + w(8), label="Penutup", prop="globe", emotion="proud", fact_ids=[]),
        ])

        class FakeLLM:
            def json(self, *a, **k):
                return out
        art = SimpleNamespace(title="T", publisher="MIT News", url="https://x", date="2026-11-13", text="x")
        script = sw.write_script(FakeLLM(), facts, art, cfg)
        self.assertEqual([s.kind for s in script.scenes], ["hook", "fact", "fact", "fact", "analysis", "kicker"])
        d = description_text(script, art, cfg)
        self.assertIn("perspektif kami", d)
        script.scenes[4].kind = "fact"
        self.assertNotIn("perspektif kami", description_text(script, art, cfg))


class AnalysisTagFrameTest(unittest.TestCase):
    def test_tag_pill_changes_the_text_zone(self):
        from PIL import Image, ImageChops
        from pipeline import infographic as ig
        with tempfile.TemporaryDirectory() as d:
            still = Path(d) / "s.png"; Image.new("RGB", (270, 480), (200, 120, 60)).save(still)
            a, b = Path(d) / "a", Path(d) / "b"
            ig.render_scene_frames(still, a, 30, 30, "Dampak ke Indonesia", None, 0.1, "#FFC53D", "push", workers=1, tag="")
            ig.render_scene_frames(still, b, 30, 30, "Dampak ke Indonesia", None, 0.1, "#FFC53D", "push", workers=1, tag="ANALISIS KAMI")
            zone = (0, 1000, 1080, 1100)
            with Image.open(a / "f_0030.jpg") as ia, Image.open(b / "f_0030.jpg") as ib:
                self.assertIsNotNone(ImageChops.difference(ia.crop(zone), ib.crop(zone)).getbbox())


if __name__ == "__main__":
    unittest.main()
