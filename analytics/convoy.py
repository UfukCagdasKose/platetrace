"""Konvoy tespiti: birlikte gecen araclari graf uzerinde iliskilendirir.

CLAUDE.md, "Design decisions already made":
    "Convoy detection normalised by traffic volume. Two neighbours
    commuting the same route every morning look exactly like a convoy.
    Edge weights must be normalised against how busy the point is, and a
    pair should require co-occurrence at multiple distinct points before
    an edge is created. False positives from routine co-travel are the
    central difficulty here, not a detail."

Algoritma:
  1. Her nokta icin, o noktadan zaman sirali gecen okumalar taranir; ayni
     zaman penceresi (varsayilan 10 dk) icinde gecen her plaka cifti o
     noktada "birlikte gorulmus" sayilir. Ayni cift ayni noktada N kere
     gecse bile, o nokta tek bir "gorulme" olarak islenir -- boylece
     gunluk tekrar eden rutin bir birlikte-seyahat, sirf tekrar sayisiyla
     graf agirligini sismiremez (asil ayirt edici sey TEKRAR degil,
     FARKLI NOKTA sayisidir).
  2. Bir ciftin kenari, sadece en az `min_distinct_points` FARKLI noktada
     birlikte gorulmusse olusturulur.
  3. Kenar agirligi, birlikte gorulen her nokta icin 1/trafik_hacmi(nokta)
     toplamidir (idf benzeri): kalabalik bir noktada rastlanti sonucu
     çakismak neredeyse beklenen bir seydir (dusuk agirlik); sakin bir
     noktada ayni iki plakanin ayni anda gecmesi cok daha az rastlantisaldir
     (yuksek agirlik). Bu, "trafik hacmine gore normalize et" gereksinimini
     karsilar.
  4. `min_weight`'i asan kenarlar konvoy adayi olarak dondurulur.

Gunluk rutin birlikte seyahat (ayni iki nokta, her gun) `min_distinct_points`
esigini (nokta SAYISI acisindan) kolayca gecebilir -- CLAUDE.md'nin
uyardigi asil zorluk budur. Onu ayiklayan agirlik esigidir.

`eval_convoy.py`'de synth_scenario.py'nin varsayilan trafik hacmiyle
olculdu: min_weight=0.025 (min_distinct_points=2 ile birlikte), gomulu
konvoyu izole halde yakalarken rutin birlikte-seyahat ciftini ve tum
rastlantisal (arka plan) kenarlari eler (2 farkli tohumda da: 0 sahte
kenar). min_weight=0.0 (coklu-nokta sarti tek basina) rutin cifti hala
false positive olarak isaretliyor; min_weight=0.035 ise konvoyun kendisini
de elemeye basliyor -- 0.025 bu ikisi arasindaki bosluk. Bu deger
synth_scenario.py'nin nokta sayisi/trafik yogunlugu varsayilanlarina
kalibre edilmistir; farkli trafik hacminde yeniden olculmelidir.
"""

import argparse
import csv
from collections import defaultdict
from datetime import datetime

import networkx as nx


def load_gecis_csv(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            r["nokta_id"] = int(r["nokta_id"])
            r["zaman"] = datetime.fromisoformat(r["zaman"])
            rows.append(r)
    return rows


def traffic_volume(rows):
    """nokta_id -> o noktadan gecen toplam okuma sayisi."""
    vol = defaultdict(int)
    for r in rows:
        vol[r["nokta_id"]] += 1
    return vol


def find_cooccurrence_points(rows, window_seconds=600):
    """(plakaA, plakaB) -> birlikte gorulduren FARKLI nokta id'lerinin kumesi.

    Ayni noktada birden fazla kez birlikte gecmis olsalar da o nokta
    kumeye sadece bir kere girer.
    """
    by_point = defaultdict(list)
    for r in rows:
        by_point[r["nokta_id"]].append(r)

    pair_points = defaultdict(set)
    for nokta_id, point_rows in by_point.items():
        point_rows = sorted(point_rows, key=lambda r: r["zaman"])
        n = len(point_rows)
        for i in range(n):
            ti = point_rows[i]["zaman"]
            for j in range(i + 1, n):
                tj = point_rows[j]["zaman"]
                if (tj - ti).total_seconds() > window_seconds:
                    break
                pa, pb = point_rows[i]["plaka"], point_rows[j]["plaka"]
                if pa == pb:
                    continue
                pair_points[tuple(sorted((pa, pb)))].add(nokta_id)
    return pair_points


def build_graph(rows, window_seconds=600, min_distinct_points=2, min_weight=0.0):
    """rows: plaka/nokta_id/zaman(datetime) alanlarina sahip kayit listesi.

    Dondurur: dugumleri plaka, kenarlari (weight, points) tasiyan bir
    networkx.Graph.
    """
    vol = traffic_volume(rows)
    pair_points = find_cooccurrence_points(rows, window_seconds)

    g = nx.Graph()
    for (pa, pb), points in pair_points.items():
        if len(points) < min_distinct_points:
            continue
        weight = sum(1.0 / vol[p] for p in points)
        if weight < min_weight:
            continue
        g.add_edge(pa, pb, weight=weight, points=sorted(points))
    return g


def detect_convoys(rows, window_seconds=600, min_distinct_points=2, min_weight=0.0):
    """Konvoy adaylarini bagli bilesen (connected component) kumeleri olarak dondurur."""
    g = build_graph(rows, window_seconds, min_distinct_points, min_weight)
    return [set(c) for c in nx.connected_components(g)], g


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="data/scenario")
    parser.add_argument("--window-seconds", type=int, default=600)
    parser.add_argument("--min-distinct-points", type=int, default=2)
    parser.add_argument("--min-weight", type=float, default=0.025,
                        help="bkz. eval_convoy.py: synth_scenario.py varsayilanlarinda "
                             "olculmus esik")
    args = parser.parse_args()

    rows = load_gecis_csv(f"{args.scenario}/gecis_kaydi.csv")
    components, g = detect_convoys(
        rows, args.window_seconds, args.min_distinct_points, args.min_weight)

    print(f"{len(g.edges)} kenar, {len(components)} bagli bilesen "
          f"(min_distinct_points={args.min_distinct_points}, min_weight={args.min_weight})\n")
    for comp in components:
        if len(comp) < 2:
            continue
        print(f"aday konvoy: {sorted(comp)}")
        for a, b, data in g.subgraph(comp).edges(data=True):
            print(f"    {a} <-> {b}  weight={data['weight']:.4f}  noktalar={data['points']}")


if __name__ == "__main__":
    main()
