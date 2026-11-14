"""Drive Blender: one process renders every scene's PNG sequence."""
from __future__ import annotations

import json
import os
import re
import shutil
import time
from pathlib import Path

from .timeline import TScene, frames_for
from .utils import ROOT, log, run_stream


def blender_bin() -> str:
    return os.environ.get("BLENDER_BIN") or shutil.which("blender") or "blender"


def build_manifest(tl: list[TScene], workdir: Path, cfg: dict, profile_name: str | None = None) -> tuple[dict, dict]:
    r = cfg["render3d"]
    prof = r["profiles"][profile_name or r["profile"]]
    xf = cfg["video"]["transition"]
    scenes, dirs = [], {}
    for t in tl:
        out_dir = workdir / "frames" / f"s{t.index:02d}"
        if out_dir.exists():
            shutil.rmtree(out_dir)
        sc = t.scene
        scenes.append({
            "out_dir": str(out_dir),
            "frames": frames_for(t.length, prof["fps"], xf),
            "fps": prof["fps"],
            "width": prof["width"],
            "height": prof["height"],
            "samples": prof["samples"],
            "motion_blur": prof.get("motion_blur", r.get("motion_blur", False)),
            "prop": "none" if sc.kind == "outro" else sc.prop,
            "emotion": sc.emotion,
            "palette": t.palette,
            "seed": t.seed,
            "mascot_side": 0 if sc.kind == "outro" else t.mascot_side,
            "camera": t.camera,
            "shift_y": r.get("shift_y", -0.16),
        })
        dirs[t.index] = out_dir
    return {"scenes": scenes}, dirs


class RenderProgress:
    """Parses Blender's live output: logs our own [blender] lines, progress/ETA every `every` saved frames."""
    SAVED = re.compile(r"Saved: ")

    def __init__(self, total_frames: int, every: int = 25, clock=time.monotonic):
        self.total, self.every, self.clock = total_frames, every, clock
        self.done, self.t0 = 0, clock()
        self.denoise_warning = False

    def __call__(self, line: str) -> None:
        if line.startswith("[blender]"):
            log.info(line)
            if "no OpenImageDenoise" in line:
                self.denoise_warning = True
        elif self.SAVED.search(line):
            self.done += 1
            if self.done % self.every == 0 or self.done == self.total:
                el = self.clock() - self.t0
                per = el / self.done
                eta = per * (self.total - self.done)
                log.info("render %d/%d frames | %.2f s/frame | elapsed %.1f min | ETA %.1f min",
                         self.done, self.total, per, el / 60, eta / 60)


def render_all(tl: list[TScene], workdir: Path, cfg: dict, profile_name: str | None = None) -> dict[int, Path]:
    manifest, dirs = build_manifest(tl, workdir, cfg, profile_name)
    mpath = workdir / "manifest.json"
    mpath.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    total = sum(s["frames"] for s in manifest["scenes"])
    log.info("rendering %d frames in %d scenes with Blender (%s)", total, len(tl), blender_bin())
    cmd = [blender_bin(), "-b", "-noaudio", "--python-exit-code", "1", "-P", str(ROOT / "blender" / "render_scene.py"),
           "--", str(mpath)]
    progress = RenderProgress(total)
    run_stream(cmd, progress)
    log.info("blender finished: %d frames in %.1f min", progress.done, (progress.clock() - progress.t0) / 60)
    for t, s in zip(tl, manifest["scenes"]):
        n = len(list(dirs[t.index].glob("f_*.png")))
        if n != s["frames"]:
            raise RuntimeError(f"scene {t.index}: expected {s['frames']} frames, found {n}")
    return dirs


def build_still_manifest(tl: list[TScene], workdir: Path, cfg: dict, profile_name: str | None = None) -> tuple[dict, dict]:
    """One high-quality still per scene. Blender still builds the animated pose timeline (12 fps keys) and renders
    a single frame ~55% into the scene, so the mascot/prop are caught mid-gesture."""
    r = cfg["render3d"]
    name = profile_name or r["profile"]
    st = r["stills"][name]
    xf = cfg["video"]["transition"]
    scenes, paths = [], {}
    for t in tl:
        out_dir = workdir / "stills" / f"s{t.index:02d}"
        if out_dir.exists():
            shutil.rmtree(out_dir)
        sc = t.scene
        frames = frames_for(t.length, 12, xf)
        scenes.append({
            "out_dir": str(out_dir), "frames": frames, "fps": 12,
            "preview_frame": max(2, int(frames * 0.55)),
            "width": st["width"], "height": st["height"], "samples": st["samples"],
            "motion_blur": False,
            "prop": "none" if sc.kind == "outro" else sc.prop, "emotion": sc.emotion,
            "palette": t.palette, "seed": t.seed,
            "mascot_side": 0 if sc.kind == "outro" else t.mascot_side,
            "camera": "pull" if sc.kind == "outro" else "push",
            "shift_y": r.get("shift_y", -0.16),
        })
        paths[t.index] = out_dir / "preview.png"
    return {"scenes": scenes}, paths


def render_stills(tl: list[TScene], workdir: Path, cfg: dict, profile_name: str | None = None) -> dict[int, Path]:
    manifest, paths = build_still_manifest(tl, workdir, cfg, profile_name)
    mpath = workdir / "manifest_stills.json"
    mpath.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    log.info("rendering %d stills with Blender (%s)", len(tl), blender_bin())
    cmd = [blender_bin(), "-b", "-noaudio", "--python-exit-code", "1", "-P", str(ROOT / "blender" / "render_scene.py"),
           "--", str(mpath)]
    progress = RenderProgress(len(tl), every=1)
    run_stream(cmd, progress)
    log.info("blender finished: %d stills in %.1f min", progress.done, (progress.clock() - progress.t0) / 60)
    for idx, pth in paths.items():
        if not pth.exists():
            raise RuntimeError(f"scene {idx}: still not rendered ({pth})")
    return paths
