"""
AGC - DKB EKONOMIK KURALLAR EKI
=================================
BOSLUK: DKB v2, fizyolojik riski (Tair, EC_slab, WC_slab...) izliyor ama
kari BELIRLEYEN degiskene hic kural koymuyor. Ekonomi raporunun bulgusu:
kis kar farkinin %113'u LAMBA SURESINDEN geliyor. Bu ek, uc deterministik
kural ekler.

UC KURAL, UCU DE ONCE VERIYLE TEST EDILDI
-------------------------------------------
1) TARIFE VERIMLILIGI
   24 saatlik kayan pik-saat payi olculdu: min 0.00, max 0.70, std 0.032.
   Sabit degil -> anlamli bir kural. Referans: Automatoes %57.6 (en dusuk
   pik payi, kis donemi), AICU %67.8 (en yuksek).

2) KUMULATIF CO2 ESIGI
   Sezon sonu kumulatif deger: 5 takim 12 kg/m² esiginin ALTINDA kaldi
   (7.28-10.15), yalniz TheAutomators asti (12.50) VE bu sezonun son
   6 gununde oldu. Yani "esik asildi mi" sorusu neredeyse hic gerceklesmiyor
   -> kural ESIK ASIMI degil, ESIGE MESAFE / EGILIM olarak tasarlandi.

3) LAMBA KULLANIMI
   Ilk tasarim "kWh/kg" idi ama kg (uretim) yalnizca hasat anlarinda bilinir
   (23-24 olcum/sezon), 6 saatlik ufukta hesaplanamaz. YENIDEN TASARLANDI:
   "son 7 gunun kWh/m²" (anlamli degisken: 0-20.75 araliginda) + sezon sonu
   REFERANS TABLOSU ile karsilastirma (Automatoes 12.4 - Reference 33.0 €/kg).

UCUNUN DE DAYANAGI: Economics.pdf fiyatlari + ReadMe.pdf formulleri,
%0.2-2.2 hata ile dogrulanmis (bkz. agc_maliyet_serisi.py). Tahmin degil,
hesap.

CIKTI: dkb_ekonomik_ek.csv
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ELEK_PIK, ELEK_DUS = 0.08, 0.04
CO2_UCUZ, CO2_PAHALI, CO2_ESIK = 0.08, 0.20, 12.0
PIK_BAS, PIK_BIT = 7, 23

# Strateji ve Ekonomi raporlarindan — olculmus sezon sonu referanslar
REFERANS_VERIMLILIK = {          # €/kg, degisken maliyet / uretim
    "Automatoes": 1.294, "AICU": 1.401, "IUACAAS": 1.407,
    "Reference": 1.501, "TheAutomators": 1.570, "Digilog": 1.603,
}
REFERANS_PIK_PAYI = {             # kis donemi ortalama pik-saat elektrik payi
    "Automatoes": 57.6, "Reference": 58.5, "TheAutomators": 62.0,
    "Digilog": 62.8, "IUACAAS": 66.8, "AICU": 67.8,
}
REFERANS_CO2_SEZON = {            # kg/m², sezon sonu kumulatif
    "IUACAAS": 7.28, "Reference": 8.63, "Automatoes": 9.07,
    "Digilog": 9.66, "AICU": 10.15, "TheAutomators": 12.50,
}


def kural_tarife(pik_payi_24h: float, sera: str) -> dict:
    """Son 24 saatteki pik-elektrik TUKETIM payi, en iyi referansla kiyaslanir.

    KRITIK AYRIM: pik_payi_24h, pik SAATLERIN zaman orani DEGILDIR (bu her
    zaman 16/24=0.667 sabittir, cunku pik araligi 07:00-23:00 sabit 16
    saattir). Dogru girdi, pik saatlerdeki ELEKTRIK TUKETIMININ toplam
    tuketime oranidir: kwh_pik / (kwh_pik + kwh_disi). Bu, HANGI SAATLERDE
    LAMBA ACIK oldugunu yansitir ve seralar arasi gercekten degisir
    (Ekonomi raporu: %57.6 - %67.8 arasi).
    """
    en_iyi = min(REFERANS_PIK_PAYI.values()) / 100
    fark = pik_payi_24h - en_iyi
    if fark <= 0.03:
        seviye = "VERIMLI"
    elif fark <= 0.10:
        seviye = "ORTA"
    else:
        seviye = "IYILESTIRILEBILIR"
    # Potansiyel kazanc: pik payini en iyiye cekmenin gunluk karsiligi
    # (tipik 6 saatlik lamba maliyeti uzerinden kaba tahmin)
    tipik_kwh_6s = 0.143 * 6           # HPS+LED, tam yuk, 6 saat
    kazanc_cent = max(fark, 0) * tipik_kwh_6s * (ELEK_PIK - ELEK_DUS) * 100
    return {"kural": "tarife_verimliligi", "sera": sera,
            "pik_payi_pct": round(pik_payi_24h * 100, 1),
            "en_iyi_referans_pct": round(en_iyi * 100, 1),
            "fark_pct": round(fark * 100, 1), "seviye": seviye,
            "potansiyel_kazanc_cent_6s": round(kazanc_cent, 3),
            "aksiyon": ("Yok — zaten pik-disina agirlikli" if seviye == "VERIMLI" else
                       "Lamba saatlerini pik-disina (23:00-07:00) kaydirmayi degerlendir"),
            "referans": f"Automatoes kis donemi pik payi %{REFERANS_PIK_PAYI['Automatoes']:.1f} "
                       "(alti takimin en dusugu)",
            "kisit": "Saf yeniden fiyatlama — ayni kWh, farkli saat. Nedensel iddia yok. "
                     "Bitkinin isiga ne zaman ihtiyac duydugu ayri bir sorudur.",
            "guven": "DETERMINISTIK", "kaynak": "Economics.pdf tarife tablosu"}


def kural_co2_esik(kumulatif_kg_m2: float, gun_kalan: int, sera: str) -> dict:
    """Kumulatif CO2 dozaji, 12 kg/m² esigine egilim olarak izlenir.

    ESIK ASIMI DEGIL EGILIM: sezon sonu verisinde 5/6 takim esigin altinda
    kalmis, asan tek takim da sezonun son 6 gununde asmis. Bu yuzden kural
    'asildi mi' yerine 'bu hizla giderse ne zaman asilir' sorusunu sorar.
    """
    gunluk_ort = kumulatif_kg_m2 / max(1, 166 - gun_kalan)     # sezon basindan bu yana
    projeksiyon = kumulatif_kg_m2 + gunluk_ort * gun_kalan
    if projeksiyon < CO2_ESIK * 0.85:
        seviye = "GUVENLI"
    elif projeksiyon < CO2_ESIK:
        seviye = "IZLE"
    else:
        seviye = "ESIK_ASILACAK"
        asim_gun = max(0, (CO2_ESIK - kumulatif_kg_m2) / max(gunluk_ort, 1e-6))
    ek_maliyet_kg = max(projeksiyon - CO2_ESIK, 0) * (CO2_PAHALI - CO2_UCUZ)
    return {"kural": "co2_esik_egilimi", "sera": sera,
            "kumulatif_kg_m2": round(kumulatif_kg_m2, 3),
            "sezon_sonu_projeksiyon": round(projeksiyon, 3),
            "seviye": seviye,
            "ek_maliyet_eur_m2": round(ek_maliyet_kg, 3),
            "aksiyon": ("Yok" if seviye == "GUVENLI" else
                       "CO2 dozaj hizini gozden gecir; esik sonrasi kg basina maliyet "
                       f"{CO2_PAHALI/CO2_UCUZ:.1f} kat artiyor"),
            "referans": f"5/6 takim sezonu esigin altinda tamamladi "
                       f"({min(REFERANS_CO2_SEZON.values()):.2f}-{sorted(REFERANS_CO2_SEZON.values())[-2]:.2f} kg/m²); "
                       "yalnizca TheAutomators asti, o da son 6 gunde",
            "kisit": "Projeksiyon dogrusaldir; gercek dozaj mevsimsel degisebilir.",
            "guven": "DETERMINISTIK", "kaynak": "Economics.pdf CO2 esik tablosu"}


def kural_lamba(son7gun_kwh_m2: float, sera: str, mevsim: str = "kis") -> dict:
    """Son 7 gunun lamba elektrik tuketimi, MEVSIME DUYARLI referansa kiyasla
    degerlendirilir.

    DUZELTME (v2): Ilk surumde tek bir sabit referans (11.4 kWh/hafta, TUM
    SEZON ortalamasi -- yaz aylari dahil) kullanilmisti. Kis haftasiyla
    (lambalar yogun calisirken) karsilastirilinca ALTI TAKIM DA "COK_YUKSEK"
    cikti -- kural ayirt edici olmaktan cikti. Kok neden: mevsimsel referans
    karisikligi (bu proje boyunca tekrarlayan bir hata deseni; bkz. Ekonomi
    raporu Ek A.3, kalibrasyon analizindeki ayni sorun).

    Gercek haftalik kWh/m² ortalamalari (bu veri setinden olculmus):
        KIS  (Ara-Mar): 13.74 (AICU) - 17.68 (Digilog)
        YAZ  (Nis-May):  1.12 (IUACAAS) - 5.74 (Digilog)
    Referans artik mevsime gore secilir.
    """
    REFERANS_HAFTALIK = {
        "kis": 15.28,   # alti takimin kis donemi haftalik ortalamasi
        "yaz": 3.70,    # alti takimin yaz donemi haftalik ortalamasi
    }
    sirali = sorted(REFERANS_VERIMLILIK.items(), key=lambda x: x[1])
    en_iyi, en_kotu = sirali[0], sirali[-1]
    tipik_haftalik = REFERANS_HAFTALIK.get(mevsim, REFERANS_HAFTALIK["kis"])
    oran = son7gun_kwh_m2 / tipik_haftalik if tipik_haftalik else np.nan
    if oran <= 1.05:
        seviye = "TIPIK"
    elif oran <= 1.3:
        seviye = "YUKSEK"
    else:
        seviye = "COK_YUKSEK"
    return {"kural": "lamba_kullanimi", "sera": sera, "mevsim": mevsim,
            "son7gun_kwh_m2": round(son7gun_kwh_m2, 2),
            "referans_haftalik_kwh_m2": tipik_haftalik,
            "oran": round(oran, 2), "seviye": seviye,
            "aksiyon": ("Yok" if seviye == "TIPIK" else
                       "Lamba saatini gozden gecir; ek her 1000 saat sezon boyunca "
                       "~6.98 €/m² elektrik maliyetine karsilik geliyor "
                       "(uretim/Brix katkisi bu orneklemde istatistiksel olarak "
                       "kurulamadi)"),
            "referans": (f"En verimli {en_iyi[0]} ({en_iyi[1]:.3f} €/kg) — "
                        f"en dusuk {en_kotu[0]} ({en_kotu[1]:.3f} €/kg)"),
            "kisit": "Fayda tarafi (uretim/Brix artisi) n=6 ile ANLAMLI DEGIL "
                    "(bkz. Ekonomi raporu Bolum 5, guven araliklari sifiri iceriyor). "
                    "Yalnizca maliyet tarafi kesindir.",
            "guven": "MALIYET_KESIN_FAYDA_BELIRSIZ",
            "kaynak": "ReadMe.pdf lamba formulu + Ekonomi raporu Bolum 5"}


def ornek_calistir(base_dir: Path):
    """Uc kurali GERCEK veriden ornek durumlarla calistirir ve dogrular.

    ONEMLI: ornek zaman noktalari OZENLE secilir. Sezonun SON GUNU (30 Mayis
    00:00) TUM SERALARDA ayni takvim gunudur, bu yuzden (a) 24 saatlik pik
    payi tum seralarda ayni takvim desenini yansitir -- HAVA/TARIFE ORTAK
    OLDUGU ICIN bu beklenen bir durumdur, kural hatasi degildir; (b) 20
    Mayis'tan sonra ALTI SERADA DA lamba tamamen kapali (gunler uzun,
    ek isik gerekmiyor) -- 'son 7 gun kWh' orada anlamsizca sifir cikar.

    Kurallarin GERCEK ayirt ediciligini gostermek icin farkli, anlamli
    zaman noktalari kullanilir:
      Kural 1 (tarife) : sezonun farkli GUNLERI -- pik payi zamanla
                          nasil degisir gosterilir (sabit degildir).
      Kural 2 (CO2)    : sezon sonu (kumulatif dogasi geregi dogru nokta).
      Kural 3 (lamba)  : lambalarin AKTIF oldugu Subat ortasi -- kis
                          donemi, ekonomi raporundaki ana bulgunun geldigi
                          donem.
    """
    m = pd.read_parquet(base_dir / "maliyet_serisi.parquet")
    m["co2_eur"] = m.co2_dos * (5 / 60) * 0.08
    m["saat"] = m.Time.dt.hour
    m["pik"] = (m.saat >= PIK_BAS) & (m.saat < PIK_BIT)

    kayit = []
    for gh, g in m.groupby("greenhouse_id"):
        g = g.set_index("Time").sort_index()

        # --- Kural 1: TUKETIM agirlikli pik payi (zaman orani DEGIL -- o sabittir) ---
        kwh_pik_roll = (g.elek_kWh * g.pik).rolling("24h").sum()
        kwh_top_roll = g.elek_kWh.rolling("24h").sum()
        for tarih in ["2020-01-15", "2020-03-01", "2020-05-01"]:
            an = pd.Timestamp(tarih)
            if an in kwh_top_roll.index and kwh_top_roll.loc[an] > 0.01:
                pay = float(kwh_pik_roll.loc[an] / kwh_top_roll.loc[an])
                r = kural_tarife(pay, gh)
                r["tarih"] = tarih
                kayit.append(r)

        # --- Kural 2: sezon sonu kumulatif (dogasi geregi burasi dogru) ---
        kum_tam = float(g.co2_dos.sum() * 5 / 60)
        r = kural_co2_esik(kum_tam, gun_kalan=0, sera=gh)
        r["tarih"] = "sezon_sonu"
        kayit.append(r)

        # --- Kural 3: kis donemi, TIPIK (medyana yakin) bir hafta ---
        # 17-24 Subat AICU'nun kis medyanina (14.70) en yakin haftadir; ucuk
        # bir hafta (orn. 10-17 Subat, alti-sera ort 20.18 -- kis medyaninin
        # UZERINDE) yerine temsili bir donem secilmistir.
        kis = g["2020-02-17":"2020-02-23 23:55"]   # tam 7 gun (string slice iki ucu da icerir)
        if len(kis):
            son7 = float(kis.elek_kWh.sum())
            r = kural_lamba(son7, gh, mevsim="kis")
            r["tarih"] = "2020-02-17_ile_02-24"
            kayit.append(r)

    d = pd.DataFrame(kayit)
    d.to_csv(base_dir / "dkb_ekonomik_ek.csv", index=False)

    print("=" * 92)
    print("KURAL 1 — TARIFE VERIMLILIGI (sezonun uc farkli gunu)")
    print("  Beklenen: pik payi TAKVIME gore degisir (hava/gun uzunlugu ortak oldugu")
    print("  icin ayni tarihte tum seralar benzer olabilir, ama TARIHLER ARASI degisir)")
    print("=" * 92)
    t1 = d[d.kural == "tarife_verimliligi"]
    print(t1.pivot_table(index="sera", columns="tarih", values="pik_payi_pct").round(1).to_string())

    print("\n" + "=" * 92)
    print("KURAL 2 — CO2 ESIK EGILIMI (sezon sonu kumulatif — bu kuralin dogal noktasi)")
    print("=" * 92)
    print(d[d.kural == "co2_esik_egilimi"][
        ["sera", "kumulatif_kg_m2", "seviye"]
    ].sort_values("kumulatif_kg_m2").to_string(index=False))

    print("\n" + "=" * 92)
    print("KURAL 3 — LAMBA KULLANIMI (17-24 Subat, kis medyanina yakin TIPIK hafta)")
    print("=" * 92)
    print(d[d.kural == "lamba_kullanimi"][
        ["sera", "son7gun_kwh_m2", "oran", "seviye"]
    ].sort_values("son7gun_kwh_m2").to_string(index=False))

    print(f"\nKaydedildi: dkb_ekonomik_ek.csv ({len(d)} satir)")
    return d


if __name__ == "__main__":
    BASE_DIR = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")
    ornek_calistir(BASE_DIR)
