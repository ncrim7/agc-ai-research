"""
AGC - LOTO BASELINE'LARI
=========================
EKSIK NEDEN OLUSTU: LOTO capraz dogrulamasi yalnizca derin modellerle
kosuldu. Elimizde derin-vs-derin karsilastirmasi var ama "gorulmemis bir
seraya genellerken derin model BASELINE'i geciyor mu?" sorusu cevapsiz.

IKI FARKLI DURUM:

  Analitik baseline'lar (persistence, seasonal_naive, moving_average,
  linear_trend): EGITIM YAPMAZLAR. Yalnizca test penceresinin kendi
  gecmisine bakarlar. Bu yuzden LOTO'da sayilari kronolojik deneyle
  AYNIDIR. Yine de tabloya konmalari gerekir - yoksa LOTO karsilastirmasi
  eksik kalir.

  Ridge: EGITILIR. LOTO protokolunde 5 takimla egitilip 6.'da test
  edilmelidir. Bu GERCEKTEN farkli bir sayi uretir. Asil is budur.

NOT - single-target sorusu: Ridge'in coklu-cikti hali, hedef basina ayri
Ridge ile MATEMATIKSEL OLARAK OZDESTIR (kayip cikti kolonlarina ayrisir,
paylasilan temsil yoktur). Sayisal olarak dogrulandi: fark 0.000e+00.
Analitik baseline'lar da tanimi geregi hedef-basinadir. Bu yuzden
baseline'lar icin ayri bir single-target kosusu GEREKMEZ.

CIKTI: loto_baseline_results.csv — loto_results.csv ile ayni sema,
birlestirilip tek tablo yapilabilir.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

INPUT_STEPS, OUTPUT_STEPS, H3_STEPS = 288, 72, 36
MA_WINDOW, TREND_WINDOW = 36, 72
RIDGE_ALPHA = 10.0
TRAIN_FRAC = 0.70

CORE_TARGETS = ["Tair", "Rhair", "CO2air", "HumDef", "Tot_PAR"]
GRODAN_TARGETS = ["EC_slab1", "EC_slab2", "WC_slab1", "WC_slab2", "t_slab1", "t_slab2"]

FEATURE_SETS = {
    "core": ("common_core_strict.parquet", "window_index_core.csv", CORE_TARGETS),
    "core_grodan": ("common_core_with_grodan_strict.parquet", "window_index_grodan.csv",
                    CORE_TARGETS + GRODAN_TARGETS),
}


# ----------------------------------------------------------------------
def hazirla(base_dir: Path, fs_name: str):
    parquet, window_csv, targets = FEATURE_SETS[fs_name]
    df = pd.read_parquet(base_dir / parquet)
    windows = pd.read_csv(base_dir / window_csv)
    feature_cols = list(df.select_dtypes(include=[np.number]).columns)
    target_idx = [feature_cols.index(t) for t in targets]

    store = {}
    for gh, grp in df.groupby("greenhouse_id", sort=False):
        grp = grp.sort_values("Time").reset_index(drop=True)
        n = len(grp)
        feats = grp[feature_cols].to_numpy(dtype=np.float32)
        ort = np.nanmean(feats[: int(n * TRAIN_FRAC)], axis=0)
        ort = np.where(np.isnan(ort), 0.0, ort)
        m = np.isnan(feats)
        feats[m] = np.take(ort, np.where(m)[1])
        store[gh] = {"feats": feats, "windows": windows[windows.greenhouse_id == gh]}
    return store, target_idx, targets


def pencere_verisi(feats, target_idx, starts):
    """Ozet oznitelikler (Ridge icin) + baseline'lar icin gerekli dilimler."""
    n_win, n_feat, n_tgt = len(starts), feats.shape[1], len(target_idx)
    t_idx = np.array(target_idx)

    X = np.empty((n_win, 4 * n_feat), np.float32)
    Y = np.empty((n_win, OUTPUT_STEPS, n_tgt), np.float32)
    son = np.empty((n_win, n_tgt), np.float32)
    mevsimsel = np.empty((n_win, OUTPUT_STEPS, n_tgt), np.float32)
    ma = np.empty((n_win, n_tgt), np.float32)
    trend = np.empty((n_win, TREND_WINDOW, n_tgt), np.float32)

    adim = np.arange(INPUT_STEPS, dtype=np.float32)
    adim_c = adim - adim.mean()
    adim_var = (adim_c ** 2).sum()

    for i, s in enumerate(starts):
        w = feats[s: s + INPUT_STEPS]
        o = feats[s + INPUT_STEPS: s + INPUT_STEPS + OUTPUT_STEPS]
        X[i, :n_feat] = w.mean(axis=0)
        X[i, n_feat:2 * n_feat] = w.std(axis=0)
        X[i, 2 * n_feat:3 * n_feat] = w[-1]
        X[i, 3 * n_feat:] = (adim_c[:, None] * (w - w.mean(axis=0))).sum(axis=0) / adim_var
        Y[i] = o[:, t_idx]
        son[i] = w[-1, t_idx]
        mevsimsel[i] = w[:OUTPUT_STEPS][:, t_idx]
        ma[i] = w[-MA_WINDOW:][:, t_idx].mean(axis=0)
        trend[i] = w[-TREND_WINDOW:][:, t_idx]
    return X, Y, (mevsimsel, son, ma, trend)


def tahmin_trend(trend_dilim):
    n_win, w, n_tgt = trend_dilim.shape
    x = np.arange(w, dtype=np.float32); xc = x - x.mean(); d = (xc ** 2).sum()
    y_ort = trend_dilim.mean(axis=1)
    egim = (xc[None, :, None] * (trend_dilim - y_ort[:, None, :])).sum(axis=1) / d
    son = y_ort + egim * (x[-1] - x.mean())
    ileri = np.arange(1, OUTPUT_STEPS + 1, dtype=np.float32)
    return son[:, None, :] + egim[:, None, :] * ileri[None, :, None]


