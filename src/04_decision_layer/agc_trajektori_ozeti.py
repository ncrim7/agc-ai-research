"""
AGC - TRAJEKTORI OZETI CIKARIMI
=================================
BACKTEST KUSURUNU DUZELTIR.

SORUN: Backtest'te model TERMINAL degeri tahmin ediyordu (t+6h anindaki
deger), ama gercek-durum PENCERE ICI MAKSIMUM olarak tanimlanmisti.
Uyusmayan karsilastirma.

Kanit (mevcut backtest ciktisi):
    KALITATIF recall   A (terminal<->terminal) 0.689  ->  B 0.425
    SAYISAL   recall   A 0.871                        ->  B 0.787

Recall'daki dusus modelin kotulugunden degil, olcumun tutarsizligindan
geliyordu. SAYISAL daha az etkilendi cunku EC/WC yavas hareket ediyor
(pencere ici max, terminal degere yakin).

COZUM: Modeller zaten 72 adimlik trajektorinin TAMAMINI uretiyor; biz
yalnizca son adimi kaydetmistik. Bu script trajektorinin PENCERE ICI
max/min degerlerini cikarir. Boylece:

    tahmin_max  <-->  gercek_max     (tutarli)
    tahmin_son  <-->  gercek_son     (tutarli)

Her iki tanim da ayri ayri saklanir; backtest ikisini de kullanabilir.

ON KOSUL: agc_all_in_one.py exec edilmis olmali.
SURE: ~25 dakika (val + test, 6 multi + 48 single checkpoint)
CIKTI: trajektori_ozeti.parquet
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ADIM = {"3h": 36, "6h": 72}


def _kontrol():
    eksik = [k for k in ["load_arrays", "collect_starts", "compute_norm_stats",
                         "WindowSequence", "get_raw_eval_data", "ANCHOR_BY_TARGET",
                         "DEFAULT_ANCHOR", "RESIDUAL_MODE", "BATCH_SIZE",
                         "MODEL_SIZE", "FEATURE_SETS"] if k not in globals()]
    if eksik:
        raise RuntimeError("Once agc_all_in_one.py'yi exec edin. Eksik: " + ", ".join(eksik))


def cikar(base_dir: Path, fs_name: str, model_name: str, split: str, only_target=None):
    """Bir checkpoint icin: her pencere x ufuk x hedef -> tahmin ve gercek
    degerlerin pencere ici max / min / son degerleri."""
    from tensorflow import keras
    g = globals()
    store, target_idx, targets, fcols = g["load_arrays"](base_dir, fs_name)
    if only_target is not None:
        if only_target not in targets:
            return None
        target_idx = [fcols.index(only_target)]; targets = [only_target]

    suffix = ("resid" if g["RESIDUAL_MODE"] else "abs") + ("_single" if only_target else "")
    mt = f"{model_name}_{suffix}_{g['MODEL_SIZE']}"
    tag = f"{fs_name}_{mt}" + (f"_{only_target}" if only_target else "")
    ck = base_dir / "checkpoints" / f"{tag}.keras"
    if not ck.exists():
        return None

    anchor = [g["ANCHOR_BY_TARGET"].get(t, g["DEFAULT_ANCHOR"]) for t in targets]
    tr = g["collect_starts"](store, "train")
    st = g["collect_starts"](store, split)
    if not st:
        return None
    stats = g["compute_norm_stats"](store, tr, target_idx, anchor)

    model = keras.models.load_model(ck, safe_mode=False, compile=False)
    seq = g["WindowSequence"](store, st, target_idx, stats, g["BATCH_SIZE"], anchor)
    P = model.predict(seq, verbose=0) * stats["tgt_std"] + stats["tgt_mean"]
    Y, cipa, gh_ids = g["get_raw_eval_data"](store, st, target_idx, anchor)
    if g["RESIDUAL_MODE"]:
        P = P + cipa                       # (n_win, 72, n_tgt)

    kayit = []
    for ad, adim in ADIM.items():
        Pd, Yd = P[:, :adim, :], Y[:, :adim, :]
        for j, t in enumerate(targets):
            for w in range(Y.shape[0]):
                kayit.append({
                    "feature_set": fs_name, "model": mt, "split": split,
                    "horizon": ad, "target": t, "window_ix": w,
                    "greenhouse_id": gh_ids[w],
                    "pred_max": float(Pd[w, :, j].max()),
                    "pred_min": float(Pd[w, :, j].min()),
                    "pred_son": float(Pd[w, -1, j]),
                    "true_max": float(Yd[w, :, j].max()),
                    "true_min": float(Yd[w, :, j].min()),
                    "true_son": float(Yd[w, -1, j]),
                })
    return pd.DataFrame(kayit)


def run(base_dir: Path, feature_sets=("core_grodan",), models=("gru", "lstm", "tcn"),
        single_target=True, splitler=("val", "test")):
    _kontrol()
    g = globals()
    parca = []
    for fs in feature_sets:
        _, _, fs_t = g["FEATURE_SETS"][fs]
        for m in models:
            for tgt in [None] + (list(fs_t) if single_target else []):
                for sp in splitler:
                    d = cikar(base_dir, fs, m, sp, tgt)
                    if d is not None:
                        parca.append(d)
                print(f"  {fs}/{m}/{tgt or 'ALL':10s} tamam")

    if not parca:
        print("Hicbir checkpoint bulunamadi."); return None
    d = pd.concat(parca, ignore_index=True)
    d.to_parquet(base_dir / "trajektori_ozeti.parquet", index=False)

    print("\n" + "=" * 78)
    print("TRAJEKTORI OZETI")
    print("=" * 78)
    print(f"  {len(d):,} satir · {d.model.nunique()} model · {d.target.nunique()} hedef")

    # --- Dogrulama: terminal degerler kalibrasyon dosyasiyla eslesiyor mu? ---
    kp = base_dir / "kalibrasyon_ham.parquet"
    if kp.exists():
        k = pd.read_parquet(kp)
        a = d.groupby(["model", "split", "horizon", "target"]).pred_son.mean()
        b = k.groupby(["model", "split", "horizon", "target"]).y_pred.mean()
        o = a.index.intersection(b.index)
        if len(o):
            f = (a.loc[o] - b.loc[o]).abs() / b.loc[o].abs().clip(lower=1e-9)
            print(f"\n  Kalibrasyon dosyasiyla tutarlilik: {len(o)} ortak, "
                  f"max bagil fark {f.max():.2e}")
            print(f"  {'TUTARLI — ayni modeller' if f.max() < 1e-3 else 'FARKLI — INCELE'}")

    # --- Terminal ile pencere-ici tahmin ne kadar farkli? ---
    t = d[d.split == "test"].copy()
    t["fark_max"] = (t.pred_max - t.pred_son).abs()
    t["fark_true"] = (t.true_max - t.true_son).abs()
    ozet = t.groupby(["horizon", "target"]).agg(
        tahmin_farki=("fark_max", "mean"), gercek_farki=("fark_true", "mean"))
    ozet["oran"] = (ozet.tahmin_farki / ozet.gercek_farki.replace(0, np.nan)).round(2)
    print("\n" + "=" * 78)
    print("PENCERE ICI MAX ile TERMINAL arasindaki fark")
    print("  oran ~1.0 -> model trajektori sekillerini dogru yakaliyor")
    print("  oran <1.0 -> model uc noktalari yeterince tahmin edemiyor (duzlestirme)")
    print("=" * 78)
    print(ozet.round(3).sort_values("oran").to_string())

    print(f"\nKaydedildi: trajektori_ozeti.parquet")
    return d


if __name__ == "__main__":
    BASE_DIR = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")
    run(BASE_DIR)
