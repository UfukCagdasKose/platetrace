"""anomalies.py'yi synth_scenario.py'nin gomulu rota/zaman anomalisi
planted event'leri uzerinde dogrular: her planted anomali dogru turde
yakalaniyor mu, kac sahte pozitif uretiliyor.

Truth eslestirmesi eval_cloning.py'nin OCR-sansina dayanan yaklasimindan
farkli: gecis_kaydi.csv'nin (sadece degerlendirme icin var olan) event_tag/
clean_plaka/event_id kolonlarini kullanarak planted anomali okumasina denk
gelen SATIRI dogrudan bulur, sonra o satirin anomalies.py tarafindan (dogru
turde) isaretlenip isaretlenmedigine bakar -- OCR'in tesadufen temiz metne
donmesine bagli degildir.

Kullanim:
    python3 synth_scenario.py --out data/scenario
    python3 eval_anomalies.py --scenario data/scenario
"""

import argparse
import json

from anomalies import MIN_DISTINCT_DAYS, ODD_HOUR_THRESHOLD_HOURS, detect_anomalies
from convoy import load_gecis_csv


def find_truth_rows(rows, truth):
    """Her planted anomali icin, event_tag=="anomaly" olan ve clean_plaka/
    nokta_id/zaman'i truth kaydiyla birebir eslesen SATIRI bulur."""
    anomaly_rows = [r for r in rows if r["event_tag"] == "anomaly"]
    matches = []
    for t in truth:
        hit = next((r for r in anomaly_rows
                    if r["clean_plaka"] == t["plate"] and r["nokta_id"] == t["nokta_id"]
                    and r["zaman"].isoformat() == t["zaman"]), None)
        matches.append((t, hit))
    return matches


def analyze(rows, truth, min_distinct_days, odd_hour_threshold):
    flags = detect_anomalies(rows, min_distinct_days, odd_hour_threshold)
    flagged_keys = {(f["plaka"], f["nokta_id"], f["zaman"], t) for f in flags for t in f["types"]}

    matches = find_truth_rows(rows, truth)
    hits, misses = 0, []
    for t, hit in matches:
        found = hit is not None and (hit["plaka"], hit["nokta_id"], hit["zaman"], t["type"]) in flagged_keys
        if found:
            hits += 1
        else:
            misses.append(t)

    # sahte pozitif: event_tag "anomaly" OLMAYAN bir satirdan gelen isaret
    non_anomaly_flags = [f for f in flags if not any(
        r["plaka"] == f["plaka"] and r["nokta_id"] == f["nokta_id"] and r["zaman"] == f["zaman"]
        and r["event_tag"] == "anomaly" for r in rows)]

    return {
        "planted": len(truth),
        "recall_hits": hits,
        "missed": misses,
        "total_flags": len(flags),
        "false_positive_flags": len(non_anomaly_flags),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="data/scenario")
    parser.add_argument("--final-min-distinct-days", type=int, default=MIN_DISTINCT_DAYS)
    parser.add_argument("--final-odd-hour-threshold", type=float, default=ODD_HOUR_THRESHOLD_HOURS)
    args = parser.parse_args()

    rows = load_gecis_csv(f"{args.scenario}/gecis_kaydi.csv")
    with open(f"{args.scenario}/ground_truth.json", encoding="utf-8") as f:
        truth = json.load(f)["anomalies"]

    print(f"planted anomali sayisi: {len(truth)}\n")

    r = analyze(rows, truth, args.final_min_distinct_days, args.final_odd_hour_threshold)
    print(f"son surum (min_distinct_days={args.final_min_distinct_days}, "
          f"odd_hour_threshold={args.final_odd_hour_threshold}sa):")
    print(f"  yakalanan/planted: {r['recall_hits']}/{r['planted']}")
    if r["missed"]:
        print(f"  kacirilan: {r['missed']}")
    print(f"  toplam isaret: {r['total_flags']}  sahte pozitif isaret: {r['false_positive_flags']}")

    print("\nodd_hour_threshold taramasi (min_distinct_days sabit):")
    for oh in [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]:
        r = analyze(rows, truth, args.final_min_distinct_days, oh)
        print(f"  odd_hour_threshold={oh:<4}  yakalanan={r['recall_hits']}/{r['planted']}  "
              f"toplam_isaret={r['total_flags']}  sahte_pozitif={r['false_positive_flags']}")

    print("\nmin_distinct_days taramasi (odd_hour_threshold sabit):")
    for md in [2, 3, 4, 5, 6, 8]:
        r = analyze(rows, truth, md, args.final_odd_hour_threshold)
        print(f"  min_distinct_days={md:<3}  yakalanan={r['recall_hits']}/{r['planted']}  "
              f"toplam_isaret={r['total_flags']}  sahte_pozitif={r['false_positive_flags']}")


if __name__ == "__main__":
    main()
