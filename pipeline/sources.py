"""Find fresh, reputable tech/science articles and download their full text.

Facts must come from a *real, linkable* article, so this module only ever returns
articles we could fetch and extract ourselves.
"""
from __future__ import annotations

import calendar
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import feedparser
import requests
import trafilatura

from . import state
from .utils import log

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36 ShortsFactoryBot/1.0")
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.8"}


@dataclass
class Candidate:
    title: str
    url: str
    publisher: str
    tier: int
    published_ts: float
    summary: str = ""

    @property
    def age_days(self) -> float:
        return (time.time() - self.published_ts) / 86400


@dataclass
class Article:
    title: str
    url: str
    publisher: str
    author: str
    date: str
    text: str
    meta: dict = field(default_factory=dict)


def _entry_ts(e) -> float:
    for key in ("published_parsed", "updated_parsed"):
        v = getattr(e, key, None) or e.get(key)
        if v:
            return float(calendar.timegm(v))
    return 0.0


def fetch_candidates(cfg: dict, history: list[dict] | None = None) -> list[Candidate]:
    sel = cfg["selection"]
    history = state.load() if history is None else history
    out: list[Candidate] = []
    for feed in cfg["feeds"]:
        try:
            r = requests.get(feed["url"], headers=HEADERS, timeout=20)
            r.raise_for_status()
            parsed = feedparser.parse(r.content)
        except Exception as exc:  # noqa: BLE001
            log.warning("feed failed %s: %s", feed["name"], str(exc)[:120])
            continue
        n = 0
        for e in parsed.entries[:40]:
            ts = _entry_ts(e)
            link = e.get("link")
            title = (e.get("title") or "").strip()
            if not link or not title or not ts:
                continue
            c = Candidate(title=title, url=link, publisher=feed["name"], tier=int(feed.get("tier", 2)),
                          published_ts=ts, summary=(e.get("summary") or "")[:500])
            if c.age_days > sel["max_age_days"] or c.age_days < -0.2:
                continue
            if state.is_seen(c.url, c.title, history):
                continue
            out.append(c)
            n += 1
        log.info("feed %-24s -> %d fresh candidates", feed["name"], n)
    # best tier first, then newest
    out.sort(key=lambda c: (c.tier, -c.published_ts))
    # de-duplicate near-identical titles across feeds
    uniq, seen = [], set()
    for c in out:
        k = " ".join(sorted(set(c.title.lower().split())))
        if k in seen:
            continue
        seen.add(k)
        uniq.append(c)
    return uniq


def fetch_article(c: Candidate, min_chars: int) -> Article | None:
    try:
        r = requests.get(c.url, headers=HEADERS, timeout=25, allow_redirects=True)
        r.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        log.warning("article fetch failed (%s): %s", c.url, str(exc)[:100])
        return None
    html = r.text
    text = trafilatura.extract(html, include_comments=False, include_tables=False, favor_precision=True,
                               url=r.url)
    if not text or len(text) < min_chars:
        log.info("skip (too short/paywalled: %s chars): %s", len(text or ""), c.title[:70])
        return None
    meta = trafilatura.extract_metadata(html, default_url=r.url)
    author = (getattr(meta, "author", None) or "").strip() if meta else ""
    date = (getattr(meta, "date", None) or "").strip() if meta else ""
    if not date:
        date = time.strftime("%Y-%m-%d", time.gmtime(c.published_ts))
    title, publisher = c.title, c.publisher
    if meta and (title == c.url or title.startswith("http")) and getattr(meta, "title", None):
        title = meta.title.strip()
    if meta and getattr(meta, "sitename", None) and c.publisher == urlsplit(c.url).netloc.removeprefix("www."):
        publisher = meta.sitename.strip()
    return Article(title=title, url=r.url, publisher=publisher, author=author, date=date, text=text,
                   meta={"domain": urlsplit(r.url).netloc.removeprefix("www.")})
