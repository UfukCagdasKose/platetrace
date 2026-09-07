"""Analitik uclarinin temel testleri.

Odak, izlenimden ziyade iki gercek bug'i regresyona karsi kilitlemek
(bkz. app/main.py'deki yorumlar):
  - limit=0, `if limit:` yuzunden sessizce yok sayilip TUM satirlari
    donduruyordu.
  - GecisKaydi.nokta_id'de foreign key kisiti olmadigi icin, Nokta
    tablosunda karsiligi olmayan bir nokta_id /klonlar'i KeyError'la
    500'e dusuruyordu.

Bunlarin yaninda her ucun bos veritabaninda cokmedigini ve en az bir
gercek (pozitif) senaryoda beklenen sonucu urettigini de kontrol eder.
"""

from app.models import ArananArac, Nokta


def add_nokta(client, ad, enlem, boylam):
    db = client.SessionLocal()
    n = Nokta(ad=ad, enlem=enlem, boylam=boylam)
    db.add(n)
    db.commit()
    db.refresh(n)
    db.close()
    return n.id


def add_aranan(client, plaka, sebep="test"):
    db = client.SessionLocal()
    db.add(ArananArac(plaka=plaka, sebep=sebep))
    db.commit()
    db.close()


def add_gecis(client, plaka, nokta_id, zaman, guven=0.9):
    r = client.post("/gecisler", json={
        "plaka": plaka, "nokta_id": nokta_id, "zaman": zaman, "guven": guven,
    })
    assert r.status_code == 200, r.text
    return r.json()


# --- bos veritabani: hicbir uc cokmemeli ---

def test_bos_db_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "db": "up", "veri_var": False}


def test_bos_db_analitik_uclari_bos_liste_doner(client):
    for path in ["/konvoylar", "/klonlar", "/anomaliler", "/aranan/eslesmeler"]:
        r = client.get(path)
        assert r.status_code == 200, path
        assert r.json() == [], path


# --- regresyon: limit=0 ---

def test_limit_sifir_analitik_uclarinda_hicbir_satir_okumamali(client):
    # `/gecisler` her zaman kosulsuz .limit(limit) uyguluyordu, hic bozuk
    # olmadi -- bug'un oldugu yer _gecis_rows (konvoy/klon/anomali ucleri).
    # O yuzden regresyon testi dogrudan bu uclardan birini hedeflemeli.
    p1 = add_nokta(client, "P1", 39.90, 32.80)
    p2 = add_nokta(client, "P2", 39.95, 32.90)
    for plaka in ["34AAA01", "34BBB02"]:
        add_gecis(client, plaka, p1, "2026-09-01T08:00:00")
        add_gecis(client, plaka, p2, "2026-09-01T08:20:00")

    dolu = client.get("/konvoylar")
    assert dolu.json() != []  # veri var, konvoy bulunmali

    bos = client.get("/konvoylar?limit=0")
    assert bos.status_code == 200
    assert bos.json() == []  # limit=0 -> hic satir okunmamali -> hic konvoy yok


# --- regresyon: eksik nokta_id /klonlar'i patlatmamali ---

def test_klonlar_eksik_nokta_id_ile_cokmemeli(client):
    # Nokta tablosunda HIC nokta yok. Iki FARKLI nokta_id sart -- ayni
    # nokta_id kullanilirsa cloning.py'nin "ayni noktaysa atla" kisayolu
    # points[] aramasina hic ugramadan devam eder ve bug'i test etmemis olur.
    add_gecis(client, "34ABC123", 9999, "2026-09-01T10:00:00")
    add_gecis(client, "34ABC123", 8888, "2026-09-01T10:00:05")

    r = client.get("/klonlar")
    assert r.status_code == 200
    assert r.json() == []


# --- pozitif senaryolar: gercek bir sonuc uretiyor mu ---

def test_klonlar_imkansiz_hizi_yakaliyor(client):
    p1 = add_nokta(client, "P1", 39.92, 32.85)
    p2 = add_nokta(client, "P2", 40.92, 32.85)  # ~111 km kuzeyde

    add_gecis(client, "34ABC123", p1, "2026-09-01T10:00:00")
    add_gecis(client, "34ABC123", p2, "2026-09-01T10:01:00")  # 1 dk'da 111 km -> imkansiz

    r = client.get("/klonlar")
    assert r.status_code == 200
    flags = r.json()
    assert len(flags) == 1
    assert flags[0]["plaka"] == "34ABC123"
    assert flags[0]["required_speed_kmh"] > 150


def test_konvoylar_birlikte_gorulen_ciftleri_dusuk_trafikte_yakaliyor(client):
    p1 = add_nokta(client, "P1", 39.90, 32.80)
    p2 = add_nokta(client, "P2", 39.95, 32.90)

    for plaka in ["34AAA01", "34BBB02"]:
        add_gecis(client, plaka, p1, "2026-09-01T08:00:00")
        add_gecis(client, plaka, p2, "2026-09-01T08:20:00")

    r = client.get("/konvoylar")
    assert r.status_code == 200
    konvoylar = r.json()
    assert any({"34AAA01", "34BBB02"} <= set(k["plakalar"]) for k in konvoylar)


def test_anomaliler_alisilmadik_saati_yakaliyor(client):
    nokta_id = add_nokta(client, "N1", 39.90, 32.80)
    # 6 gun boyunca hep sabah 08:00'de gecis (duzenli gecmis)
    for day in range(1, 7):
        add_gecis(client, "34ABC123", nokta_id, f"2026-09-0{day}T08:00:00")
    # 7. gun, aynı gunun icinde ama gece yarisina yakin -- alisilmadik saat
    add_gecis(client, "34ABC123", nokta_id, "2026-09-07T21:00:00")

    r = client.get("/anomaliler")
    assert r.status_code == 200
    anomaliler = r.json()
    assert any(a["zaman"].startswith("2026-09-07T21:00:00") and "odd_hour" in a["types"]
               for a in anomaliler)


def test_aranan_eslesmeler_tam_ve_bulanik_eslesmeyi_buluyor(client):
    nokta_id = add_nokta(client, "N1", 39.90, 32.80)
    add_aranan(client, "34ABC123", sebep="kayip arac")

    add_gecis(client, "34ABC123", nokta_id, "2026-09-01T10:00:00")  # tam eslesme
    add_gecis(client, "34ABC12B", nokta_id, "2026-09-01T11:00:00")  # 8<->B, bulanik eslesme

    r = client.get("/aranan/eslesmeler")
    assert r.status_code == 200
    eslesmeler = {e["okunan_plaka"] for e in r.json()}
    assert eslesmeler == {"34ABC123", "34ABC12B"}