def metrikler(y, p, targets, h):
    yt, yp = y[:, :h], p[:, :h]
    e = yp - yt
    mae = np.abs(e).mean(axis=(0, 1))
    rmse = np.sqrt((e ** 2).mean(axis=(0, 1)))
    sr = (e ** 2).sum(axis=(0, 1))
    st = ((yt - yt.mean(axis=(0, 1), keepdims=True)) ** 2).sum(axis=(0, 1))
    r2 = np.where(st > 0, 1 - sr / np.maximum(st, 1e-12), np.nan)
    return [{"target": t, "MAE": float(mae[j]), "RMSE": float(rmse[j]), "R2": float(r2[j])}
            for j, t in enumerate(targets)]


# ----------------------------------------------------------------------
def fold_calistir(base_dir, fs_name, tutulan):
    store, target_idx, targets = hazirla(base_dir, fs_name)
    takimlar = list(store.keys())
    egitim_takimlari = [t for t in takimlar if t != tutulan]

    def topla(takim_listesi, split):
        out = []
        for gh in takim_listesi:
            w = store[gh]["windows"]
            for s in w.loc[w.split == split, "input_start"]:
                out.append((gh, int(s)))
        return out

    tr = topla(egitim_takimlari, "train")
    testler = {"A_hava_gorulmus": topla([tutulan], "train"),
               "B_hava_gorulmemis": topla([tutulan], "test")}
    print(f"  egitim(5 takim)={len(tr)}  testA={len(testler['A_hava_gorulmus'])}  "
          f"testB={len(testler['B_hava_gorulmemis'])}")

    # Ridge'i 5 takimla egit
    Xtr_l, Ytr_l = [], []
    for gh in egitim_takimlari:
        st = [s for g, s in tr if g == gh]
        if st:
            x, y, _ = pencere_verisi(store[gh]["feats"], target_idx, st)
            Xtr_l.append(x); Ytr_l.append(y)
    Xtr = np.concatenate(Xtr_l); Ytr = np.concatenate(Ytr_l)
    sc = StandardScaler().fit(Xtr)
    ridge = Ridge(alpha=RIDGE_ALPHA).fit(sc.transform(Xtr), Ytr.reshape(len(Ytr), -1))

    satirlar = []
    for etiket, starts in testler.items():
        if not starts:
            continue
        st = [s for _, s in starts]
        X, Y, (mevs, son, ma, trend) = pencere_verisi(store[tutulan]["feats"], target_idx, st)

        tahminler = {
            "persistence":    np.repeat(son[:, None, :], OUTPUT_STEPS, axis=1),
            "seasonal_naive": mevs,
            "moving_average": np.repeat(ma[:, None, :], OUTPUT_STEPS, axis=1),
            "linear_trend":   tahmin_trend(trend),
            "ridge":          ridge.predict(sc.transform(X)).reshape(-1, OUTPUT_STEPS, len(targets)),
        }
        for ad, p in tahminler.items():
            for hl, hs in (("3h", H3_STEPS), ("6h", OUTPUT_STEPS)):
                for r in metrikler(Y, p, targets, hs):
                    satirlar.append({"feature_set": fs_name, "model": ad,
                                     "held_out_team": tutulan, "model_size": "baseline",
                                     "test_set": etiket, "horizon": hl,
                                     "n_windows": len(st), **r})
    return satirlar


def run_loto_baselines(base_dir: Path, feature_sets=("core", "core_grodan"), takimlar=None):
    cikti = base_dir / "loto_baseline_results.csv"
    tamam = set()
    if cikti.exists():
        onc = pd.read_csv(cikti)
        tamam = {(r.feature_set, r.held_out_team) for r in onc.itertuples()}
        print(f"Mevcut dosya: {len(onc)} satir, {len(tamam)} fold atlanacak.\n")

    ilk, _, _ = hazirla(base_dir, feature_sets[0])
    tum_takimlar = takimlar or list(ilk.keys())
    plan = [(fs, t) for fs in feature_sets for t in tum_takimlar]
    print(f"Planlanan fold: {len(plan)}\n")

    for i, (fs, t) in enumerate(plan, 1):
        if (fs, t) in tamam:
            print(f"[{i}/{len(plan)}] ATLANDI: {fs} / {t}")
            continue
        print(f"[{i}/{len(plan)}] {fs} / holdout={t}")
        try:
            s = fold_calistir(base_dir, fs, t)
            pd.DataFrame(s).to_csv(cikti, mode="a", header=not cikti.exists(), index=False)
            print(f"  -> {len(s)} satir kaydedildi")
        except Exception as exc:
            print(f"  HATA: {exc}")

    df = pd.read_csv(cikti)
    B = df[(df.test_set == "B_hava_gorulmemis") & (df.horizon == "3h")]
    print("\n" + "=" * 80)
    print("LOTO BASELINE — Test B (durust olcum), 3h, 6 takim ortalamasi")
    print("=" * 80)
    for fs in feature_sets:
        s = B[B.feature_set == fs]
        if s.empty:
            continue
        piv = s.pivot_table(index="target", columns="model", values="MAE")
        piv["EN_IYI"] = piv.idxmin(axis=1)
        print(f"\n--- {fs} ---")
        print(piv.round(3).to_string())
    print(f"\nKaydedildi: {cikti.name}")
    print("Derin model sonuclariyla birlestirmek icin: loto_results.csv ile concat")
    return df


if __name__ == "__main__":
    BASE_DIR = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")
    run_loto_baselines(BASE_DIR)
