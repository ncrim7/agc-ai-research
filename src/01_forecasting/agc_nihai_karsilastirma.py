"""
AGC - NIHAI KARSILASTIRMA TABLOSU
==================================
Uc deneyi birlestirir ve makalede kullanilacak ana tabloyu uretir:

  1. Baseline'lar          -> all_forecasting_results_long.csv
  2. Cok hedefli derin     -> deep_model_results_multi.csv    (trained_target = "ALL")
  3. Hedef basina derin    -> deep_model_results_single.csv   (trained_target = hedef adi)
  4. (varsa) LOTO          -> loto_results.csv

Cevapladigi sorular:
  A) Hedef basina AYRI model egitmek, tek cok-hedefli modelden iyi mi?
     -> "target-specific strategy" iddiasinin DOGRUDAN testi
  B) Her hedef icin nihai kazanan hangi yontem?
  C) Derin ogrenme baseline'i gecen hedeflerde ne kadar geciyor?

KULLANIM:
    karsilastir(BASE_DIR)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def _yukle(base_dir: Path, ad: str) -> pd.DataFrame | None:
    p = base_dir / ad
    if not p.exists():
        print(f"  (yok, atlaniyor: {ad})")
        return None
    try:
        df = pd.read_csv(p)
        print(f"  yuklendi: {ad}  ({len(df)} satir)")
        return df
    except Exception as exc:
        print(f"  HATA {ad}: {exc}")
        return None


def karsilastir(base_dir: Path, model_size: str = "small") -> pd.DataFrame:
    print("Dosyalar okunuyor:")
    baseline = _yukle(base_dir, "all_forecasting_results_long.csv")
    multi = _yukle(base_dir, "deep_model_results_multi.csv")
    single = _yukle(base_dir, "deep_model_results_single.csv")

    parcalar = []

    if baseline is not None:
        b = baseline[baseline.eval_mode == "pooled"].copy()
        b["yontem_ailesi"] = "baseline"
        b["egitim_modu"] = "-"
        parcalar.append(b[["feature_set", "horizon", "target", "model",
                           "MAE", "RMSE", "R2", "yontem_ailesi", "egitim_modu"]])

    for df, mod in ((multi, "cok_hedefli"), (single, "hedef_basina")):
        if df is None:
            continue
        d = df[df.eval_mode == "pooled"].copy()
        if "model_size" in d.columns:
            d = d[d.model_size == model_size]
        d["yontem_ailesi"] = "derin"
        d["egitim_modu"] = mod
        parcalar.append(d[["feature_set", "horizon", "target", "model",
                           "MAE", "RMSE", "R2", "yontem_ailesi", "egitim_modu"]])

    if not parcalar:
        print("Hicbir sonuc dosyasi bulunamadi.")
        return pd.DataFrame()

    tum = pd.concat(parcalar, ignore_index=True)
    tum["MAE"] = pd.to_numeric(tum["MAE"], errors="coerce")
    tum = tum.dropna(subset=["MAE"])

    # ---- A) Hedef basina vs cok hedefli ----
    if single is not None and multi is not None:
        print("\n" + "=" * 84)
        print("A) HEDEF BASINA AYRI MODEL vs TEK COK-HEDEFLI MODEL")
        print("   Negatif % = hedef basina egitmek DAHA IYI")
        print("=" * 84)
        d = tum[tum.yontem_ailesi == "derin"]
        # mimari adini cikar (gru/lstm/tcn)
        d = d.assign(mimari=d.model.str.split("_").str[0])
        piv = d.pivot_table(index=["feature_set", "horizon", "target", "mimari"],
                            columns="egitim_modu", values="MAE")
        if {"cok_hedefli", "hedef_basina"}.issubset(piv.columns):
            piv["fark_%"] = ((piv["hedef_basina"] - piv["cok_hedefli"])
                             / piv["cok_hedefli"] * 100).round(1)
            for mim in sorted(d.mimari.unique()):
                s = piv.xs(mim, level="mimari")
                ort = s["fark_%"].mean()
                kazanan = "hedef_basina" if ort < 0 else "cok_hedefli"
                print(f"\n--- {mim.upper()} --- ortalama fark {ort:+.1f}%  -> {kazanan} onde")
                print(s.round(3).to_string())

            genel = piv["fark_%"].mean()
            print("\n" + "-" * 84)
            print(f"GENEL: hedef basina egitim, cok hedefliye gore {genel:+.1f}%")
            print("  (negatifse 'target-specific strategy' iddiasi DOGRUDAN desteklenir)")

    # ---- B) Nihai kazanan tablosu ----
    print("\n" + "=" * 84)
    print("B) NIHAI TABLO — her hedef icin en iyi yontem")
    print("=" * 84)
    satirlar = []
    for (fs, h, t), grp in tum.groupby(["feature_set", "horizon", "target"]):
        bl = grp[grp.yontem_ailesi == "baseline"]
        dl = grp[grp.yontem_ailesi == "derin"]
        if bl.empty or dl.empty:
            continue
        eb, ed = bl.loc[bl.MAE.idxmin()], dl.loc[dl.MAE.idxmin()]
        satirlar.append({
            "feature_set": fs, "horizon": h, "target": t,
            "en_iyi_baseline": eb.model, "baseline_MAE": round(eb.MAE, 3),
            "en_iyi_derin": ed.model, "derin_MAE": round(ed.MAE, 3),
            "derin_egitim": ed.egitim_modu,
            "kazanan": "DERIN" if ed.MAE < eb.MAE else "baseline",
            "kazanc_%": round((eb.MAE - ed.MAE) / eb.MAE * 100, 1),
        })
    nihai = pd.DataFrame(satirlar)
    for fs in nihai.feature_set.unique():
        for h in ["3h", "6h"]:
            s = nihai[(nihai.feature_set == fs) & (nihai.horizon == h)]
            if s.empty:
                continue
            print(f"\n--- {fs} / {h} ---")
            print(s.drop(columns=["feature_set", "horizon"])
                   .sort_values("kazanc_%", ascending=False).to_string(index=False))

    print("\n" + "=" * 84)
    print("C) OZET")
    print("=" * 84)
    print(nihai.kazanan.value_counts().to_string())
    kaz = nihai[nihai.kazanan == "DERIN"]
    if not kaz.empty:
        print(f"\nDerin ogrenmenin kazandigi {len(kaz)} durumda ortalama kazanc: "
              f"{kaz['kazanc_%'].mean():.1f}%  (medyan {kaz['kazanc_%'].median():.1f}%)")
        print("\nEn buyuk 5 kazanc:")
        print(kaz.nlargest(5, "kazanc_%")[["feature_set","horizon","target",
                                           "en_iyi_derin","kazanc_%"]].to_string(index=False))
    kayip = nihai[nihai.kazanan == "baseline"]
    if not kayip.empty:
        print(f"\nBaseline'in kazandigi {len(kayip)} durumda ortalama fark: "
              f"{-kayip['kazanc_%'].mean():.1f}%")

    cikti = base_dir / "nihai_karsilastirma.csv"
    nihai.to_csv(cikti, index=False)
    tum.to_csv(base_dir / "tum_sonuclar_birlesik.csv", index=False)
    print(f"\nKaydedildi: {cikti.name} ve tum_sonuclar_birlesik.csv")
    return nihai


if __name__ == "__main__":
    BASE_DIR = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")
    karsilastir(BASE_DIR)
