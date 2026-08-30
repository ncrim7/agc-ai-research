"""
AGC - DOGRULAMALI CIKARIM: pencere basina hata cikarimi
=========================================================
NEDEN GEREKLI: Istatistiksel anlamlilik testleri (Diebold-Mariano, bootstrap)
PENCERE BASINA hata ister. Mevcut CSV'lerimizde yalnizca ORTALAMA metrikler
(MAE, RMSE, R2) var; ortalamadan anlamlilik hesaplanamaz.

YAKLASIM: Kayitli checkpoint'lerden tahmin cikarilir (yeniden EGITIM YOK).
  - ModelCheckpoint(save_best_only=True) en iyi dogrulama epoch'unun
    agirliklarini kaydetti
  - EarlyStopping(restore_best_weights=True) tahmin oncesi ayni agirliklari
    geri yukledi
  => Diskteki dosya, raporlanan MAE'yi ureten modelin BIREBIR kendisidir
  => predict() deterministiktir (dropout inference'ta kapali)

AMA VARSAYIMLA YETINMIYORUZ: her model icin cikarilan pencere hatalarindan
MAE yeniden hesaplanir ve CSV'deki orijinal degerle KARSILASTIRILIR.
  - Eslesirse  -> checkpoint dogrulanmis olur (varsayim degil, kanit)
  - Eslesmezse -> o model YENIDEN EGITILMELI olarak isaretlenir

Bu dogrulama rapora da girer:
  "Pencere basina hatalar kayitli modellerden cikarildi; toplam metrikler
   orijinal kosu degerleriyle 1e-4 bagil toleransta dogrulandi."

ON KOSUL: agc_all_in_one.py bu notebook'ta exec edilmis olmali
          (load_arrays, WindowSequence, compute_norm_stats vb. gerekli).

CIKTI:
  pencere_hatalari.parquet   - anlamlilik testinin girdisi
  cikarim_dogrulama.csv      - her model icin eslesme raporu
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

TOLERANS = 1e-4          # bagil fark; bunun ustu ESLESMEDI sayilir
HORIZONS = (("3h", 36), ("6h", 72))


# ----------------------------------------------------------------------
def _on_kosul_kontrol():
    g = globals()
    gerekli = ["load_arrays", "collect_starts", "compute_norm_stats", "WindowSequence",
               "get_raw_eval_data", "ANCHOR_BY_TARGET", "DEFAULT_ANCHOR",
               "RESIDUAL_MODE", "BATCH_SIZE", "MODEL_SIZE", "FEATURE_SETS"]
    eksik = [k for k in gerekli if k not in g]
    if eksik:
        raise RuntimeError(
            "Once agc_all_in_one.py'yi exec edin. Eksik semboller: " + ", ".join(eksik))


def pencere_bazli_mae(Y_true: np.ndarray, pred: np.ndarray) -> dict:
    """Her pencere icin, her hedef ve ufuk bazinda ortalama mutlak hata.
    Donen: {(horizon_label): (n_win, n_tgt) dizisi}"""
    out = {}
    for hl, hs in HORIZONS:
        out[hl] = np.abs(pred[:, :hs, :] - Y_true[:, :hs, :]).mean(axis=1)
    return out


def _kayitlar(mae_dict, gh_ids, targets, ortak: dict) -> list[dict]:
    kayit = []
    for hl, arr in mae_dict.items():
        for j, t in enumerate(targets):
            for i in range(arr.shape[0]):
                kayit.append({**ortak, "horizon": hl, "target": t,
                              "window_ix": i, "greenhouse_id": gh_ids[i],
                              "abs_error": float(arr[i, j])})
    return kayit


# ----------------------------------------------------------------------
def cikar_derin(base_dir: Path, fs_name: str, model_name: str,
                only_target: str | None) -> tuple[list[dict], dict]:
    """Tek bir checkpoint'ten pencere hatalarini cikarir."""
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
        return [], {"tag": tag, "durum": "CHECKPOINT_YOK"}

    anchor_types = [g["ANCHOR_BY_TARGET"].get(t, g["DEFAULT_ANCHOR"]) for t in targets]
    tr = g["collect_starts"](store, "train")
    te = g["collect_starts"](store, "test")
    stats = g["compute_norm_stats"](store, tr, target_idx, anchor_types)

    model = keras.models.load_model(ckpt, safe_mode=False, compile=False)
    seq = g["WindowSequence"](store, te, target_idx, stats, g["BATCH_SIZE"], anchor_types)
    pred = model.predict(seq, verbose=0) * stats["tgt_std"] + stats["tgt_mean"]

    Y_true, anchor, gh_ids = g["get_raw_eval_data"](store, te, target_idx, anchor_types)
    if g["RESIDUAL_MODE"]:
        pred = pred + anchor

    mae_d = pencere_bazli_mae(Y_true, pred)
    ortak = {"feature_set": fs_name, "model": model_tag,
             "trained_target": only_target or "ALL", "kaynak": "derin"}
    return _kayitlar(mae_d, gh_ids, targets, ortak), {
        "tag": tag, "durum": "OK", "n_windows": len(te),
        "hesaplanan": {(hl, t): float(mae_d[hl][:, j].mean())
                       for hl, _ in HORIZONS for j, t in enumerate(targets)}}


