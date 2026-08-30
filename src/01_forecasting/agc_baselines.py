"""
AGC 2. Edisyon - Hafta 2: Baseline Modelleri
=============================================
5 baseline: Persistence, Seasonal Naive, Moving Average, Linear Trend, Ridge
2 feature-set (core / core_grodan) x 2 degerlendirme (pooled / per_greenhouse)

Cikti:
  all_forecasting_results_long.csv  - ana sonuc tablosu (long format)
  error_by_step.csv                 - adim adim hata egrisi (grafik icin)

TASARIM KARARLARI
-----------------
1) Pencere tensoru MATERIALIZE EDILMIYOR. Sera basina ham dizi kucuk
   (47809 x 46 float32 ~ 9 MB); buyuk olan sey pencerelenmis tensor
   (23298 x 288 x 46 ~ 1.2 GB). Bu yuzden pencere indekslerinden dogrudan
   dilim alip ozet hesapliyoruz, tensoru hic kurmuyoruz.

2) GIRDI tarafindaki NaN: train split'inin sutun ortalamasiyla dolduruluyor
   (sera bazinda hesaplanip o seraya uygulaniyor - val/test'ten bilgi
   sizmiyor). HEDEF tarafinda NaN yok; pencere uretiminde zaten elendi.

3) Ridge girdisi: 288x46 ham pencere DUZLESTIRILMIYOR (overfit riski).
   Her sutun icin 4 ozet (mean/std/son deger/egim) -> 4*n_feature boyut.

4) Seasonal Naive: cikti penceresi t+1..t+72, 24 saat oncesi t-287..t-216,
   yani GIRDI penceresinin ilk 72 adimi. Ekstra veri okumaya gerek yok.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

INPUT_STEPS = 288
OUTPUT_STEPS = 72
H3_STEPS = 36              # 3 saat = ilk 36 adim
MA_WINDOW = 36             # hareketli ortalama: son 3 saat
TREND_WINDOW = 72          # egim tahmini: son 6 saat
RIDGE_ALPHA = 10.0

CORE_TARGETS = ["Tair", "Rhair", "CO2air", "HumDef", "Tot_PAR"]
GRODAN_TARGETS = ["EC_slab1", "EC_slab2", "WC_slab1", "WC_slab2", "t_slab1", "t_slab2"]

FEATURE_SETS = {
    "core": ("common_core_strict.parquet", "window_index_core.csv", CORE_TARGETS),
    # ADIL KARSILASTIRMA icin: core ozniteliklerini GRODAN pencere alt kumesinde
    # degerlendirir. core (568 test penceresi) ve core_grodan (470) FARKLI test
    # setleri kullaniyor (86 saatlik Grodan boslugu son haftayi eliyor), bu yuzden
    # dogrudan karsilastirmak gecersiz. core_matched vs core_grodan AYNI
    # pencerelerde calisir -> "Grodan eklemek ise yariyor mu" sorusunun gecerli testi.
    "core_matched": ("common_core_strict.parquet", "window_index_grodan.csv", CORE_TARGETS),
    "core_grodan": (
        "common_core_with_grodan_strict.parquet",
        "window_index_grodan.csv",
        CORE_TARGETS + GRODAN_TARGETS,
    ),
}


# ----------------------------------------------------------------------
# VERI HAZIRLIK
# ----------------------------------------------------------------------

def prepare_greenhouse_arrays(
    df: pd.DataFrame, windows: pd.DataFrame, targets: list[str]
) -> dict[str, dict]:
    """Sera bazinda: NaN doldur, feature/target dizilerini cikar."""
    feature_cols = [c for c in df.select_dtypes(include=[np.number]).columns]
    store: dict[str, dict] = {}

    for gh, grp in df.groupby("greenhouse_id", sort=False):
        grp = grp.sort_values("Time").reset_index(drop=True)
        w = windows[windows.greenhouse_id == gh]
        if w.empty:
            continue

        # Train split sinirini pencere indeksinden degil, satir sayisindan al
        # (pencere uretimiyle ayni mantik: ilk %70 train)
        n = len(grp)
        train_end = int(n * 0.70)

        feats = grp[feature_cols].to_numpy(dtype=np.float32)
        train_means = np.nanmean(feats[:train_end], axis=0)
        train_means = np.where(np.isnan(train_means), 0.0, train_means)

        # GIRDI NaN doldurma - train ortalamasi ile
        nan_mask = np.isnan(feats)
        feats[nan_mask] = np.take(train_means, np.where(nan_mask)[1])

        target_idx = [feature_cols.index(t) for t in targets]
        store[gh] = {
            "feats": feats,
            "target_idx": target_idx,
            "windows": w.reset_index(drop=True),
            "feature_cols": feature_cols,
        }
    return store


def extract_window_data(
    feats: np.ndarray, target_idx: list[int], starts: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Pencere indekslerinden: girdi ozeti (Ridge icin), hedef trajektorisi,
    ve baseline'lar icin gerekli girdi dilimleri.

    Donen:
      X_summary : (n_win, 4*n_feat)  - mean/std/son/egim
      Y         : (n_win, 72, n_tgt) - gercek cikti
      IN_TGT    : (n_win, 288, n_tgt) yerine sadece gerekli dilimler:
                  ilk 72 (seasonal), son MA_WINDOW (ma), son TREND_WINDOW (trend)
    """
    n_win = len(starts)
    n_feat = feats.shape[1]
    n_tgt = len(target_idx)

    X_summary = np.empty((n_win, 4 * n_feat), dtype=np.float32)
    Y = np.empty((n_win, OUTPUT_STEPS, n_tgt), dtype=np.float32)
    seasonal = np.empty((n_win, OUTPUT_STEPS, n_tgt), dtype=np.float32)
    last_val = np.empty((n_win, n_tgt), dtype=np.float32)
    ma_val = np.empty((n_win, n_tgt), dtype=np.float32)
    trend_slice = np.empty((n_win, TREND_WINDOW, n_tgt), dtype=np.float32)

    t_idx = np.array(target_idx)
    step_axis = np.arange(INPUT_STEPS, dtype=np.float32)
    step_centered = step_axis - step_axis.mean()
    step_var = (step_centered ** 2).sum()

    for i, s in enumerate(starts):
        win = feats[s : s + INPUT_STEPS]                    # (288, n_feat) view
        out = feats[s + INPUT_STEPS : s + INPUT_STEPS + OUTPUT_STEPS]

        X_summary[i, 0:n_feat] = win.mean(axis=0)
        X_summary[i, n_feat : 2 * n_feat] = win.std(axis=0)
        X_summary[i, 2 * n_feat : 3 * n_feat] = win[-1]
        X_summary[i, 3 * n_feat : 4 * n_feat] = (
            (step_centered[:, None] * (win - win.mean(axis=0))).sum(axis=0) / step_var
        )

        Y[i] = out[:, t_idx]
        seasonal[i] = win[:OUTPUT_STEPS][:, t_idx]
        last_val[i] = win[-1, t_idx]
        ma_val[i] = win[-MA_WINDOW:][:, t_idx].mean(axis=0)
        trend_slice[i] = win[-TREND_WINDOW:][:, t_idx]

    return X_summary, Y, (seasonal, last_val, ma_val, trend_slice)


