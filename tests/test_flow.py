"""Orchestration test: real main.py / timeline / subtitles / ffmpeg, with LLM, network, TTS, Blender and upload faked."""
import json, subprocess, sys, tempfile, time, unittest, yaml
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PIL import Image
from pipeline import main as M, state
from pipeline.facts import FactsOut, FactItem, JudgeOut, JudgeItem, PickOut
from pipeline.script_writer import ScriptOut, SceneOut
from pipeline.sources import Article, Candidate
from pipeline.tts import Voiced, WordTime
from pipeline.utils import ROOT, load_config

TEXT = ("Researchers at MIT unveiled a new chip on Monday. The chip uses 48% less energy than the previous design "
        "while running image models, according to the team. It was fabricated at 3 nanometers and tested on 1,200 "
        "images. The work was published in Nature Electronics. " * 6)
EVID = ["The chip uses 48% less energy than the previous design while running image models",
        "It was fabricated at 3 nanometers and tested on 1,200 images",
        "The work was published in Nature Electronics"]
CLAIMS = ["Chip memakai energi 48% lebih sedikit dari desain sebelumnya.", "Chip dibuat pada skala 3 nanometer dan diuji pada 1.200 gambar.",
          "Hasilnya diterbitkan di jurnal Nature Electronics."]
W = lambda n: " ".join(["kata"] * n)


class FakeLLM:
    def __init__(self, *a, **k): pass
    def json(self, prompt, schema, **kw):
        if schema is PickOut: return PickOut(index=0, reason="x")
        if schema is FactsOut: return FactsOut(facts=[FactItem(claim=c, evidence=e, kind="number") for c, e in zip(CLAIMS, EVID)])
        if schema is JudgeOut: return JudgeOut(items=[JudgeItem(id=i, verdict="supported", note="") for i in (1, 2, 3)])
        sc = [SceneOut(narration="Tahukah kamu chip baru ini " + W(7), label="Chip Baru", prop="chip", emotion="surprised", fact_ids=[1]),
              SceneOut(narration="Menurut tim peneliti chip memakai energi 48 persen lebih sedikit " + W(5), label="Hemat Energi", prop="battery", emotion="excited", fact_ids=[1]),
              SceneOut(narration="Chip dibuat pada skala 3 nanometer dan diuji pada 1200 gambar " + W(3), label="Skala Nano", prop="atom", emotion="thinking", fact_ids=[2]),
              SceneOut(narration="Hasilnya terbit di jurnal Nature Electronics " + W(8), label="Terbit di Nature", prop="globe", emotion="proud", fact_ids=[3]),
              SceneOut(narration="Artinya komputer bisa lebih irit daya " + W(7), label="Dampaknya", prop="gear", emotion="happy", fact_ids=[1]),
              SceneOut(narration="Analisis kami: Indonesia berpotensi ikut diuntungkan jika industri dalam negeri mampu mengadopsi desain chip hemat daya semacam ini", label="Dampak ke Indonesia", prop="bulb", emotion="thinking", fact_ids=[2]),
              SceneOut(narration="Menurutmu seberapa jauh komputer bisa dihemat " + W(5), label="Masa Depan", prop="rocket", emotion="happy", fact_ids=[])]
        return ScriptOut(title="Chip Baru MIT Hemat Energi", summary="Peneliti MIT memamerkan chip hemat energi.", tags=["chip", "MIT"], scenes=sc)


def fake_synth(text, out_mp3, cfg, retries=4):
    words = text.split(); dur = len(words) * 0.27
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=frequency=220:duration={dur}", "-c:a", "libmp3lame", str(out_mp3)], check=True)
    return Voiced(Path(out_mp3), dur, [WordTime(w, 0.05 + i * 0.27, 0.05 + (i + 1) * 0.27 - 0.02) for i, w in enumerate(words)])


def fake_render(tl, workdir, cfg, profile_name=None):
    manifest, dirs = M.render_all.__wrapped__(tl, workdir, cfg, profile_name) if hasattr(M.render_all, "__wrapped__") else (None, None)
    return manifest


class FlowTest(unittest.TestCase):
    def test_full_flow_still_mode(self):
        self._flow("still")

    def test_full_flow_video_mode(self):
        self._flow("video")

    def _flow(self, mode):
        tmp = Path(tempfile.mkdtemp())
        cfg = load_config()
        cfg["render3d"].update(interpolation="dup", profile="t", mode=mode)
        cfg["render3d"]["stills"]["t"] = {"width": 108, "height": 192, "samples": 1}
        if mode == "still":
            cfg["video"]["fps"] = 10      # keeps the Pillow frame count (and the test) small
        cfg["render3d"]["profiles"]["t"] = {"width": 108, "height": 192, "samples": 1, "fps": 12}
        cfg["audio"]["music"] = False; cfg["audio"]["whoosh"] = True
        cfg["video"].update(preset="ultrafast", crf=30)
        cfg["selection"]["llm_judge"] = True
        (tmp / "cfg.yaml").write_text(yaml.safe_dump(cfg), "utf-8")
        cand = Candidate("A new chip", "https://news.mit.edu/x", "MIT News", 1, time.time())
        art = Article("A new chip cuts power", "https://news.mit.edu/x", "MIT News", "", "2026-11-10", TEXT, {"domain": "news.mit.edu"})

        from pipeline.render3d import build_manifest
        def render(tl, workdir, cfg_, prof=None):
            manifest, dirs = build_manifest(tl, workdir, cfg_, prof)
            for s in manifest["scenes"]:
                Path(s["out_dir"]).mkdir(parents=True, exist_ok=True)
                for i in range(1, s["frames"] + 1):
                    Image.new("RGB", (s["width"], s["height"]), (30 + i % 40, 90, 200)).save(Path(s["out_dir"]) / f"f_{i:04d}.png")
            return dirs

        from pipeline.render3d import build_still_manifest
        def stills(tl, workdir, cfg_, prof=None):
            manifest, paths = build_still_manifest(tl, workdir, cfg_, prof)
            for pth in paths.values():
                pth.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (108, 192), (200, 120, 60)).save(pth)
            return paths

        uploaded = {}
        def up(video, title, desc, tags, cfg_):
            uploaded.update(video=video, title=title, desc=desc); return "abc123"

        with mock.patch.object(M, "LLM", FakeLLM), mock.patch.object(M, "fetch_candidates", lambda c: [cand]), \
             mock.patch.object(M, "fetch_article", lambda c, n: art), mock.patch("pipeline.timeline.synthesize", fake_synth), \
             mock.patch.object(M, "render_all", render), mock.patch.object(M, "render_stills", stills), \
             mock.patch.object(M, "upload", up), \
             mock.patch.object(state, "HISTORY", tmp / "history.json"), \
             mock.patch.object(sys, "argv", ["main", "--out", str(tmp / "out"), "--config", str(tmp / "cfg.yaml")]):
            M.main()
        v = uploaded["video"]
        self.assertTrue(v.exists() and v.stat().st_size > 10_000)
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1", str(v)], capture_output=True, text=True).stdout)
        self.assertGreater(dur, 15); self.assertLess(dur, 58)
        self.assertIn("https://news.mit.edu/x", uploaded["desc"])
        self.assertIn("MIT News", uploaded["desc"])
        hist = json.loads((tmp / "history.json").read_text())
        self.assertEqual(hist[-1]["video_id"], "abc123")
        self.assertTrue(state.is_seen("https://news.mit.edu/x", "whatever", hist))


if __name__ == "__main__":
    unittest.main()