def cikar_baseline(base_dir: Path, fs_name: str) -> tuple[list[dict], dict]:
    """Baseline'lar egitim gerektirmez - dogrudan yeniden hesaplanir."""
    g = globals()
    store, target_idx, targets, _ = g["load_arrays"](base_dir, fs_name)
    te = g["collect_starts"](store, "test")

    INPUT, OUT = 288, 72
    MA_W, TR_W = 36, 72
    t_idx = np.array(target_idx)
    n = len(te)
    Y = np.empty((n, OUT, len(targets)), np.float32)
    son = np.empty((n, len(targets)), np.float32)
    mevs = np.empty((n, OUT, len(targets)), np.float32)
    ma = np.empty((n, len(targets)), np.float32)
    trend = np.empty((n, TR_W, len(targets)), np.float32)
    gh_ids = []

    for i, (gh, s) in enumerate(te):
        f = store[gh]["feats"]
        w = f[s:s + INPUT]
        Y[i] = f[s + INPUT:s + INPUT + OUT][:, t_idx]
        son[i] = w[-1, t_idx]
        mevs[i] = w[:OUT][:, t_idx]
        ma[i] = w[-MA_W:][:, t_idx].mean(axis=0)
        trend[i] = w[-TR_W:][:, t_idx]
        gh_ids.append(gh)
    gh_ids = np.array(gh_ids)

    x = np.arange(TR_W, dtype=np.float32); xc = x - x.mean(); d = (xc ** 2).sum()
    y_ort = trend.mean(axis=1)
    egim = (xc[None, :, None] * (trend - y_ort[:, None, :])).sum(axis=1) / d
    son_t = y_ort + egim * (x[-1] - x.mean())
    ileri = np.arange(1, OUT + 1, dtype=np.float32)

    tahminler = {
        "persistence": np.repeat(son[:, None, :], OUT, axis=1),
        "seasonal_naive": mevs,
        "moving_average": np.repeat(ma[:, None, :], OUT, axis=1),
        "linear_trend": son_t[:, None, :] + egim[:, None, :] * ileri[None, :, None],
    }

    kayit, ozet = [], {}
    for ad, p in tahminler.items():
        mae_d = pencere_bazli_mae(Y, p)
        kayit += _kayitlar(mae_d, gh_ids, targets,
                           {"feature_set": fs_name, "model": ad,
                            "trained_target": "ALL", "kaynak": "baseline"})
        ozet[ad] = {(hl, t): float(mae_d[hl][:, j].mean())
                    for hl, _ in HORIZONS for j, t in enumerate(targets)}
    return kayit, ozet


