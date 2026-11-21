"""Offline end-to-end smoke test for the hybrid 2.5D documentary renderer.

Requires Blender and FFmpeg; uses synthetic audio and never calls an external API.
Usage: python tests/e2e_documentary_fake.py [outdir]
"""
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.utils import load_config, run
from pipeline.script_writer import Scene
from pipeline.timeline import TScene, total_duration
from pipeline.tts import Voiced, WordTime
from pipeline.render3d import render_stills
from pipeline.infographic import build_scene_frames
from pipeline.compose import make_clip, compose
from pipeline.subtitles import build_ass


out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/e2e-documentary")
shutil.rmtree(out, ignore_errors=True)
out.mkdir(parents=True)
cfg = load_config()
cfg["render3d"]["visual_style"] = "documentary_blueprint"
cfg["render3d"]["stills"]["tiny"] = {"width": 216, "height": 384, "samples": 8}
cfg["audio"]["music"] = False
cfg["audio"]["whoosh"] = False
cfg["video"]["transition"] = 0.2

rows = [
    ("Kasus ini bermula dari sebuah temuan yang kemudian menjadi perhatian publik.", "Awal Peristiwa", "chip", "surprised", "hook"),
    ("Dokumen dan keterangan resmi menjadi dasar untuk menyusun kronologi secara hati-hati.", "Kronologi", "shield", "thinking", "fact"),
    ("Sumber: dokumentasi berita. Perkembangan berikutnya masih perlu dipantau.", "Sumber", "globe", "proud", "outro"),
]
timeline = []
cursor = 0.0
for i, (text, label, prop, emotion, kind) in enumerate(rows):
    audio = out / f"voice_{i:02d}.mp3"
    words = text.split()
    duration = len(words) * 0.22
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
         f"sine=frequency={220 + 50 * i}:duration={duration}", "-c:a", "libmp3lame", str(audio)], quiet=True)
    times = [WordTime(w, 0.02 + j * 0.22, 0.02 + (j + 1) * 0.22 - 0.02) for j, w in enumerate(words)]
    lead = 0.08
    length = lead + duration + 0.18
    scene = Scene(text, label, prop, emotion, [1] if kind != "outro" else [], kind)
    timeline.append(TScene(scene, Voiced(audio, duration, times), start=cursor, length=length, lead=lead,
                           index=i, mascot_side=1 if i % 2 == 0 else -1, palette="blueprint",
                           camera=["push", "orbit", "pull"][i], seed=31 + i))
    cursor += length

stills = render_stills(timeline, out, cfg, "tiny")
dirs = build_scene_frames(timeline, stills, out, cfg, "#F5A623")
clips = []
for item in timeline:
    clip = out / f"clip_{item.index:02d}.mp4"
    make_clip(dirs[item.index], clip, 30, 1080, 1920, cfg, 216, pattern="f_%04d.jpg")
    clips.append(clip)

meta = {"publisher": "Test Source", "title": "Offline documentary renderer test", "date": "2026-11-21", "domain": "example.invalid"}
(out / "subs.ass").write_text(build_ass(timeline, cfg, meta, {"accent": "#F5A623"}), encoding="utf-8")
final = out / "documentary-test.mp4"
compose(timeline, clips, out / "subs.ass", out, final, cfg)
probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height,r_frame_rate,codec_name",
                        "-of", "json", str(final)], check=True, capture_output=True, text=True)
import json
streams = json.loads(probe.stdout)["streams"]
video = next(x for x in streams if x.get("codec_type") == "video")
assert (video["width"], video["height"], video["r_frame_rate"]) == (1080, 1920, "30/1"), video
assert final.stat().st_size > 100_000
print("DOCUMENTARY_E2E_OK", final, round(total_duration(timeline), 2), "seconds")
