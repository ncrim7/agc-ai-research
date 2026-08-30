from __future__ import annotations
"""
AGC 2. Edisyon - TEK PARCA: Derin Modeller + LOTO Capraz Dogrulama
===================================================================
agc_deep_models.py ve agc_loto_cv.py'nin BIRLESIMI. Import gerektirmez -
Colab'da tek hucreye yapistirip calistir.

KULLANIM (yapistirdiktan sonra AYRI bir hucrede):

    from pathlib import Path
    BASE_DIR = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")

    run_loto(BASE_DIR)                                                   # LOTO, 36 kosu
    run(BASE_DIR, feature_sets=("core",),        target_mode="single")   # 15 kosu
    run(BASE_DIR, feature_sets=("core_grodan",), target_mode="single")   # 33 kosu

Ikisi de cokmeye dayaniklidir: Colab koparsa ayni hucreyi tekrar calistir,
tamamlanmis kosulari atlayip kaldigi yerden devam eder.
"""

"""
AGC 2. Edisyon - Hafta 3: Derin Modeller (GRU / LSTM / TCN)
============================================================
Baseline sonuclari sunu gosterdi: seasonal_naive'in hatasi ufka gore
neredeyse HIC artmiyor (Tair 3h 1.182 -> 6h 1.193). Persistence ayni
araligta %70 bozuluyor. Yani sistem gunluk donguye kilitli.

Seasonal naive'in kullandigi deger y(t+h-288), GIRDI penceresinin ilk 72
adiminda zaten var. Ama 288 adimlik bir diziyi sirayla isleyen RNN'de o
bilgi en BASTA duruyor - recency bias'in en cok vurdugu konum. Onceki GRU
denemesinin baseline'i gecememesinin muhtemel sebebi bu.

COZUM: residual (artik) mimarisi.
    y_hat = seasonal_naive + model_duzeltmesi
Model sifir cikti verse bile seasonal_naive kadar iyi olur. Cita tabana
gomulur, model sadece "bugun dunden nasil farkli" sorusunu ogrenir.

RESIDUAL_MODE = False yaparak mutlak-hedef egitimi ablasyon olarak kosulabilir.

BELLEK: pencere tensoru materialize EDILMIYOR. Sera basina ham dizi
(~9 MB) bellekte durur, batch'ler indeksten dilimlenerek uretilir.
23298 x 288 x 46 float32 = ~1.2 GB olurdu, Colab'da patlardi.

COLAB: her epoch sonunda checkpoint Drive'a yazilir. Oturum koparsa
RESUME=True ile kaldigi yerden devam eder.
"""


import json
from pathlib import Path

import numpy as np
import pandas as pd

import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers

# ----------------------------------------------------------------------
# KONFIGURASYON
# ----------------------------------------------------------------------
INPUT_STEPS = 288
OUTPUT_STEPS = 72
H3_STEPS = 36

RESIDUAL_MODE = True       # False -> mutlak hedef egitimi (ablasyon)

# HEDEF BASINA CIPA SECIMI
# Ilk kosuda TUM hedefler seasonal cipaya baglandi -> EC/WC_slab'de felaket
# (TCN 0.162 vs persistence 0.043, 3.8x kotu). Sebep: kok bolgesi degiskenleri
# GUNLUK DONGUSEL DEGIL, yavas suruklenen buyukluklerdir. "Dun bu saatte" onlar
# icin kotu bir cipa; model once yanlis cipayi geri almak zorunda kaliyor.
# Baseline tablosu hangi cipanin dogru oldugunu zaten soyluyor:
#   EC_slab 3h: persistence 0.043 << seasonal 0.136  -> persistence
#   WC_slab 3h: persistence 1.057 <  seasonal 1.419  -> persistence
#   t_slab  6h: seasonal 0.813    << persistence 1.533 -> seasonal
#   Tair/Rhair/CO2air/HumDef/Tot_PAR: seasonal her yerde kazaniyor
ANCHOR_BY_TARGET = {
    "Tair": "seasonal", "Rhair": "seasonal", "CO2air": "seasonal",
    "HumDef": "seasonal", "Tot_PAR": "seasonal",
    "t_slab1": "seasonal", "t_slab2": "seasonal",
    "EC_slab1": "persistence", "EC_slab2": "persistence",
    "WC_slab1": "persistence", "WC_slab2": "persistence",
}
DEFAULT_ANCHOR = "seasonal"