# ----------------------------------------------------------------------
def dogrula_ve_cikar(base_dir: Path, feature_sets=("core", "core_grodan"),
                     models=("gru", "lstm", "tcn"), single_target=True):
    _on_kosul_kontrol()
    g = globals()

    # Orijinal raporlanan degerler
    ref = []
    for ad in ("deep_model_results_multi.csv", "deep_model_results_single.csv",
               "all_forecasting_results_long.csv"):
        p = base_dir / ad
        if p.exists():
            d = pd.read_csv(p)
            d = d[d.eval_mode == "pooled"]
            if "model_size" in d.columns:
                d = d[(d.model_size == g["MODEL_SIZE"]) | (d.model_size.isna())]
            ref.append(d[["feature_set", "model", "horizon", "target", "MAE"] +
                         (["trained_target"] if "trained_target" in d.columns else [])]
                       .assign(trained_target=d.get("trained_target", "ALL")))
    referans = pd.concat(ref, ignore_index=True) if ref else pd.DataFrame()
    print(f"Referans metrik satiri: {len(referans)}\n")

    tum_kayit, rapor = [], []

    for fs in feature_sets:
        print(f"=== {fs} / baseline'lar ===")
        k, ozet = cikar_baseline(base_dir, fs)
        tum_kayit += k
        for ad, deg in ozet.items():
            for (hl, t), v in deg.items():
                r = referans[(referans.feature_set == fs) & (referans.model == ad) &
                             (referans.horizon == hl) & (referans.target == t)]
                orij = float(r.MAE.iloc[0]) if len(r) else np.nan
                bagil = abs(v - orij) / max(abs(orij), 1e-12) if np.isfinite(orij) else np.nan
                rapor.append({"feature_set": fs, "model": ad, "trained_target": "ALL",
                              "horizon": hl, "target": t, "hesaplanan": round(v, 6),
                              "orijinal": orij, "bagil_fark": bagil,
                              "durum": "ESLESTI" if (np.isfinite(bagil) and bagil < TOLERANS)
                                       else ("REFERANS_YOK" if not np.isfinite(bagil) else "ESLESMEDI")})
        print(f"  {len(k)} kayit\n")

        _, _, fs_targets = g["FEATURE_SETS"][fs]
        hedef_listesi = [None] + (list(fs_targets) if single_target else [])
        for m in models:
            for tgt in hedef_listesi:
                etiket = f"{fs}/{m}" + (f"/{tgt}" if tgt else "/ALL")
                k, meta = cikar_derin(base_dir, fs, m, tgt)
                if meta["durum"] != "OK":
                    print(f"  {etiket:38s} {meta['durum']}")
                    rapor.append({"feature_set": fs, "model": m, "trained_target": tgt or "ALL",
                                  "horizon": "-", "target": "-", "hesaplanan": np.nan,
                                  "orijinal": np.nan, "bagil_fark": np.nan,
                                  "durum": meta["durum"]})
                    continue
                tum_kayit += k
                kotu = 0
                for (hl, t), v in meta["hesaplanan"].items():
                    mt = f"{m}_resid" + ("_single" if tgt else "") + f"_{g['MODEL_SIZE']}"
                    r = referans[(referans.feature_set == fs) & (referans.model == mt) &
                                 (referans.horizon == hl) & (referans.target == t) &
                                 (referans.trained_target == (tgt or "ALL"))]
                    orij = float(r.MAE.iloc[0]) if len(r) else np.nan
                    bagil = abs(v - orij) / max(abs(orij), 1e-12) if np.isfinite(orij) else np.nan
                    d = "ESLESTI" if (np.isfinite(bagil) and bagil < TOLERANS) else \
                        ("REFERANS_YOK" if not np.isfinite(bagil) else "ESLESMEDI")
                    if d == "ESLESMEDI":
                        kotu += 1
                    rapor.append({"feature_set": fs, "model": mt, "trained_target": tgt or "ALL",
                                  "horizon": hl, "target": t, "hesaplanan": round(v, 6),
                                  "orijinal": orij, "bagil_fark": bagil, "durum": d})
                print(f"  {etiket:38s} {'OK' if kotu == 0 else f'{kotu} ESLESMEDI'}")

    hatalar = pd.DataFrame(tum_kayit)
    hatalar.to_parquet(base_dir / "pencere_hatalari.parquet", index=False)
    rap = pd.DataFrame(rapor)
    rap.to_csv(base_dir / "cikarim_dogrulama.csv", index=False)

    print("\n" + "=" * 78)
    print("DOGRULAMA OZETI")
    print("=" * 78)
    print(rap.durum.value_counts().to_string())
    kotu = rap[rap.durum == "ESLESMEDI"]
    if len(kotu):
        print("\nESLESMEYEN MODELLER — bunlar YENIDEN EGITILMELI:")
        print(kotu.groupby(["feature_set", "model", "trained_target"])
                 .bagil_fark.max().sort_values(ascending=False).head(20).to_string())
    else:
        print("\nTUM MODELLER DOGRULANDI.")
        print("Checkpoint'lerden cikarilan pencere hatalari, orijinal kosu")
        print(f"metrikleriyle {TOLERANS} bagil toleransta ortusuyor.")
    yok = rap[rap.durum == "CHECKPOINT_YOK"]
    if len(yok):
        print(f"\nCheckpoint bulunamayan: {len(yok)} model (yeniden egitim gerekir)")

    print(f"\npencere_hatalari.parquet : {len(hatalar):,} satir")
    print(f"cikarim_dogrulama.csv    : {len(rap)} satir")
    return hatalar, rap


if __name__ == "__main__":
    BASE_DIR = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")
    dogrula_ve_cikar(BASE_DIR)
