"""End-to-end smoke test WITHOUT network: fake TTS audio + tiny Blender render + real ffmpeg compose.
Usage: python tests/e2e_fake.py [outdir]"""
import subprocess, sys, shutil
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.utils import load_config, run
from pipeline.script_writer import Scene, Script
from pipeline.timeline import TScene, total_duration
from pipeline.tts import Voiced, WordTime
from pipeline.render3d import render_all
from pipeline.compose import make_clip, compose
from pipeline.subtitles import build_ass

out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/e2e"); shutil.rmtree(out, ignore_errors=True); out.mkdir(parents=True)
cfg = load_config()
cfg["render3d"]["profiles"]["tiny"] = {"width": 216, "height": 384, "samples": 10, "fps": 12}
cfg["audio"]["music"] = False
texts = [("Tahukah kamu, chip terbaru ini bisa berpikir lebih cepat dari sebelumnya?", "Chip Super Cepat", "chip", "surprised", "hook"),
         ("Menurut para peneliti, perangkat ini menghemat daya hingga setengahnya.", "Hemat Daya", "battery", "excited", "fact"),
         ("Sumber: MIT News. Tautannya ada di deskripsi. Follow untuk fakta berikutnya!", "Sumber", "globe", "happy", "outro")]
tl, t = [], 0.0
for i, (txt, label, prop, emo, kind) in enumerate(texts):
    mp3 = out / f"voice_{i:02d}.mp3"
    words = txt.split(); dur = len(words) * 0.30
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=frequency={200+60*i}:duration={dur}", "-c:a", "libmp3lame", str(mp3)], quiet=True)
    wt = [WordTime(w, 0.05 + k * 0.30, 0.05 + (k + 1) * 0.30 - 0.03) for k, w in enumerate(words)]
    lead = 0.15; length = lead + dur + 0.3
    tl.append(TScene(Scene(txt, label, prop, emo, [1], kind), Voiced(mp3, dur, wt), start=t, length=length, lead=lead, index=i,
                     mascot_side=1 if i % 2 == 0 else -1, palette="ocean", camera=["push", "orbit", "pull"][i], seed=i + 5))
    t += length
cfg["video"]["transition"] = 0.35
dirs = render_all(tl, out, cfg, "tiny")
prof = cfg["render3d"]["profiles"]["tiny"]
clips = []
for x in tl:
    c = out / f"clip_{x.index}.mp4"; make_clip(dirs[x.index], c, prof["fps"], 1080, 1920, cfg, prof["width"]); clips.append(c)
art = {"publisher": "MIT News", "title": "A new chip design cuts power use by half in AI workloads", "date": "2026-11-10", "domain": "news.mit.edu"}
(out / "subs.ass").write_text(build_ass(tl, cfg, art, {"accent": "#FFC53D"}), encoding="utf-8")
compose(tl, clips, out / "subs.ass", out, out / "video.mp4", cfg)
print("OK", out / "video.mp4", round(total_duration(tl), 2), "s")
