"""
AGC 2. Edisyon - Hafta 1 (devam): Pencere Uretimi
====================================================
common_core_strict.parquet / common_core_with_grodan_strict.parquet uzerinden
24 saatlik (288 adim) girdi penceresinden 72 adim (6 saat) cikti penceresi
uretir. Cikti 3h icin ilk 36 adima dilimlenir (ayri egitim YOK - karar gunlugu).

Onemli tasarim kararlari:
- Pencereler MATERIALIZE EDILMIYOR (X/y tensor olarak simdi uretilmiyor) -
  sadece bir INDEKS (input_start/output_start/split) uretiliyor. Gercek array
  cikarma islemi model egitim asamasinda (Hafta 3) yapilacak. Bu, Colab
  bellegini erken doldurmamak icin bilincli bir tercih.
- Her sera KENDI ICINDE ayri islenir (split ve purge sera sinirlarini asmaz).
- Pencere SINIRI (input+output = 360 adim = 30 saat) bir split'in disina
  tasarsa o pencere ATILIR (purge) - train/val/test arasi sizinti onlenir.
- Cikti araliginda (72 adim) hedef kolonlarda NaN varsa pencere ATILIR.
  Girdi tarafinda kalan az sayida NaN (bkz. data_health_report_week1.csv)
  model egitiminde ayrica ele alinacak (impute/mask), burada elenmiyor.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

INPUT_STEPS = 288    # 24 saat (5 dk adimlarla)
OUTPUT_STEPS = 72     # 6 saat -> ilk 36 adim = 3h degerlendirme icin dilimlenir
STRIDE = 12           # 1 saat
TRAIN_FRAC = 0.70
VAL_FRAC = 0.15
# TEST_FRAC = kalan 0.15

CORE_TARGETS = ["Tair", "Rhair", "CO2air", "HumDef", "Tot_PAR"]
GRODAN_TARGETS = ["EC_slab1", "EC_slab2", "WC_slab1", "WC_slab2", "t_slab1", "t_slab2"]


def chronological_split_bounds(n_rows: int) -> dict[str, tuple[int, int]]:
    train_end = int(n_rows * TRAIN_FRAC)
    val_end = train_end + int(n_rows * VAL_FRAC)
    return {
        "train": (0, train_end),
        "val": (train_end, val_end),
        "test": (val_end, n_rows),
    }


def generate_windows_for_greenhouse(df: pd.DataFrame, target_cols: list[str]) -> pd.DataFrame:
    """Tek bir seranin (Time'a gore siralanmis, index sifirlanmis) verisinden pencere kayitlari uretir."""
    n = len(df)
    bounds = chronological_split_bounds(n)
    target_arr = df[target_cols].to_numpy()

    records = []
    last_start = n - (INPUT_STEPS + OUTPUT_STEPS)
    for input_start in range(0, last_start + 1, STRIDE):
        output_start = input_start + INPUT_STEPS
        window_end = output_start + OUTPUT_STEPS  # exclusive

        split_name = None
        for name, (lo, hi) in bounds.items():
            if lo <= input_start < hi:
                split_name = name
                break
        if split_name is None:
            continue

        lo, hi = bounds[split_name]
        if window_end > hi:
            continue  # split sinirini asiyor -> purge

        target_slice = target_arr[output_start:window_end]
        if np.isnan(target_slice).any():
            continue  # cikti araliginda hedef NaN -> pencere gecersiz

        records.append(
            {
                "input_start": input_start,
                "output_start": output_start,
                "window_end": window_end,
                "split": split_name,
            }
        )

    return pd.DataFrame(records)


def build_window_index(df: pd.DataFrame, target_cols: list[str], greenhouse_col: str = "greenhouse_id") -> pd.DataFrame:
    """Pooled df'den, HER SERA ICIN AYRI AYRI pencere uretip birlestirir."""
    all_windows = []
    for gh_id, group in df.groupby(greenhouse_col, sort=False):
        group = group.sort_values("Time").reset_index(drop=True)
        windows = generate_windows_for_greenhouse(group, target_cols)
        windows["greenhouse_id"] = gh_id
        all_windows.append(windows)
    return pd.concat(all_windows, ignore_index=True)


def summarize_windows(window_df: pd.DataFrame, feature_set: str) -> pd.DataFrame:
    summary = (
        window_df.groupby(["greenhouse_id", "split"])
        .size()
        .unstack(fill_value=0)
    )
    for col in ("train", "val", "test"):
        if col not in summary.columns:
            summary[col] = 0
    summary = summary[["train", "val", "test"]]
    summary["total"] = summary.sum(axis=1)
    summary["feature_set"] = feature_set
    return summary.reset_index()


def run(base_dir: Path) -> None:
    core_df = pd.read_parquet(base_dir / "common_core_strict.parquet")
    core_windows = build_window_index(core_df, CORE_TARGETS)
    core_windows.to_csv(base_dir / "window_index_core.csv", index=False)

    grodan_df = pd.read_parquet(base_dir / "common_core_with_grodan_strict.parquet")
    grodan_windows = build_window_index(grodan_df, CORE_TARGETS + GRODAN_TARGETS)
    grodan_windows.to_csv(base_dir / "window_index_grodan.csv", index=False)

    summary = pd.concat(
        [
            summarize_windows(core_windows, "core"),
            summarize_windows(grodan_windows, "core_grodan"),
        ],
        ignore_index=True,
    )
    summary.to_csv(base_dir / "window_generation_summary.csv", index=False)

    print(summary.to_string(index=False))
    print(f"\nToplam CORE penceresi: {len(core_windows)}")
    print(f"Toplam CORE+GRODAN penceresi: {len(grodan_windows)}")


if __name__ == "__main__":
    BASE_DIR = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")
    run(BASE_DIR)