# TARGET_MODE: "multi"  -> tek model tum hedefleri birden tahmin eder
#                          (paylasilan encoder + hedef basina bagimsiz lineer kafa)
#              "single" -> her hedef icin AYRI model
# Multi ana deney (butce: 3 model x 2 feature-set = 6 kosu).
# Single ablasyon icin (3 x 16 = 48 kosu, tam kosarsan 8-16 saat GPU) -
# tek konfigurasyonda kosman onerilir: run(..., target_mode="single",
# models=("gru",), feature_sets=("core",)) -> 5 kosu.
TARGET_MODE = "multi"

BATCH_SIZE = 64
EPOCHS = 150               # bagalyici degil; early stopping yonetir
PATIENCE = 20              # 8 -> 20: ReduceLROnPlateau'ya daha cok sans
LEARNING_RATE = 1e-3
L2_REG = 1e-4              # agirlik cezasi - overfitting'e karsi
SEED = 42

# MODEL BOYUTU — bu projedeki EN KRITIK hiperparametre
# ---------------------------------------------------------------------
# Ilk kosuda TCN 199.208, GRU 75.816 parametre kullanildi ve hepsi
# baseline'lara kaybetti. Sebep epoch sayisi DEGIL, efektif ornek sayisi:
#
#   Train'de sera basina 33.466 satir, pencere araligi 360 adim
#   Cakismayan pencere: 33.466 / 360 = 93 per sera -> 6 serada ~558
#   Stride=12 kullandigimiz icin ardisik pencereler %95.8 ORTUSUYOR,
#   yani raporlanan 16.482 pencere bagimsiz ornek DEGIL.
#
#   199.208 parametre / 558 bagimsiz ornek = ornek basina 357 parametre.
#   Bu oranda model ezberler, genellemez. Baseline'lar kazanir cunku
#   persistence ve seasonal naive'in SIFIR parametresi vardir.
#
# "small" varsayilan yapildi. "medium"/"large" karsilastirma icin durur -
# ablasyon olarak kosarsan kapasite-genelleme iliskisi makalede tablo olur.
SIZE_PRESETS = {
    "small":  {"rnn_units": 24, "tcn_filters": 16, "tcn_dilations": (1, 2, 4, 8, 16, 32, 64), "dropout": 0.2},
    "medium": {"rnn_units": 48, "tcn_filters": 32, "tcn_dilations": (1, 2, 4, 8, 16, 32, 64), "dropout": 0.2},
    "large":  {"rnn_units": 96, "tcn_filters": 64, "tcn_dilations": (1, 2, 4, 8, 16, 32, 64), "dropout": 0.2},
}
MODEL_SIZE = "small"

CORE_TARGETS = ["Tair", "Rhair", "CO2air", "HumDef", "Tot_PAR"]
GRODAN_TARGETS = ["EC_slab1", "EC_slab2", "WC_slab1", "WC_slab2", "t_slab1", "t_slab2"]

FEATURE_SETS = {
    "core": ("common_core_strict.parquet", "window_index_core.csv", CORE_TARGETS),
    "core_grodan": ("common_core_with_grodan_strict.parquet", "window_index_grodan.csv",
                    CORE_TARGETS + GRODAN_TARGETS),
}


# ----------------------------------------------------------------------
# VERI KATMANI
# ----------------------------------------------------------------------

def load_arrays(base_dir: Path, fs_name: str):
    parquet_name, window_name, targets = FEATURE_SETS[fs_name]
    df = pd.read_parquet(base_dir / parquet_name)
    windows = pd.read_csv(base_dir / window_name)

    feature_cols = list(df.select_dtypes(include=[np.number]).columns)
    target_idx = [feature_cols.index(t) for t in targets]

    store = {}
    for gh, grp in df.groupby("greenhouse_id", sort=False):
        grp = grp.sort_values("Time").reset_index(drop=True)
        n = len(grp)
        train_end = int(n * 0.70)

        feats = grp[feature_cols].to_numpy(dtype=np.float32)
        train_means = np.nanmean(feats[:train_end], axis=0)
        train_means = np.where(np.isnan(train_means), 0.0, train_means)
        nan_mask = np.isnan(feats)
        feats[nan_mask] = np.take(train_means, np.where(nan_mask)[1])

        store[gh] = {"feats": feats, "windows": windows[windows.greenhouse_id == gh]}

    return store, target_idx, targets, feature_cols


def collect_starts(store: dict, split: str) -> list[tuple[str, int]]:
    out = []
    for gh, d in store.items():
        for s in d["windows"].loc[d["windows"].split == split, "input_start"]:
            out.append((gh, int(s)))
    return out


