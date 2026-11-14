"""Illustration + big text + infographic frames (Pillow).

One still 3D illustration per scene (rendered by Blender) is animated with a slow Ken-Burns move.
On top of it we draw either
  * a STAT card (big count-up number, a fill bar for percentages, unit text), when the narration contains a
    number, or
  * a KEYWORD card (the scene label in huge type) otherwise.

Fact safety: a stat is only ever taken from the scene's own narration, and the script validator has already
checked that every number in the narration exists in the verified facts. Nothing is invented here.
"""
from __future__ import annotations

import math
import multiprocessing as mp
import os
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

from .utils import ROOT, log

W, H = 1080, 1920
FONT_BOLD = ROOT / "assets" / "fonts" / "Poppins-ExtraBold.ttf"
FONT_SEMI = ROOT / "assets" / "fonts" / "Poppins-SemiBold.ttf"
INK = (22, 24, 48, 255)
WHITE = (255, 255, 255, 255)


# --------------------------------------------------------------------------- stat extraction
@dataclass
class Stat:
    kind: str          # percent | number | year
    value: float
    text: str          # exactly as written in the narration ("48", "1.200")
    unit: str          # word after the number ("nanometer"), "" if none / percent
    decimals: int = 0
    grouped: bool = False

    @property
    def display(self) -> str:
        return f"{self.text}%" if self.kind == "percent" else self.text

    def display_at(self, frac: float) -> str:
        """Count-up text at 0..1 of the way to the final value (final frame returns the original text)."""
        if frac >= 1.0 or self.kind == "year":
            return self.display
        v = self.value * max(0.0, frac)
        if self.decimals:
            s = f"{v:.{self.decimals}f}".replace(".", ",")
        elif self.grouped:
            s = f"{int(round(v)):,}".replace(",", ".")
        else:
            s = str(int(round(v)))
        return f"{s}%" if self.kind == "percent" else s


_NUM = re.compile(r"(?<![\w.,])(\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?)(?:\s*(%|[A-Za-z]+))?")


