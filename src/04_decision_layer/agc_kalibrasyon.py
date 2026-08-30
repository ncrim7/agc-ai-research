"""
AGC - BELIRSIZLIK KALIBRASYONU
================================
KARAR KATMANI ICIN ONKOSUL.

Karar katmani "esigi asma olasiligi %94" gibi iddialar uretecek. Bu iddianin
gecerli olmasi icin tahmin araliklarinin KALIBRE olmasi gerekir: %95 dedigimiz
aralik, vakalarin gercekten %95'ini icermelidir. Bu hic test edilmedi.

YONTEM
------
Modellerimiz NOKTA tahmini uretir. Aralik su sekilde kurulur:

    aralik = nokta_tahmin ± q(alpha)

burada q(alpha), DOGRULAMA setindeki isaretli hatalarin yuzdeligidir.
Dogrulama kullanilir cunku test setinden alip test setinde olcmek dongusel olur.

Sonra TEST setinde ampirik kapsama olculur: gercek deger araligin icinde mi?

UC KAPSAMA TESTI (marjinal yetmez)
-----------------------------------
1) MARJINAL   : genel kapsama, nominal seviyeye esit mi?
2) SERA BAZLI : her serada ayri ayri tutuyor mu?
3) KOSULLU    : gunun saatine ve son donem oynakligina gore tutuyor mu?

Ucuncusu kritiktir. Marjinal kapsama dogru ama kosullu kapsama bozuksa,
aralikar tam da onemsedigimiz durumlarda (hizli degisim, uc degerler)
yaniltici olur — ve karar katmani en cok orada uyari verir.

ADIM SECIMI: kalibrasyon, ufuk ORTALAMASI uzerinde degil, karar katmaninin
kullanacagi TERMINAL DEGER uzerinde yapilir (t+3h icin adim 36, t+6h icin
adim 72). Cunku esik kurali "6 saat sonra EC 6'yi asacak mi" diye sorar,
"6 saat boyunca ortalama EC ne olacak" diye degil.

ON KOSUL: agc_all_in_one.py exec edilmis olmali.
SURE: ~25 dakika (dogrulama + test, 6 multi + 48 single checkpoint)

CIKTI:
  kalibrasyon_ham.parquet    - pencere basina y_true / y_pred (val + test)
  kalibrasyon_ozet.csv       - hedef x ufuk x nominal seviye: ampirik kapsama
  kalibrasyon_kosullu.csv    - sera ve saat bazinda kapsama
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ADIMLAR = {"3h": 36, "6h": 72}          # terminal adim (1-tabanli -> indeks 35/71)
SEVIYELER = [0.50, 0.80, 0.90, 0.95, 0.99]


def _kontrol():
    eksik = [k for k in ["load_arrays", "collect_starts", "compute_norm_stats",
                         "WindowSequence", "get_raw_eval_data", "ANCHOR_BY_TARGET",
                         "DEFAULT_ANCHOR", "RESIDUAL_MODE", "BATCH_SIZE",
                         "MODEL_SIZE", "FEATURE_SETS"] if k not in globals()]
    if eksik:
        raise RuntimeError("Once agc_all_in_one.py'yi exec edin. Eksik: " + ", ".join(eksik))


def cikar(base_dir: Path, fs_name: str, model_name: str, split: str, only_target=None):
    """Belirtilen split icin terminal adim tahmin ve gercek degerleri."""
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
        return None

    anchor = [g["ANCHOR_BY_TARGET"].get(t, g["DEFAULT_ANCHOR"]) for t in targets]
    tr = g["collect_starts"](store, "train")
    hedef_starts = g["collect_starts"](store, split)
    if not hedef_starts:
        return None
    stats = g["compute_norm_stats"](store, tr, target_idx, anchor)

    model = keras.models.load_model(ck, safe_mode=False, compile=False)
    seq = g["WindowSequence"](store, hedef_starts, target_idx, stats, g["BATCH_SIZE"], anchor)
    P = model.predict(seq, verbose=0) * stats["tgt_std"] + stats["tgt_mean"]
    Y, cipa, gh_ids = g["get_raw_eval_data"](store, hedef_starts, target_idx, anchor)
    if g["RESIDUAL_MODE"]:
        P = P + cipa

    # Pencere baslangic saati (kosullu kapsama icin)
    saatler = []
    for gh, s in hedef_starts:
        saatler.append(int(s % 288 // 12))     # pencere icindeki konumdan yaklasik saat

    kayit = []
    for ad, adim in ADIMLAR.items():
        i = adim - 1
        for j, t in enumerate(targets):
            for w in range(Y.shape[0]):
                kayit.append({"feature_set": fs_name, "model": mt, "split": split,
                              "horizon": ad, "target": t, "window_ix": w,
                              "greenhouse_id": gh_ids[w], "saat": saatler[w],
                              "y_true": float(Y[w, i, j]), "y_pred": float(P[w, i, j])})
    return pd.DataFrame(kayit)


def kapsama(val: pd.DataFrame, test: pd.DataFrame):
    """Dogrulamadan yuzdelik al, testte ampirik kapsamayi olc."""
    satir, kosullu = [], []
    anahtar = ["feature_set", "model", "horizon", "target"]

    for k, vg in val.groupby(anahtar):
        tg = test[(test[anahtar] == pd.Series(k, index=anahtar)).all(axis=1)]
        if len(tg) < 50 or len(vg) < 50:
            continue
        v_err = (vg.y_pred - vg.y_true).to_numpy()
        t_err = (tg.y_pred - tg.y_true).to_numpy()

        for s in SEVIYELER:
            a = (1 - s) / 2
            lo, hi = np.percentile(v_err, [100 * a, 100 * (1 - a)])
            icinde = (t_err >= lo) & (t_err <= hi)
            satir.append({**dict(zip(anahtar, k)), "nominal": s,
                          "ampirik": float(icinde.mean()),
                          "sapma": float(icinde.mean() - s),
                          "alt": float(lo), "ust": float(hi),
                          "genislik": float(hi - lo), "n_test": len(tg)})

            if s == 0.95:
                tg2 = tg.assign(icinde=icinde)
                for gh, gg in tg2.groupby("greenhouse_id"):
                    kosullu.append({**dict(zip(anahtar, k)), "kirilim": "sera",
                                    "deger": gh, "ampirik": float(gg.icinde.mean()),
                                    "n": len(gg)})
                tg2["dilim"] = pd.cut(tg2.saat, [-1, 5, 11, 17, 23],
                                      labels=["gece", "sabah", "oglen", "aksam"])
                for d, gg in tg2.groupby("dilim", observed=True):
                    if len(gg) > 20:
                        kosullu.append({**dict(zip(anahtar, k)), "kirilim": "saat",
                                        "deger": str(d), "ampirik": float(gg.icinde.mean()),
                                        "n": len(gg)})
                # Oynaklik: gercek degerin o hedefteki mutlak sapmasi
                med = tg2.y_true.median()
                tg2["uc_mu"] = (tg2.y_true - med).abs() > (tg2.y_true - med).abs().quantile(.80)
                for d, gg in tg2.groupby("uc_mu"):
                    kosullu.append({**dict(zip(anahtar, k)), "kirilim": "uc_deger",
                                    "deger": "uc %20" if d else "normal %80",
                                    "ampirik": float(gg.icinde.mean()), "n": len(gg)})
    return pd.DataFrame(satir), pd.DataFrame(kosullu)


def run(base_dir: Path, feature_sets=("core_grodan",), models=("gru", "lstm", "tcn"),
        single_target=True):
    _kontrol()
    g = globals()
    parcalar = []
    for fs in feature_sets:
        _, _, fs_t = g["FEATURE_SETS"][fs]
        for m in models:
            for tgt in [None] + (list(fs_t) if single_target else []):
                for split in ("val", "test"):
                    d = cikar(base_dir, fs, m, split, tgt)
                    if d is not None:
                        parcalar.append(d)
                print(f"  {fs}/{m}/{tgt or 'ALL':10s} tamam")

    ham = pd.concat(parcalar, ignore_index=True)
    ham.to_parquet(base_dir / "kalibrasyon_ham.parquet", index=False)
    val = ham[ham.split == "val"]; test = ham[ham.split == "test"]
    print(f"\ndogrulama {len(val):,} · test {len(test):,} satir")

    ozet, kosullu = kapsama(val, test)
    ozet.to_csv(base_dir / "kalibrasyon_ozet.csv", index=False)
    kosullu.to_csv(base_dir / "kalibrasyon_kosullu.csv", index=False)

    print("\n" + "=" * 82)
    print("1. MARJINAL KAPSAMA — nominal vs ampirik (en iyi model, hedef basina)")
    print("=" * 82)
    eniyi = (ozet[ozet.nominal == 0.95].sort_values("genislik")
             .groupby(["horizon", "target"]).head(1)[["horizon", "target", "model"]])
    se = ozet.merge(eniyi, on=["horizon", "target", "model"])
    for h in ["3h", "6h"]:
        p = se[se.horizon == h].pivot_table(index="target", columns="nominal", values="ampirik")
        print(f"\n--- {h} ---")
        print(p.round(3).to_string())

    print("\n" + "=" * 82)
    print("2. KALIBRASYON SAPMASI  (ampirik − nominal, %95 seviyesinde)")
    print("   |sapma| < 0.03 -> iyi · 0.03-0.08 -> kabul edilebilir · >0.08 -> BOZUK")
    print("=" * 82)
    s95 = se[se.nominal == 0.95].copy()
    s95["durum"] = np.where(s95.sapma.abs() < .03, "iyi",
                     np.where(s95.sapma.abs() < .08, "kabul edilebilir", "BOZUK"))
    print(s95[["horizon", "target", "model", "ampirik", "sapma", "genislik", "durum"]]
          .sort_values(["horizon", "sapma"]).round(3).to_string(index=False))
    print("\n" + s95.durum.value_counts().to_string())

    print("\n" + "=" * 82)
    print("3. KOSULLU KAPSAMA — marjinal dogru olsa bile burada bozulabilir")
    print("=" * 82)
    if len(kosullu):
        km = kosullu.merge(eniyi, on=["horizon", "target", "model"])
        for kir in ["sera", "saat", "uc_deger"]:
            s = km[km.kirilim == kir]
            if s.empty:
                continue
            p = s.pivot_table(index="target", columns="deger", values="ampirik")
            print(f"\n--- {kir} bazinda (%95 nominal) ---")
            print(p.round(3).to_string())
            en_kotu = p.min().min()
            print(f"    en dusuk kapsama: {en_kotu:.3f}" +
                  ("   <-- BOZUK, aralik bu durumda yaniltici" if en_kotu < .85 else ""))

    print("\nKaydedildi: kalibrasyon_ozet.csv · kalibrasyon_kosullu.csv · kalibrasyon_ham.parquet")
    return ozet, kosullu


if __name__ == "__main__":
    BASE_DIR = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")
    run(BASE_DIR)
