"""Track seviyesinde karakter oylamasi.

Bir arac takibi (track) boyunca her karede ayri ayri OCR okunur; bu modul
o okumalari tek bir plakaya indirger. Tek kare okumasi kirilgandir (bkz.
eval_ocr.py'daki bozulma egrisi); ayni plakayi 15-30 karede okuyup
karakter bazinda mod almak vizyon katmanindaki en buyuk dogruluk kazanci
(CLAUDE.md, "Design decisions already made").

Hizalama karmasikligindan kacinmak icin: once okumalar arasinda en sik
gorulen uzunluk secilir (plaka uzunlugu zaten Turk plaka formatina gore
degisir, bu adim hem format farkliligini hem de OCR'in karakter
ekleyip/silme hatalarini ayni mekanizmayla eler), sonra sadece o uzunluktaki
okumalar arasinda pozisyon bazinda en sik karakter alinir.
"""

from collections import Counter


def _mode(values):
    """En sik gorulen degeri dondurur; esitlikte ilk gorulen kazanir."""
    values = list(values)
    counts = Counter(values)
    best_count = max(counts.values())
    for v in values:
        if counts[v] == best_count:
            return v


def vote_plate(reads):
    """OCR okumalarindan tek bir plaka metni cikarir.

    reads: bir track'teki karelerin OCR ciktilari (list[str]).
    Bos okumalar yok sayilir. Hicbir gecerli okuma yoksa "" doner.
    """
    reads = [r for r in reads if r]
    if not reads:
        return ""

    mode_length = _mode(len(r) for r in reads)
    candidates = [r for r in reads if len(r) == mode_length]

    return "".join(
        _mode(r[i] for r in candidates) for i in range(mode_length)
    )


if __name__ == "__main__":
    # Hizli akil kontrolu: cogunluk dogruysa oylama tek hatali okumayi eler.
    assert vote_plate(["34ABC123", "34ABC123", "34ABX123"]) == "34ABC123"
    # Yanlis uzunluktaki okumalar (silinen/eklenen karakter) elenir.
    assert vote_plate(["34ABC123", "34ABC12", "34ABC123"]) == "34ABC123"
    assert vote_plate([]) == ""
    assert vote_plate(["06CEG741"]) == "06CEG741"
    print("voting.py: tum kontroller gecti")
