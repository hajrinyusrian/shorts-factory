"""ASS subtitle generation: karaoke word-highlight captions, scene label pills, source badge, sources card."""
from __future__ import annotations

import textwrap

from .timeline import TScene

W, H = 1080, 1920


def ass_color(hex_rgb: str, alpha: int = 0) -> str:
    h = hex_rgb.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def ts(sec: float) -> str:
    sec = max(0.0, sec)
    cs = int(round(sec * 100))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def esc(s: str) -> str:
    return s.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def rrect(w: int, h: int, r: int) -> str:
    """ASS drawing path for a rounded rectangle (top-left origin)."""
    k = int(r * 0.45)
    return (f"m {r} 0 l {w - r} 0 b {w - k} 0 {w} {k} {w} {r} l {w} {h - r} b {w} {h - k} {w - k} {h} {w - r} {h} "
            f"l {r} {h} b {k} {h} 0 {h - k} 0 {h - r} l 0 {r} b 0 {k} {k} 0 {r} 0")


def make_chunks(words, max_line_chars: int = 17, max_lines: int = 2):
    """Group WordTime items into caption chunks (<= max_lines lines of <= max_line_chars)."""
    chunks, cur, lines, line_len = [], [], 1, 0

    def flush():
        nonlocal cur, lines, line_len
        if cur:
            chunks.append(cur)
        cur, lines, line_len = [], 1, 0

    for w in words:
        n = len(w.text)
        if cur and line_len + 1 + n > max_line_chars:
            if lines >= max_lines:
                flush()
            else:
                lines += 1
                line_len = 0
                cur.append(None)  # line break marker
        line_len += (1 if line_len else 0) + n
        cur.append(w)
        if w.text[-1:] in ".!?" or (w.text[-1:] in ",;:" and line_len > 9 and lines >= max_lines):
            flush()
    flush()
    return chunks


def build_ass(tl: list[TScene], cfg: dict, article: dict, palette: dict) -> str:
    st = cfg["subtitles"]
    accent = ass_color(palette.get("accent", "#FFD23F"))
    pill_bg = ass_color(palette.get("pill", "#FFFFFF"))
    ink = ass_color("#1B1F3B")
    white = ass_color("#FFFFFF")
    shadow = ass_color("#000000", 110)
    outline = ass_color("#14102E")
    f_bold, f_semi = st["font_bold"], st["font_semibold"]
    cap_size, cap_y = st["caption_size"], st["caption_y"]

    out = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 2",
        "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding",
        f"Style: Cap,{f_bold},{cap_size},{accent},{white},{outline},{shadow},0,0,0,0,100,100,0,0,1,10,5,5,60,60,0,1",
        f"Style: Pill,{f_bold},{st['label_size']},{ink},{ink},{pill_bg},{shadow},0,0,0,0,100,100,1,0,3,20,0,8,60,60,0,1",
        f"Style: Src,{f_semi},{st['source_size']},{white},{white},{outline},{shadow},0,0,0,0,100,100,0,0,1,4,2,8,60,60,0,1",
        f"Style: Big,{f_bold},{st['card_title_size']},{white},{white},{outline},{shadow},0,0,0,0,100,100,0,0,1,6,3,8,80,80,0,1",
        f"Style: Card,{f_semi},{st['card_body_size']},{white},{white},{outline},{shadow},0,0,0,0,100,100,0,0,1,3,2,8,80,80,0,1",
        f"Style: Shape,{f_bold},20,{ink},{ink},{ink},{ink},0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    def ev(layer, a, b, style, text):
        out.append(f"Dialogue: {layer},{ts(a)},{ts(b)},{style},,0,0,0,,{text}")

    src_line = esc(f"Sumber: {article['publisher']}")
    for t in tl:
        sc = t.scene
        a, b = t.start, t.end + (0.0 if sc.kind == "outro" else 0.0)
        if sc.kind == "outro":
            _outro_card(ev, t, article, st, palette)
            continue
        # label pill (top) - in still/infographic mode the label is drawn as big text by pipeline/infographic.py
        if st.get("label_pill", True):
            ev(2, a + 0.15, b - 0.05, "Pill",
               rf"{{\an8\pos({W // 2},{st['label_y']})\fad(150,120)\fscx70\fscy70\t(0,200,\fscx108\fscy108)"
               rf"\t(200,320,\fscx100\fscy100)}}{esc(sc.label.upper() if st.get('label_upper', True) else sc.label)}")
        # persistent source badge
        ev(2, a + 0.35, b - 0.05, "Src",
           rf"{{\an8\pos({W // 2},{st['label_y'] + st['label_size'] + 62})\fad(200,100)}}{src_line}")
        # karaoke captions
        base = t.start + t.lead
        for chunk in make_chunks(t.voice.words, st["max_line_chars"], 2):
            ws = [w for w in chunk if w is not None]
            c0 = base + ws[0].start
            c1 = base + ws[-1].end
            # hold the caption a hair past the last word but never into the next chunk (handled by next start)
            c1 = min(c1 + 0.12, t.end - 0.02)
            parts, wi = [], 0
            for item in chunk:
                if item is None:
                    parts.append(r"\N")
                    continue
                nxt = None
                for j in range(wi + 1, len(ws)):
                    nxt = ws[j]
                    break
                dur = ((base + nxt.start) if nxt else c1) - (base + item.start)
                cs = max(1, int(round(dur * 100)))
                parts.append(rf"{{\k{cs}}}{esc(item.text)} ")
                wi += 1
            text = "".join(parts).replace(r" \N", r"\N").rstrip()
            ev(3, c0 - 0.03, c1, "Cap",
               rf"{{\an5\pos({W // 2},{cap_y})\fad(40,0)\fscx86\fscy86\t(0,110,\fscx106\fscy106)"
               rf"\t(110,210,\fscx100\fscy100)}}{text}")
    return "\n".join(out) + "\n"


def _outro_card(ev, t: TScene, article: dict, st: dict, palette: dict):
    a, b = t.start + 0.2, t.end
    cx = W // 2
    top = st["card_y"]
    card_w, card_h = 960, 520
    ev(1, a, b, "Shape",
       rf"{{\an7\pos({cx - card_w // 2},{top})\1c&H2A1410&\1a&H40&\bord0\shad0\fad(200,0)\p1}}{rrect(card_w, card_h, 44)}{{\p0}}")
    ev(2, a + 0.1, b, "Pill",
       rf"{{\an8\pos({cx},{top - 40})\fad(200,0)}}SUMBER")
    ev(3, a + 0.15, b, "Big",
       rf"{{\an8\pos({cx},{top + 60})\fad(250,0)}}{esc(article['publisher'])}")
    title = esc(article["title"])
    wrapped = r"\N".join(textwrap.wrap(title, 38)[:3])
    ev(3, a + 0.25, b, "Card", rf"{{\an8\pos({cx},{top + 190})\fad(300,0)}}{wrapped}")
    meta = " | ".join(x for x in (article.get("domain", ""), article.get("date", "")) if x)
    ev(3, a + 0.35, b, "Src", rf"{{\an8\pos({cx},{top + card_h - 110})\fad(300,0)}}{esc(meta)}")
