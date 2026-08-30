"""
AGC - HAVA TAHMINI UST SINIRI (Oracle deneyi)
===============================================
SORU: Hatamizin ne kadari GELECEK HAVAYI BILMEMEKTEN geliyor?

Model su an yalnizca GECMIS havayi goruyor. Gercek kullanimda meteoroloji
tahmini mevcut olur. "Mukemmel hava tahmini verilseydi hata ne olurdu"
sorusunun cevabi, hatayi iki bilesene ayirir:

    toplam hata = (hava bilinmezligi) + (sera dinamiginin icsel belirsizligi)

Bu ayristirma iki sey saglar:
  1) Gercek kullanimda ne kadar iyilesme beklenebilecegini soyler
  2) Kalibrasyon bozulmasinin sebebini test eder — Mayis'ta hava
     degiskenligi artiyorsa ve hata buyuk olcude havadan geliyorsa,
     kalibrasyonun Mayis'ta bozulmasi aciklanmis olur

ADIL KARSILASTIRMA TASARIMI
----------------------------
Iki model de 360 adimlik girdi alir; MIMARI BIREBIR AYNIDIR:

    adim   0-287 : gecmis — tum sensorler (her iki modelde de ayni)
    adim 288-359 : gelecek penceresi
                     TEMEL  : tamamen sifir
                     KAHIN  : yalnizca HAVA kanallari dolu,
                              sera degiskenleri sifir

Ek olarak bir "gelecek mi" gostergesi kanali eklenir (0/1), boylece model
iki bolgeyi ayirt edebilir.

Tek fark BILGIDIR, kapasite veya mimari degil. Bu yuzden aradaki fark
dogrudan "gelecek havayi bilmenin degeri" olarak yorumlanabilir.

NOT: Bu bir UST SINIRDIR. Gercek meteoroloji tahmini mukemmel degildir;
gercek kazanc bu degerin altinda kalir.

ON KOSUL: agc_all_in_one.py exec edilmis olmali.
SURE: model basina ~10 dk. Varsayilan 2 model x 2 varyant = ~40 dk.
CIKTI: hava_oracle_sonuclari.csv
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers

GECMIS, GELECEK = 288, 72
TOPLAM = GECMIS + GELECEK
HORIZONS = (("3h", 36), ("6h", 72))

# Weather.csv kaynakli kolonlar (dis ortam). Auto-tespit icin aday liste;
# yalnizca veride MEVCUT olanlar kullanilir.
HAVA_ADAYLARI = ["Tout", "Rhout", "Iglob", "Windsp", "Winddir", "Rain",
                 "RadSum", "PARout", "AbsHumOut", "Pyrgeo", "Tsky"]


def _g():
    eksik = [k for k in ["load_arrays", "collect_starts", "ANCHOR_BY_TARGET",
                         "DEFAULT_ANCHOR", "RESIDUAL_MODE", "BATCH_SIZE", "SIZE_PRESETS",
                         "MODEL_SIZE", "FEATURE_SETS", "L2_REG", "build_anchor",
                         "EPOCHS", "PATIENCE", "LEARNING_RATE", "SEED"] if k not in globals()]
    if eksik:
        raise RuntimeError("Once agc_all_in_one.py'yi exec edin. Eksik: " + ", ".join(eksik))
    return globals()


# ----------------------------------------------------------------------
class OracleSequence(keras.utils.Sequence):
    """360 adimlik girdi. Son 72 adim: kahin ise hava dolu, temel ise sifir."""

    def __init__(self, store, starts, target_idx, hava_idx, stats, batch,
                 anchor_types, kahin: bool, shuffle=False):
        self.store, self.starts = store, list(starts)
        self.t_idx = np.array(target_idx)
        self.h_idx = np.array(hava_idx, dtype=int)
        self.stats, self.batch = stats, batch
        self.anchor_types, self.kahin = anchor_types, kahin
        self.shuffle = shuffle
        self.rng = np.random.default_rng(_g()["SEED"])
        self.n_feat = store[self.starts[0][0]]["feats"].shape[1]
        self.on_epoch_end()

    def __len__(self):
        return int(np.ceil(len(self.starts) / self.batch))

    def on_epoch_end(self):
        if self.shuffle:
            self.rng.shuffle(self.starts)

    def __getitem__(self, i):
        b = self.starts[i * self.batch:(i + 1) * self.batch]
        X = np.zeros((len(b), TOPLAM, self.n_feat + 1), np.float32)
        Y = np.empty((len(b), GELECEK, len(self.t_idx)), np.float32)
        fm, fs = self.stats["feat_mean"], self.stats["feat_std"]

        for k, (gh, s) in enumerate(b):
            f = self.store[gh]["feats"]
            gec = f[s:s + GECMIS]
            X[k, :GECMIS, :self.n_feat] = (gec - fm) / fs
            if self.kahin:
                gel = f[s + GECMIS:s + GECMIS + GELECEK]
                z = (gel - fm) / fs
                # Yalnizca hava kanallari; sera degiskenleri sifir kalir.
                # NOT: X[k, GECMIS:, h_idx] yazimi numpy'da eksen sirasini
                # degistirir ((3,72) bekler), bu yuzden once dilim alinip
                # sonra fancy index uygulanir.
                X[k, GECMIS:, :self.n_feat][:, self.h_idx] = z[:, self.h_idx]
            X[k, GECMIS:, -1] = 1.0                      # "gelecek mi" gostergesi

            out = f[s + GECMIS:s + GECMIS + GELECEK][:, self.t_idx]
            if _g()["RESIDUAL_MODE"]:
                Y[k] = out - _g()["build_anchor"](gec, self.t_idx, self.anchor_types)
            else:
                Y[k] = out
        Y = (Y - self.stats["tgt_mean"]) / self.stats["tgt_std"]
        return X, Y


def kur_model(mimari: str, n_feat: int, n_tgt: int, cfg: dict):
    """agc_all_in_one'daki mimarilerin 360 adimlik girdi alan hali."""
    reg = keras.regularizers.l2(_g()["L2_REG"])
    inp = keras.Input((TOPLAM, n_feat))

    def kafa(x, bott):
        x = layers.Dense(bott, activation="relu", kernel_regularizer=reg)(x)
        x = layers.Dense(GELECEK * n_tgt, kernel_regularizer=reg)(x)
        return layers.Reshape((GELECEK, n_tgt))(x)

    if mimari in ("gru", "lstm"):
        K = layers.GRU if mimari == "gru" else layers.LSTM
        x = K(cfg["rnn_units"], dropout=cfg["dropout"], kernel_regularizer=reg)(inp)
        return keras.Model(inp, kafa(x, cfg["rnn_units"]), name=mimari)

    f = cfg["tcn_filters"]
    x = layers.Conv1D(f, 1, padding="same", kernel_regularizer=reg)(inp)
    for d in cfg["tcn_dilations"]:
        prev = x
        x = layers.Conv1D(f, 3, padding="causal", dilation_rate=d,
                          activation="relu", kernel_regularizer=reg)(x)
        x = layers.Dropout(cfg["dropout"])(x)
        x = layers.Conv1D(f, 3, padding="causal", dilation_rate=d,
                          activation="relu", kernel_regularizer=reg)(x)
        x = layers.Add()([prev, x])
    x = layers.Lambda(lambda t: t[:, -1, :])(x)
    return keras.Model(inp, kafa(x, f), name="tcn")