def extract_stat(text: str) -> Stat | None:
    """Pick the most chart-worthy number of a sentence: a percentage first, then a plain quantity, then a year."""
    cands: list[Stat] = []
    for m in _NUM.finditer(text):
        raw, unit = m.group(1), (m.group(2) or "")
        grouped = bool(re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", raw))
        decimals = 0
        if grouped:
            value = float(re.sub(r"[.,]", "", raw))
        else:
            value = float(raw.replace(",", "."))
            decimals = len(re.split(r"[.,]", raw)[1]) if re.search(r"[.,]", raw) else 0
        is_pct = unit == "%" or unit.lower() == "persen"
        is_year = (not is_pct and not grouped and not decimals and len(raw) == 4 and 1900 <= value <= 2100)
        kind = "percent" if is_pct else ("year" if is_year else "number")
        cands.append(Stat(kind, value, raw, "" if is_pct else unit.lower(), decimals, grouped))
    for want in ("percent", "number", "year"):
        for c in cands:
            if c.kind == want:
                return c
    return None


# --------------------------------------------------------------------------- drawing helpers
def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def _wrap(text: str, font, max_w: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if font.getlength(trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _fit_lines(text: str, path: Path, max_w: int, max_lines: int, start: int, minimum: int):
    size = start
    while size >= minimum:
        f = _font(path, size)
        lines = _wrap(text, f, max_w)
        if len(lines) <= max_lines and all(f.getlength(l) <= max_w for l in lines):
            return f, lines, size
        size -= 4
    f = _font(path, minimum)
    return f, _wrap(text, f, max_w)[:max_lines], minimum


def _text_layer(lines: list[str], font, size: int, fill, width: int, stroke: int = 9, line_gap: float = 1.08) -> Image.Image:
    """Centered outlined text on a transparent layer, with a soft drop shadow."""
    lh = int(size * line_gap)
    h = lh * len(lines) + stroke * 2 + 30
    layer = Image.new("RGBA", (width, h), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (width, h), (0, 0, 0, 0))
    d, ds = ImageDraw.Draw(layer), ImageDraw.Draw(shadow)
    for i, line in enumerate(lines):
        x = (width - font.getlength(line)) / 2
        y = stroke + 6 + i * lh
        ds.text((x, y + 10), line, font=font, fill=(10, 10, 30, 150), stroke_width=stroke, stroke_fill=(10, 10, 30, 150))
        d.text((x, y), line, font=font, fill=fill, stroke_width=stroke, stroke_fill=INK)
    return Image.alpha_composite(shadow, layer)


def _ease_out_cubic(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


def _ease_out_back(x: float) -> float:
    x = min(1.0, max(0.0, x))
    c1, c3 = 1.4, 2.4
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def _hex(c: str, a: int = 255):
    c = c.lstrip("#")
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), a)


# --------------------------------------------------------------------------- scene renderer
class SceneRenderer:
    """Builds the frames of one scene. Heavy text layers are prepared once; per frame we only crop/zoom the still
    and composite an animated card."""

    ZONE_Y = 1030         # top of the big-text zone (just below the 3D object)
    ZONE_H = 400          # must end above the karaoke caption (subtitles.caption_y)

    def __init__(self, still: Path, big_text: str, stat: Stat | None, lead: float, accent: str, move: str,
                 n_frames: int, fps: int, tag: str = ""):
        self.still = Image.open(still).convert("RGB")
        self.n, self.fps, self.lead, self.move = n_frames, fps, lead, move
        self.accent = _hex(accent)
        self.stat = stat
        self.big_text = big_text.strip()
        self.tag_layer = self._make_tag(tag) if tag else None
        self.t0 = lead + 0.12                      # card entrance start (s)
        self.card_w = 820   # keeps text clear of the Shorts right-hand button column (x > ~950)
        if stat is not None:
            self._prep_stat()
        elif self.big_text:
            f, lines, size = _fit_lines(self.big_text.upper(), FONT_BOLD, self.card_w, 2, 116, 76)
            self.layer = _text_layer(lines, f, size, WHITE, W)
        else:
            self.layer = None

    def _make_tag(self, text: str) -> Image.Image:
        """Small accent pill above the big text (used to mark the ANALYSIS scene as opinion)."""
        f = _font(FONT_BOLD, 40)
        tw = int(f.getlength(text))
        w, h = tw + 64, 64
        layer = Image.new("RGBA", (W, h + 8), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        x0 = (W - w) // 2
        d.rounded_rectangle((x0, 0, x0 + w, h), radius=h // 2, fill=self.accent, outline=INK, width=5)
        d.text((x0 + 32, 8), text, font=f, fill=INK)
        return layer

    # ---- stat card pieces
    def _prep_stat(self) -> None:
        s = self.stat
        self.num_font = _font(FONT_BOLD, 210 if len(s.display) <= 6 else 160)
        self.unit_layer = None
        if s.unit and s.kind == "number":
            uf, ul, us = _fit_lines(s.unit.upper(), FONT_SEMI, self.card_w, 1, 54, 36)
            self.unit_layer = _text_layer(ul, uf, us, _hex("#FFFFFF"), W, stroke=5)
        self._num_cache: dict[str, Image.Image] = {}

    def _num_layer(self, txt: str) -> Image.Image:
        if txt not in self._num_cache:
            size = self.num_font.size
            self._num_cache[txt] = _text_layer([txt], self.num_font, size, self.accent, W, stroke=10, line_gap=1.0)
            if len(self._num_cache) > 400:
                self._num_cache.pop(next(iter(self._num_cache)))
        return self._num_cache[txt]

    def _bar(self, frac: float) -> Image.Image:
        w, h = 760, 30
        layer = Image.new("RGBA", (W, h + 12), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        x0 = (W - w) // 2
        d.rounded_rectangle((x0 - 5, 1, x0 + w + 5, h + 7), radius=20, fill=INK)
        d.rounded_rectangle((x0, 6, x0 + w, h + 2), radius=14, fill=(255, 255, 255, 70))
        fw = int(w * min(1.0, max(0.0, frac)))
        if fw >= 18:
            d.rounded_rectangle((x0, 6, x0 + fw, h + 2), radius=14, fill=self.accent)
        return layer

    # ---- Ken-Burns crop box on the still
    def _box(self, k: float):
        W0, H0 = self.still.size
        k = k * k * (3 - 2 * k)
        if self.move == "pull":
            z, cx = 1.08 - 0.08 * k, 0.5
        elif self.move == "orbit":
            z, cx = 1.06, 0.47 + 0.06 * k
        else:
            z, cx = 1.0 + 0.08 * k, 0.5
        bw, bh = W0 / z, H0 / z
        x0 = min(max(cx * W0 - bw / 2, 0), W0 - bw)
        y0 = min(max(0.47 * H0 - bh / 2, 0), H0 - bh)
        return (x0, y0, x0 + bw, y0 + bh)

    def frame(self, i: int) -> Image.Image:
        t = i / self.fps
        base = self.still.resize((W, H), Image.BICUBIC, box=self._box(i / max(1, self.n - 1)))
        a = _ease_out_back((t - self.t0) / 0.45) if t >= self.t0 else 0.0
        if a <= 0.01:
            return base
        alpha = min(1.0, a)
        dy = int((1 - min(1.0, a)) * 80 + 5 * math.sin(t * 2.0))
        parts: list[tuple[Image.Image, int]] = []
        y = self.ZONE_Y + dy
        if self.tag_layer is not None:
            parts.append((self.tag_layer, y - 10))
            y += self.tag_layer.height + 6
        if self.stat is not None:
            frac = _ease_out_cubic((t - self.t0 - 0.1) / 1.0)
            s = self.stat
            num = self._num_layer(s.display_at(frac))
            parts.append((num, y))
            y += num.height - 8
            if s.kind == "percent":
                parts.append((self._bar(frac * min(100.0, s.value) / 100.0), y))
                y += 46
            elif self.unit_layer is not None:
                parts.append((self.unit_layer, y))
        elif self.layer is not None:
            parts.append((self.layer, y + 10))
        rgba = base.convert("RGBA")
        for layer, ly in parts:
            lay = layer
            if alpha < 1.0:
                lay = layer.copy()
                lay.putalpha(ImageChops.multiply(layer.split()[3], Image.new("L", layer.size, int(255 * alpha))))
            rgba.alpha_composite(lay, (0, max(0, ly)))
        return rgba.convert("RGB")


_R: SceneRenderer | None = None
_OUT: Path | None = None


def _render_index(i: int) -> None:
    assert _R is not None and _OUT is not None
    _R.frame(i).save(_OUT / f"f_{i + 1:04d}.jpg", quality=93, subsampling=0)


def render_scene_frames(still: Path, out_dir: Path, n_frames: int, fps: int, big_text: str, stat: Stat | None,
                        lead: float, accent: str, move: str, workers: int | None = None, tag: str = "") -> int:
    """Write n_frames JPEGs (f_0001.jpg ...) for one scene. Returns the number of frames written."""
    global _R, _OUT
    out_dir.mkdir(parents=True, exist_ok=True)
    _R, _OUT = SceneRenderer(still, big_text, stat, lead, accent, move, n_frames, fps, tag), out_dir
    workers = workers or max(1, min(4, os.cpu_count() or 1))
    if workers == 1 or n_frames < 24:
        for i in range(n_frames):
            _render_index(i)
    else:
        with mp.get_context("fork").Pool(workers) as pool:
            pool.map(_render_index, range(n_frames), chunksize=12)
    return n_frames


def build_scene_frames(tl, stills: dict[int, Path], workdir: Path, cfg: dict, accent: str) -> dict[int, Path]:
    """Frames for every scene of the timeline (30 fps JPEG sequences). Outro keeps the plain illustration."""
    fps, xf = cfg["video"]["fps"], cfg["video"]["transition"]
    dirs: dict[int, Path] = {}
    for t in tl:
        n = int(math.ceil((t.length + xf) * fps))
        d = workdir / "frames" / f"s{t.index:02d}"
        if d.exists():
            for old in d.glob("f_*.jpg"):
                old.unlink()
        outro = t.scene.kind == "outro"
        analysis = t.scene.kind == "analysis"
        stat = None if (outro or analysis) else extract_stat(t.scene.narration)
        text = "" if outro else t.scene.label
        done = render_scene_frames(stills[t.index], d, n, fps, text, stat, t.lead, accent, t.camera,
                                   tag="ANALISIS KAMI" if analysis else "")
        log.info("scene %d frames: %d (%s)", t.index, done,
                 f"stat {stat.display}" if stat else ("outro" if outro else "keyword"))
        dirs[t.index] = d
    return dirs
