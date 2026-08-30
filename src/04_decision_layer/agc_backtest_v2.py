"""
AGC - BACKTEST v2 (tutarli karsilastirma)
===========================================
Ilk backtest'te olcum kusuru vardi: model TERMINAL degeri tahmin ederken
gercek-durum PENCERE ICI MAKSIMUM olarak tanimlanmisti. Bu script uc
degerlendirme modunu yan yana koyar ve kusuru gorunur kilar:

  A) TERMINAL <-> TERMINAL   tutarli, ama olaylarin ~yarisini gormuyor
  B) TERMINAL <-> PENCERE    TUTARSIZ (ilk backtest'teki hata)
  C) PENCERE  <-> PENCERE    tutarli VE dogru  <-- referans alinmali

C dogrudur cunku risk yonetiminde onemli olan "6. saatte ne oldu" degil,
"bu 6 saat icinde tehlikeli bir ana girildi mi".

BELIRSIZLIK YENIDEN KALIBRE EDILIR
-----------------------------------
SAYISAL olasilik hesabi icin sigma gerekir. Terminal tahmin ile pencere-max
tahmininin hata dagilimlari FARKLIDIR, bu yuzden her mod icin sigma ayri
hesaplanir — dogrulama setinden, teste bakilmadan.

Girdi : trajektori_ozeti.parquet · decision_knowledge_base.csv
Cikti : backtest_v2_detay.csv · backtest_v2_ozet.csv
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

P_ESIK = 0.50            # 'orta' hassasiyet
SEVIYE = 0.95


# ----------------------------------------------------------------------
def sigma_hesapla(val: pd.DataFrame, mod: str, yon: str) -> dict:
    """Dogrulama setinden, mod ve yone gore hata sigmasi.

    Sigma, %95 aralik genisliginden turetilir: genislik = 2*1.96*sigma.
    Bu, kalibrasyon analiziyle ayni mantiktir; teste bakilmaz.
    """
    if mod == "terminal":
        p, t = "pred_son", "true_son"
    else:
        p, t = ("pred_max", "true_max") if yon == "yuksek" else ("pred_min", "true_min")
    v = val.assign(err=val[p] - val[t])
    g = v.groupby(["model", "horizon", "target"]).err.apply(
        lambda s: (np.percentile(s, 97.5) - np.percentile(s, 2.5)) / 3.92)
    return g.to_dict()


def en_iyi_model(val: pd.DataFrame) -> dict:
    """Hedef-ufuk basina en dar terminal aralikli model (kalibrasyonla tutarli)."""
    v = val.assign(err=val.pred_son - val.true_son)
    g = (v.groupby(["horizon", "target", "model"]).err
          .apply(lambda s: np.percentile(s, 97.5) - np.percentile(s, 2.5))
          .reset_index(name="w"))
    en = g.sort_values("w").groupby(["horizon", "target"]).head(1)
    return {(r.target, r.horizon): r.model for r in en.itertuples()}


def karar(tahmin, sigma, esik, yon, guven):
    if guven == "KAPSAM_DISI":
        return np.zeros(len(tahmin), bool), np.full(len(tahmin), np.nan)
    if guven == "SAYISAL" and np.isfinite(sigma) and sigma > 0:
        z = (tahmin - esik) / sigma
        p = stats.norm.cdf(z) if yon == "yuksek" else stats.norm.cdf(-z)
        return p >= P_ESIK, p
    u = tahmin > esik if yon == "yuksek" else tahmin < esik
    return u, np.full(len(tahmin), np.nan)


# ----------------------------------------------------------------------
def run(base_dir: Path):
    tj = pd.read_parquet(base_dir / "trajektori_ozeti.parquet")
    dkb = pd.read_csv(base_dir / "decision_knowledge_base.csv")
    val, test = tj[tj.split == "val"], tj[tj.split == "test"]
    print(f"dogrulama {len(val):,} · test {len(test):,}\n")

    sec = en_iyi_model(val)
    guven = {(r.hedef, r.ufuk): r.guven
             for r in dkb.drop_duplicates(["hedef", "ufuk"]).itertuples()}
    sig = {("terminal", y): sigma_hesapla(val, "terminal", y) for y in ("yuksek", "dusuk")}
    sig.update({("pencere", y): sigma_hesapla(val, "pencere", y) for y in ("yuksek", "dusuk")})

    kurallar = dkb[["hedef", "ufuk", "sera", "esik_turu", "esik", "yon"]].drop_duplicates()

    MODLAR = {  # ad -> (tahmin kaynagi, gercek kaynagi)
        "A_ter_ter": ("terminal", "terminal"),
        "B_ter_pen": ("terminal", "pencere"),
        "C_pen_pen": ("pencere", "pencere"),
    }

    sat = []
    for _, k in kurallar.iterrows():
        h, u, yon = k.hedef, k.ufuk, k.yon
        gv = guven.get((h, u), "KAPSAM_DISI")
        model = sec.get((h, u))
        if model is None:
            continue
        a = test[(test.target == h) & (test.horizon == u) & (test.model == model)]
        if k.sera != "TUMU":
            a = a[a.greenhouse_id == k.sera]
        if a.empty:
            continue

        for ad, (tk, gk) in MODLAR.items():
            tp_kol = "pred_son" if tk == "terminal" else ("pred_max" if yon == "yuksek" else "pred_min")
            gc_kol = "true_son" if gk == "terminal" else ("true_max" if yon == "yuksek" else "true_min")
            s = sig[(tk, yon)].get((model, u, h), np.nan)

            uy, _ = karar(a[tp_kol].to_numpy(), s, k.esik, yon, gv)
            gc = (a[gc_kol] > k.esik).to_numpy() if yon == "yuksek" else (a[gc_kol] < k.esik).to_numpy()
            sat.append({"hedef": h, "ufuk": u, "sera": k.sera, "esik_turu": k.esik_turu,
                        "yon": yon, "esik": k.esik, "guven": gv, "mod": ad, "n": len(a),
                        "TP": int((uy & gc).sum()), "FP": int((uy & ~gc).sum()),
                        "FN": int((~uy & gc).sum()), "TN": int((~uy & ~gc).sum()),
                        "olay_orani": float(gc.mean())})

    d = pd.DataFrame(sat)
    d["precision"] = d.TP / (d.TP + d.FP).replace(0, np.nan)
    d["recall"] = d.TP / (d.TP + d.FN).replace(0, np.nan)
    d["F1"] = 2 * d.precision * d.recall / (d.precision + d.recall)
    d.to_csv(base_dir / "backtest_v2_detay.csv", index=False)

    def ozetle(s):
        TP, FP, FN, TN = [int(s[c].sum()) for c in ["TP", "FP", "FN", "TN"]]
        pr = TP / max(TP + FP, 1); rc = TP / max(TP + FN, 1)
        return dict(TP=TP, FP=FP, FN=FN, TN=TN, precision=round(pr, 3),
                    recall=round(rc, 3), F1=round(2 * pr * rc / max(pr + rc, 1e-9), 3),
                    olay=round(s.olay_orani.mean(), 3))

    print("=" * 84)
    print("1. UC MOD KARSILASTIRMASI (KAPSAM_DISI haric)")
    print("=" * 84)
    k = d[d.guven != "KAPSAM_DISI"]
    t = pd.DataFrame({m: ozetle(k[k["mod"] == m]) for m in MODLAR}).T
    print(t.to_string())
    print("\n  A: tutarli ama olaylari eksik sayiyor (temel oran dusuk)")
    print("  B: TUTARSIZ — ilk backtest'in hatasi, recall'i yapay olarak dusuruyor")
    print("  C: tutarli VE dogru — REFERANS ALINMALI")

    print("\n" + "=" * 84)
    print("2. C MODU — guven seviyesine gore")
    print("=" * 84)
    c = d[d["mod"] == "C_pen_pen"]
    for g in ["SAYISAL", "KALITATIF", "KAPSAM_DISI"]:
        s = c[c.guven == g]
        if s.empty:
            continue
        o = ozetle(s)
        print(f"  {g:12s} kural={len(s):3d}  TP={o['TP']:5d} FP={o['FP']:5d} FN={o['FN']:5d}  "
              f"precision={o['precision']:.3f} recall={o['recall']:.3f} temel={o['olay']:.3f}")

    print("\n" + "=" * 84)
    print("3. C MODU — hedef bazinda (ZARF kurallari)")
    print("=" * 84)
    z = c[c.esik_turu == "ZARF"].groupby(["hedef", "ufuk", "guven"]).agg(
        TP=("TP", "sum"), FP=("FP", "sum"), FN=("FN", "sum"), temel=("olay_orani", "mean"))
    z["precision"] = (z.TP / (z.TP + z.FP)).round(3)
    z["recall"] = (z.TP / (z.TP + z.FN)).round(3)
    z["kazanc_kat"] = (z.precision / z.temel).round(1)
    print(z[["TP", "FP", "FN", "temel", "precision", "recall", "kazanc_kat"]]
          .sort_values("precision", ascending=False).round(3).to_string())

    print("\n" + "=" * 84)
    print("4. OLCUM KUSURUNUN BUYUKLUGU  (B'nin C'ye gore hatasi)")
    print("=" * 84)
    p = d[d.guven != "KAPSAM_DISI"].pivot_table(
        index=["hedef", "ufuk"], columns="mod", values="recall", aggfunc="mean")
    if {"B_ter_pen", "C_pen_pen"}.issubset(p.columns):
        p["recall_kaybi"] = (p.C_pen_pen - p.B_ter_pen).round(3)
        print(p.round(3).sort_values("recall_kaybi", ascending=False).to_string())
        print(f"\n  Ortalama recall kaybi: {p.recall_kaybi.mean():+.3f}")
        print("  -> Ilk backtest, tutarsiz olcum nedeniyle sistemi bu kadar kotu gosteriyordu.")

    print("\n" + "=" * 84)
    print("5. NIHAI TABLO (C modu, KAPSAM_DISI haric)")
    print("=" * 84)
    o = ozetle(k[k["mod"] == "C_pen_pen"])
    print(f"   {'':22s}{'Gercekten oldu':>16s}{'Olmadi':>12s}")
    print(f"   {'Uyari verdi':22s}{o['TP']:>16,}{o['FP']:>12,}")
    print(f"   {'Uyari vermedi':22s}{o['FN']:>16,}{o['TN']:>12,}")
    print(f"\n   precision {o['precision']:.3f} · recall {o['recall']:.3f} · F1 {o['F1']:.3f}")
    print(f"   temel olay orani {o['olay']:.3f} -> precision temel orana gore "
          f"{o['precision']/max(o['olay'],1e-9):.1f} kat iyi")

    kd = d[(d.guven == "KAPSAM_DISI") & (d["mod"] == "C_pen_pen")]
    print(f"\n   Sistemin SUSTUGU alanda kacirilan olay: {int(kd.FN.sum()):,}")
    print("   (bu bilincli bir tercihtir: belirsizlik cok yuksek oldugu icin uyari verilmez)")

    d.to_csv(base_dir / "backtest_v2_ozet.csv", index=False)
    print(f"\nKaydedildi: backtest_v2_detay.csv")
    return d


if __name__ == "__main__":
    BASE_DIR = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")
    run(BASE_DIR)
