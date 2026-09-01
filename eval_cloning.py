"""cloning.py'yi synth_scenario.py'nin gomulu klonlanmis plaka planted
event'i uzerinde dogrular: gercek klon plaka yakalaniyor mu, baska
(sahte) hicbir plaka yanlislikla isaretleniyor mu.

Kullanim:
    python3 synth_scenario.py --out data/scenario
    python3 eval_cloning.py --scenario data/scenario
"""

import argparse
import json

from cloning import MAX_PLAUSIBLE_SPEED_KMH, detect_clones, load_points
from convoy import load_gecis_csv


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="data/scenario")
    parser.add_argument("--max-speed", type=float, default=MAX_PLAUSIBLE_SPEED_KMH)
    args = parser.parse_args()

    rows = load_gecis_csv(f"{args.scenario}/gecis_kaydi.csv")
    points = load_points(f"{args.scenario}/nokta.csv")
    with open(f"{args.scenario}/ground_truth.json", encoding="utf-8") as f:
        truth = json.load(f)

    flags = detect_clones(rows, points, args.max_speed)
    # f["plaka"] tek bir metin ("21EU666") ya da fuzzy-kumelenmis iki farkli
    # OCR okumasi ("21EU666~21EU665") olabilir; ikisini de acip topluyoruz.
    flagged_variants = {v for f in flags for v in f["plaka"].split("~")}

    planted_plate = truth["cloned_plate"]["plate"]
    detected = planted_plate in flagged_variants
    false_positives = flagged_variants - {planted_plate}

    print(f"esik: {args.max_speed:.0f} km/h")
    print(f"planted klon plakasi ({planted_plate}) yakalandi mi: {detected}")
    print(f"toplam isaretlenen plaka (varyant) sayisi: {len(flagged_variants)}")
    print(f"sahte pozitif plakalar: {sorted(false_positives) if false_positives else 'yok'}")

    matching = [f for f in flags if planted_plate in f["plaka"].split("~")]
    if matching:
        best = max(matching, key=lambda f: f["required_speed_kmh"])
        print(f"  gereken hiz: {best['required_speed_kmh']} km/h "
              f"({best['distance_km']} km / {best['seconds']:.0f} sn, "
              f"okuma ciftinin plakalari: {best['plaka']})")


if __name__ == "__main__":
    main()