# ----------------------------------------------------------------------
# BASELINE TAHMINLERI
# ----------------------------------------------------------------------

def predict_persistence(last_val: np.ndarray) -> np.ndarray:
    return np.repeat(last_val[:, None, :], OUTPUT_STEPS, axis=1)


def predict_seasonal(seasonal: np.ndarray) -> np.ndarray:
    return seasonal


def predict_moving_average(ma_val: np.ndarray) -> np.ndarray:
    return np.repeat(ma_val[:, None, :], OUTPUT_STEPS, axis=1)


def predict_linear_trend(trend_slice: np.ndarray) -> np.ndarray:
    """Son TREND_WINDOW adima dogru cizgi uydurup ileri uzatir."""
    n_win, w, n_tgt = trend_slice.shape
    x = np.arange(w, dtype=np.float32)
    xc = x - x.mean()
    denom = (xc ** 2).sum()

    y_mean = trend_slice.mean(axis=1)                       # (n_win, n_tgt)
    slope = (xc[None, :, None] * (trend_slice - y_mean[:, None, :])).sum(axis=1) / denom
    intercept_at_end = y_mean + slope * (x[-1] - x.mean())

    future = np.arange(1, OUTPUT_STEPS + 1, dtype=np.float32)
    return intercept_at_end[:, None, :] + slope[:, None, :] * future[None, :, None]


# ----------------------------------------------------------------------
# METRIKLER
# ----------------------------------------------------------------------

