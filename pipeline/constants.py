"""Values shared between the pipeline and the Blender scripts (kept in sync by tests/test_basic.py)."""

# prop key -> when to use it (this text goes straight into the script-writing prompt)
PROPS = {
    "chip":    "semikonduktor, prosesor, komputasi, perangkat keras",
    "planet":  "luar angkasa, astronomi, planet, eksplorasi antariksa",
    "rocket":  "peluncuran roket, penerbangan, kecepatan, startup/peluncuran",
    "battery": "baterai, energi, kendaraan listrik, pengisian daya",
    "neural":  "AI, jaringan saraf tiruan, machine learning, data",
    "globe":   "internet, jaringan global, iklim, dampak dunia",
    "bulb":    "ide, inovasi, penemuan, efisiensi energi",
    "shield":  "keamanan siber, privasi, perlindungan",
    "atom":    "fisika, kuantum, material, nanoteknologi, sains dasar",
    "gear":    "robotika, rekayasa, manufaktur, mesin",
}
PROP_KEYS = list(PROPS)
EMOTIONS = ["happy", "surprised", "thinking", "excited", "proud"]
PALETTES = ["ocean", "sunset", "mint", "candy", "sky", "dusk", "blueprint"]
CAMERA_MOVES = ["push", "orbit", "pull"]
