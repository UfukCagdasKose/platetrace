"""watchlist.py'nin fuzzy eslestirmesini, gercek OCR hatasi enjekte
edilmis senaryo verisi (synth_scenario.py) uzerinde exact-match'e karsi
olcer.

gecis_kaydi.csv'deki clean_plaka sutunu (senaryonun gercek plakasi)
zemin dogruluk olarak kullanilir: bir eslesme, ancak eslesen satirin
clean_plaka'si watchlist girdisinin plakasiyla ayniysa "dogru" sayilir.
Boylece hem kacan gercek hitler (recall) hem de rastlantisal fuzzy
carpismalar (precision) olculebilir -- CLAUDE.md'nin "her dogruluk
iddiasi bir rakam ve onu ureten script gerektirir" kuralinin bu katman
icin karsiligi.

Kullanim:
    python3 synth_scenario.py --out data/scenario   # once senaryo uret
    python3 eval_watchlist.py --scenario data/scenario
"""

import argparse
import csv

from watchlist import find_matches


def load_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def evaluate(gecis_rows, watchlist, max_distance):
    tp, fp = [], []
    detected_plates = set()
    for row in gecis_rows:
        for entry, dist in find_matches(row["plaka"], watchlist, max_distance=max_distance):
            if row["clean_plaka"] == entry["plaka"]:
                tp.append((row, entry, dist))
                detected_plates.add(entry["plaka"])
            else:
                fp.append((row, entry, dist))
    return tp, fp, detected_plates


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="data/scenario")
    parser.add_argument("--max-distance", type=int, default=1)
    args = parser.parse_args()

    gecis_rows = load_csv(f"{args.scenario}/gecis_kaydi.csv")
    watchlist = load_csv(f"{args.scenario}/aranan_arac.csv")
    should_appear = {w["plaka"] for w in watchlist if w["appears"] == "True"}
    # Watchlist plakasi cok kere gorulurse tek bir dogru eslesme "plaka-duzeyi"
    # recall'i doyurur; asil OCR hatasina duyarli olan "okuma-duzeyi" recall'dir.
    total_sightings = sum(1 for row in gecis_rows if row["clean_plaka"] in should_appear)

    print(f"watchlist: {len(watchlist)} girdi ({len(should_appear)} trafikte gorunuyor, "
          f"{total_sightings} kez okundu)  gecis_kaydi: {len(gecis_rows)} satir\n")

    print(f"{'yontem':>22}  {'plaka-recall':>16}  {'okuma-recall':>16}  {'precision':>16}")
    for label, max_dist in [("exact", 0), (f"fuzzy (mesafe<={args.max_distance})", args.max_distance)]:
        tp, fp, detected = evaluate(gecis_rows, watchlist, max_dist)
        found = detected & should_appear
        plate_recall = len(found) / len(should_appear) if should_appear else 0.0
        read_recall = len(tp) / total_sightings if total_sightings else 0.0
        precision = len(tp) / (len(tp) + len(fp)) if (tp or fp) else 1.0
        print(f"{label:>22}  {plate_recall:>7.3f} ({len(found)}/{len(should_appear)})  "
              f"{read_recall:>7.3f} ({len(tp)}/{total_sightings})  "
              f"{precision:>7.3f} ({len(tp)}/{len(tp) + len(fp)})")

        missed = sorted(should_appear - detected)
        if missed:
            print(f"    kacan (hicbir okuma yakalayamadi): {missed}")
        if fp:
            examples = ", ".join(f"{r['plaka']}~{e['plaka']}(d={d})" for r, e, d in fp[:5])
            print(f"    yanlis pozitif ornekleri: {examples}")
        print()


if __name__ == "__main__":
    main()
