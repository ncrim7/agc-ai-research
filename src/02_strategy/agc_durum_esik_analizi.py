"""
AGC - DURUM DAGILIMI ve ESIK ANALIZI
======================================
Karar katmani icin gerekli tek veri cekimi.

NEDEN: Eşik kurali yazabilmek icin iki sey bilinmeli:
  1) Degisken hangi araliklarda geziyor (dagilim)
  2) Aday esiklere ne siklikla yaklasiliyor

Hic yaklasilmayan bir esik icin kural yazmak bosunadir.
Surekli asilan bir esik ise alarm yorgunlugu yaratir.

Ayrica gunduz/gece ayrimi kritiktir: sera fizyolojisinde esikler
gun icinde farklidir (gece dusuk sicaklik normal, gunduz degil).

CIKTI:
  durum_dagilimi.csv        - hedef x sera: yuzdelikler, gunduz/gece
  esik_frekanslari.csv      - aday esikler ve asilma yuzdeleri
  gunluk_profil.csv         - saat bazinda ortalama (esik zamanlamasi icin)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HEDEFLER = ["Tair", "Rhair", "CO2air", "HumDef", "Tot_PAR",
            "EC_slab1", "EC_slab2", "WC_slab1", "WC_slab2", "t_slab1", "t_slab2"]

# Aday esikler — bahcecilik literaturunden TASLAK degerler.
# Bu script sadece "ne siklikla yaklasiliyor" sorusunu olcer;
# esiklerin dogrulugu ayrica literaturle teyit edilecektir.
ADAY_ESIK = {
    "Tair":     [("alt_stres", 15, "<"), ("gece_dusuk", 17, "<"),
                 ("ust_uyari", 28, ">"), ("polen_riski", 30, ">")],
    "Rhair":    [("cok_kuru", 60, "<"), ("mantar_uyari", 85, ">"), ("mantar_kritik", 90, ">")],
    "HumDef":   [("terleme_durur", 2.0, "<"), ("su_stresi", 10.0, ">")],
    "CO2air":   [("zenginlestirme_yok", 450, "<"), ("yuksek", 1200, ">")],
    "EC_slab1": [("dusuk", 2.5, "<"), ("tuz_stresi", 6.0, ">"), ("kritik", 7.0, ">")],
    "EC_slab2": [("dusuk", 2.5, "<"), ("tuz_stresi", 6.0, ">"), ("kritik", 7.0, ">")],
    "WC_slab1": [("su_stresi", 50, "<"), ("kritik_kuru", 45, "<"), ("asiri_islak", 85, ">")],
    "WC_slab2": [("su_stresi", 50, "<"), ("kritik_kuru", 45, "<"), ("asiri_islak", 85, ">")],
    "t_slab1":  [("kok_soguk", 15, "<"), ("kok_sicak", 26, ">")],
    "t_slab2":  [("kok_soguk", 15, "<"), ("kok_sicak", 26, ">")],
}


def run(base_dir: Path, gunduz_esigi: float = 20.0):
    f = base_dir / "common_core_with_grodan_strict.parquet"
    if not f.exists():
        raise FileNotFoundError(f"{f} bulunamadi")
    kolonlar = ["Time", "greenhouse_id"] + HEDEFLER + ["Tot_PAR"]
    df = pd.read_parquet(f, columns=list(dict.fromkeys(kolonlar)))
    df["saat"] = df["Time"].dt.hour
    df["gunduz"] = df["Tot_PAR"] > gunduz_esigi
    print(f"Yuklendi: {len(df):,} satir · gunduz orani %{100*df.gunduz.mean():.1f}\n")

    # ---------- 1. Dagilim ----------
    q = [1, 5, 25, 50, 75, 95, 99]
    satir = []
    for h in HEDEFLER:
        if h not in df.columns:
            continue
        for gh, g in df.groupby("greenhouse_id", sort=False):
            for ad, alt in [("tumu", g), ("gunduz", g[g.gunduz]), ("gece", g[~g.gunduz])]:
                s = alt[h].dropna()
                if len(s) < 100:
                    continue
                d = {"hedef": h, "sera": gh, "donem": ad, "n": len(s),
                     "ort": s.mean(), "std": s.std(), "min": s.min(), "max": s.max()}
                d.update({f"p{x}": np.percentile(s, x) for x in q})
                satir.append(d)
    dag = pd.DataFrame(satir)
    dag.round(3).to_csv(base_dir / "durum_dagilimi.csv", index=False)

    print("=" * 88)
    print("1. DURUM DAGILIMI — tum seralar birlikte, gunduz/gece")
    print("=" * 88)
    for ad in ("gunduz", "gece"):
        s = dag[dag.donem == ad].groupby("hedef")[["p1", "p5", "p25", "p50", "p75", "p95", "p99"]].mean()
        print(f"\n--- {ad.upper()} ---")
        print(s.round(2).to_string())

    # ---------- 2. Esik frekanslari ----------
    satir = []
    for h, esikler in ADAY_ESIK.items():
        if h not in df.columns:
            continue
        for ad, deger, yon in esikler:
            for donem, alt in [("tumu", df), ("gunduz", df[df.gunduz]), ("gece", df[~df.gunduz])]:
                s = alt[h].dropna()
                if len(s) < 100:
                    continue
                asim = (s < deger) if yon == "<" else (s > deger)
                satir.append({"hedef": h, "esik_adi": ad, "esik": deger, "yon": yon,
                              "donem": donem, "asilma_%": round(100 * asim.mean(), 2)})
    esik = pd.DataFrame(satir)
    esik.to_csv(base_dir / "esik_frekanslari.csv", index=False)

    print("\n" + "=" * 88)
    print("2. ADAY ESIKLERE ASILMA SIKLIGI")
    print("   %0   -> kural yazmak bosuna (hic olmuyor)")
    print("   >%30 -> alarm yorgunlugu riski (surekli oluyor)")
    print("   %1-15 -> kural yazmaya deger aralik")
    print("=" * 88)
    piv = esik.pivot_table(index=["hedef", "esik_adi", "esik", "yon"],
                           columns="donem", values="asilma_%")
    piv = piv[["tumu", "gunduz", "gece"]]
    piv["degerlendirme"] = np.where(piv["tumu"] < 0.05, "hic olmuyor",
                            np.where(piv["tumu"] > 30, "cok sik",
                            np.where(piv["tumu"] > 1, "KURAL YAZILABILIR", "nadir")))
    print(piv.round(2).to_string())

    # ---------- 3. Gunluk profil ----------
    prof = df.groupby("saat")[[h for h in HEDEFLER if h in df.columns]].mean()
    prof.round(2).to_csv(base_dir / "gunluk_profil.csv")
    print("\n" + "=" * 88)
    print("3. GUNLUK PROFIL — saat bazinda ortalama (esik zamanlamasi icin)")
    print("=" * 88)
    print(prof[["Tair", "Rhair", "HumDef", "CO2air", "WC_slab1", "EC_slab1"]].round(2).to_string())

    print("\nKaydedildi: durum_dagilimi.csv · esik_frekanslari.csv · gunluk_profil.csv")
    return dag, esik, prof


if __name__ == "__main__":
    BASE_DIR = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")
    run(BASE_DIR)