def build_anchor(win: np.ndarray, t_idx: np.ndarray, anchor_types: list[str]) -> np.ndarray:
    """Girdi penceresinden (288, n_feat) her hedef icin cipa trajektorisi (72, n_tgt).

    seasonal    -> girdinin ilk 72 adimi (= 24 saat oncesi, cikti ile ayni saat dilimi)
    persistence -> girdinin son degeri, 72 kez tekrarlanir
    """
    out = np.empty((OUTPUT_STEPS, len(t_idx)), np.float32)
    for j, (col, atype) in enumerate(zip(t_idx, anchor_types)):
        if atype == "persistence":
            out[:, j] = win[-1, col]
        else:
            out[:, j] = win[:OUTPUT_STEPS, col]
    return out


def compute_norm_stats(store: dict, starts: list, target_idx: list[int],
                       anchor_types: list[str]) -> dict:
    """Train pencerelerinden oznitelik ve artik istatistikleri. SADECE train."""
    feat_sum = feat_sq = None
    count = 0
    resid_vals = []
    t_idx = np.array(target_idx)

    for gh, s in starts:
        win = store[gh]["feats"][s : s + INPUT_STEPS]
        win64 = win.astype(np.float64)
        if feat_sum is None:
            feat_sum = win64.sum(axis=0)
            feat_sq = (win64 ** 2).sum(axis=0)
        else:
            feat_sum += win64.sum(axis=0)
            feat_sq += (win64 ** 2).sum(axis=0)
        count += INPUT_STEPS

        out = store[gh]["feats"][s + INPUT_STEPS : s + INPUT_STEPS + OUTPUT_STEPS][:, t_idx]
        anchor = build_anchor(win, t_idx, anchor_types)
        resid_vals.append(out - anchor if RESIDUAL_MODE else out)

    feat_mean = (feat_sum / count).astype(np.float32)
    feat_var = np.maximum(feat_sq / count - (feat_sum / count) ** 2, 1e-8)
    feat_std = np.sqrt(feat_var).astype(np.float32)
    feat_std[feat_std < 1e-6] = 1.0        # sabit kolon -> bolme patlamasin

    resid = np.concatenate(resid_vals, axis=0)
    tgt_mean = resid.mean(axis=0).astype(np.float32)
    tgt_std = resid.std(axis=0).astype(np.float32)
    tgt_std[tgt_std < 1e-6] = 1.0

    return {"feat_mean": feat_mean, "feat_std": feat_std,
            "tgt_mean": tgt_mean, "tgt_std": tgt_std}


class WindowSequence(keras.utils.Sequence):
    """Pencere tensorunu materialize etmeden batch uretir."""

    def __init__(self, store, starts, target_idx, stats, batch_size, anchor_types, shuffle=False):
        self.store, self.starts = store, list(starts)
        self.target_idx = np.array(target_idx)
        self.anchor_types = anchor_types
        self.stats = stats
        self.batch_size = batch_size
        self.shuffle = shuffle
        self.rng = np.random.default_rng(SEED)
        self.on_epoch_end()

    def __len__(self):
        return int(np.ceil(len(self.starts) / self.batch_size))

    def on_epoch_end(self):
        if self.shuffle:
            self.rng.shuffle(self.starts)

    def __getitem__(self, i):
        batch = self.starts[i * self.batch_size : (i + 1) * self.batch_size]
        X = np.empty((len(batch), INPUT_STEPS, self.store[batch[0][0]]["feats"].shape[1]), np.float32)
        Y = np.empty((len(batch), OUTPUT_STEPS, len(self.target_idx)), np.float32)

        for k, (gh, s) in enumerate(batch):
            f = self.store[gh]["feats"]
            win = f[s : s + INPUT_STEPS]
            out = f[s + INPUT_STEPS : s + INPUT_STEPS + OUTPUT_STEPS][:, self.target_idx]
            X[k] = win
            if RESIDUAL_MODE:
                Y[k] = out - build_anchor(win, self.target_idx, self.anchor_types)
            else:
                Y[k] = out

        X = (X - self.stats["feat_mean"]) / self.stats["feat_std"]
        Y = (Y - self.stats["tgt_mean"]) / self.stats["tgt_std"]
        return X, Y


