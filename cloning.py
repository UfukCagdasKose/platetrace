"""Plaka klonlama tespiti: ayni plakanin, fiziksel olarak imkansiz bir
hizda iki nokta arasinda 'seyahat ettigi' okuma ciftlerini isaretler.

CLAUDE.md mimarisi: "plate cloning detection (physically impossible
travel speed)".

Ayni plakanin farkli zamanlarda farkli noktalarda okunmasi normaldir --
arac gercekten oradan gecmistir. Ama iki nokta arasindaki mesafeyi,
aralarindaki sureye bolup gereken hizi hesapladigimizda
MAX_PLAUSIBLE_SPEED_KMH'i asiyorsa, ayni fiziksel aracin iki yerde
(neredeyse) ayni anda olmasi imkansizdir: plaka klonlanmis olabilir
(baska bir arac ayni plakayla dolasiyor) ya da bir OCR hatasi iki farkli
araci ayni metne okumustur. Bu modul sadece fiziksel tutarliligi
kontrol eder; hangi ihtimal oldugunu ayirt etmez.

Bir plakanin TUM okuma ciftleri (sadece ardisik olanlar degil)
karsilastirilir -- plaka basina okuma sayisi kucuk oldugu icin O(n^2)
maliyeti onemsizdir, ve bu sayede A->B, B->C ayri ayri makul gorunse
bile A->C'nin imkansiz oldugu durumlar da yakalanir.

Kimlik tespiti tam metin esitligiyle degil, watchlist.py'deki fuzzy
mesafeyle yapilir: klonlanmis bir plakanin iki okumasi OCR'dan BAGIMSIZ
olarak gectigi icin (synth_scenario.py'de iki okuma ayri ayri
bozuluyor), ayni fiziksel plaka iki farkli metne okunabilir (ör.
"21EU666" / "21EU665"). Tam metin esitligiyle gruplasaydik bu cift hic
gorulmezdi -- gercek senaryo verisiyle test edilirken bu tam olarak
oldu, bu yuzden ayni fuzzy mesafe mantigi (0<->O, 1<->I, 8<->B, 5<->S
bedava, esik <=1) burada da plaka-kimligi kumeleme adiminda kullanilir.
"""

import argparse
import csv
from collections import defaultdict
from itertools import combinations
from math import asin, cos, radians, sin, sqrt

from convoy import load_gecis_csv
from watchlist import weighted_edit_distance

MAX_PLAUSIBLE_SPEED_KMH = 150.0  # synth_scenario.py'deki varsayimla ayni


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlmb = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlmb / 2) ** 2
    return 2 * r * asin(sqrt(a))


def load_points(path):
    points = {}
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            points[int(r["id"])] = (float(r["enlem"]), float(r["boylam"]))
    return points


def cluster_plate_identities(plates, max_distance=1):
    """Birbirine watchlist.py mesafesiyle <=max_distance uzaklikta olan
    farkli plaka metinlerini (OCR'in ayni araci farkli okumus olabilecegi
    varyantlari) union-find ile tek bir kimlige birlestirir.

    Donen: {plaka_metni: temsilci_kok} sozlugu.
    """
    parent = {p: p for p in plates}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    plates = list(plates)
    for i in range(len(plates)):
        for j in range(i + 1, len(plates)):
            if weighted_edit_distance(plates[i], plates[j]) <= max_distance:
                ra, rb = find(plates[i]), find(plates[j])
                if ra != rb:
                    parent[ra] = rb

    return {p: find(p) for p in plates}


def detect_clones(rows, points, max_speed_kmh=MAX_PLAUSIBLE_SPEED_KMH, fuzzy_identity=True):
    """rows: plaka/nokta_id/zaman(datetime) alanlarina sahip kayit listesi.

    fuzzy_identity=True ise (varsayilan), okumalar tam metin esitligi
    yerine cluster_plate_identities() ile kumelenir -- ayni fiziksel
    plakanin iki bagimsiz OCR hatasiyla farkli okunmus olma ihtimaline
    karsi (bkz. modul docstring'i).

    Donen: gereken hizi asan her okuma cifti icin bir dict listesi.
    """
    if fuzzy_identity:
        clusters = cluster_plate_identities({r["plaka"] for r in rows})
        key_of = lambda r: clusters[r["plaka"]]
    else:
        key_of = lambda r: r["plaka"]

    by_identity = defaultdict(list)
    for r in rows:
        by_identity[key_of(r)].append(r)

    flags = []
    for reads in by_identity.values():
        for a, b in combinations(sorted(reads, key=lambda r: r["zaman"]), 2):
            if a["nokta_id"] == b["nokta_id"]:
                continue
            seconds = abs((b["zaman"] - a["zaman"]).total_seconds())
            if seconds == 0:
                continue
            lat1, lon1 = points[a["nokta_id"]]
            lat2, lon2 = points[b["nokta_id"]]
            dist = haversine_km(lat1, lon1, lat2, lon2)
            speed = dist / (seconds / 3600.0)
            if speed > max_speed_kmh:
                flags.append({
                    "plaka": a["plaka"] if a["plaka"] == b["plaka"] else f"{a['plaka']}~{b['plaka']}",
                    "from_nokta": a["nokta_id"], "from_zaman": a["zaman"],
                    "to_nokta": b["nokta_id"], "to_zaman": b["zaman"],
                    "distance_km": round(dist, 2),
                    "seconds": round(seconds, 1),
                    "required_speed_kmh": round(speed, 1),
                })
    return flags


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="data/scenario")
    parser.add_argument("--max-speed", type=float, default=MAX_PLAUSIBLE_SPEED_KMH)
    args = parser.parse_args()

    rows = load_gecis_csv(f"{args.scenario}/gecis_kaydi.csv")
    points = load_points(f"{args.scenario}/nokta.csv")

    flags = detect_clones(rows, points, args.max_speed)
    plates = sorted({f["plaka"] for f in flags})
    print(f"{len(flags)} imkansiz-hiz cifti, {len(plates)} farkli plaka "
          f"(esik={args.max_speed:.0f} km/h)\n")
    for f in flags:
        print(f"  {f['plaka']}: nokta {f['from_nokta']} ({f['from_zaman']}) -> "
              f"nokta {f['to_nokta']} ({f['to_zaman']})  "
              f"{f['distance_km']} km / {f['seconds']:.0f} sn -> {f['required_speed_kmh']} km/h")


if __name__ == "__main__":
    main()
