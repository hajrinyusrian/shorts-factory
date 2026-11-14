"""Indonesian neural TTS (edge-tts, free) with word-level timing for karaoke captions."""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

import edge_tts

from .utils import ffprobe_duration, log, run

TICKS = 10_000_000.0  # edge-tts offsets are in 100-ns units


@dataclass
class WordTime:
    text: str
    start: float
    end: float


@dataclass
class Voiced:
    path: Path
    duration: float
    words: list[WordTime]   # aligned to the ORIGINAL (display) words


def speak_text(text: str, pron: dict[str, str]) -> tuple[str, list[int]]:
    """Apply pronunciation fixes. Returns (tts_text, tokens_per_original_word)."""
    out_words, counts = [], []
    for w in text.split():
        core = re.sub(r"^\W+|\W+$", "", w)
        rep = pron.get(core) or pron.get(core.upper())
        spoken = w.replace(core, rep, 1) if rep and core else w
        out_words.append(spoken)
        counts.append(max(1, len(re.findall(r"\w+", spoken))))
    return " ".join(out_words), counts


async def _stream(text: str, voice: str, rate: str, pitch: str, mp3: Path) -> list[dict]:
    comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, boundary="WordBoundary")
    bounds: list[dict] = []
    with open(mp3, "wb") as fh:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                fh.write(chunk["data"])
            elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                bounds.append(chunk)
    return bounds


def _align(display_words: list[str], counts: list[int], bounds: list[dict], duration: float) -> list[WordTime]:
    wb = [b for b in bounds if b["type"] == "WordBoundary"]
    n = len(display_words)
    if wb and sum(counts) == len(wb):
        out, k = [], 0
        for w, c in zip(display_words, counts):
            first, last = wb[k], wb[k + c - 1]
            out.append(WordTime(w, first["offset"] / TICKS, (last["offset"] + last["duration"]) / TICKS))
            k += c
        return out
    # fallback: proportional to character length inside the spoken span
    if wb:
        t0 = wb[0]["offset"] / TICKS
        t1 = (wb[-1]["offset"] + wb[-1]["duration"]) / TICKS
    else:
        t0, t1 = 0.05, max(0.2, duration - 0.05)
    weights = [len(w) + (3 if re.search(r"[,.!?;:]$", w) else 0) + 1 for w in display_words]
    tot, acc, out = float(sum(weights)), 0.0, []
    for w, wt in zip(display_words, weights):
        s = t0 + (t1 - t0) * acc / tot
        acc += wt
        out.append(WordTime(w, s, t0 + (t1 - t0) * acc / tot))
    return out


def synthesize(text: str, out_mp3: Path, cfg: dict, retries: int = 4) -> Voiced:
    t = cfg["tts"]
    tts_text, counts = speak_text(text, t.get("pronunciation", {}))
    display = text.split()
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            bounds = asyncio.run(_stream(tts_text, t["voice"], t.get("rate", "+0%"), t.get("pitch", "+0Hz"), out_mp3))
            if out_mp3.stat().st_size < 2000:
                raise RuntimeError("empty audio")
            dur = ffprobe_duration(out_mp3)
            words = _align(display, counts, bounds, dur)
            return Voiced(out_mp3, dur, words)
        except Exception as exc:  # noqa: BLE001
            last = exc
            log.warning("TTS attempt %d failed: %s", attempt, str(exc)[:140])
            import time
            time.sleep(2 * attempt)
    if t.get("fallback_gtts", True):
        log.warning("edge-tts unavailable -> falling back to gTTS (no word timing, proportional captions)")
        try:
            from gtts import gTTS
            gTTS(text=text, lang="id").save(str(out_mp3))
            dur = ffprobe_duration(out_mp3)
            return Voiced(out_mp3, dur, _align(display, [1] * len(display), [], dur))
        except Exception as exc:  # noqa: BLE001
            last = exc
    raise RuntimeError(f"TTS failed: {last}")