def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, targets: list[str], horizon_steps: int) -> list[dict]:
    yt = y_true[:, :horizon_steps, :]
    yp = y_pred[:, :horizon_steps, :]
    err = yp - yt

    mae = np.abs(err).mean(axis=(0, 1))
    rmse = np.sqrt((err ** 2).mean(axis=(0, 1)))
    ss_res = (err ** 2).sum(axis=(0, 1))
    ss_tot = ((yt - yt.mean(axis=(0, 1), keepdims=True)) ** 2).sum(axis=(0, 1))
    r2 = np.where(ss_tot > 0, 1 - ss_res / np.maximum(ss_tot, 1e-12), np.nan)

    rows = []
    for j, tgt in enumerate(targets):
        rows.append({"target": tgt, "MAE": float(mae[j]), "RMSE": float(rmse[j]), "R2": float(r2[j])})
    return rows


def error_curve(y_true: np.ndarray, y_pred: np.ndarray, targets: list[str]) -> list[dict]:
    mae_by_step = np.abs(y_pred - y_true).mean(axis=0)       # (72, n_tgt)
    rows = []
    for step in range(OUTPUT_STEPS):
        for j, tgt in enumerate(targets):
            rows.append({"step": step + 1, "minutes_ahead": (step + 1) * 5,
                         "target": tgt, "MAE": float(mae_by_step[step, j])})
    return rows


# ----------------------------------------------------------------------
# ANA AKIS
# ----------------------------------------------------------------------

def run_feature_set(base_dir: Path, fs_name: str) -> tuple[list[dict], list[dict]]:
    parquet_name, window_name, targets = FEATURE_SETS[fs_name]
    df = pd.read_parquet(base_dir / parquet_name)
    windows = pd.read_csv(base_dir / window_name)

    # core_matched capraz kullanim yapiyor (core parquet + grodan pencereleri).
    # Bu yalnizca iki parquet AYNI satir sirasina sahipse gecerli - dogrula.
    max_needed = int(windows["window_end"].max())
    min_rows = df.groupby("greenhouse_id").size().min()
    if max_needed > min_rows:
        raise ValueError(
            f"{fs_name}: pencere indeksi ({max_needed}) parquet satir sayisini ({min_rows}) asiyor - "
            "iki dosyanin satir sirasi uyusmuyor."
        )

    store = prepare_greenhouse_arrays(df, windows, targets)

    results: list[dict] = []
    curves: list[dict] = []

    # --- Sera bazinda pencere verisini cikar ---
    per_gh: dict[str, dict] = {}
    for gh, d in store.items():
        w = d["windows"]
        parts = {}
        for split in ("train", "test"):
            starts = w.loc[w.split == split, "input_start"].to_numpy()
            if len(starts) == 0:
                continue
            X, Y, extras = extract_window_data(d["feats"], d["target_idx"], starts)
            parts[split] = {"X": X, "Y": Y, "extras": extras}
        per_gh[gh] = parts
        print(f"  {fs_name}/{gh}: train={len(parts.get('train',{}).get('X',[]))} test={len(parts.get('test',{}).get('X',[]))}")

    # --- Analitik baseline'lar (egitim gerektirmez) ---
    baseline_fns = {
        "persistence": lambda ex: predict_persistence(ex[1]),
        "seasonal_naive": lambda ex: predict_seasonal(ex[0]),
        "moving_average": lambda ex: predict_moving_average(ex[2]),
        "linear_trend": lambda ex: predict_linear_trend(ex[3]),
    }

    pooled_true, pooled_pred = {}, {m: [] for m in baseline_fns}
    pooled_true_list = []

    for gh, parts in per_gh.items():
        if "test" not in parts:
            continue
        Y = parts["test"]["Y"]
        pooled_true_list.append(Y)
        for mname, fn in baseline_fns.items():
            pred = fn(parts["test"]["extras"])
            pooled_pred[mname].append(pred)
            for hlabel, hsteps in (("3h", H3_STEPS), ("6h", OUTPUT_STEPS)):
                for r in compute_metrics(Y, pred, targets, hsteps):
                    results.append({"feature_set": fs_name, "eval_mode": "per_greenhouse",
                                    "greenhouse_id": gh, "model": mname,
                                    "horizon": hlabel, **r})

    Y_pooled = np.concatenate(pooled_true_list, axis=0)
    for mname in baseline_fns:
        P = np.concatenate(pooled_pred[mname], axis=0)
        for hlabel, hsteps in (("3h", H3_STEPS), ("6h", OUTPUT_STEPS)):
            for r in compute_metrics(Y_pooled, P, targets, hsteps):
                results.append({"feature_set": fs_name, "eval_mode": "pooled",
                                "greenhouse_id": "ALL", "model": mname,
                                "horizon": hlabel, **r})
        for r in error_curve(Y_pooled, P, targets):
            curves.append({"feature_set": fs_name, "eval_mode": "pooled", "model": mname, **r})

    # --- Ridge: per_greenhouse ---
    for gh, parts in per_gh.items():
        if "train" not in parts or "test" not in parts:
            continue
        pred = fit_predict_ridge(parts["train"], parts["test"], len(targets))
        for hlabel, hsteps in (("3h", H3_STEPS), ("6h", OUTPUT_STEPS)):
            for r in compute_metrics(parts["test"]["Y"], pred, targets, hsteps):
                results.append({"feature_set": fs_name, "eval_mode": "per_greenhouse",
                                "greenhouse_id": gh, "model": "ridge",
                                "horizon": hlabel, **r})

    # --- Ridge: pooled ---
    Xtr = np.concatenate([p["train"]["X"] for p in per_gh.values() if "train" in p], axis=0)
    Ytr = np.concatenate([p["train"]["Y"] for p in per_gh.values() if "train" in p], axis=0)
    Xte = np.concatenate([p["test"]["X"] for p in per_gh.values() if "test" in p], axis=0)
    pred_pooled = fit_predict_ridge({"X": Xtr, "Y": Ytr}, {"X": Xte}, len(targets))

    for hlabel, hsteps in (("3h", H3_STEPS), ("6h", OUTPUT_STEPS)):
        for r in compute_metrics(Y_pooled, pred_pooled, targets, hsteps):
            results.append({"feature_set": fs_name, "eval_mode": "pooled",
                            "greenhouse_id": "ALL", "model": "ridge",
                            "horizon": hlabel, **r})
    for r in error_curve(Y_pooled, pred_pooled, targets):
        curves.append({"feature_set": fs_name, "eval_mode": "pooled", "model": "ridge", **r})

    return results, curves


