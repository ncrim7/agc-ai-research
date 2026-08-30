"""
AGC - EKSIKLERI TAMAMLAMA
===========================
Raporun iki bilinen eksigini kapatir:

EKSIK 1 (Ek F.3) — Ridge anlamlilik testinde yok
  Anlamlilik testi pencere basina hata degerlerine ihtiyac duyar. Ridge icin
  bu degerler cikarilmamisti, bu yuzden Ridge'in en iyi baseline oldugu 10
  karsilastirma test edilememisti. Bu script Ridge'i egitip pencere basina
  hatalarini uretir.

EKSIK 2 (Ek F.4) — hedef basina modellerin RMSE ve R2 degerleri yok
  Onceki cikarim yalnizca mutlak hata (MAE icin) kaydediyordu. Bu script
  ayni checkpoint'lerden RMSE ve R2 de hesaplar; boylece TUM modeller tek
  ve dogrulanmis kaynaktan raporlanabilir.

ON KOSUL: agc_all_in_one.py bu notebook'ta exec edilmis olmali.

SURE: ~25 dakika (48 single + 6 multi checkpoint yuklemesi + Ridge egitimi)

CIKTI:
  pencere_hatalari_v2.parquet  - Ridge dahil, pencere basina hatalar
  metrikler_tam.csv            - TUM modeller icin MAE + RMSE + R2
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

INPUT_STEPS, OUTPUT_STEPS = 288, 72
HORIZONS = (("3h", 36), ("6h", 72))
MA_W, TREND_W, RIDGE_ALPHA = 36, 72, 10.0


def _kontrol():
    eksik = [k for k in ["load_arrays", "collect_starts", "compute_norm_stats",
                         "WindowSequence", "get_raw_eval_data", "ANCHOR_BY_TARGET",
                         "DEFAULT_ANCHOR", "RESIDUAL_MODE", "BATCH_SIZE",
                         "MODEL_SIZE", "FEATURE_SETS"] if k not in globals()]
    if eksik:
        raise RuntimeError("Once agc_all_in_one.py'yi exec edin. Eksik: " + ", ".join(eksik))


def _metrikler(Y, P, targets, ortak):
    """Pencere basina mutlak hata + toplam MAE/RMSE/R2."""
    kayit, ozet = [], []
    for hl, hs in HORIZONS:
        yt, yp = Y[:, :hs, :], P[:, :hs, :]
        err = yp - yt
        pw = np.abs(err).mean(axis=1)                       # (n_win, n_tgt)
        mae = np.abs(err).mean(axis=(0, 1))
        rmse = np.sqrt((err ** 2).mean(axis=(0, 1)))
        sr = (err ** 2).sum(axis=(0, 1))
        st = ((yt - yt.mean(axis=(0, 1), keepdims=True)) ** 2).sum(axis=(0, 1))
        r2 = np.where(st > 0, 1 - sr / np.maximum(st, 1e-12), np.nan)
        for j, t in enumerate(targets):
            ozet.append({**ortak, "horizon": hl, "target": t,
                         "MAE": float(mae[j]), "RMSE": float(rmse[j]), "R2": float(r2[j])})
            for i in range(pw.shape[0]):
                kayit.append({**ortak, "horizon": hl, "target": t, "window_ix": i,
                              "abs_error": float(pw[i, j])})
    return kayit, ozet


def _pencere_dilimleri(feats, t_idx, starts):
    n, nf, nt = len(starts), feats.shape[1], len(t_idx)
    X = np.empty((n, 4 * nf), np.float32)
    Y = np.empty((n, OUTPUT_STEPS, nt), np.float32)
    adim = np.arange(INPUT_STEPS, dtype=np.float32)
    ac = adim - adim.mean(); av = (ac ** 2).sum()
    for i, s in enumerate(starts):
        w = feats[s:s + INPUT_STEPS]
        X[i, :nf] = w.mean(axis=0)
        X[i, nf:2 * nf] = w.std(axis=0)
        X[i, 2 * nf:3 * nf] = w[-1]
        X[i, 3 * nf:] = (ac[:, None] * (w - w.mean(axis=0))).sum(axis=0) / av
        Y[i] = feats[s + INPUT_STEPS:s + INPUT_STEPS + OUTPUT_STEPS][:, t_idx]
    return X, Y


# ----------------------------------------------------------------------
def ridge_cikar(base_dir: Path, fs_name: str):
    """EKSIK 1: Ridge'i egitip pencere basina hatalarini uretir.
    agc_baselines.py ile AYNI kurulum: 4 ozet oznitelik, train-only scaler, alpha=10."""
    g = globals()
    store, target_idx, targets, _ = g["load_arrays"](base_dir, fs_name)
    t_idx = np.array(target_idx)

    Xtr_l, Ytr_l = [], []
    for gh, d in store.items():
        st = d["windows"].loc[d["windows"].split == "train", "input_start"].to_numpy()
        if len(st):
            x, y = _pencere_dilimleri(d["feats"], t_idx, st)
            Xtr_l.append(x); Ytr_l.append(y)
    Xtr = np.concatenate(Xtr_l); Ytr = np.concatenate(Ytr_l)
    sc = StandardScaler().fit(Xtr)
    mdl = Ridge(alpha=RIDGE_ALPHA).fit(sc.transform(Xtr), Ytr.reshape(len(Ytr), -1))

    te = g["collect_starts"](store, "test")
    Xte_l, Yte_l, gh_ids = [], [], []
    for gh, d in store.items():
        st = [s for ghx, s in te if ghx == gh]
        if st:
            x, y = _pencere_dilimleri(d["feats"], t_idx, st)
            Xte_l.append(x); Yte_l.append(y); gh_ids += [gh] * len(st)
    X, Y = np.concatenate(Xte_l), np.concatenate(Yte_l)
    P = mdl.predict(sc.transform(X)).reshape(-1, OUTPUT_STEPS, len(targets)).astype(np.float32)

    k, o = _metrikler(Y, P, targets, {"feature_set": fs_name, "model": "ridge",
                                      "trained_target": "ALL", "kaynak": "baseline"})
    for kk, gh in zip([x for x in k if x["horizon"] == "3h"][:0] or [], []):
        pass
    # greenhouse_id ekle
    nwin = len(gh_ids)
    for rec in k:
        rec["greenhouse_id"] = gh_ids[rec["window_ix"] % nwin]
    return k, o


def derin_cikar(base_dir: Path, fs_name: str, model_name: str, only_target=None):
    """EKSIK 2: ayni checkpoint'ten MAE + RMSE + R2 birlikte."""
    from tensorflow import keras
    g = globals()
    store, target_idx, targets, fcols = g["load_arrays"](base_dir, fs_name)
    if only_target is not None:
        target_idx = [fcols.index(only_target)]; targets = [only_target]

    suffix = ("resid" if g["RESIDUAL_MODE"] else "abs") + ("_single" if only_target else "")
    mt = f"{model_name}_{suffix}_{g['MODEL_SIZE']}"
    tag = f"{fs_name}_{mt}" + (f"_{only_target}" if only_target else "")
    ck = base_dir / "checkpoints" / f"{tag}.keras"
    if not ck.exists():
        return [], [], None

    anchor = [g["ANCHOR_BY_TARGET"].get(t, g["DEFAULT_ANCHOR"]) for t in targets]
    tr = g["collect_starts"](store, "train"); te = g["collect_starts"](store, "test")
    stats = g["compute_norm_stats"](store, tr, target_idx, anchor)
    mdl = keras.models.load_model(ck, safe_mode=False, compile=False)
    seq = g["WindowSequence"](store, te, target_idx, stats, g["BATCH_SIZE"], anchor)
    P = mdl.predict(seq, verbose=0) * stats["tgt_std"] + stats["tgt_mean"]
    Y, cipa, gh_ids = g["get_raw_eval_data"](store, te, target_idx, anchor)
    if g["RESIDUAL_MODE"]:
        P = P + cipa

    k, o = _metrikler(Y, P, targets, {"feature_set": fs_name, "model": mt,
                                      "trained_target": only_target or "ALL", "kaynak": "derin"})
    for rec in k:
        rec["greenhouse_id"] = gh_ids[rec["window_ix"]]
    return k, o, mt


