"""Rota/zaman anomali tespiti: bir aracin KENDI gecmis okumalarina gore
alisilmadik bir noktada ya da alisilmadik bir saatte gorulmesini isaretler.

CLAUDE.md mimarisi, roadmap'in son acik analitik maddesi: "route / time
anomaly detection".

Watchlist/convoy/cloning'in aksine burada disaridan bir referans yok --
"normal" tamamen aracin kendi gecmisinden ogrenilir. Bu yuzden az sayida
okumasi olan bir arac icin (arka plan trafiginin buyuk cogunlugu) "normal"
tanimlamak anlamsizdir: yeterli gecmisi olmayan kimlikler hic degerlendirilmez
(min_distinct_days esigi, bkz. detect_anomalies). Bu esik olmadan, 1-3
okumasi olan her arka plan araci "ilk kez gorulen nokta" olarak isaretlenir --
konvoy tespitindeki trafik-hacmi normalizasyonuyla ayni turden bir sinyal/
gurultu ayrimi sorunu.

Iki anomali turu (synth_scenario.plant_anomalies ile ayni ikili ayrim):
  - odd_point: arac, kendi gecmisinde (bu okuma haric) hic gorulmedigi bir
    noktada gorulur.
  - odd_hour: arac, gunun-saatine gore kendi gecmisindeki EN YAKIN okumaya
    (dairesel fark, gece yarisini asan farklari da doğru olcer) olan farki
    odd_hour_threshold saatten fazla olan bir saatte gorulur.

Her okumaya bakilirken o okumanin KENDISI kendi gecmisinden cikarilir
(leave-one-out): aksi halde bir noktanin/saatin "gecmiste var" olmasi
sadece o okumanin kendisi yuzunden dogru olur ve odd_point/odd_hour hicbir
zaman tetiklenmez.

Kimlik tespiti cloning.py'deki gibi fuzzy'dir (bkz. o modulun docstring'i):
ayni fiziksel aracin OCR'dan BAGIMSIZ bozulmus iki okumasi farkli metne
gelebilir; tam metin esitligiyle gruplasaydik ayni aracin gecmisi yapay
olarak ikiye bolunur ve her parca digerine gore "hep ilk kez gorulen nokta/
saat" uretebilirdi.

Bilinen sinir: fuzzy esik <=1 duzeltebileceginden daha agir bozulmus TEK bir
kritik okuma (birden fazla karakter birden yanlis), o aracin gecmis
kumesine hic baglanamaz ve tek basina min_distinct_days esigini gecemeyip
sessizce degerlendirme disi kalir -- sahte pozitif degil, kacirilan bir
gercek pozitif. eval_anomalies.py bunu severity=0.2'de 8 tohumda 1 kez
olcup gosteriyor (15/16); esigi gevsetmek bunun yerine yanlis-birlestirme
riskini artirir, bu yuzden duzeltilmedi.
"""

import argparse
from collections import defaultdict

from cloning import cluster_plate_identities
from convoy import load_gecis_csv

ODD_HOUR_THRESHOLD_HOURS = 3.0
# eval_anomalies.py'de synth_scenario.py'nin varsayilanlarina karsi olculdu (8 tohum,
# 16 planted anomali): min_distinct_days=4 iyi rota/saat gecmisi olan ama kisa (4 gunluk)
# bir commuter'i yanlislikla isaretleyip 1 sahte pozitif uretiyordu; >=5, 0 sahte pozitifle
# ayni recall'i (15/16) koruyor.
MIN_DISTINCT_DAYS = 5


def group_by_identity(rows, fuzzy_identity=True):
    if fuzzy_identity:
        clusters = cluster_plate_identities({r["plaka"] for r in rows})
        key_of = lambda r: clusters[r["plaka"]]
    else:
        key_of = lambda r: r["plaka"]

    by_identity = defaultdict(list)
    for r in rows:
        by_identity[key_of(r)].append(r)
    return by_identity


def circular_hour_gap(h1, h2):
    """Iki gunun-saati arasindaki en kisa dairesel fark (0-24 sarmali dahil)."""
    d = abs(h1 - h2) % 24
    return min(d, 24 - d)


def hour_of(dt):
    return dt.hour + dt.minute / 60.0 + dt.second / 3600.0


def detect_anomalies(rows, min_distinct_days=MIN_DISTINCT_DAYS,
                      odd_hour_threshold=ODD_HOUR_THRESHOLD_HOURS, fuzzy_identity=True):
    """rows: plaka/nokta_id/zaman(datetime) alanlarina sahip kayit listesi.

    Donen: her anomali okuma icin bir dict listesi (types alaninda
    "odd_point" ve/veya "odd_hour" bulunur).
    """
    by_identity = group_by_identity(rows, fuzzy_identity)

    flags = []
    for reads in by_identity.values():
        for i, r in enumerate(reads):
            others = reads[:i] + reads[i + 1:]
            other_days = {o["zaman"].date() for o in others}
            if len(other_days) < min_distinct_days:
                continue  # bu kimlik icin "normal" tanimlayacak yeterli gecmis yok

            types = []
            other_points = {o["nokta_id"] for o in others}
            if r["nokta_id"] not in other_points:
                types.append("odd_point")

            r_hour = hour_of(r["zaman"])
            other_hours = [hour_of(o["zaman"]) for o in others]
            min_gap = min(circular_hour_gap(r_hour, h) for h in other_hours)
            if min_gap > odd_hour_threshold:
                types.append("odd_hour")

            if types:
                flags.append({
                    "plaka": r["plaka"],
                    "nokta_id": r["nokta_id"],
                    "zaman": r["zaman"],
                    "types": types,
                    "nearest_hour_gap": round(min_gap, 2),
                    "history_days": len(other_days),
                })
    return flags


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="data/scenario")
    parser.add_argument("--min-distinct-days", type=int, default=MIN_DISTINCT_DAYS)
    parser.add_argument("--odd-hour-threshold", type=float, default=ODD_HOUR_THRESHOLD_HOURS)
    args = parser.parse_args()

    rows = load_gecis_csv(f"{args.scenario}/gecis_kaydi.csv")
    flags = detect_anomalies(rows, args.min_distinct_days, args.odd_hour_threshold)

    print(f"{len(flags)} anomali okuma isaretlendi "
          f"(min_distinct_days={args.min_distinct_days}, odd_hour_threshold={args.odd_hour_threshold}sa)\n")
    for f in sorted(flags, key=lambda f: f["zaman"]):
        print(f"  {f['plaka']} @ nokta {f['nokta_id']} ({f['zaman']})  "
              f"turler={f['types']}  en_yakin_saat_farki={f['nearest_hour_gap']}sa  "
              f"gecmis_gun_sayisi={f['history_days']}")


if __name__ == "__main__":
    main()
