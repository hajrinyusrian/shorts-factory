# Shorts Factory – YouTube Shorts faceless otomatis (fakta teknologi, animasi 3D ala Pixar)

Satu kali jalan = satu video:

```
RSS sumber tepercaya ──► artikel asli (teks penuh) ──► Gemini mengekstrak fakta + kutipan bukti
        │                                                        │
        │                              verifikasi PROGRAM (kutipan harus ada di artikel,
        │                              angka harus identik) + audit LLM kedua
        ▼                                                        ▼
  riwayat (tanpa topik ganda)                    naskah Indonesia (divalidasi kode: angka, panjang, prop)
                                                                 │
              edge-tts (suara + timing per kata) ◄───────────────┘
                         │
   Blender (Cycles) render maskot "Bit" + prop 3D  ──► ffmpeg: transisi, caption karaoke, kartu sumber, audio
                         │
                 YouTube Data API v3 ──► Shorts (deskripsi memuat tautan sumber)
```

## Kenapa faktanya bisa dipercaya
1. Ide **tidak** dikarang AI: berasal dari artikel nyata (MIT News, NASA, IEEE Spectrum, ScienceDaily, dll. – lihat `config.yaml`).
2. Gemini hanya boleh menulis ulang fakta **dengan kutipan bukti verbatim**. Kode memeriksa kutipan itu benar‑benar ada di teks artikel (cocok persis / fuzzy ≥ 94%) dan semua angka di klaim ada di kutipan.
3. Audit kedua oleh LLM ("didukung / tidak didukung"). Fakta yang gagal dibuang; kurang dari 3 fakta lolos → artikel dilewati.
4. Naskah divalidasi kode: angka apa pun di narasi/judul harus ada di fakta terverifikasi; jumlah kata, label, prop, dan `fact_ids` dicek; gagal → diminta ulang dengan umpan balik.
5. Sumber tampil **di video** (badge "Sumber: …" di tiap scene + kartu sumber di akhir) dan **di deskripsi** (penerbit, judul, URL, tanggal).

> Batas yang jujur: verifikasi memastikan klaim sesuai *artikelnya*, bukan bahwa artikelnya pasti benar. Karena itu feed dipilih dari institusi/pers tepercaya (tier 1–3). Tinjau `out/*/facts.json` dan `description.txt` (artifact di GitHub Actions) secara berkala.

## Struktur
```
config.yaml                 semua pengaturan (feed, suara, profil render, gaya caption, upload)
pipeline/                   sources → facts → script_writer → tts → timeline → render3d → subtitles/compose → upload
blender/                    render_scene.py (adegan), mascot.py (robot Bit), props.py (10 prop 3D), common.py
assets/fonts                Poppins (OFL). assets/music: taruh musik BEBAS HAK CIPTA (opsional)
.github/workflows/daily.yml jadwal harian + render + upload + simpan riwayat
tests/                      unit test (verifikasi fakta, validasi naskah, caption) + e2e_fake.py (tanpa jaringan)
```
Prop 3D: `chip planet rocket battery neural globe bulb shield atom gear` (+ maskot robot dengan emosi happy/surprised/thinking/excited/proud).

## Setup (sekali)
1. Buat repo GitHub dari folder ini. **Gunakan repo publik** bila ingin gratis penuh: menit Actions untuk repo publik tidak dibatasi; repo privat hanya 2.000 menit/bulan (1 video ≈ 45–60 menit).
2. *Settings → Secrets and variables → Actions*: `GEMINI_API_KEY`, `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`.
3. **Penting – OAuth:** di Google Cloud → OAuth consent screen, ubah status dari *Testing* ke **In production**. Pada mode Testing, refresh token umumnya kedaluwarsa ±7 hari sehingga upload otomatis berhenti. (Untuk pemakaian pribadi tidak perlu verifikasi penuh; akan muncul layar peringatan saat login.) Buat ulang `YT_REFRESH_TOKEN` setelah mengubahnya.
4. **Penting – status video:** project API yang belum lolos *YouTube API Services audit* dapat membuat video hasil upload API dikunci **private**. Uji dengan 1–2 video; bila terkunci, ajukan audit resmi atau publikasikan manual dari Studio. Cek kebijakan terbaru di dokumentasi YouTube.
5. Jalankan manual dulu: *Actions → daily-short → Run workflow*, pilih `dry_run = true`, unduh artifact `short-output`, tonton hasilnya. Baru aktifkan jadwal (cron 08:30 UTC ≈ 15:30 WIB → terunggah sekitar 17:00 WIB; atur di `daily.yml`).