def get_raw_eval_data(store, starts, target_idx, anchor_types):
    """Metrikler icin: gercek hedef + cipa (normalize EDILMEMIS)."""
    t_idx = np.array(target_idx)
    Y = np.empty((len(starts), OUTPUT_STEPS, len(t_idx)), np.float32)
    A = np.empty_like(Y)
    gh_ids = []
    for k, (gh, s) in enumerate(starts):
        f = store[gh]["feats"]
        win = f[s : s + INPUT_STEPS]
        Y[k] = f[s + INPUT_STEPS : s + INPUT_STEPS + OUTPUT_STEPS][:, t_idx]
        A[k] = build_anchor(win, t_idx, anchor_types)
        gh_ids.append(gh)
    return Y, A, np.array(gh_ids)


# ----------------------------------------------------------------------
# MODELLER
# ----------------------------------------------------------------------

def _head(x, n_tgt, bottleneck):
    """Cikti kafasi. 72 x n_tgt dogrudan Dense ile uretmek parametreyi patlatir
    (orn. 96 birim -> 96*360 = 34.560 sadece burada). Once dar bir darbogazdan
    geciriyoruz."""
    reg = keras.regularizers.l2(L2_REG)
    x = layers.Dense(bottleneck, activation="relu", kernel_regularizer=reg)(x)
    x = layers.Dense(OUTPUT_STEPS * n_tgt, kernel_regularizer=reg)(x)
    return layers.Reshape((OUTPUT_STEPS, n_tgt))(x)


def build_gru(n_feat, n_tgt, cfg):
    reg = keras.regularizers.l2(L2_REG)
    inp = keras.Input((INPUT_STEPS, n_feat))
    x = layers.GRU(cfg["rnn_units"], dropout=cfg["dropout"], kernel_regularizer=reg)(inp)
    return keras.Model(inp, _head(x, n_tgt, cfg["rnn_units"]), name="gru")


def build_lstm(n_feat, n_tgt, cfg):
    reg = keras.regularizers.l2(L2_REG)
    inp = keras.Input((INPUT_STEPS, n_feat))
    x = layers.LSTM(cfg["rnn_units"], dropout=cfg["dropout"], kernel_regularizer=reg)(inp)
    return keras.Model(inp, _head(x, n_tgt, cfg["rnn_units"]), name="lstm")


def build_tcn(n_feat, n_tgt, cfg, kernel=3):
    """Dilated causal TCN.

    Alici alan = 2*(kernel-1)*sum(dilations)+1 = 2*2*127+1 = 509 > 288.
    Son adim TUM girdi penceresini gorur - RNN'in recency bias'i yok.
    Ilk kosuda TCN en iyi derin modeldi; kapasite dusurulunce daha da
    iyilesmesi bekleniyor (bkz. SIZE_PRESETS aciklamasi).
    """
    reg = keras.regularizers.l2(L2_REG)
    f = cfg["tcn_filters"]
    inp = keras.Input((INPUT_STEPS, n_feat))
    x = layers.Conv1D(f, 1, padding="same", kernel_regularizer=reg)(inp)
    for d in cfg["tcn_dilations"]:
        prev = x
        x = layers.Conv1D(f, kernel, padding="causal", dilation_rate=d,
                          activation="relu", kernel_regularizer=reg)(x)
        x = layers.Dropout(cfg["dropout"])(x)
        x = layers.Conv1D(f, kernel, padding="causal", dilation_rate=d,
                          activation="relu", kernel_regularizer=reg)(x)
        x = layers.Add()([prev, x])
    x = layers.Lambda(lambda t: t[:, -1, :])(x)      # causal -> son adim tam alici alan
    return keras.Model(inp, _head(x, n_tgt, f), name="tcn")


BUILDERS = {"gru": build_gru, "lstm": build_lstm, "tcn": build_tcn}


# ----------------------------------------------------------------------
# METRIKLER (baseline scriptiyle AYNI format)
# ----------------------------------------------------------------------

def compute_metrics(y_true, y_pred, targets, horizon_steps):
    yt, yp = y_true[:, :horizon_steps], y_pred[:, :horizon_steps]
    err = yp - yt
    mae = np.abs(err).mean(axis=(0, 1))
    rmse = np.sqrt((err ** 2).mean(axis=(0, 1)))
    ss_res = (err ** 2).sum(axis=(0, 1))
    ss_tot = ((yt - yt.mean(axis=(0, 1), keepdims=True)) ** 2).sum(axis=(0, 1))
    r2 = np.where(ss_tot > 0, 1 - ss_res / np.maximum(ss_tot, 1e-12), np.nan)
    return [{"target": t, "MAE": float(mae[j]), "RMSE": float(rmse[j]), "R2": float(r2[j])}
            for j, t in enumerate(targets)]


