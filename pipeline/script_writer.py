"""Turn verified facts into a Shorts script (Indonesian narration + per-scene 3D directions).

The model is only allowed to use the verified facts. Its output is validated by code
(numbers, length, props, ids) and regenerated with feedback until it passes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Literal

from pydantic import BaseModel, Field

from .constants import PROPS, PROP_KEYS, EMOTIONS
from .facts import Fact
from .llm import LLM
from .sources import Article
from .utils import log, number_tokens


class SceneOut(BaseModel):
    narration: str = Field(description="narasi Bahasa Indonesia untuk scene ini")
    label: str = Field(description="label singkat di layar, maks 28 karakter")
    prop: Literal["chip", "planet", "rocket", "battery", "neural", "globe", "bulb", "shield", "atom", "gear"]
    emotion: Literal["happy", "surprised", "thinking", "excited", "proud"]
    fact_ids: list[int] = Field(description="id fakta yang dipakai di scene ini")


class ScriptOut(BaseModel):
    title: str
    summary: str = Field(description="1-2 kalimat ringkasan untuk deskripsi video")
    tags: list[str]
    scenes: list[SceneOut]


@dataclass
class Scene:
    narration: str
    label: str
    prop: str
    emotion: str
    fact_ids: list[int]
    kind: str = "fact"   # hook | fact | kicker | outro


@dataclass
class Script:
    title: str
    summary: str
    tags: list[str]
    scenes: list[Scene] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


SYSTEM = """Kamu penulis naskah YouTube Shorts "Fakta Teknologi" berbahasa Indonesia yang akurat, hangat, dan menghibur.
Gaya: kalimat pendek, bahasa Indonesia santai tapi baku-secukupnya, seperti teman yang pintar menjelaskan.
ATURAN KERAS (akurasi lebih penting daripada gaya):
1. Gunakan HANYA informasi dari daftar FAKTA TERVERIFIKASI. Dilarang menambah fakta, angka, nama, tanggal, atau perbandingan dari luar daftar.
2. Setiap angka yang kamu sebut harus identik dengan angka di fakta. Jangan membuat penomoran (mis. "fakta 1").
3. Jaga atribusi: sebut "menurut <pihak>" bila fakta berupa klaim/hasil pihak tertentu. Jangan menyebut sesuatu "terbukti", "pertama di dunia", "terbaik", atau "revolusioner" kecuali tertulis di fakta.
4. Tulis singkatan agar terbaca benar oleh mesin suara: pisahkan huruf dengan spasi, mis. "A I", "G P U", "C P U".
5. Tanpa emoji, hashtag, tautan, atau tanda bintang di narasi."""


def _prop_help() -> str:
    return "\n".join(f"- {k}: {v}" for k, v in PROPS.items())


def build_prompt(facts: list[Fact], art: Article, cfg: dict, feedback: list[str] | None, shorter: bool) -> str:
    sc = cfg["script"]
    fl = "\n".join(f"[{f.id}] {f.claim}" for f in facts)
    fb = ""
    if feedback:
        fb = "\nPERBAIKI MASALAH BERIKUT dari percobaan sebelumnya:\n" + "\n".join(f"- {e}" for e in feedback)
    if shorter:
        fb += "\n- Naskah sebelumnya terlalu panjang untuk durasi Shorts. Buat LEBIH RINGKAS."
    return f"""Buat naskah Shorts dari fakta terverifikasi berikut.
Sumber: {art.publisher} - "{art.title}" ({art.date})

FAKTA TERVERIFIKASI:
{fl}

STRUKTUR ({sc['min_scenes']}-{sc['max_scenes']} scene):
- Scene 1 = HOOK ({sc['hook_words'][0]}-{sc['hook_words'][1]} kata): pertanyaan/pernyataan memikat yang JUJUR terhadap isi video; boleh memakai 1 fakta.
- Scene tengah = FAKTA ({sc['fact_words'][0]}-{sc['fact_words'][1]} kata tiap scene): satu ide per scene, urutan logis, hubungkan dengan kata sambung alami.
- Scene terakhir = PENUTUP ({sc['kicker_words'][0]}-{sc['kicker_words'][1]} kata): makna/dampak singkat atau pertanyaan untuk penonton. Tidak boleh ada angka baru.
- Total {sc['total_words'][0]}-{sc['total_words'][1]} kata.
Setiap scene pilih "prop" 3D yang paling cocok (jangan sama dengan scene sebelumnya):
{_prop_help()}
"emotion" maskot robot "Bit": happy, surprised, thinking, excited, proud (variasikan, hook biasanya surprised/excited).
"label" = judul pendek di layar (maks {sc['label_max']} karakter, tanpa titik).
"title" = judul video maks {sc['title_max']} karakter, menarik tapi tidak menyesatkan, tanpa hashtag.
"tags" = 6-10 kata kunci (Indonesia & Inggris), tanpa #.{fb}"""


