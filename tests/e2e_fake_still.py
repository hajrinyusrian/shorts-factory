"""Offline end-to-end smoke test of the STILL (illustration + big text + infographic) mode.
Fake TTS audio + real Blender stills + real Pillow frames + real ffmpeg compose. No network.
Usage: python tests/e2e_fake_still.py [outdir]"""
import sys, shutil
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.utils import load_config, run
from pipeline.script_writer import Scene
from pipeline.timeline import TScene, total_duration
from pipeline.tts import Voiced, WordTime
from pipeline.render3d import render_stills
from pipeline.infographic import build_scene_frames
from pipeline.compose import make_clip, compose
from pipeline.subtitles import build_ass

out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/e2e_still"); shutil.rmtree(out, ignore_errors=True); out.mkdir(parents=True)
cfg = load_config()
cfg["render3d"]["stills"]["tiny"] = {"width": 360, "height": 640, "samples": 32}
cfg["audio"]["music"] = False
texts = [("Tahukah kamu, chip terbaru ini bisa berpikir lebih cepat dari sebelumnya?", "Chip Super Cepat", "chip", "surprised", "hook"),
         ("Menurut para peneliti, perangkat ini menghemat daya hingga 48 persen dibanding desain lama.", "Hemat Daya", "battery", "excited", "fact"),
         ("Chip itu dibuat pada 3 nanometer dan diuji pada 1.200 gambar berbeda.", "Dibuat Sangat Kecil", "atom", "thinking", "fact"),
         ("Analisis kami: Indonesia berpotensi ikut diuntungkan jika industri lokal siap beradaptasi.", "Dampak ke Indonesia", "bulb", "thinking", "analysis"),
         ("Sumber: MIT News. Tautannya ada di deskripsi. Follow untuk fakta berikutnya!", "Sumber", "globe", "happy", "outro")]
tl, t = [], 0.0
for i, (txt, label, prop, emo, kind) in enumerate(texts):
    mp3 = out / f"voice_{i:02d}.mp3"
    words = txt.split(); dur = len(words) * 0.30
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=frequency={200+60*i}:duration={dur}", "-c:a", "libmp3lame", str(mp3)], quiet=True)
    wt = [WordTime(w, 0.05 + k * 0.30, 0.05 + (k + 1) * 0.30 - 0.03) for k, w in enumerate(words)]
    lead = 0.15; length = lead + dur + 0.3
    tl.append(TScene(Scene(txt, label, prop, emo, [1], kind), Voiced(mp3, dur, wt), start=t, length=length, lead=lead, index=i,
                     mascot_side=1 if i % 2 == 0 else -1, palette="sunset", camera=["push", "orbit", "pull", "push", "pull"][i], seed=i + 5))
    t += length
cfg["video"]["transition"] = 0.35
stills = render_stills(tl, out, cfg, "tiny")
dirs = build_scene_frames(tl, stills, out, cfg, "#FFD23F")
clips = []
for x in tl:
    c = out / f"clip_{x.index}.mp4"; make_clip(dirs[x.index], c, 30, 1080, 1920, cfg, 1080, pattern="f_%04d.jpg"); clips.append(c)
art = {"publisher": "MIT News", "title": "A new chip design cuts power use by half in AI workloads", "date": "2026-11-10", "domain": "news.mit.edu"}
(out / "subs.ass").write_text(build_ass(tl, cfg, art, {"accent": "#FFD23F"}), encoding="utf-8")
compose(tl, clips, out / "subs.ass", out, out / "video.mp4", cfg)
print("OK", out / "video.mp4", round(total_duration(tl), 2), "s")
