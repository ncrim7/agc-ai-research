"""
AGC 2. Edisyon - Leave-One-Team-Out (LOTO) Capraz Dogrulama
=============================================================
SORU: Model, kontrol politikasini hic gormedigi bir seraya genellesiyor mu?

TASARIM VE ORTAK-HAVA SIZINTISI
--------------------------------
Alti sera AYNI TESISTE ve AYNI Weather.csv'yi paylasiyor. Klasik LOTO'da
(5 takimin tum zamani ile egit, 6. takimin tum zamani ile test et) model,
test doneminin DIS HAVA kosullarini diger 5 takim uzerinden zaten gormus
olur. Sera iklimi buyuk olcude dis havayla suruldugu icin bu ciddi bir
sizintidir ve sonuclari oldugundan iyi gosterir.

Bu script tek egitimle IKI test seti uretip sizintiyi OLCER:

  Fold = tutulan takim T
  EGITIM : diger 5 takimin TRAIN donemi pencereleri
  DOGRULAMA: diger 5 takimin VAL donemi pencereleri
  TEST A ("hava GORULMUS")  : T'nin TRAIN donemi pencereleri
                              -> hava kosullari egitimde vardi (5 takim uzerinden),
                                 politika gorulmedi
  TEST B ("hava GORULMEMIS"): T'nin TEST donemi pencereleri
                              -> ne hava ne politika gorulmedi (durust olcum)

  A ile B arasindaki fark = ortak-hava sizintisinin buyuklugu.
  Bu farkin kendisi makalede raporlanabilir bir bulgudur.

MALIYET: 6 fold x 3 model x 2 feature-set = 36 kosu (multi-target).
Single-target ile carpilirsa 288 kosu olurdu - bilincli olarak yapilmiyor;
LOTO'nun cevapladigi soru "gorulmemis seraya genelleme", hedef basina ayri
model gerektirmiyor.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import tensorflow as tf
from tensorflow import keras

import agc_deep_models as dm


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
    seq = dm.WindowSequence(store, starts, target_idx, stats, dm.BATCH_SIZE, anchor_types)
    pred = model.predict(seq, verbose=0) * stats["tgt_std"] + stats["tgt_mean"]

    Y_true, Anchor, _ = dm.get_raw_eval_data(store, starts, target_idx, anchor_types)
    if dm.RESIDUAL_MODE:
        pred = pred + Anchor

    rows = []
    for hlabel, hsteps in (("3h", dm.H3_STEPS), ("6h", dm.OUTPUT_STEPS)):
        for r in dm.compute_metrics(Y_true, pred, targets, hsteps):
            rows.append({"test_set": etiket, "horizon": hlabel, "n_windows": len(starts), **r})
    return rows


def run_fold(model_name, fs_name, base_dir, held_out):
    tf.keras.utils.set_random_seed(dm.SEED)
    store, target_idx, targets, feature_cols = dm.load_arrays(base_dir, fs_name)

    teams = list(store.keys())
    if held_out not in teams:
        raise ValueError(f"{held_out} veride yok")
    train_teams = [t for t in teams if t != held_out]

    anchor_types = [dm.ANCHOR_BY_TARGET.get(t, dm.DEFAULT_ANCHOR) for t in targets]

    tr = collect_starts_for_teams(store, train_teams, "train")
    va = collect_starts_for_teams(store, train_teams, "val")
    te_seen = collect_starts_for_teams(store, [held_out], "train")    # hava gorulmus
    te_unseen = collect_starts_for_teams(store, [held_out], "test")   # hava gorulmemis

    print(f"  egitim(5 takim)={len(tr)}  dogrulama={len(va)}  "
          f"testA-gorulmus={len(te_seen)}  testB-gorulmemis={len(te_unseen)}")

    stats = dm.compute_norm_stats(store, tr, target_idx, anchor_types)
    n_feat, n_tgt = store[tr[0][0]]["feats"].shape[1], len(target_idx)

    train_seq = dm.WindowSequence(store, tr, target_idx, stats, dm.BATCH_SIZE, anchor_types, shuffle=True)
    val_seq = dm.WindowSequence(store, va, target_idx, stats, dm.BATCH_SIZE, anchor_types)

    cfg = dm.SIZE_PRESETS[dm.MODEL_SIZE]
    model = dm.BUILDERS[model_name](n_feat, n_tgt, cfg)
    model.compile(optimizer=keras.optimizers.Adam(dm.LEARNING_RATE), loss="mse", metrics=["mae"])

    ckpt_dir = base_dir / "checkpoints_loto"
    ckpt_dir.mkdir(exist_ok=True)
    ckpt = ckpt_dir / f"{fs_name}_{model_name}_{dm.MODEL_SIZE}_holdout_{held_out}.keras"

    model.fit(
        train_seq, validation_data=val_seq, epochs=dm.EPOCHS, verbose=2,
        callbacks=[
            keras.callbacks.EarlyStopping(monitor="val_loss", patience=dm.PATIENCE, restore_best_weights=True),
            keras.callbacks.ModelCheckpoint(ckpt, monitor="val_loss", save_best_only=True),
            keras.callbacks.ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=4, min_lr=1e-5),
        ],
    )

    rows = []
    for starts, etiket in ((te_seen, "A_hava_gorulmus"), (te_unseen, "B_hava_gorulmemis")):
        for r in evaluate(model, store, starts, target_idx, targets, anchor_types, stats, etiket):
            rows.append({"feature_set": fs_name, "model": f"{model_name}_{dm.MODEL_SIZE}",
                         "held_out_team": held_out, "model_size": dm.MODEL_SIZE, **r})
    return rows


def run(base_dir: Path, models=("gru", "lstm", "tcn"),
        feature_sets=("core", "core_grodan"), teams=None, out_name="loto_results.csv"):
    out = base_dir / out_name

    tamamlanan = set()
    if out.exists():
        onceki = pd.read_csv(out)
        for _, r in onceki.iterrows():
            tamamlanan.add((r["feature_set"], r["model"], r["held_out_team"]))
        print(f"Mevcut LOTO dosyasi: {len(onceki)} satir, {len(tamamlanan)} kosu atlanacak.\n")

    ilk_store, *_ = dm.load_arrays(base_dir, feature_sets[0])
    tum_takimlar = teams or list(ilk_store.keys())

    plan = [(fs, m, t) for fs in feature_sets for m in models for t in tum_takimlar]
    print(f"Toplam planlanan LOTO kosusu: {len(plan)}\n")

    for i, (fs, m, t) in enumerate(plan, 1):
        anahtar = (fs, f"{m}_{dm.MODEL_SIZE}", t)
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


if __name__ == "__main__":
    BASE_DIR = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")
    run(BASE_DIR)
