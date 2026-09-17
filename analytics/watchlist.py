"""Bulanik (fuzzy) watchlist (ArananArac) eslestirme.

CLAUDE.md, "Design decisions already made":
    "Fuzzy watchlist matching, not exact string equality. OCR makes
    errors; exact matching would miss most real hits. Levenshtein
    distance <= 1, with position-aware confusion handling
    (0<->O, 1<->I, 8<->B, 5<->S)."

Duz Levenshtein mesafesi butun ikame hatalarina esit agirlik verir. Ama
OCR hatalari rastgele degil: 0/O, 1/I, 8/B, 5/S gorsel olarak birbirine
benzer ve CRNN'in en sik karistirdigi karakterlerdir (bkz. eval_ocr.py'nin
bozulma egrisi). Bu yuzden mesafe hesabinda bu ciftler arasindaki ikame
"bedava" (agirlik 0) sayilir; geri kalan her ekleme/silme/ikame agirlik
1'dir. Esik 1: tek "gercek" hataya + istenildigi kadar confusion-pair
hatasina izin verir. Confusion, DP'nin ikame adiminda (ayni pozisyondaki
karakter ciftinde) uygulanir, yani "position-aware".

Not: CLAUDE.md'deki orijinal listede "1<->İ" (noktali Turkce I) yaziyor;
burada duz ASCII "I" kullanildi, cunku plaka karakter seti (synth_plates.
PLATE_LETTERS, train_ocr.CHARS) zaten Q/W/X disinda ascii harfler --
İ modelin uretebilecegi bir karakter degil. Gercekten İ de kapsanmali
istenirse (ör. disaridan gelen watchlist girdileri icin) CONFUSION_GROUPS'a
eklemek yeterli.
"""

CONFUSION_GROUPS = [
    frozenset("0O"),
    frozenset("1I"),
    frozenset("8B"),
    frozenset("5S"),
]

_CONFUSION_OF = {ch: group for group in CONFUSION_GROUPS for ch in group}


def _sub_cost(a, b):
    if a == b:
        return 0
    if b in _CONFUSION_OF.get(a, ()):
        return 0
    return 1


def weighted_edit_distance(a, b):
    """Levenshtein mesafesi; confusion-pair ikameleri (0/O, 1/I, 8/B, 5/S) bedava."""
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(
                prev[j] + 1,                      # silme
                cur[j - 1] + 1,                    # ekleme
                prev[j - 1] + _sub_cost(ca, cb),   # ikame (confusion bedava)
            )
        prev = cur
    return prev[-1]


def _plate_of(entry):
    return entry["plaka"] if isinstance(entry, dict) else entry.plaka


def find_matches(plaka, watchlist, max_distance=1):
    """plaka'yi watchlist'teki her girdiyle karsilastirir.

    watchlist: 'plaka' anahtarli dict'ler veya .plaka alanli nesneler
    (ör. ArananArac ORM kaydi) uzerinde yinelenebilir herhangi bir seyk.
    Donen deger: (entry, mesafe) ciftlerinden olusan, mesafeye gore
    artan sirali bir liste (max_distance'i asanlar elenir).
    """
    plaka = plaka.strip().upper()
    matches = []
    for entry in watchlist:
        target = _plate_of(entry).strip().upper()
        dist = weighted_edit_distance(plaka, target)
        if dist <= max_distance:
            matches.append((entry, dist))
    matches.sort(key=lambda m: m[1])
    return matches


if __name__ == "__main__":
    # Hizli akil kontrolu.
    assert weighted_edit_distance("34ABC128", "34ABC128") == 0
    assert weighted_edit_distance("34ABC128", "34ABC12B") == 0  # 8<->B confusion, bedava
    assert weighted_edit_distance("34ABC120", "34ABC12O") == 0  # 0<->O confusion, bedava
    assert weighted_edit_distance("34ABC123", "34ABC124") == 1  # confusion degil, gercek hata
    assert weighted_edit_distance("34ABC123", "34ABC1234") == 1  # tek ekleme
    assert weighted_edit_distance("34ABC123", "99ZZZ000") > 1

    watchlist = [{"plaka": "34ABC128", "sebep": "test"}]
    assert find_matches("34ABC12B", watchlist) != []   # confusion -> eslesir (mesafe 0)
    assert find_matches("34ABC124", watchlist) != []   # tek gercek hata -> eslesir (mesafe 1)
    assert find_matches("34ABC199", watchlist) == []   # iki gercek hata -> esik disi (mesafe 2)
    print("watchlist.py: tum kontroller gecti")