def norm_stats(store, starts, target_idx, anchor_types):
    """agc_all_in_one ile ayni mantik — yalnizca gecmis penceresi uzerinden."""
    g = _g()
    fs_, fq, n, art = None, None, 0, []
    t_idx = np.array(target_idx)
    for gh, s in starts:
        w = store[gh]["feats"][s:s + GECMIS]; w64 = w.astype(np.float64)
        if fs_ is None:
            fs_, fq = w64.sum(0), (w64 ** 2).sum(0)
        else:
            fs_ += w64.sum(0); fq += (w64 ** 2).sum(0)
        n += GECMIS
        out = store[gh]["feats"][s + GECMIS:s + GECMIS + GELECEK][:, t_idx]
        art.append(out - g["build_anchor"](w, t_idx, anchor_types)
                   if g["RESIDUAL_MODE"] else out)
    fm = (fs_ / n).astype(np.float32)
    sd = np.sqrt(np.maximum(fq / n - (fs_ / n) ** 2, 1e-8)).astype(np.float32)
    sd[sd < 1e-6] = 1.0
    a = np.concatenate(art, 0)
    tm, ts = a.mean(0).astype(np.float32), a.std(0).astype(np.float32)
    ts[ts < 1e-6] = 1.0
    return {"feat_mean": fm, "feat_std": sd, "tgt_mean": tm, "tgt_std": ts}


def metrik(Y, P, targets, ortak):
    r = []
    for hl, hs in HORIZONS:
        e = P[:, :hs] - Y[:, :hs]
        mae = np.abs(e).mean((0, 1)); rmse = np.sqrt((e ** 2).mean((0, 1)))
        sr = (e ** 2).sum((0, 1))
        st = ((Y[:, :hs] - Y[:, :hs].mean((0, 1), keepdims=True)) ** 2).sum((0, 1))
        r2 = np.where(st > 0, 1 - sr / np.maximum(st, 1e-12), np.nan)
        for j, t in enumerate(targets):
            r.append({**ortak, "horizon": hl, "target": t, "MAE": float(mae[j]),
                      "RMSE": float(rmse[j]), "R2": float(r2[j])})
    return r


