"""
AGC - Karisik semali sonuc CSV'sini onarir ve karsilastirma tablosunu basar.

SORUN: Eski kosular 9 kolonla yazilmisti; yeni kosular 13 kolon uretti
(model_size, anchor_scheme, l2 eklendi) ve ayni dosyaya BASLIKSIZ eklendi.
pandas okurken "Expected 9 fields, saw 13" hatasi veriyor.
VERI KAYBI YOK - sadece dosya bicimi bozuk.

Bu script satir satir okuyup uzunluga gore gruplar, tek temiz dosya uretir.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

# Yeni surumde eklenen kolonlar, EKLENME SIRASIYLA
EK_KOLONLAR = ["trained_target", "model_size", "anchor_scheme", "l2"]


def onar(csv_path: Path) -> pd.DataFrame:
    with open(csv_path, newline="", encoding="utf-8") as f:
        satirlar = [r for r in csv.reader(f) if r]

    basliklar = [i for i, r in enumerate(satirlar) if r[0] == "feature_set"]
    if not basliklar:
        raise ValueError("Baslik satiri bulunamadi")
    temel = satirlar[basliklar[0]]
    n_temel = len(temel)
    print(f"Temel baslik ({n_temel} kolon): {temel}")

    gruplar: dict[int, list] = {}
    for i, r in enumerate(satirlar):
        if i in basliklar:
            continue
        gruplar.setdefault(len(r), []).append(r)

    parcalar = []
    for uzunluk, rows in sorted(gruplar.items()):
        fazla = uzunluk - n_temel
        kolonlar = temel + EK_KOLONLAR[:fazla] if fazla > 0 else temel[:uzunluk]
        df = pd.DataFrame(rows, columns=kolonlar)
        print(f"  {uzunluk} kolonlu {len(rows):>4} satir -> {kolonlar[n_temel:] or 'ek kolon yok'}")
        parcalar.append(df)

    df = pd.concat(parcalar, ignore_index=True)
    for c in ("MAE", "RMSE", "R2"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in EK_KOLONLAR:
        if c not in df.columns:
            df[c] = None
    # Eski kosularda bu alanlar bostu - gecmise donuk etiketle
    df["model_size"] = df["model_size"].fillna("large")
    df["anchor_scheme"] = df["anchor_scheme"].fillna("all_seasonal_v1")
    df["trained_target"] = df["trained_target"].fillna("ALL")
    return df


def run(base_dir: Path, dosya="deep_model_results_multi.csv"):
    p = base_dir / dosya
    df = onar(p)

    yedek = p.with_suffix(".bozuk.bak")
    p.rename(yedek)
    df.to_csv(p, index=False)
    print(f"\nOnarildi: {len(df)} satir -> {p.name}  (bozuk hali: {yedek.name})")

    # --- Karsilastirma: eski (large + hepsi seasonal) vs yeni (small + hedef bazli cipa) ---
    pooled = df[(df.eval_mode == "pooled") & (df.trained_target == "ALL")]
    for fs in pooled.feature_set.unique():
        for h in ("3h", "6h"):
            sub = pooled[(pooled.feature_set == fs) & (pooled.horizon == h)]
            if sub.empty:
                continue
            print(f"\n{'='*70}\n{fs} / {h} — MAE\n{'='*70}")
            piv = sub.pivot_table(index="target", columns=["model_size", "model"], values="MAE")
            print(piv.round(3).to_string())

    return df


if __name__ == "__main__":
    BASE_DIR = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")
    run(BASE_DIR)