# ----------------------------------------------------------------------
# EGITIM
# ----------------------------------------------------------------------

def train_one(model_name, fs_name, base_dir, resume=False, only_target=None):
    """only_target=None -> multi-target (tum hedefler tek modelde)
       only_target='Tair' -> sadece o hedef icin ayri model (single mod)"""
    tf.keras.utils.set_random_seed(SEED)
    store, target_idx, targets, feature_cols = load_arrays(base_dir, fs_name)

    if only_target is not None:
        if only_target not in targets:
            raise ValueError(f"{only_target} bu feature-set'te yok")
        target_idx = [feature_cols.index(only_target)]
        targets = [only_target]

    # KONFIGURASYON PARMAK IZI
    # Resume anahtari SADECE (feature_set, model, target) olsaydi, kapasite veya
    # cipa semasi degistiginde eski sonuclar "tamamlanmis" sayilip yeni kosu
    # ATLANIRDI - sessizce eski sayilari raporlardik. Bu yuzden konfigurasyonu
    # model etiketine gomuyoruz: ayar degisince etiket degisir, kosu tekrarlanir.
    suffix = ("resid" if RESIDUAL_MODE else "abs") + ("_single" if only_target else "")
    model_tag = f"{model_name}_{suffix}_{MODEL_SIZE}"

    tr = collect_starts(store, "train")
    va = collect_starts(store, "val")
    te = collect_starts(store, "test")
    print(f"[{fs_name}/{model_tag}{'/' + only_target if only_target else ''}] "
          f"train={len(tr)} val={len(va)} test={len(te)}")

    anchor_types = [ANCHOR_BY_TARGET.get(t, DEFAULT_ANCHOR) for t in targets]
    print(f"  cipalar: {dict(zip(targets, anchor_types))}")

    stats = compute_norm_stats(store, tr, target_idx, anchor_types)
    n_feat, n_tgt = store[tr[0][0]]["feats"].shape[1], len(target_idx)

    train_seq = WindowSequence(store, tr, target_idx, stats, BATCH_SIZE, anchor_types, shuffle=True)
    val_seq = WindowSequence(store, va, target_idx, stats, BATCH_SIZE, anchor_types)
    test_seq = WindowSequence(store, te, target_idx, stats, BATCH_SIZE, anchor_types)

    ckpt_dir = base_dir / "checkpoints"
    ckpt_dir.mkdir(exist_ok=True)
    tag = f"{fs_name}_{model_tag}" + (f"_{only_target}" if only_target else "")
    ckpt_path = ckpt_dir / f"{tag}.keras"

    if resume and ckpt_path.exists():
        print(f"  checkpoint bulundu, devam ediliyor: {ckpt_path.name}")
        model = keras.models.load_model(ckpt_path)
    else:
        cfg = SIZE_PRESETS[MODEL_SIZE]
        model = BUILDERS[model_name](n_feat, n_tgt, cfg)
        model.compile(optimizer=keras.optimizers.Adam(LEARNING_RATE), loss="mse", metrics=["mae"])

    # EFEKTIF ORNEK SAYISI TESHISI
    # Ardisik pencereler stride=12 ile %95.8 ortusuyor. Gercek bagimsiz ornek
    # sayisi cok daha dusuk. Parametre/bagimsiz-ornek orani 50'yi asiyorsa
    # ezberleme riski yuksektir.
    span = INPUT_STEPS + OUTPUT_STEPS
    n_gh = len(store)
    rows_per_gh = len(next(iter(store.values()))["feats"])
    efektif = int(rows_per_gh * 0.70 / span) * n_gh
    oran = model.count_params() / max(efektif, 1)
    print(f"  parametre: {model.count_params():,} | boyut={MODEL_SIZE}")
    print(f"  raporlanan train penceresi: {len(tr):,}  ama CAKISMAYAN (efektif): ~{efektif}")
    print(f"  parametre / bagimsiz ornek = {oran:.0f}" + ("   <-- YUKSEK, ezberleme riski" if oran > 50 else "   (makul)"))

    callbacks = [
        keras.callbacks.EarlyStopping(monitor="val_loss", patience=PATIENCE, restore_best_weights=True),
        keras.callbacks.ModelCheckpoint(ckpt_path, monitor="val_loss", save_best_only=True),
        keras.callbacks.ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=4, min_lr=1e-5),
    ]
    hist = model.fit(train_seq, validation_data=val_seq, epochs=EPOCHS, callbacks=callbacks, verbose=2)

    # --- Tahmin + geri olcekleme ---
    pred_norm = model.predict(test_seq, verbose=0)
    pred = pred_norm * stats["tgt_std"] + stats["tgt_mean"]

    Y_true, Anchor, gh_ids = get_raw_eval_data(store, te, target_idx, anchor_types)
    if RESIDUAL_MODE:
        pred = pred + Anchor

    rows = []
    for hlabel, hsteps in (("3h", H3_STEPS), ("6h", OUTPUT_STEPS)):
        for r in compute_metrics(Y_true, pred, targets, hsteps):
            rows.append({"feature_set": fs_name, "eval_mode": "pooled", "greenhouse_id": "ALL",
                         "model": model_tag, "horizon": hlabel, **r})
        for gh in np.unique(gh_ids):
            m = gh_ids == gh
            for r in compute_metrics(Y_true[m], pred[m], targets, hsteps):
                rows.append({"feature_set": fs_name, "eval_mode": "per_greenhouse", "greenhouse_id": gh,
                             "model": model_tag, "horizon": hlabel, **r})

    (ckpt_dir / f"{tag}_history.json").write_text(
        json.dumps({k: [float(v) for v in vals] for k, vals in hist.history.items()})
    )
    return rows


