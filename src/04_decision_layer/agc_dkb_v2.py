"""
AGC - DECISION KNOWLEDGE BASE v2
==================================
Onceki DKB "hangi degiskeni iyi tahmin edebiliyoruz" diye kurulmustu — yanlis
uctan. Bu surum "hangi degisken NET KARI etkiliyor" diye kurulur.

UC ZEMIN
--------
1) EKONOMI (deterministik, %0.2-2.2 hata ile dogrulandi)
   Economics.pdf fiyatlari + ReadMe formulleri ile 5 dakikalik maliyet serisi
   yeniden insa edildi ve resmi Resources degerleriyle karsilastirildi.
   -> "Bu aksiyon su kadar eder" artik hesap, tahmin degil.

2) KALIBRASYON (olculdu)
   Her hedefin tahmin belirsizligi olculdu. Sistem yalnizca kalibre oldugu
   yerde olasilik iddia eder; digerlerinde yon soyler; bazi hedeflerde susar.

3) KALITE (kismen olculdu)
   Brix 0.35 €/kg (Economics.pdf, kesin)
   B sinifi yarim fiyat (Economics.pdf, kesin)
   Sicaklik -> Brix -0.223/°C (bizim veri, t=-4.30, KORELASYONEL)
   EC -> Brix OLCULEMEDI (guc yetersiz: MDE 0.445 > literatur etkisi 0.40)

KRITIK TASARIM KARARLARI
------------------------
* ESIK = seraya ozgu zarf (p5/p95), mutlak literatur esigi DEGIL.
  Gerekce: mutlak esik strateji tespit eder, risk degil. EC>6 kurali
  Digilog'a surekli alarm verirdi — oysa Digilog en yuksek Brix'i aldi.
* SUREKLI SAPMA kriteri: pencerenin TAMAMI zarf disinda olmali.
  Gerekce: "dokunma" tanimiyla alarm orani %91 (gunde 21.9 saat) idi;
  "surekli" ile %31'e (7.5 saat) dusuyor ve olay orani %19.3 -> %3.1.
* MALIYET SAATE BAGLI: elektrik tarifesi 07:00-23:00 arasi iki kat.
  Ayni aksiyonun maliyeti saate gore 8.4 kat degisiyor.
* AKSIYON YONU soylenir, BUYUKLUGU soylenmez (model nedensel degil).

CIKTI: dkb_v2.csv · dkb_v2_ozet.csv
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

# ---- Economics.pdf ----
ISI_EUR, ELEK_PIK, ELEK_DUS = 0.0083, 0.08, 0.04
CO2_UCUZ, CO2_PAHALI, CO2_ESIK = 0.08, 0.20, 12.0
BRIX_EUR = 0.35                      # €/kg per Brix — sezon boyunca sabit
B_SINIFI_ORAN = 0.50                 # B sinifi yarim fiyat
# ---- ReadMe.pdf ----
K_RAIL, K_GROW = 2.1, 0.62           # W/m² per °C
HPS_W, LED_W = 81.0, 61.52           # W/m²
PIK_BAS, PIK_BIT = 7, 23

# Kalibrasyon olcumunden — hedef basina sistem ne iddia edebilir
# (agc_decision_kb ciktisiyla tutarli; Tot_PAR hesaplanabilir oldugu icin
#  tahmin hedefi degil, surucu oznitelik)
GUVEN = {
    "EC_slab1": "SAYISAL", "EC_slab2": "SAYISAL", "WC_slab1": "SAYISAL",
    "WC_slab2": "KALITATIF", "t_slab1": "KALITATIF", "t_slab2": "KALITATIF",
    "Tair": "KALITATIF", "HumDef": "KALITATIF", "CO2air": "KALITATIF",
    "Rhair": "KALITATIF", "Tot_PAR": "SURUCU",
}

# Aksiyon ailesi: (yon) -> (aksiyon, hangi maliyet kalemi, kisit)
AKSIYON = {
    ("Tair", "dusuk"):  ("Isitmayi artir veya enerji perdesini kapat", "isi",
                         "Isitma maliyeti dusuk kalem (%5-12) ama surekli"),
    ("Tair", "yuksek"): ("Havalandirmayi artir veya golgele", "yok",
                         "Havalandirma CO2 ve nem kaybi yaratir; sicaklik dusuk Brix'e iyi gelir"),
    ("HumDef", "dusuk"): ("Havalandirma veya isitma ile nem acigini yukselt", "isi",
                          "Dusuk nem acigi terlemeyi durdurur -> kalsiyum tasinimi aksar -> B sinifi riski"),
    ("HumDef", "yuksek"): ("Nemlendir veya havalandirmayi azalt", "yok",
                           "Yuksek nem acigi su stresi yaratir"),
    ("EC_slab1", "yuksek"): ("Sulama siklığini artir veya drenaj oranini yukselt", "yok",
                             "Yuksek EC Brix'i artirabilir ama B sinifi riskini de artirir"),
    ("EC_slab1", "dusuk"):  ("Besin cozeltisi konsantrasyonunu artir", "yok",
                             "Ani artis kok soku yaratir"),
    ("WC_slab1", "dusuk"):  ("Sulama siklığini artir", "yok",
                             "Asiri sulama kok bolgesinde oksijeni azaltir"),
    ("WC_slab1", "yuksek"): ("Sulama siklığini azalt", "yok",
                             "Ani kesinti su stresi yaratir"),
    ("t_slab1", "dusuk"):   ("Kok bolgesi isitmasini artir", "isi",
                             "Substrat yavas tepki verir, erken mudahale gerekir"),
    ("t_slab1", "yuksek"):  ("Sulama ile kok bolgesini serinlet", "yok", "Su sicakligi ani dusurulmemeli"),
    ("CO2air", "dusuk"):    ("CO2 dozajini artir", "co2",
                             "Ilk 12 kg/m² sonrasi birim maliyet 2.5 kat artar"),
    ("CO2air", "yuksek"):   ("CO2 dozajini azalt", "co2", "Fazla CO2 israftir"),
    ("Rhair", "yuksek"):    ("Havalandir veya isit", "isi", "Yuksek nem mantar riski"),
    ("Rhair", "dusuk"):     ("Havalandirmayi azalt", "yok", "Dusuk nem terlemeyi artirir"),
}
for a, b in [("EC_slab1", "EC_slab2"), ("WC_slab1", "WC_slab2"), ("t_slab1", "t_slab2")]:
    for y in ("yuksek", "dusuk"):
        AKSIYON[(b, y)] = AKSIYON[(a, y)]

# Strateji raporundan olculmus takim referanslari
REFERANS = {
    ("EC_slab1", "yuksek"): "AICU drenaj oranini 0.43'e cikardi (alti takimin en yuksegi)",
    ("WC_slab1", "dusuk"):  "IUACAAS en yuksek sulamayi uyguladi (867 L/m²/sezon)",
    ("Tair", "dusuk"):      "Automatoes en sicak serayi ikinci en dusuk isitmayla isletti (23.3°C / 185 MJ)",
    ("Tair", "yuksek"):     "Digilog en serin rejimi uyguladi, en yuksek Brix'i (8.86) aldi",
    ("HumDef", "dusuk"):    "Reference neredeyse sifir B sinifi uretti (14.3 kg'da 0.003)",
}


def saatlik_maliyet(kalem: str, saat: int, siddet: float = 1.0) -> float:
    """Bir aksiyonun 1 saatlik maliyeti, cent/m². Saate baglidir."""
    pik = PIK_BAS <= saat < PIK_BIT
    if kalem == "isi":
        # 10°C boru-hava farki varsayimi, siddetle olceklenir
        mj = (10 * siddet * (K_RAIL + K_GROW)) * 3600 / 1e6
        return mj * ISI_EUR * 100
    if kalem == "elektrik":
        kwh = (HPS_W + LED_W) * siddet / 1000
        return kwh * (ELEK_PIK if pik else ELEK_DUS) * 100
    if kalem == "co2":
        return 0.05 * siddet * CO2_UCUZ * 100          # ~0.05 kg/m²/saat tipik dozaj
    return 0.0


def run(base_dir: Path):
    zarf = pd.read_csv(base_dir / "dkb_zarf.csv")
    zt = zarf[zarf.donem == "tumu"]

    kayit = []
    for _, z in zt.iterrows():
        h, gh = z.hedef, z.sera
        gv = GUVEN.get(h, "KALITATIF")
        if gv == "SURUCU":
            continue                                    # tahmin hedefi degil
        for yon, esik in [("yuksek", z.zarf_ust), ("dusuk", z.zarf_alt)]:
            aks, kalem, kisit = AKSIYON.get((h, yon), ("— tanimlanmadi", "yok", "—"))
            kayit.append({
                "hedef": h, "sera": gh, "yon": yon, "esik": round(float(esik), 3),
                "esik_turu": "ZARF", "kriter": "SUREKLI",     # tum pencere disarida
                "medyan": round(float(z.medyan), 3),
                "risk": ("Bu seranin normal calisma araliginin "
                         f"{'ustune cikiyor' if yon == 'yuksek' else 'altina iniyor'}"),
                "guven": gv, "aksiyon": aks, "maliyet_kalemi": kalem, "kisit": kisit,
                "referans": REFERANS.get((h, yon), ""),
                "maliyet_pik": round(saatlik_maliyet(kalem, 8), 3),
                "maliyet_pikdisi": round(saatlik_maliyet(kalem, 2), 3),
            })
    d = pd.DataFrame(kayit)
    d.to_csv(base_dir / "dkb_v2.csv", index=False)

    print("=" * 84)
    print("1. KURAL SAYISI — guven seviyesine gore")
    print("=" * 84)
    print(d.groupby(["guven", "hedef"]).size().unstack(fill_value=0).to_string())

    print("\n" + "=" * 84)
    print("2. AKSIYONLARIN SAATE BAGLI MALIYETI (cent/m²/saat)")
    print("=" * 84)
    print(f"  {'kalem':10s}{'08:00 (pik)':>13s}{'02:00 (pik disi)':>18s}")
    for kal in ["isi", "co2", "elektrik"]:
        a, b = saatlik_maliyet(kal, 8), saatlik_maliyet(kal, 2)
        ek = f"   <- {a/b:.0f} kat fark" if abs(a - b) > 1e-9 else "   (tarife farki yok)"
        print(f"  {kal:10s}{a:13.3f}{b:18.3f}{ek}")
    print("\n  Elektrik tarifesi 07:00-23:00 arasi 0.08, disinda 0.04 €/kWh.")
    print("  Lamba kararinin maliyeti gunun saatine gore IKI KAT degisiyor.")

    print("\n" + "=" * 84)
    print("3. EKONOMIK KALDIRACLAR — olculmus buyukluk (€/m², sezon)")
    print("=" * 84)
    kald = pd.DataFrame([
        {"kaldirac": "Tarife kaydirma (pik %25 -> pik disi)", "etki": "1.58 – 1.96",
         "tur": "DETERMINISTIK", "not": "saf yeniden fiyatlama, nedensel iddia yok"},
        {"kaldirac": "B sinifini sifirlamak", "etki": "0.00 – 0.84",
         "tur": "OLCULMUS", "not": "Reference bunu basardi (14.3 kg'da 0.003 B)"},
        {"kaldirac": "Brix farki (8.46 -> 8.88)", "etki": "0.00 – 1.47",
         "tur": "OLCULMUS", "not": "0.35 €/kg, Economics.pdf"},
        {"kaldirac": "Isitma farki (en iyi vs en kotu)", "etki": "2.47",
         "tur": "DETERMINISTIK", "not": "toplam maliyetin yalnizca %5-12'si"},
        {"kaldirac": "Elektrik farki (en iyi vs en kotu)", "etki": "4.97",
         "tur": "DETERMINISTIK", "not": "toplam maliyetin %55-65'i — EN BUYUK KALEM"},
    ])
    print(kald.to_string(index=False))
    print(f"\n  Referans: net kar araligi 2.60 – 8.15 €/m² (Automatoes birinci)")
    print(f"  Automatoes'un ikinciye farki: 1.65 €/m²")

    print("\n" + "=" * 84)
    print("4. SISTEM NE IDDIA EDEBILIR?")
    print("=" * 84)
    for g, s in d.groupby("guven"):
        hed = sorted(s.hedef.unique())
        if g == "SAYISAL":
            print(f"  SAYISAL   {hed}\n            -> 'esigi asma olasiligi %X' denebilir")
        else:
            print(f"  KALITATIF {hed}\n            -> yalnizca 'yukselis/dusus egiliminde' denebilir")
    print(f"  SURUCU    ['Tot_PAR']\n            -> tahmin hedefi DEGIL; dis PAR + perde + lamba ile HESAPLANIR")

    kald.to_csv(base_dir / "dkb_v2_ozet.csv", index=False)
    print(f"\n  Toplam kural: {len(d)}")
    print(f"Kaydedildi: dkb_v2.csv · dkb_v2_ozet.csv")
    return d, kald


if __name__ == "__main__":
    BASE_DIR = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")
    run(BASE_DIR)