def calistir(base_dir: Path, feature_sets=("core", "core_grodan"),
             models=("gru", "lstm", "tcn"), single_target=True):
    _kontrol()
    g = globals()
    kayit, ozet = [], []

    for fs in feature_sets:
        print(f"=== {fs} ===")
        print("  ridge (eksik 1) ...", end=" ", flush=True)
        k, o = ridge_cikar(base_dir, fs)
        kayit += k; ozet += o; print("OK")

        _, _, fs_t = g["FEATURE_SETS"][fs]
        for m in models:
            for tgt in [None] + (list(fs_t) if single_target else []):
                k, o, mt = derin_cikar(base_dir, fs, m, tgt)
                etiket = f"{m}/{tgt or 'ALL'}"
                print(f"  {etiket:22s} {'OK' if mt else 'CHECKPOINT YOK'}")
                kayit += k; ozet += o

    h = pd.DataFrame(kayit)
    z = pd.DataFrame(ozet)
    h.to_parquet(base_dir / "pencere_hatalari_v2.parquet", index=False)
    z.to_csv(base_dir / "metrikler_tam.csv", index=False)

    print("\n" + "=" * 70)
    print("TAMAMLANDI")
    print("=" * 70)
    print(f"  pencere_hatalari_v2.parquet : {len(h):,} satır  (Ridge DAHİL)")
    print(f"  metrikler_tam.csv           : {len(z):,} satır  (MAE + RMSE + R2)")
    print(f"\n  Modeller: {sorted(z.model.unique())}")

    # Tutarlilik: eski parquet ile ortak modellerde MAE eslesiyor mu?
    eski = base_dir / "pencere_hatalari.parquet"
    if eski.exists():
        e = pd.read_parquet(eski)
        a = h.groupby(["feature_set", "model", "trained_target", "horizon", "target"]).abs_error.mean()
        b = e.groupby(["feature_set", "model", "trained_target", "horizon", "target"]).abs_error.mean()
        o2 = a.index.intersection(b.index)
        if len(o2):
            f = (a.loc[o2] - b.loc[o2]).abs() / b.loc[o2].abs().clip(lower=1e-12)
            print(f"\n  Eski parquet ile tutarlilik: {len(o2)} ortak, max bagil fark {f.max():.2e}")
            print(f"  {'TUTARLI — ayni modeller' if f.max() < 1e-3 else 'FARKLI — INCELE'}")
    return h, z


if __name__ == "__main__":
    BASE_DIR = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")
    calistir(BASE_DIR)
