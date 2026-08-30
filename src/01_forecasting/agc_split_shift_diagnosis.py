"""
AGC 2. Edisyon - Split Dagilim Kaymasi Teshisi
===============================================
NEDEN: Egitim loglarinda val_loss ILK EPOCH'ta zaten train'in ~2.2 kati
(core/gru: loss 0.984 vs val_loss 2.239). Bu overfitting DEGIL - overfitting
epoch'lar boyunca gelisir. Epoch 1'deki fark, val dagiliminin train'den
YAPISAL olarak farkli oldugunu gosterir.

Hipotez: kronolojik bolme tek bir yetistirme sezonunu kesiyor.
  train = 16 Ara - ~1 Nis  (karanlik, surekli isitma, kucuk bitki)
  val   = ~1 Nis - ~1 May
  test  = ~1 May - 30 May  (yuksek radyasyon, buyuk bitki, havalandirma rejimi)

Bu script hipotezi SAYISALLASTIRIR. Cikti dogrudan makaleye tablo olur.

Onemli olcum: "artik olcegi" = |y(t+h) - cipa(t+h)| standart sapmasi.
Model tam olarak bunu ogrenmeye calisiyor. Train'de kucuk, test'te buyukse
model daha kolay bir donemde ogrenip daha zor bir donemde sinava giriyor demektir.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

INPUT_STEPS, OUTPUT_STEPS = 288, 72
CORE_TARGETS = ["Tair", "Rhair", "CO2air", "HumDef", "Tot_PAR"]
GRODAN_TARGETS = ["EC_slab1", "EC_slab2", "WC_slab1", "WC_slab2", "t_slab1", "t_slab2"]


def residual_scale(feats: np.ndarray, starts: np.ndarray, col: int, anchor: str) -> float:
    """Bu split'te 'cipaya gore artik'in standart sapmasi."""
    vals = []
    for s in starts:
        out = feats[s + INPUT_STEPS : s + INPUT_STEPS + OUTPUT_STEPS, col]
        a = feats[s + INPUT_STEPS - 1, col] if anchor == "persistence" else feats[s : s + OUTPUT_STEPS, col]
        vals.append(out - a)
    return float(np.nanstd(np.concatenate([np.atleast_1d(v) for v in vals]))) if vals else np.nan


def run(base_dir: Path, parquet="common_core_with_grodan_strict.parquet",
        window_csv="window_index_grodan.csv"):
    df = pd.read_parquet(base_dir / parquet)
    windows = pd.read_csv(base_dir / window_csv)
    targets = [t for t in CORE_TARGETS + GRODAN_TARGETS if t in df.columns]

    rows_level, rows_resid, rows_time = [], [], []

    for gh, grp in df.groupby("greenhouse_id", sort=False):
        grp = grp.sort_values("Time").reset_index(drop=True)
        feats = grp[targets].to_numpy(dtype=np.float32)
        w = windows[windows.greenhouse_id == gh]

        n = len(grp)
        bounds = {"train": (0, int(n * .70)),
                  "val": (int(n * .70), int(n * .70) + int(n * .15)),
                  "test": (int(n * .70) + int(n * .15), n)}

        for split, (lo, hi) in bounds.items():
            seg = grp.iloc[lo:hi]
            rows_time.append({"greenhouse_id": gh, "split": split,
                              "baslangic": str(seg["Time"].iloc[0])[:10],
                              "bitis": str(seg["Time"].iloc[-1])[:10],
                              "gun": round((seg["Time"].iloc[-1] - seg["Time"].iloc[0]).total_seconds() / 86400, 1)})
            for j, t in enumerate(targets):
                v = feats[lo:hi, j]
                rows_level.append({"greenhouse_id": gh, "split": split, "target": t,
                                   "mean": float(np.nanmean(v)), "std": float(np.nanstd(v))})

            starts = w.loc[w.split == split, "input_start"].to_numpy()
            for j, t in enumerate(targets):
                anchor = "persistence" if t.startswith(("EC_slab", "WC_slab")) else "seasonal"
                rows_resid.append({"greenhouse_id": gh, "split": split, "target": t,
                                   "anchor": anchor,
                                   "artik_std": residual_scale(feats, starts, j, anchor)})

    time_df = pd.DataFrame(rows_time)
    level_df = pd.DataFrame(rows_level)
    resid_df = pd.DataFrame(rows_resid)

    print("=" * 78)
    print("1. SPLIT ZAMAN ARALIKLARI (bir seradan ornek)")
    print("=" * 78)
    print(time_df[time_df.greenhouse_id == time_df.greenhouse_id.iloc[0]].to_string(index=False))

    print("\n" + "=" * 78)
    print("2. HEDEF SEVIYESI — split ortalamasi (6 sera ortalamasi)")
    print("=" * 78)
    piv = level_df.pivot_table(index="target", columns="split", values="mean")[["train", "val", "test"]]
    piv["test/train"] = (piv["test"] / piv["train"]).round(2)
    print(piv.round(2).to_string())

    print("\n" + "=" * 78)
    print("3. ARTIK OLCEGI — model tam olarak BUNU ogreniyor")
    print("   test/train > 1 ise: model kolay donemde ogrenip zor donemde sinava giriyor")
    print("=" * 78)
    pr = resid_df.pivot_table(index=["target", "anchor"], columns="split", values="artik_std")[["train", "val", "test"]]
    pr["val/train"] = (pr["val"] / pr["train"]).round(2)
    pr["test/train"] = (pr["test"] / pr["train"]).round(2)
    print(pr.round(3).to_string())

    out = base_dir / "split_shift_diagnosis.csv"
    resid_df.to_csv(out, index=False)
    level_df.to_csv(base_dir / "split_level_stats.csv", index=False)

    ort = pr["val/train"].mean()
    print("\n" + "=" * 78)
    print(f"ORTALAMA val/train artik olcek orani: {ort:.2f}")
    print("Egitim logundaki val_loss/train_loss ~2.2 ile karsilastir.")
    print("Yakinsa: val_loss yuksekligi OVERFITTING DEGIL, mevsimsel dagilim kaymasidir.")
    print("=" * 78)
    print(f"Kaydedildi: {out}")


if __name__ == "__main__":
    BASE_DIR = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")
    run(BASE_DIR)