## Jalankan lokal
```bash
pip install -r requirements.txt            # + ffmpeg, + Blender 4.2 (build resmi; paket apt TIDAK punya denoiser)
export GEMINI_API_KEY=...  BLENDER_BIN=/path/to/blender
python -m pipeline.main --dry-run --profile fast
python -m unittest discover -s tests -v
```

## Profil render (kualitas ↔ waktu)
| profil | resolusi render | fps render | sampel | perkiraan di runner 4‑core |
|---|---|---|---|---|
| fast | 432×768 | 12 | 12 | ~25 menit |
| balanced (default) | 540×960 | 12 | 14 | ~45 menit |
| high | 720×1280 | 15 | 24 | ~2 jam |

Frame di‑upscale ke 1080×1920 dan di‑interpolasi ke 30 fps (`interpolation: mci`). Jika ingin gerakan lebih halus: nyalakan `motion_blur` (+~70% waktu) atau pakai profil `high`.

## Mode visual (`render3d.mode` di config.yaml)
- **`still` (default):** satu ilustrasi 3D (Blender, 1 gambar per scene) + animasi Ken-Burns + **teks besar / angka berhitung naik / bar persen** (Pillow). Angka diambil hanya dari narasi scene yang sudah divalidasi terhadap fakta. Scene dibuat pendek (6-8 scene, ~5-8 detik) agar visual sering berganti. Ukuran/sampel still per profil ada di `render3d.stills`.
- **`video`:** animasi 3D penuh per frame (lambat, sekitar 1 jam di runner; lihat tabel profil di bawah).
- Terukur di sandbox 1 core, Blender 4.0 tanpa denoiser: 360x640 @ 32 sampel = ~35 detik per still. Waktu di runner 4-core dengan build resmi 4.2 **belum terukur**; cek baris `render N/M` di log dry run.

## Mode Indonesia + analis (`selection.prefer_indonesia`, `script.analysis`)
- **Seleksi:** kandidat artikel diberi skor relevansi Indonesia (feed `region: id`, sebutan eksplisit Indonesia/ASEAN, atau topik berdampak lokal seperti nikel, pusat data, kabel laut, fintech). Yang skornya tinggi dicoba lebih dulu; editor LLM memilih yang paling konkret.
- **Scene ANALISIS:** scene tepat sebelum penutup adalah *pendapat*, bukan fakta. Kode memaksa: diawali kata "Analisis", menyebut "Indonesia", memakai bahasa hati-hati (mungkin/berpotensi/kemungkinan), tanpa angka, tanpa nama baru di luar fakta terverifikasi, tanpa kata pasti/dijamin. Di layar ditandai pil "ANALISIS KAMI"; deskripsi memuat catatan bahwa bagian itu perspektif kami (dibantu AI).
- Kata "terbukti / pertama di dunia / terbaik / revolusioner" kini diblokir di seluruh naskah kecuali tertulis di fakta.
- **Batas jujur:** validator tidak bisa menilai apakah penalaran analisisnya *bagus*, hanya bahwa ia tidak memuat angka/nama baru dan berbahasa hati-hati. Baca `script.json` secara berkala. URL feed Indonesia di `config.yaml` belum terverifikasi (feed yang gagal dilewati dengan peringatan di log).

## Status pengujian (jujur)
Sudah diuji di sandbox: render Blender semua 10 prop + maskot (Blender 4.0), mode still end-to-end (Blender 4.0 + Pillow + ffmpeg, video 1080x1920 H.264+AAC), pembuatan caption ASS, perakitan ffmpeg (xfade, audio, whoosh, caption karaoke), validator fakta/naskah, penyelarasan kata TTS (unit test). **Belum bisa diuji di sana** (tanpa internet bebas): panggilan Gemini, ambil RSS/artikel, edge‑tts, upload YouTube, Blender 4.2 + denoiser OIDN (build resmi), dan waktu render di runner GitHub. Jalankan `dry_run` dulu; bila sebuah feed gagal, ia dilewati dengan peringatan di log (ganti URL di `config.yaml`).

## Hal yang perlu kamu putuskan/awasi
- **Kebijakan YouTube "inauthentic/mass‑produced content":** variasikan topik, jangan menaikkan frekuensi terlalu agresif, dan beri nilai tambah (sudut pandang, konteks). Narasi AI + suara sintetis diungkap di deskripsi; atur `contains_synthetic_media` di `config.yaml` bila perlu.
- **Hak cipta:** hanya meringkas dengan kata sendiri + mencantumkan sumber; jangan menaruh musik berhak cipta di `assets/music`.
- **Kuota API YouTube:** default 10.000 unit/hari, 1 upload ≈ 1.600 unit.
- Gemini free tier punya batas permintaan/hari; satu video memakai ±4–8 panggilan.
