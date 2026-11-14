"""Scene timeline: audio durations -> scene start/length, frame counts, outro card."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from .script_writer import Scene, Script
from .tts import Voiced, synthesize
from .utils import log


@dataclass
class TScene:
    scene: Scene
    voice: Voiced
    start: float = 0.0          # when this scene begins on the final timeline
    length: float = 0.0         # visible length (without the cross-fade tail)
    lead: float = 0.0           # silence before narration starts inside the scene
    index: int = 0
    mascot_side: int = 1
    palette: str = "ocean"
    camera: str = "push"
    seed: int = 1

    @property
    def end(self) -> float:
        return self.start + self.length


def build_outro(script: Script, publisher: str) -> Scene:
    text = f"Sumber: {publisher}. Tautannya ada di deskripsi. Follow untuk fakta teknologi berikutnya!"
    return Scene(narration=text, label="Sumber", prop="globe", emotion="happy", fact_ids=[], kind="outro")


def build_timeline(script: Script, publisher: str, workdir: Path, cfg: dict, palette: str, seed: int) -> list[TScene]:
    v = cfg["video"]
    tl: list[TScene] = []
    scenes = list(script.scenes) + [build_outro(script, publisher)]
    t = 0.0
    cams = cfg["render3d"].get("camera_moves", ["push", "orbit", "pull"])
    for i, sc in enumerate(scenes):
        mp3 = workdir / f"voice_{i:02d}.mp3"
        voice = synthesize(sc.narration, mp3, cfg)
        lead = v["first_scene_lead"] if i == 0 else v["scene_lead"]
        tail = v["scene_tail"] if i < len(scenes) - 1 else v["last_tail"]
        length = lead + voice.duration + tail
        ts = TScene(scene=sc, voice=voice, start=t, length=length, lead=lead, index=i,
                    mascot_side=1 if i % 2 == 0 else -1, palette=palette, camera=cams[i % len(cams)],
                    seed=seed * 31 + i)
        tl.append(ts)
        t += length
        log.info("scene %d [%s] %.1fs  voice=%.1fs  prop=%s", i, sc.kind, length, voice.duration, sc.prop)
    return tl


def total_duration(tl: list[TScene]) -> float:
    return tl[-1].end if tl else 0.0


def frames_for(length: float, fps: int, extra: float) -> int:
    return int(math.ceil((length + extra) * fps))