def run(base_dir: Path, models=("gru", "lstm", "tcn"), feature_sets=("core", "core_grodan"),
        resume=False, target_mode=None, out_name=None):
    """48 kosuluk single-target deneyi icin COKMEYE DAYANIKLI kosucu.

    - Her kosu bittikten HEMEN SONRA CSV'ye eklenir (sonda degil).
    - Yeniden baslatildiginda tamamlanmis kosular ATLANIR.
    Colab koparsa hucreyi tekrar calistirmak yeterli; kaldigi yerden devam eder.
    """
    mode = target_mode or TARGET_MODE
    out = base_dir / (out_name or f"deep_model_results_{mode}.csv")

    # --- Daha once tamamlanmis kosulari tespit et ---
    tamamlanan: set[tuple] = set()
    if out.exists():
        try:
            onceki = pd.read_csv(out)
        except Exception as exc:
            print(f"UYARI: {out.name} okunamadi ({exc}).")
            print("agc_fix_results_csv.py ile onarin. Simdilik yeni dosyaya yaziliyor.")
            out = out.with_name(out.stem + "_v2.csv")
            onceki = None
        if onceki is not None:
            for _, r in onceki.iterrows():
                tamamlanan.add((r["feature_set"], r["model"], r.get("trained_target", "ALL")))
            print(f"Mevcut sonuc dosyasi: {len(onceki)} satir, "
                  f"{len(tamamlanan)} tamamlanmis kosu atlanacak.\n")

    # --- Kosu listesini olustur ---
    plan = []
    for fs in feature_sets:
        _, _, fs_targets = FEATURE_SETS[fs]
        for m in models:
            for tgt in ([None] if mode == "multi" else list(fs_targets)):
                plan.append((fs, m, tgt))

    print(f"Toplam planlanan kosu: {len(plan)}  (mod={mode})")

    for i, (fs, m, tgt) in enumerate(plan, 1):
        suffix = ("resid" if RESIDUAL_MODE else "abs") + ("_single" if tgt else "")
        anahtar = (fs, f"{m}_{suffix}_{MODEL_SIZE}", tgt or "ALL")
        etiket = f"{fs} / {m}" + (f" / {tgt}" if tgt else "") + f" [{MODEL_SIZE}]"

        if anahtar in tamamlanan:
            print(f"[{i}/{len(plan)}] ATLANDI (zaten var): {etiket}")
            continue

        print(f"\n{'='*70}\n[{i}/{len(plan)}] {etiket}\n{'='*70}")
        try:
            satirlar = train_one(m, fs, base_dir, resume=resume, only_target=tgt)
            for s in satirlar:
                s["trained_target"] = tgt or "ALL"
                s["model_size"] = MODEL_SIZE
                s["anchor_scheme"] = "per_target_v2"     # v1 = hepsi seasonal
                s["l2"] = L2_REG
            yeni = pd.DataFrame(satirlar)
            # SEMA HIZALAMA: eski dosyada olmayan kolon eklenirse CSV bozulur
            # (basliksiz ekleme -> "Expected N fields, saw M"). Once hizala.
            if out.exists():
                mevcut_kolonlar = list(pd.read_csv(out, nrows=0).columns)
                for k in mevcut_kolonlar:
                    if k not in yeni.columns:
                        yeni[k] = None
                fazla = [k for k in yeni.columns if k not in mevcut_kolonlar]
                if fazla:
                    # Yeni kolon var -> ayri dosyaya yaz, mevcut dosyayi bozma
                    hedef = out.with_name(out.stem + "_v2.csv")
                    yeni.to_csv(hedef, mode="a", header=not hedef.exists(), index=False)
                    print(f"  -> yeni sema, {hedef.name} dosyasina yazildi ({len(yeni)} satir)")
                    tamamlanan.add(anahtar)
                    continue
                yeni = yeni[mevcut_kolonlar]
            yeni.to_csv(out, mode="a", header=not out.exists(), index=False)
            tamamlanan.add(anahtar)
            print(f"  -> kaydedildi ({len(satirlar)} satir)")
        except Exception as exc:      # bir kosu patlarsa digerleri devam etsin
            print(f"  HATA ({etiket}): {exc}")

    if not out.exists():
        print("Hic sonuc uretilmedi.")
        return

    df = pd.read_csv(out)
    print("\n" + "=" * 78)
    print(f"POOLED TEST MAE — target_mode={mode}  ({len(df)} satir)")
    print("=" * 78)
    for fs in feature_sets:
        for h in ("3h", "6h"):
            sub = df[(df.feature_set == fs) & (df.eval_mode == "pooled") & (df.horizon == h)]
            if not sub.empty:
                print(f"\n--- {fs} / {h} ---")
                print(sub.pivot_table(index="target", columns="model", values="MAE").round(3).to_string())
    print(f"\nKaydedildi: {out}")
    print("Baseline'larla karsilastirmak icin all_forecasting_results_long.csv ile birlestir.")


