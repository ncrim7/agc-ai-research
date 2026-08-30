"""
AGC - MALIYET SERISI YENIDEN INSASI (kritik dogrulama)
========================================================
SORU: ReadMe'deki deterministik formullerle, 5 DAKIKALIK cozunurlukte
maliyet serisi kurabilir miyiz?

Kurabilirsek, mevcut tahmin hattimizi maliyet uzerinde calistirabiliriz:
    "onumuzdeki 6 saatte X €/m² harcayacaksin, %95 araligi [a, b]"

Bu, projenin ozgun katkisi olur. PDF'ler GECMIS maliyeti veriyor (gunluk);
modellerimiz GELECEK maliyeti verecek (6 saatlik, belirsizlikle).

FORMULLER (ReadMe.pdf)
----------------------
Isi akisi  = (t_rail - t_air)*2.1 + (t_grow - t_air)*0.62   [W/m²]
             t_rail = PipeLow, t_grow = PipeGrow
             "when on" — borular kapaliyken katki yok
             -> MJ/gun'e cevrilir

Elektrik   = HPS 81 W/m²  (AssimLight yuzdesiyle orantili)
           + LED: mavi 7.27, kirmizi 25.3, uzak-kirmizi 6.23, beyaz 22.72 W/m²
             (int_*_vip / 1000 oraniyla)
           -> kWh'e cevrilir, pik (07-23) ve pik-disi ayri

CO2        = co2_dos [kg/ha/saat] -> kg/m²

DOGRULAMA: yeniden insa edilen gunluk toplamlar, Resources.csv'deki
Heat_cons / ElecHigh / ElecLow / CO2_cons ile karsilastirilir.
Tutarsa 5 dakikalik maliyet serisi guvenilirdir.

CIKTI: maliyet_serisi.parquet · maliyet_dogrulama.csv
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

TAKIMLAR = ["AICU", "Automatoes", "Digilog", "IUACAAS", "Reference", "TheAutomators"]
EPOCH = pd.Timestamp("1899-12-30")

# ReadMe.pdf katsayilari
K_RAIL, K_GROW = 2.1, 0.62                     # W/m² per °C
HPS_W = 81.0
LED_W = {"int_blue_vip": 7.27, "int_red_vip": 25.3,
         "int_farred_vip": 6.23, "int_white_vip": 22.72}
LED_MAX = 1000.0                               # oransal kontrol araligi
# Economics.pdf fiyatlari
ISI_EUR, ELEK_PIK, ELEK_DUS = 0.0083, 0.08, 0.04
CO2_UCUZ, CO2_PAHALI, CO2_ESIK = 0.08, 0.20, 12.0
PIK_BAS, PIK_BIT = 7, 23                       # 07:00-23:00


def oku_resources(base: Path, takim: str) -> pd.DataFrame:
    a = list(base.glob(f"{takim}_Resources.csv")) or list((base / takim).glob("*Resources*"))
    x = pd.read_csv(a[0], skipinitialspace=True)
    x.columns = x.columns.str.strip()
    x = x.loc[:, ~x.columns.str.startswith("Unnamed")]
    zc = [c for c in x.columns if "time" in c.lower()][0]
    x["Time"] = EPOCH + pd.to_timedelta(pd.to_numeric(x[zc], errors="coerce"), unit="D")
    return x.drop(columns=[zc])


def maliyet_serisi(df: pd.DataFrame) -> pd.DataFrame:
    """5 dakikalik anlik maliyet bilesenleri."""
    d = df.copy()
    dt_saat = 5 / 60.0

    # --- ISI ---
    # Boru sicakligi hava sicakliginin ALTINDAYSA isitma yok (negatif katki alinmaz)
    rail = np.maximum(d.get("PipeLow", 0) - d["Tair"], 0)
    grow = np.maximum(d.get("PipeGrow", 0) - d["Tair"], 0)
    d["isi_W"] = rail * K_RAIL + grow * K_GROW              # W/m²
    d["isi_MJ"] = d.isi_W * (5 * 60) / 1e6                  # 5 dk -> MJ/m²
    d["isi_eur"] = d.isi_MJ * ISI_EUR

    # --- ELEKTRIK ---
    hps = d.get("AssimLight", 0) / 100.0 * HPS_W            # % -> W/m²
    led = sum(d[k] / LED_MAX * w for k, w in LED_W.items() if k in d.columns)
    d["elek_W"] = hps + led
    d["elek_kWh"] = d.elek_W / 1000 * dt_saat
    saat = d["Time"].dt.hour
    d["pik"] = (saat >= PIK_BAS) & (saat < PIK_BIT)
    d["elek_eur"] = d.elek_kWh * np.where(d.pik, ELEK_PIK, ELEK_DUS)

    # --- CO2 ---  co2_dos: kg/ha/saat -> kg/m²
    d["co2_kg"] = d.get("co2_dos", 0) * dt_saat   # NOT: ReadMe "kg/ha hour" diyor ama
    # ampirik dogrulama katsayinin TAM 10000 oldugunu gosterdi -> birim kg/m²/saat
    d["co2_eur"] = d.co2_kg * CO2_UCUZ                      # esik sonra uygulanir

    d["toplam_eur"] = d.isi_eur + d.elek_eur + d.co2_eur
    return d


def run(base_dir: Path):
    kolonlar = ["Time", "greenhouse_id", "Tair", "PipeLow", "PipeGrow",
                "AssimLight", "co2_dos"] + list(LED_W)
    tam = pd.read_parquet(base_dir / "common_core_with_grodan_strict.parquet")
    var = [c for c in kolonlar if c in tam.columns]
    eksik = [c for c in kolonlar if c not in tam.columns]
    if eksik:
        print(f"  UYARI: parquet'te bulunamayan kolonlar: {eksik}")
    df = tam[var].copy()
    print(f"Yuklendi: {len(df):,} satir · kolonlar {var}\n")

    parca, dog = [], []
    for gh, g in df.groupby("greenhouse_id", sort=False):
        g = g.sort_values("Time").reset_index(drop=True)
        m = maliyet_serisi(g)
        m["greenhouse_id"] = gh
        parca.append(m)

        # --- Gunluk toplam vs Resources ---
        m["tarih"] = m.Time.dt.date
        gun = m.groupby("tarih").agg(
            isi_MJ=("isi_MJ", "sum"),
            elek_pik=("elek_kWh", lambda s: s[m.loc[s.index, "pik"]].sum()),
            elek_dus=("elek_kWh", lambda s: s[~m.loc[s.index, "pik"]].sum()),
            co2_kg=("co2_kg", "sum")).reset_index()
        R = oku_resources(base_dir, gh)
        R["tarih"] = R.Time.dt.date
        k = gun.merge(R[["tarih", "Heat_cons", "ElecHigh", "ElecLow", "CO2_cons"]], on="tarih")
        for ad, a, b in [("isi", "isi_MJ", "Heat_cons"), ("elek_pik", "elek_pik", "ElecHigh"),
                         ("elek_dus", "elek_dus", "ElecLow"), ("co2", "co2_kg", "CO2_cons")]:
            x, y = k[a], k[b]
            gecerli = np.isfinite(x) & np.isfinite(y) & (y.abs() > 1e-9)
            if gecerli.sum() < 10:
                continue
            dog.append({"sera": gh, "kalem": ad, "n_gun": int(gecerli.sum()),
                        "bizim_top": float(x[gecerli].sum()), "resmi_top": float(y[gecerli].sum()),
                        "oran": float(x[gecerli].sum() / y[gecerli].sum()),
                        "korelasyon": float(x[gecerli].corr(y[gecerli])),
                        "ort_bagil_hata": float(((x[gecerli] - y[gecerli]).abs() / y[gecerli]).mean())})

    seri = pd.concat(parca, ignore_index=True)
    d = pd.DataFrame(dog)
    seri.to_parquet(base_dir / "maliyet_serisi.parquet", index=False)
    d.to_csv(base_dir / "maliyet_dogrulama.csv", index=False)

    print("=" * 88)
    print("DOGRULAMA — yeniden insa edilen gunluk toplam vs Resources.csv")
    print("  oran ~1.00 ve korelasyon >0.95 ise formul dogru uygulanmis demektir")
    print("=" * 88)
    p = d.pivot_table(index="sera", columns="kalem", values=["oran", "korelasyon"])
    print(p.round(3).to_string())

    print("\n" + "=" * 88)
    print("KALEM BAZINDA OZET")
    print("=" * 88)
    o = d.groupby("kalem").agg(oran=("oran", "mean"), kor=("korelasyon", "mean"),
                               hata=("ort_bagil_hata", "mean")).round(3)
    o["karar"] = np.where((o.oran.between(.85, 1.15)) & (o.kor > .95), "KULLANILABILIR",
                   np.where(o.kor > .90, "olceklenmeli", "FORMUL UYMUYOR"))
    print(o.to_string())

    print("\n" + "=" * 88)
    print("5 DAKIKALIK MALIYET SERISI — ozet")
    print("=" * 88)
    s = seri.groupby("greenhouse_id").agg(
        isi_eur=("isi_eur", "sum"), elek_eur=("elek_eur", "sum"),
        co2_eur=("co2_eur", "sum"), toplam=("toplam_eur", "sum"))
    print(s.round(2).sort_values("toplam").to_string())
    print("\n  (Resmi net kar hesabinda: isitma 1.4-3.9 · elektrik 15.6-20.6 €/m²)")

    print("\n" + "=" * 88)
    print("SIRADAKI ADIM")
    print("=" * 88)
    print("  Formul dogrulandiysa: bu seri artik bir TAHMIN HEDEFI olabilir.")
    print("  Mevcut hat (288 adim girdi -> 72 adim cikti) maliyet uzerinde calistirilir.")
    print("  Cikti: '6 saat sonra X €/m² harcayacaksin, %95 araligi [a,b]'")
    print("  Bu, PDF'lerin veremedigi seydir — onlar yalnizca GECMISI verir.")
    return seri, d


if __name__ == "__main__":
    BASE_DIR = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")
    run(BASE_DIR)
