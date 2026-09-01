"""convoy.py'nin naive (normalize etmeyen) ile trafik-hacmi normalizeli
son surumunu, synth_scenario.py'nin gomulu konvoy / rutin-birlikte-seyahat
planted event'leri uzerinde karsilastirir.

CLAUDE.md'nin "her dogruluk iddiasi bir rakam ve onu ureten script
gerektirir" kuralinin bu katman icin karsiligi: "min_distinct_points=2
yeterli mi" ve "esik degeri ne olmali" sorularina tahminle degil, gercek
senaryo verisi uzerinde olcerek cevap verir.

Kullanim:
    python3 synth_scenario.py --out data/scenario
    python3 eval_convoy.py --scenario data/scenario
"""

import argparse
import itertools
import json

import networkx as nx

from convoy import build_graph, load_gecis_csv


def analyze(g, convoy_plates, routine_plates):
    convoy_component = next(
        (c for c in nx.connected_components(g) if set(convoy_plates) & c), set())
    convoy_isolated = convoy_component == set(convoy_plates)

    routine_flagged = g.has_edge(*routine_plates)

    convoy_edges = {tuple(sorted(e)) for e in itertools.combinations(sorted(convoy_plates), 2)}
    fp_edges = [e for e in g.edges() if tuple(sorted(e)) not in convoy_edges]

    return {
        "convoy_isolated": convoy_isolated,
        "routine_flagged": routine_flagged,
        "total_edges": g.number_of_edges(),
        "false_positive_edges": len(fp_edges),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="data/scenario")
    parser.add_argument("--window-seconds", type=int, default=600)
    parser.add_argument("--final-min-weight", type=float, default=0.025)
    args = parser.parse_args()

    rows = load_gecis_csv(f"{args.scenario}/gecis_kaydi.csv")
    with open(f"{args.scenario}/ground_truth.json", encoding="utf-8") as f:
        truth = json.load(f)
    convoy_plates = truth["convoy"]["plates"]
    routine_plates = truth["routine_co_travel"]["plates"]

    configs = [
        ("naive (min_nokta=1, agirliksiz)", dict(min_distinct_points=1, min_weight=0.0)),
        ("coklu-nokta (min_nokta=2, agirliksiz)", dict(min_distinct_points=2, min_weight=0.0)),
        (f"son surum (min_nokta=2, agirlik>={args.final_min_weight})",
         dict(min_distinct_points=2, min_weight=args.final_min_weight)),
    ]

    print(f"{'yapilandirma':<42} {'konvoy izole?':>13} {'rutin FP?':>10} "
          f"{'toplam kenar':>13} {'sahte kenar':>12}")
    for label, kwargs in configs:
        g = build_graph(rows, args.window_seconds, **kwargs)
        r = analyze(g, convoy_plates, routine_plates)
        print(f"{label:<42} {str(r['convoy_isolated']):>13} {str(r['routine_flagged']):>10} "
              f"{r['total_edges']:>13} {r['false_positive_edges']:>12}")

    print("\nesik taramasi (min_nokta=2, farkli min_weight degerleri):")
    for mw in [0.0, 0.01, 0.015, 0.02, 0.025, 0.03, 0.035]:
        g = build_graph(rows, args.window_seconds, min_distinct_points=2, min_weight=mw)
        r = analyze(g, convoy_plates, routine_plates)
        print(f"  min_weight={mw:<6}  konvoy_izole={str(r['convoy_isolated']):<5}  "
              f"rutin_FP={str(r['routine_flagged']):<5}  sahte_kenar={r['false_positive_edges']}")


if __name__ == "__main__":
    main()