# ======================================================================
# LEAVE-ONE-TEAM-OUT (LOTO) CAPRAZ DOGRULAMA
# ======================================================================



def collect_starts_for_teams(store, teams, split):
    """Belirli takimlarin belirli split'indeki pencere baslangiclari."""
    out = []
    for gh in teams:
        w = store[gh]["windows"]
        for s in w.loc[w.split == split, "input_start"]:
            out.append((gh, int(s)))
    return out


def evaluate(model, store, starts, target_idx, targets, anchor_types, stats, etiket):
    """Verilen pencere kumesinde tahmin uret ve metrikleri hesapla."""
    if not starts:
        return []
    seq = WindowSequence(store, starts, target_idx, stats, BATCH_SIZE, anchor_types)
    pred = model.predict(seq, verbose=0) * stats["tgt_std"] + stats["tgt_mean"]

    Y_true, Anchor, _ = get_raw_eval_data(store, starts, target_idx, anchor_types)
    if RESIDUAL_MODE:
        pred = pred + Anchor

    rows = []
    for hlabel, hsteps in (("3h", H3_STEPS), ("6h", OUTPUT_STEPS)):
        for r in compute_metrics(Y_true, pred, targets, hsteps):
            rows.append({"test_set": etiket, "horizon": hlabel, "n_windows": len(starts), **r})
    return rows


def run_fold(model_name, fs_name, base_dir, held_out):
    tf.keras.utils.set_random_seed(SEED)
    store, target_idx, targets, feature_cols = load_arrays(base_dir, fs_name)

    teams = list(store.keys())
    if held_out not in teams:
        raise ValueError(f"{held_out} veride yok")
    train_teams = [t for t in teams if t != held_out]

    anchor_types = [ANCHOR_BY_TARGET.get(t, DEFAULT_ANCHOR) for t in targets]

    tr = collect_starts_for_teams(store, train_teams, "train")
    va = collect_starts_for_teams(store, train_teams, "val")
    te_seen = collect_starts_for_teams(store, [held_out], "train")    # hava gorulmus
    te_unseen = collect_starts_for_teams(store, [held_out], "test")   # hava gorulmemis

    print(f"  egitim(5 takim)={len(tr)}  dogrulama={len(va)}  "
          f"testA-gorulmus={len(te_seen)}  testB-gorulmemis={len(te_unseen)}")

    stats = compute_norm_stats(store, tr, target_idx, anchor_types)
    n_feat, n_tgt = store[tr[0][0]]["feats"].shape[1], len(target_idx)

    train_seq = WindowSequence(store, tr, target_idx, stats, BATCH_SIZE, anchor_types, shuffle=True)
    val_seq = WindowSequence(store, va, target_idx, stats, BATCH_SIZE, anchor_types)

    cfg = SIZE_PRESETS[MODEL_SIZE]
    model = BUILDERS[model_name](n_feat, n_tgt, cfg)
    model.compile(optimizer=keras.optimizers.Adam(LEARNING_RATE), loss="mse", metrics=["mae"])

    ckpt_dir = base_dir / "checkpoints_loto"
    ckpt_dir.mkdir(exist_ok=True)
    ckpt = ckpt_dir / f"{fs_name}_{model_name}_{MODEL_SIZE}_holdout_{held_out}.keras"

    model.fit(
        train_seq, validation_data=val_seq, epochs=EPOCHS, verbose=2,
        callbacks=[
            keras.callbacks.EarlyStopping(monitor="val_loss", patience=PATIENCE, restore_best_weights=True),
            keras.callbacks.ModelCheckpoint(ckpt, monitor="val_loss", save_best_only=True),
            keras.callbacks.ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=4, min_lr=1e-5),
        ],
    )

    rows = []
    for starts, etiket in ((te_seen, "A_hava_gorulmus"), (te_unseen, "B_hava_gorulmemis")):
        for r in evaluate(model, store, starts, target_idx, targets, anchor_types, stats, etiket):
            rows.append({"feature_set": fs_name, "model": f"{model_name}_{MODEL_SIZE}",
                         "held_out_team": held_out, "model_size": MODEL_SIZE, **r})
    return rows


