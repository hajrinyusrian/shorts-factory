"""Orchestrator:  idea (from a real article) -> verified facts -> script -> voice -> 3D render -> video -> YouTube.

    python -m pipeline.main                    # full run, uploads
    python -m pipeline.main --dry-run          # everything except the upload / history update
    python -m pipeline.main --profile fast     # cheaper 3D render
    python -m pipeline.main --url <article>    # force a specific article
"""
from __future__ import annotations

import argparse
import json
import random
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path

from . import state
from .compose import compose, make_clip
from .facts import build_fact_sheet, pick_candidates_order
from .llm import LLM
from .render3d import render_all
from .script_writer import write_script
from .sources import Article, Candidate, fetch_article, fetch_candidates
from .subtitles import build_ass
from .timeline import build_timeline, total_duration
from .upload import upload
from .utils import ROOT, load_config, log, slugify
from .constants import PALETTES

# palette accent colours must mirror blender/render_scene.py (used for caption highlight colour)
PALETTE_UI = {
    "ocean": "#FFC53D", "sunset": "#FFD23F", "mint": "#FF9F1C", "candy": "#FDE047", "sky": "#FB923C", "dusk": "#FFB020",
}


def pick_article(llm: LLM, cfg: dict, forced_url: str | None):
    sel = cfg["selection"]
    if forced_url:
        c = Candidate(title=forced_url, url=forced_url, publisher=forced_url.split("/")[2].removeprefix("www."),
                      tier=1, published_ts=time.time())
        a = fetch_article(c, sel["min_article_chars"])
        if not a:
            raise RuntimeError("could not read the forced article")
        yield a
        return
    cands = fetch_candidates(cfg)
    log.info("%d fresh unseen candidates", len(cands))
    tried = 0
    for c in pick_candidates_order(llm, cands):
        if tried >= sel["max_articles_to_try"]:
            break
        tried += 1
        art = fetch_article(c, sel["min_article_chars"])
        if art:
            yield art


def description_text(script, art: Article, cfg: dict) -> str:
    tags = " ".join(cfg["channel"]["hashtags"])
    src = [f"Sumber utama: {art.publisher} - {art.title}", art.url]
    if art.date:
        src.append(f"Tanggal terbit: {art.date}")
    return (f"{script.summary}\n\n" + "\n".join(src) + f"\n\n{cfg['channel']['description_footer']}\n\n{tags}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="build the video but do not upload or record history")
    ap.add_argument("--profile", choices=["fast", "balanced", "high"], default=None)
    ap.add_argument("--url", default=None, help="use this article instead of the feeds")
    ap.add_argument("--out", default=str(ROOT / "out"))
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    cfg = load_config(args.config)
    t0 = time.time()
    llm = LLM(cfg["llm"]["models"])

    # ---- 1) article -> verified facts ------------------------------------------------------
    art, facts = None, []
    for cand in pick_article(llm, cfg, args.url):
        log.info("candidate: [%s] %s", cand.publisher, cand.title[:90])
        fs = build_fact_sheet(llm, cand, cfg)
        if len(fs) >= cfg["selection"]["min_verified_facts"]:
            art, facts = cand, fs
            break
        log.info("only %d verified facts -> next article", len(fs))
    if not art:
        raise SystemExit("No article produced enough verified facts. Nothing published.")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    work = Path(args.out) / f"{stamp}-{slugify(art.title, 32)}"
    work.mkdir(parents=True, exist_ok=True)
    (work / "facts.json").write_text(json.dumps([f.to_dict() for f in facts], ensure_ascii=False, indent=2), "utf-8")

    # ---- 2) script (validated) + voice timeline; shorten if it overruns -------------------------
    palette_name = random.Random(art.url).choice(PALETTES)
    script, tl, shorter = None, None, False
    for attempt in range(2):
        script = write_script(llm, facts, art, cfg, shorter=shorter)
        tl = build_timeline(script, art.publisher, work, cfg, palette_name, seed=zlib.crc32(art.url.encode()) % 1000)
        dur = total_duration(tl)
        log.info("timeline total %.1fs (max %ds)", dur, cfg["video"]["max_seconds"])
        if dur <= cfg["video"]["max_seconds"]:
            break
        shorter = True
    else:
        raise SystemExit("script still too long after retry")
    (work / "script.json").write_text(json.dumps(script.to_dict(), ensure_ascii=False, indent=2), "utf-8")

    # ---- 3) 3D render with Blender -----------------------------------------------------------------
    prof_name = args.profile or cfg["render3d"]["profile"]
    prof = cfg["render3d"]["profiles"][prof_name]
    dirs = render_all(tl, work, cfg, prof_name)

    # ---- 4) captions + final video -----------------------------------------------------------------
    v = cfg["video"]
    clips = []
    for t in tl:
        clip = work / f"clip_{t.index:02d}.mp4"
        make_clip(dirs[t.index], clip, prof["fps"], v["width"], v["height"], cfg, prof["width"])
        clips.append(clip)
    article_meta = {"publisher": art.publisher, "title": art.title, "date": art.date, "domain": art.meta.get("domain", "")}
    ass = build_ass(tl, cfg, article_meta, {"accent": PALETTE_UI.get(palette_name, "#FFD23F")})
    (work / "subs.ass").write_text(ass, encoding="utf-8")
    final = work / "video.mp4"
    compose(tl, clips, work / "subs.ass", work, final, cfg)

    desc = description_text(script, art, cfg)
    (work / "description.txt").write_text(f"{script.title}\n\n{desc}\n\nTAGS: {', '.join(script.tags)}\n", "utf-8")
    log.info("video ready: %s (%.1f MB) in %.1f min", final, final.stat().st_size / 1e6, (time.time() - t0) / 60)

    # ---- 5) upload + history ---------------------------------------------------------------------------
    if args.dry_run:
        log.info("dry run: not uploading")
        return
    vid = upload(final, f"{script.title}", desc, script.tags + ["Shorts"], cfg)
    state.record({"video_id": vid, "title": script.title, "source_url": art.url, "source_title": art.title,
                  "publisher": art.publisher})
    log.info("done: https://youtube.com/shorts/%s", vid)


if __name__ == "__main__":
    main()
