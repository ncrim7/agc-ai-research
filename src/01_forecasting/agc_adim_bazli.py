"""
AGC - ADIM BAZLI HATA CIKARIMI
================================
NEDEN: Sartname "ufka gore hata egrisi" istiyor (t+5dk -> t+6saat). Elimizde:
  - error_by_step.csv       -> yalnizca BASELINE'lar
  - pencere_hatalari.parquet -> ufuk ORTALAMASI (3h/6h), adim bazinda degil

Bu script ayni dogrulanmis checkpoint'lerden tahminleri tekrar cikarir, ama
bu sefer 72 adimin HER BIRI icin ayri hata kaydeder.

ONEMLI: Yeni bir sonuc URETMEZ. Ayni modeller, ayni test pencereleri.
Sadece ozetleme granulerligi degisiyor. Dogrulama olarak, adim bazli
hatalarin ortalamasi = daha once dogrulanan ufuk MAE'sine esit olmali;
script bunu kontrol eder.

BELLEK NOTU: pencere basina 72 adim x N hedef kaydetmek buyuk dosya uretir
(3408 pencere x 72 adim x 5 hedef = 1.2M satir / model). Bu yuzden
PENCERELER UZERINDE ORTALAMA alinir; cikti adim x hedef x model olur.
Boylece dosya kucuk kalir ve egri cizmek icin yeterlidir.
Ek olarak adim bazli standart sapma da kaydedilir (hata bandi cizilebilsin).

ON KOSUL: agc_all_in_one.py exec edilmis olmali.
CIKTI: adim_bazli_hatalar.csv
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

OUTPUT_STEPS = 72
INPUT_STEPS = 288


def _kontrol():
    eksik = [k for k in ["load_arrays", "collect_starts", "compute_norm_stats",
                         "WindowSequence", "get_raw_eval_data", "ANCHOR_BY_TARGET",
                         "DEFAULT_ANCHOR", "RESIDUAL_MODE", "BATCH_SIZE",
                         "MODEL_SIZE", "FEATURE_SETS"] if k not in globals()]
    if eksik:
        raise RuntimeError("Once agc_all_in_one.py'yi exec edin. Eksik: " + ", ".join(eksik))


def _kayit(err_win: np.ndarray, targets, ortak: dict) -> list[dict]:
    """err_win: (n_win, 72, n_tgt) -> adim bazinda ortalama ve std."""
    ort = err_win.mean(axis=0)      # (72, n_tgt)
    std = err_win.std(axis=0)
    n = err_win.shape[0]
    out = []
    for s in range(OUTPUT_STEPS):
        for j, t in enumerate(targets):
            out.append({**ortak, "step": s + 1, "dakika": (s + 1) * 5,
                        "target": t, "MAE": float(ort[s, j]),
                        "std": float(std[s, j]), "n_windows": n})
    return out


def cikar_derin(base_dir: Path, fs_name: str, model_name: str, only_target=None):
    from tensorflow import keras
    g = globals()
    store, target_idx, targets, feature_cols = g["load_arrays"](base_dir, fs_name)
    if only_target is not None:
        target_idx = [feature_cols.index(only_target)]
        targets = [only_target]

    suffix = ("resid" if g["RESIDUAL_MODE"] else "abs") + ("_single" if only_target else "")
    model_tag = f"{model_name}_{suffix}_{g['MODEL_SIZE']}"
    tag = f"{fs_name}_{model_tag}" + (f"_{only_target}" if only_target else "")
    ckpt = base_dir / "checkpoints" / f"{tag}.keras"
    if not ckpt.exists():
        return [], None

    anchor = [g["ANCHOR_BY_TARGET"].get(t, g["DEFAULT_ANCHOR"]) for t in targets]
    tr = g["collect_starts"](store, "train")
    te = g["collect_starts"](store, "test")
    stats = g["compute_norm_stats"](store, tr, target_idx, anchor)

    model = keras.models.load_model(ckpt, safe_mode=False, compile=False)
    seq = g["WindowSequence"](store, te, target_idx, stats, g["BATCH_SIZE"], anchor)
    pred = model.predict(seq, verbose=0) * stats["tgt_std"] + stats["tgt_mean"]
    Y, cipa, _ = g["get_raw_eval_data"](store, te, target_idx, anchor)
    if g["RESIDUAL_MODE"]:
        pred = pred + cipa

    err = np.abs(pred - Y)          # (n_win, 72, n_tgt)
    return _kayit(err, targets, {"feature_set": fs_name, "model": model_tag,
                                 "trained_target": only_target or "ALL",
                                 "kaynak": "derin"}), err


def cikar_baseline(base_dir: Path, fs_name: str):
    g = globals()
    store, target_idx, targets, _ = g["load_arrays"](base_dir, fs_name)
    te = g["collect_starts"](store, "test")
    t_idx = np.array(target_idx)
    n, nt = len(te), len(targets)

    Y = np.empty((n, OUTPUT_STEPS, nt), np.float32)
    son = np.empty((n, nt), np.float32)
    mevs = np.empty((n, OUTPUT_STEPS, nt), np.float32)
    ma = np.empty((n, nt), np.float32)
    trend = np.empty((n, 72, nt), np.float32)

    for i, (gh, s) in enumerate(te):
        f = store[gh]["feats"]; w = f[s:s + INPUT_STEPS]
        Y[i] = f[s + INPUT_STEPS:s + INPUT_STEPS + OUTPUT_STEPS][:, t_idx]
        son[i] = w[-1, t_idx]; mevs[i] = w[:OUTPUT_STEPS][:, t_idx]
        ma[i] = w[-36:][:, t_idx].mean(axis=0); trend[i] = w[-72:][:, t_idx]

    x = np.arange(72, dtype=np.float32); xc = x - x.mean(); d = (xc ** 2).sum()
    ym = trend.mean(axis=1)
    eg = (xc[None, :, None] * (trend - ym[:, None, :])).sum(axis=1) / d
    st = ym + eg * (x[-1] - x.mean())
    il = np.arange(1, OUTPUT_STEPS + 1, dtype=np.float32)

    tahmin = {"persistence": np.repeat(son[:, None, :], OUTPUT_STEPS, axis=1),
              "seasonal_naive": mevs,
              "moving_average": np.repeat(ma[:, None, :], OUTPUT_STEPS, axis=1),
              "linear_trend": st[:, None, :] + eg[:, None, :] * il[None, :, None]}

    kayit = []
    for ad, p in tahmin.items():
        kayit += _kayit(np.abs(p - Y), targets,
                        {"feature_set": fs_name, "model": ad,
                         "trained_target": "ALL", "kaynak": "baseline"})
    return kayit


def calistir(base_dir: Path, feature_sets=("core", "core_grodan"),
             models=("gru", "lstm", "tcn"), single_target=True):
    _kontrol()
    g = globals()
    tum = []

    for fs in feature_sets:
        print(f"=== {fs} / baseline ===")
        tum += cikar_baseline(base_dir, fs)

        _, _, fs_t = g["FEATURE_SETS"][fs]
        for m in models:
            for tgt in [None] + (list(fs_t) if single_target else []):
                k, _ = cikar_derin(base_dir, fs, m, tgt)
                etiket = f"{fs}/{m}/{tgt or 'ALL'}"
                print(f"  {etiket:38s} {'OK' if k else 'CHECKPOINT YOK'}")
                tum += k

    df = pd.DataFrame(tum)
    df.to_csv(base_dir / "adim_bazli_hatalar.csv", index=False)

    # --- DOGRULAMA: adim ortalamasi = ufuk MAE'si olmali ---
    print("\n" + "=" * 74)
    print("DOGRULAMA — adim bazli hatalarin ortalamasi, ufuk MAE'sine esit mi?")
    print("=" * 74)
    ref = base_dir / "pencere_hatalari.parquet"
    if ref.exists():
        p = pd.read_parquet(ref)
        p3 = p[p.horizon == "3h"].groupby(["feature_set", "model", "trained_target", "target"]).abs_error.mean()
        y3 = (df[df.step <= 36].groupby(["feature_set", "model", "trained_target", "target"])
                .apply(lambda s: np.average(s.MAE), include_groups=False))
        ortak = p3.index.intersection(y3.index)
        if len(ortak):
            fark = (y3.loc[ortak] - p3.loc[ortak]).abs() / p3.loc[ortak].abs().clip(lower=1e-12)
            print(f"  Karsilastirilan: {len(ortak)}  |  max bagil fark: {fark.max():.2e}")
            print(f"  {'TUTARLI' if fark.max() < 1e-3 else 'TUTARSIZ — INCELE'}")
    else:
        print("  pencere_hatalari.parquet yok, dogrulama atlandi")

    print(f"\nKaydedildi: adim_bazli_hatalar.csv  ({len(df):,} satir)")
    return df


if __name__ == "__main__":
    BASE_DIR = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")
    calistir(BASE_DIR)