def run_loto(base_dir: Path, models=("gru", "lstm", "tcn"),
        feature_sets=("core", "core_grodan"), teams=None, out_name="loto_results.csv"):
    out = base_dir / out_name

    tamamlanan = set()
    if out.exists():
        onceki = pd.read_csv(out)
        for _, r in onceki.iterrows():
            tamamlanan.add((r["feature_set"], r["model"], r["held_out_team"]))
        print(f"Mevcut LOTO dosyasi: {len(onceki)} satir, {len(tamamlanan)} kosu atlanacak.\n")

    ilk_store, *_ = load_arrays(base_dir, feature_sets[0])
    tum_takimlar = teams or list(ilk_store.keys())

    plan = [(fs, m, t) for fs in feature_sets for m in models for t in tum_takimlar]
    print(f"Toplam planlanan LOTO kosusu: {len(plan)}\n")

    for i, (fs, m, t) in enumerate(plan, 1):
        anahtar = (fs, f"{m}_{MODEL_SIZE}", t)
        etiket = f"{fs} / {m} / holdout={t}"
        if anahtar in tamamlanan:
            print(f"[{i}/{len(plan)}] ATLANDI: {etiket}")
            continue

        print(f"\n{'='*70}\n[{i}/{len(plan)}] {etiket}\n{'='*70}")
        try:
            satirlar = run_fold(m, fs, base_dir, t)
            pd.DataFrame(satirlar).to_csv(out, mode="a", header=not out.exists(), index=False)
            tamamlanan.add(anahtar)
            print(f"  -> kaydedildi ({len(satirlar)} satir)")
        except Exception as exc:
            print(f"  HATA ({etiket}): {exc}")

    if not out.exists():
        print("Hic sonuc uretilmedi.")
        return

    df = pd.read_csv(out)
    print("\n" + "=" * 78)
    print("LOTO SONUCLARI — takimlar arasi MAE (3h)")
    print("=" * 78)
    for fs in feature_sets:
        sub = df[(df.feature_set == fs) & (df.horizon == "3h") & (df.test_set == "B_hava_gorulmemis")]
        if sub.empty:
            continue
        print(f"\n--- {fs} / TEST B (durust olcum) ---")
        piv = sub.pivot_table(index="target", columns="held_out_team", values="MAE")
        piv["ortalama"] = piv.mean(axis=1)
        piv["en_kotu"] = piv.drop(columns="ortalama").max(axis=1)
        print(piv.round(3).to_string())

    print("\n" + "=" * 78)
    print("ORTAK-HAVA SIZINTISININ BUYUKLUGU (A: hava gorulmus vs B: gorulmemis)")
    print("B/A orani > 1 ise: klasik LOTO sonuclari iyimser demektir.")
    print("=" * 78)
    kar = df[df.horizon == "3h"].pivot_table(index=["feature_set", "target"],
                                             columns="test_set", values="MAE")
    if {"A_hava_gorulmus", "B_hava_gorulmemis"}.issubset(kar.columns):
        kar["B/A"] = (kar["B_hava_gorulmemis"] / kar["A_hava_gorulmus"]).round(2)
        print(kar.round(3).to_string())
    print(f"\nKaydedildi: {out}")
