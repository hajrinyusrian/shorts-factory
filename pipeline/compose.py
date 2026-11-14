"""FFmpeg assembly: frames -> clips -> cross-faded video + ASS captions + mixed audio."""
from __future__ import annotations

import random
import shutil
from pathlib import Path

from .timeline import TScene, total_duration
from .utils import ROOT, log, run

TRANSITIONS = ["smoothleft", "circleopen", "smoothup", "fade", "smoothright", "radial"]


def make_clip(frames_dir: Path, out: Path, render_fps: int, w: int, h: int, cfg: dict, render_w: int) -> None:
    v = cfg["video"]
    interp = cfg["render3d"].get("interpolation", "dup")
    vf = []
    if v["fps"] != render_fps:
        if interp == "mci":
            vf.append(f"minterpolate=fps={v['fps']}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1")
        elif interp == "blend":
            vf.append(f"framerate=fps={v['fps']}:interp_start=0:interp_end=255:scene=100")
        else:
            vf.append(f"fps={v['fps']}")
    vf.append(f"scale={w}:{h}:flags=lanczos")
    if render_w < w:
        vf.append("unsharp=5:5:0.55:5:5:0.0")
    vf.append("format=yuv420p")
    run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(render_fps), "-i", str(frames_dir / "f_%04d.png"),
         "-vf", ",".join(vf), "-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p",
         "-r", str(v["fps"]), str(out)], quiet=True)


def whoosh_filter(dur: float = 0.5) -> str:
    return (f"anoisesrc=color=pink:d={dur}:a=0.6:r=48000,highpass=f=350,lowpass=f=4500,"
            f"afade=t=in:d={dur * 0.45:.2f},afade=t=out:st={dur * 0.45:.2f}:d={dur * 0.55:.2f},volume=0.55")


def compose(tl: list[TScene], clips: list[Path], ass_path: Path, workdir: Path, out_mp4: Path, cfg: dict) -> None:
    v = cfg["video"]
    xf = v["transition"]
    total = total_duration(tl)
    n = len(tl)
    # stage fonts + subtitles next to the working dir so the filter needs no path escaping
    fonts = workdir / "fonts"
    if fonts.exists():
        shutil.rmtree(fonts)
    shutil.copytree(ROOT / "assets" / "fonts", fonts)

    inputs: list[str] = []
    for c in clips:
        inputs += ["-i", str(c)]
    for t in tl:
        inputs += ["-i", str(t.voice.path)]
    music = _pick_music(cfg)
    music_idx = None
    if music:
        music_idx = 2 * n
        inputs += ["-stream_loop", "-1", "-i", str(music)]

    fc: list[str] = []
    for i in range(n):
        fc.append(f"[{i}:v]fps={v['fps']},format=yuv420p,setsar=1[v{i}]")
    cur = "v0"
    for i in range(1, n):
        offset = tl[i].start  # == sum of previous visible lengths
        tr = TRANSITIONS[(i - 1) % len(TRANSITIONS)]
        nxt = f"x{i}"
        fc.append(f"[{cur}][v{i}]xfade=transition={tr}:duration={xf}:offset={offset:.3f}[{nxt}]")
        cur = nxt
    fc.append(f"[{cur}]ass=subs.ass:fontsdir=fonts,format=yuv420p[vout]")

    # --- audio: narration at scene start + lead, whoosh at each scene cut
    a_parts = []
    for i, t in enumerate(tl):
        d = int((t.start + t.lead) * 1000)
        fc.append(f"[{n + i}:a]aresample=48000,adelay={d}|{d},volume=1.0[n{i}]")
        a_parts.append(f"[n{i}]")
    fc.append("".join(a_parts) + f"amix=inputs={n}:normalize=0:dropout_transition=0,apad[narr_raw]")
    sfx_labels = []
    if cfg["audio"].get("whoosh", True):
        for i in range(1, n):
            d = max(0, int((tl[i].start - 0.18) * 1000))
            fc.append(f"{whoosh_filter()},adelay={d}|{d}[w{i}]")
            sfx_labels.append(f"[w{i}]")
    if music_idx is not None:
        mv = cfg["audio"].get("music_volume", 0.10)
        fc.append("[narr_raw]asplit=2[narr_a][narr_sc]")
        fc.append(f"[{music_idx}:a]aresample=48000,volume={mv},afade=t=in:d=1.5[mus]")
        fc.append("[mus][narr_sc]sidechaincompress=threshold=0.04:ratio=10:attack=15:release=450[mus_d]")
        mix_in = ["[narr_a]", "[mus_d]"] + sfx_labels
    else:
        mix_in = ["[narr_raw]"] + sfx_labels
    fc.append("".join(mix_in) + f"amix=inputs={len(mix_in)}:normalize=0:dropout_transition=0,"
              f"loudnorm=I={cfg['audio'].get('lufs', -14)}:TP=-1.5:LRA=11,atrim=0:{total:.3f},"
              f"afade=t=out:st={max(0.0, total - 0.35):.3f}:d=0.35[aout]")

    (workdir / "filter.txt").write_text(";\n".join(fc), encoding="utf-8")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex_script", "filter.txt",
           "-map", "[vout]", "-map", "[aout]", "-t", f"{total:.3f}",
           "-c:v", "libx264", "-preset", v.get("preset", "medium"), "-crf", str(v.get("crf", 18)),
           "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
           "-r", str(v["fps"]), "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart",
           str(out_mp4.resolve())]
    import subprocess
    log.info("ffmpeg final compose (%.1fs, %d scenes)", total, n)
    proc = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg compose failed:\n" + (proc.stderr or "")[-3000:])


def _pick_music(cfg: dict) -> Path | None:
    d = ROOT / "assets" / "music"
    files = [p for p in d.glob("*") if p.suffix.lower() in (".mp3", ".m4a", ".wav", ".ogg")]
    if not files or not cfg["audio"].get("music", True):
        return None
    return random.choice(files)
