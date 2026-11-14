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
    kind: str = "fact"   # hook | fact | analysis | kicker | outro


@dataclass
class Script:
    title: str
    summary: str
    tags: list[str]
    scenes: list[Scene] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


SYSTEM = """Kamu analis teknologi senior sekaligus penulis naskah YouTube Shorts "Fakta Teknologi" untuk penonton Indonesia.
Gaya: tajam tapi hangat. Kalimat pendek, bahasa Indonesia santai tapi baku-secukupnya. Kamu selalu menjawab "lalu kenapa ini penting buat kita di Indonesia?" tanpa lebay dan tanpa mengarang.
ATURAN KERAS (akurasi lebih penting daripada gaya):
1. Gunakan HANYA informasi dari daftar FAKTA TERVERIFIKASI. Dilarang menambah fakta, angka, nama, tanggal, atau perbandingan dari luar daftar.
2. Setiap angka yang kamu sebut harus identik dengan angka di fakta. Jangan membuat penomoran (mis. "fakta 1").
3. Jaga atribusi: sebut "menurut <pihak>" bila fakta berupa klaim/hasil pihak tertentu. Jangan menyebut sesuatu "terbukti", "pertama di dunia", "terbaik", atau "revolusioner" kecuali tertulis di fakta.
4. Tulis singkatan dengan huruf biasa tanpa spasi (mis. AI, GPU, CPU). Jangan memisahkan hurufnya: pelafalan untuk suara diatur oleh kode, dan teks di layar harus rapi.
5. Tanpa emoji, hashtag, tautan, atau tanda bintang di narasi.
6. Scene ANALISIS (bila diminta) adalah PENDAPAT, bukan fakta: awali dengan kata "Analisis", pakai bahasa hati-hati (mungkin, bisa jadi, berpotensi, kemungkinan), kaitkan dengan Indonesia, dan jangan menyebut angka, nama perusahaan/lembaga/tempat, atau fakta baru di luar daftar."""


_SPACED_ACRONYM = re.compile(r"\b(?:[A-Z] )+[A-Z]\b")


def unspace_acronyms(text: str) -> str:
    """'A I' -> 'AI', 'G P U' -> 'GPU'. Models sometimes spell acronyms out; the screen text must stay normal
    (the TTS layer, not the script, decides how an acronym is pronounced)."""
    return _SPACED_ACRONYM.sub(lambda m: m.group(0).replace(" ", ""), text)


def normalize_out(out: "ScriptOut") -> None:
    out.title = unspace_acronyms(out.title)
    out.summary = unspace_acronyms(out.summary)
    for sc in out.scenes:
        sc.narration = unspace_acronyms(sc.narration)
        sc.label = unspace_acronyms(sc.label)


HEDGES = ("mungkin", "bisa jadi", "berpotensi", "kemungkinan", "tampaknya", "sepertinya", "diperkirakan",
          "seandainya", "andai", "jika ")
GENERIC_ACRONYMS = {"AI", "GPU", "CPU", "NPU", "LLM", "USB", "IT", "IoT", "EV", "RI"}
FORBIDDEN_ALWAYS = ("terbukti", "pertama di dunia", "terbaik", "revolusioner")
FORBIDDEN_ANALYSIS = ("pasti", "dijamin", "tidak diragukan")


def analysis_index(sc: dict, n: int) -> int | None:
    """Position of the ANALYSIS scene (the one right before the closing line), or None when disabled."""
    return n - 2 if sc.get("analysis") and n >= 4 else None


def new_names(text: str, facts_text: str, allowed: set[str]) -> set[str]:
    """Capitalised words (not sentence-initial) that appear neither in the verified facts nor in the allow-list."""
    known = set(re.findall(r"[a-z0-9\-]+", facts_text.lower()))
    out: set[str] = set()
    for sent in re.split(r"(?<=[.!?:])\s+", text.strip()):
        for tok in re.findall(r"[A-Za-z][A-Za-z0-9\-]*", sent)[1:]:
            if tok[0].isupper() and tok not in GENERIC_ACRONYMS and tok not in allowed and tok.lower() not in known:
                out.add(tok)
    return out