def bir_kosu(base_dir: Path, fs_name: str, mimari: str, kahin: bool):
    g = _g()
    tf.keras.utils.set_random_seed(g["SEED"])
    store, target_idx, targets, fcols = g["load_arrays"](base_dir, fs_name)
    hava = [fcols.index(c) for c in HAVA_ADAYLARI if c in fcols]
    anchor = [g["ANCHOR_BY_TARGET"].get(t, g["DEFAULT_ANCHOR"]) for t in targets]

    # 360 adimlik pencere daha uzun -> sinira tasan pencereleri ele
    def uygun(split):
        out = []
        for gh, d in store.items():
            n = len(d["feats"])
            sinir = {"train": (0, int(n * .70)),
                     "val": (int(n * .70), int(n * .70) + int(n * .15)),
                     "test": (int(n * .70) + int(n * .15), n)}[split]
            w = d["windows"]
            for s in w.loc[w.split == split, "input_start"]:
                if s + TOPLAM <= sinir[1]:
                    out.append((gh, int(s)))
        return out

    tr, va, te = uygun("train"), uygun("val"), uygun("test")
    stats = norm_stats(store, tr, target_idx, anchor)
    cfg = g["SIZE_PRESETS"][g["MODEL_SIZE"]]
    n_feat = store[tr[0][0]]["feats"].shape[1] + 1
    model = kur_model(mimari, n_feat, len(targets), cfg)
    model.compile(optimizer=keras.optimizers.Adam(g["LEARNING_RATE"]), loss="mse")

    S = lambda st, sh: OracleSequence(store, st, target_idx, hava, stats,
                                      g["BATCH_SIZE"], anchor, kahin, sh)
    ck = base_dir / "checkpoints_oracle"; ck.mkdir(exist_ok=True)
    etiket = f"{fs_name}_{mimari}_{'kahin' if kahin else 'temel'}"
    model.fit(S(tr, True), validation_data=S(va, False), epochs=g["EPOCHS"], verbose=2,
              callbacks=[keras.callbacks.EarlyStopping(monitor="val_loss",
                            patience=g["PATIENCE"], restore_best_weights=True),
                         keras.callbacks.ModelCheckpoint(ck / f"{etiket}.keras",
                            monitor="val_loss", save_best_only=True),
                         keras.callbacks.ReduceLROnPlateau(monitor="val_loss",
                            factor=.5, patience=4, min_lr=1e-5)])

    P = model.predict(S(te, False), verbose=0) * stats["tgt_std"] + stats["tgt_mean"]
    t_idx = np.array(target_idx)
    Y = np.empty((len(te), GELECEK, len(targets)), np.float32)
    A = np.empty_like(Y)
    for k, (gh, s) in enumerate(te):
        f = store[gh]["feats"]
        Y[k] = f[s + GECMIS:s + GECMIS + GELECEK][:, t_idx]
        A[k] = g["build_anchor"](f[s:s + GECMIS], t_idx, anchor)
    if g["RESIDUAL_MODE"]:
        P = P + A
    print(f"    parametre {model.count_params():,} · hava kanali {len(hava)} · test {len(te)}")
    return metrik(Y, P, targets, {"feature_set": fs_name, "mimari": mimari,
                                  "varyant": "kahin" if kahin else "temel"})


def run(base_dir: Path, feature_sets=("core_grodan",), mimariler=("tcn", "gru")):
    g = _g()
    satir = []
    for fs in feature_sets:
        for m in mimariler:
            for kahin in (False, True):
                ad = f"{fs}/{m}/{'KAHIN' if kahin else 'temel'}"
                print(f"\n{'='*66}\n{ad}\n{'='*66}")
                try:
                    satir += bir_kosu(base_dir, fs, m, kahin)
                except Exception as exc:
                    print(f"  HATA: {exc}")
    d = pd.DataFrame(satir)
    d.to_csv(base_dir / "hava_oracle_sonuclari.csv", index=False)

    print("\n" + "=" * 78)
    print("HAVA BILGISININ DEGERI — hatanin ne kadari gelecek havayi bilmemekten?")
    print("=" * 78)
    p = d.pivot_table(index=["feature_set", "horizon", "target"],
                      columns=["mimari", "varyant"], values="MAE")
    for m in d.mimari.unique():
        if (m, "temel") in p.columns and (m, "kahin") in p.columns:
            p[(m, "azalma_%")] = ((p[(m, "temel")] - p[(m, "kahin")]) /
                                  p[(m, "temel")] * 100).round(1)
    print(p.round(3).to_string())

    print("\n" + "=" * 78)
    for m in d.mimari.unique():
        if (m, "azalma_%") in p.columns:
            v = p[(m, "azalma_%")]
            print(f"{m.upper():5s}  ortalama azalma %{v.mean():.1f} · medyan %{v.median():.1f} · "
                  f"en yuksek %{v.max():.1f} ({v.idxmax()[2]})")
    print("\nYORUM: azalma yuzdesi, hatanin gelecek havayi bilmemekten gelen KISMIDIR.")
    print("Kalan kisim seranin icsel dinamik belirsizligidir.")
    print("Bu bir UST SINIRDIR — gercek meteoroloji tahmini mukemmel degildir.")
    return d


if __name__ == "__main__":
    BASE_DIR = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")
    run(BASE_DIR)
