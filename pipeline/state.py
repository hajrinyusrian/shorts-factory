"""History of what has already been published, so topics never repeat."""
from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from rapidfuzz import fuzz

from .utils import ROOT, norm_text

HISTORY = ROOT / "data" / "history.json"


def canon_url(url: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc.lower(), p.path.rstrip("/"), "", ""))


def load() -> list[dict]:
    if HISTORY.exists():
        try:
            return json.loads(HISTORY.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
    return []


def is_seen(url: str, title: str, history: list[dict] | None = None) -> bool:
    history = load() if history is None else history
    cu, nt = canon_url(url), norm_text(title)
    for h in history:
        if canon_url(h.get("source_url", "")) == cu:
            return True
        if fuzz.token_set_ratio(nt, norm_text(h.get("source_title", ""))) >= 88:
            return True
    return False


def record(entry: dict, keep: int = 400) -> None:
    hist = load()
    entry = dict(entry, ts=int(time.time()))
    hist.append(entry)
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    HISTORY.write_text(json.dumps(hist[-keep:], ensure_ascii=False, indent=2), encoding="utf-8")