def analysis_errors(narration: str, label: str, facts_text: str, sc: dict, pos: int) -> list[str]:
    errs: list[str] = []
    low = narration.lower()
    if not narration.strip().lower().startswith("analisis"):
        errs.append(f"scene {pos}: scene analisis harus diawali kata 'Analisis' (mis. 'Analisis kami: ...')")
    if "indonesia" not in low:
        errs.append(f"scene {pos}: scene analisis harus mengaitkan dengan Indonesia (sebut kata 'Indonesia')")
    if not any(h in low + " " for h in HEDGES):
        errs.append(f"scene {pos}: scene analisis harus memakai bahasa hati-hati (mungkin / bisa jadi / berpotensi / kemungkinan)")
    if number_tokens(narration):
        errs.append(f"scene {pos}: scene analisis tidak boleh memuat angka")
    for w in FORBIDDEN_ANALYSIS:
        if w in low:
            errs.append(f"scene {pos}: scene analisis tidak boleh memakai '{w}' (itu pendapat, bukan kepastian)")
    allowed = set(sc.get("analysis_allowed_names", ["Indonesia", "Asia", "Tenggara", "ASEAN", "Analisis"]))
    bad = new_names(narration, facts_text, allowed)
    if bad:
        errs.append(f"scene {pos}: scene analisis menyebut nama yang tidak ada di fakta: {sorted(bad)}")
    return errs


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
    aw = sc.get("analysis_words", [12, 24])
    analysis_block = (
        f"- Scene tepat SEBELUM penutup = ANALISIS ({aw[0]}-{aw[1]} kata): sudut pandang analis tentang apa artinya bagi Indonesia "
        "(industri, pekerja, pengguna, regulasi, infrastruktur). WAJIB: diawali kata \"Analisis\" (mis. \"Analisis kami: ...\"), "
        "menyebut kata \"Indonesia\", memakai bahasa hati-hati (mungkin/bisa jadi/berpotensi/kemungkinan), TANPA angka, "
        "TANPA nama perusahaan/lembaga/tempat baru, dan isi fact_ids dengan fakta yang menjadi dasar penalaranmu.\n"
    ) if sc.get("analysis") else ""
    return f"""Buat naskah Shorts dari fakta terverifikasi berikut.
Sumber: {art.publisher} - "{art.title}" ({art.date})

FAKTA TERVERIFIKASI:
{fl}

STRUKTUR ({sc['min_scenes']}-{sc['max_scenes']} scene):
- Scene 1 = HOOK ({sc['hook_words'][0]}-{sc['hook_words'][1]} kata): pertanyaan/pernyataan memikat yang JUJUR terhadap isi video; boleh memakai 1 fakta.
- Scene tengah = FAKTA ({sc['fact_words'][0]}-{sc['fact_words'][1]} kata tiap scene): satu ide per scene, urutan logis, hubungkan dengan kata sambung alami.
{analysis_block}- Scene terakhir = PENUTUP ({sc['kicker_words'][0]}-{sc['kicker_words'][1]} kata): makna/dampak singkat atau pertanyaan untuk penonton. Tidak boleh ada angka baru.
- Total {sc['total_words'][0]}-{sc['total_words'][1]} kata.
- Satu fakta boleh dipakai di lebih dari satu scene dengan sudut berbeda (apa isinya, lalu kenapa penting), tanpa menambah fakta baru.
- Setiap scene tampil sebagai ilustrasi + TEKS BESAR + infografis angka. Kalimat yang memuat angka dari fakta akan ditampilkan sebagai angka besar, jadi taruh angka itu di scene yang tepat.
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
    ai = analysis_index(sc, n)
    facts_text = " ".join(f.claim for f in facts)
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
        elif i == ai:
            lo, hi = sc.get("analysis_words", [12, 24])
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
        if i == ai:
            errs.extend(analysis_errors(s.narration, s.label, facts_text, sc, i + 1))
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
    everything = " ".join([out.title, out.summary] + [x.narration + " " + x.label for x in out.scenes]).lower()
    for w in FORBIDDEN_ALWAYS:
        if w in everything and w not in facts_text.lower():
            errs.append(f"kata '{w}' tidak boleh dipakai kecuali tertulis di fakta")
    used = {x for s in out.scenes for x in s.fact_ids}
    if len(used) < min(3, len(ids)):
        errs.append("pakai minimal 3 fakta berbeda")
    return errs


def write_script(llm: LLM, facts: list[Fact], art: Article, cfg: dict, shorter: bool = False) -> Script:
    feedback: list[str] | None = None
    for attempt in range(1, cfg["script"].get("max_attempts", 4) + 1):
        prompt = build_prompt(facts, art, cfg, feedback, shorter)
        out = llm.json(prompt, ScriptOut, system=SYSTEM, temperature=0.65 if attempt == 1 else 0.4)
        normalize_out(out)
        errs = validate(out, facts, cfg)
        if not errs:
            n = len(out.scenes)
            scenes = []
            for i, s in enumerate(out.scenes):
                kind = ("hook" if i == 0 else "kicker" if i == n - 1 else
                        "analysis" if i == analysis_index(cfg["script"], n) else "fact")
                scenes.append(Scene(s.narration.strip(), s.label.strip().rstrip("."), s.prop, s.emotion,
                                    s.fact_ids, kind))
            tags = [t.strip().lstrip("#") for t in out.tags if t.strip()][:10]
            log.info("script OK on attempt %d (%d scenes)", attempt, n)
            return Script(out.title.strip(), out.summary.strip(), tags, scenes)
        log.warning("script attempt %d rejected: %s", attempt, "; ".join(errs)[:400])
        feedback = errs
    raise RuntimeError("could not produce a valid script: " + "; ".join(feedback or []))
