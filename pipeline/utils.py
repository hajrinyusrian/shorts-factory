"""Small shared helpers: config, logging, subprocess, text normalisation."""
from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def setup_logging() -> logging.Logger:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    return logging.getLogger("shorts")


log = setup_logging()


def load_config(path: str | os.PathLike | None = None) -> dict:
    path = Path(path) if path else ROOT / "config.yaml"
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def run(cmd: list[str], *, check: bool = True, quiet: bool = False, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run a command, stream nothing unless it fails."""
    if not quiet:
        log.info("$ %s", " ".join(str(c) for c in cmd)[:300])
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if check and proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-3000:]
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(map(str, cmd))[:200]}\n{tail}")
    return proc


def run_stream(cmd: list[str], on_line=None, *, tail_chars: int = 3000) -> str:
    """Run a command and hand every output line to `on_line` while it runs (so CI logs show live progress).

    stderr is merged into stdout. Raises RuntimeError with the output tail if the command fails.
    Returns the output tail.
    """
    log.info("$ %s", " ".join(str(c) for c in cmd)[:300])
    tail = ""
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
                          errors="replace") as proc:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip("\n")
            tail = (tail + line + "\n")[-tail_chars:]
            if on_line:
                on_line(line)
        code = proc.wait()
    if code != 0:
        raise RuntimeError(f"command failed ({code}): {' '.join(map(str, cmd))[:200]}\n{tail}")
    return tail


def ffprobe_duration(path: str | os.PathLike) -> float:
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1", str(path)],
              quiet=True).stdout.strip()
    return float(out)


# ---------------------------------------------------------------------------
# text normalisation used for fact verification
# ---------------------------------------------------------------------------
_QUOTES = {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-",
           "\u2212": "-", "\u00a0": " ", "\u2009": " ", "\u200a": " ", "\u200b": ""}


def norm_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    for k, v in _QUOTES.items():
        s = s.replace(k, v)
    s = re.sub(r"\s+", " ", s).strip().casefold()
    return s


_NUM_RE = re.compile(r"\d[\d.,]*\d|\d")


def number_tokens(s: str) -> set[str]:
    """Digits-only canonical numbers: '1,000' == '1.000' == '1000'; '3.5' == '3,5' == '35'."""
    return {re.sub(r"[.,]", "", m) for m in _NUM_RE.findall(s or "")}


def slugify(s: str, n: int = 48) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:n] or "video"


def env(name: str, default: str | None = None, required: bool = False) -> str | None:
    v = os.environ.get(name, default)
    if required and not v:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return v