def validate(out: ScriptOut, facts: list[Fact], cfg: dict) -> list[str]:
    sc = cfg["script"]
    errs: list[str] = []
    ids = {f.id for f in facts}
    allowed_nums: set[str] = set()
    for f in facts:
        allowed_nums |= number_tokens(f.claim)
    n = len(out.scenes)
    if not sc["min_scenes"] <= n <= sc["max_scenes"]:
        errs.append(f"jumlah scene {n}, harus {sc['min_scenes']}-{sc['max_scenes']}")
    total = 0
    prev_prop = None
    for i, s in enumerate(out.scenes):
        words = len(s.narration.split())
        total += words
        if i == 0:
            lo, hi = sc["hook_words"]
        elif i == n - 1:
            lo, hi = sc["kicker_words"]
        else:
            lo, hi = sc["fact_words"]
        if not lo <= words <= hi:
            errs.append(f"scene {i + 1}: {words} kata, harus {lo}-{hi}")
        bad = set(number_tokens(s.narration)) - allowed_nums
        if bad:
            errs.append(f"scene {i + 1}: angka {sorted(bad)} tidak ada di fakta")
        if re.search(r"[#*]|https?://|www\.", s.narration) or re.search(r"[\U00010000-\U0010ffff\u2600-\u27bf]", s.narration):
            errs.append(f"scene {i + 1}: narasi mengandung emoji/hashtag/tautan/bintang")
        if 0 < i < n - 1 and not s.fact_ids:
            errs.append(f"scene {i + 1}: scene fakta harus mengisi fact_ids")
        if any(x not in ids for x in s.fact_ids):
            errs.append(f"scene {i + 1}: fact_ids tidak valid {s.fact_ids}")
        if i == n - 1 and number_tokens(s.narration):
            errs.append("penutup tidak boleh memuat angka")
        if len(s.label) > sc["label_max"]:
            errs.append(f"scene {i + 1}: label {len(s.label)} karakter > {sc['label_max']}")
        if s.prop == prev_prop:
            errs.append(f"scene {i + 1}: prop sama dengan scene sebelumnya ({s.prop})")
        prev_prop = s.prop
    if not sc["total_words"][0] <= total <= sc["total_words"][1]:
        errs.append(f"total {total} kata, harus {sc['total_words'][0]}-{sc['total_words'][1]}")
    if len(out.title) > sc["title_max"] or "#" in out.title:
        errs.append(f"judul maks {sc['title_max']} karakter & tanpa #")
    if set(number_tokens(out.title)) - allowed_nums:
        errs.append("judul memuat angka yang tidak ada di fakta")
    if set(number_tokens(out.summary)) - allowed_nums:
        errs.append("ringkasan memuat angka yang tidak ada di fakta")
    used = {x for s in out.scenes for x in s.fact_ids}
    if len(used) < min(3, len(ids)):
        errs.append("pakai minimal 3 fakta berbeda")
    return errs


def write_script(llm: LLM, facts: list[Fact], art: Article, cfg: dict, shorter: bool = False) -> Script:
    feedback: list[str] | None = None
    for attempt in range(1, cfg["script"].get("max_attempts", 4) + 1):
        prompt = build_prompt(facts, art, cfg, feedback, shorter)
        out = llm.json(prompt, ScriptOut, system=SYSTEM, temperature=0.65 if attempt == 1 else 0.4)
        errs = validate(out, facts, cfg)
        if not errs:
            n = len(out.scenes)
            scenes = []
            for i, s in enumerate(out.scenes):
                kind = "hook" if i == 0 else ("kicker" if i == n - 1 else "fact")
                scenes.append(Scene(s.narration.strip(), s.label.strip().rstrip("."), s.prop, s.emotion,
                                    s.fact_ids, kind))
            tags = [t.strip().lstrip("#") for t in out.tags if t.strip()][:10]
            log.info("script OK on attempt %d (%d scenes)", attempt, n)
            return Script(out.title.strip(), out.summary.strip(), tags, scenes)
        log.warning("script attempt %d rejected: %s", attempt, "; ".join(errs)[:400])
        feedback = errs
    raise RuntimeError("could not produce a valid script: " + "; ".join(feedback or []))