def fit_predict_ridge(train_part: dict, test_part: dict, n_targets: int) -> np.ndarray:
    """Ozet ozniteliklerden 72xN_target trajektorisini tahmin eder.

    StandardScaler SADECE train'e fit edilir. Sifir varyansli kolonlarda
    sklearn scale_=1.0 kullanir, sifira bolme olmaz (sabit kolon sorunu
    burada patlamaz - bkz. dogrulama kontrol 5).
    """
    Xtr, Ytr = train_part["X"], train_part["Y"]
    Xte = test_part["X"]

    scaler = StandardScaler().fit(Xtr)
    Xtr_s = scaler.transform(Xtr)
    Xte_s = scaler.transform(Xte)

    n_win_tr = Ytr.shape[0]
    Ytr_flat = Ytr.reshape(n_win_tr, -1)

    model = Ridge(alpha=RIDGE_ALPHA)
    model.fit(Xtr_s, Ytr_flat)
    pred_flat = model.predict(Xte_s)
    return pred_flat.reshape(-1, OUTPUT_STEPS, n_targets).astype(np.float32)


def run(base_dir: Path) -> None:
    all_results, all_curves = [], []
    for fs_name in FEATURE_SETS:
        print(f"\n=== {fs_name} ===")
        res, cur = run_feature_set(base_dir, fs_name)
        all_results.extend(res)
        all_curves.extend(cur)

    res_df = pd.DataFrame(all_results)
    cur_df = pd.DataFrame(all_curves)
    res_df.to_csv(base_dir / "all_forecasting_results_long.csv", index=False)
    cur_df.to_csv(base_dir / "error_by_step.csv", index=False)

    print("\n" + "=" * 78)
    print("POOLED SONUCLAR — MAE (dusuk = iyi)")
    print("=" * 78)
    for fs in FEATURE_SETS:
        for h in ("3h", "6h"):
            sub = res_df[(res_df.feature_set == fs) & (res_df.eval_mode == "pooled") & (res_df.horizon == h)]
            if sub.empty:
                continue
            pivot = sub.pivot_table(index="target", columns="model", values="MAE")
            pivot["EN_IYI"] = pivot.idxmin(axis=1)
            print(f"\n--- {fs} / {h} ---")
            print(pivot.round(3).to_string())

    print(f"\nKaydedildi: all_forecasting_results_long.csv ({len(res_df)} satir)")
    print(f"Kaydedildi: error_by_step.csv ({len(cur_df)} satir)")


if __name__ == "__main__":
    BASE_DIR = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")
    run(BASE_DIR)
