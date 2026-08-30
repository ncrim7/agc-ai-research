"""
AGC - RISK MOTORU GERIYE DONUK DEGERLENDIRME (Backtest)
=========================================================
Risk motoru uyari uretiyor. Bu script o uyarilarin ISABETLI olup olmadigini
olcer. Bu olcum olmadan sistem bir demodur; olcumle birlikte olculmus bir
sistemdir.

YONTEM
------
Test donemi (Mayis) boyunca her pencere icin:
  1) Motor uyari verir miydi?      -> y_pred + DKB kurallari
  2) Gercekte olay oldu mu?        -> y_true
  3) Karsilastir                   -> dogru yakalama / yanlis alarm / kacirma

IKI GERCEK-DURUM TANIMI (ikisi de hesaplanir)
----------------------------------------------
A) TERMINAL : "t+6h aninda esik asilmis miydi?"
   Mevcut veriyle hesaplanir (kalibrasyon_ham.parquet).

B) PENCERE  : "6 saatlik pencerenin HERHANGI bir aninda esik asildi mi?"
   Ham parquet'ten cikti trajektorisi okunur.

B daha dogrudur — risk yonetiminde onemli olan "6. saatte ne oldu" degil,
"bu 6 saat icinde tehlikeli bir ana girildi mi". Aradaki fark da bir
bulgudur: terminal adima bakmak olaylarin ne kadarini kaciriyor?

MODEL SECIMI: her hedef-ufuk icin kalibrasyon analizinde en dar aralikli
bulunan model kullanilir (kalibrasyon raporuyla tutarli).

TEMEL ORAN UYARISI: zarf esikleri p5/p95 oldugu icin, tanim geregi verinin
~%5'i her kuyrukta disaridadir. Yani olay temel orani ~%5-10'dur. Precision
bu temel orana gore yorumlanmalidir; %50 precision, temel oran %5 iken
10 kat iyilesme demektir.

CIKTI: backtest_ozet.csv · backtest_detay.csv · backtest_karsilastirma.csv
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

GECMIS, GELECEK = 288, 72
ADIM = {"3h": 36, "6h": 72}
P_ESIK = 0.50            # 'orta' hassasiyet — kullanici secimi


# ----------------------------------------------------------------------
def en_iyi_modeller(dkb: pd.DataFrame, ham: pd.DataFrame) -> dict:
    """Kalibrasyon ile ayni secim: hedef-ufuk basina en dar aralikli model."""
    val = ham[ham.split == "val"].copy(); test = ham[ham.split == "test"]
    val["err"] = val.y_pred - val.y_true
    g = (val.groupby(["horizon", "target", "model"]).err
            .apply(lambda s: np.percentile(s, 97.5) - np.percentile(s, 2.5))
            .reset_index(name="genislik"))
    mevcut = set(zip(test.horizon, test.target, test.model))
    g = g[[tuple(x) in mevcut for x in zip(g.horizon, g.target, g.model)]]
    en = g.sort_values("genislik").groupby(["horizon", "target"]).head(1)
    return {(r.target, r.horizon): r.model for r in en.itertuples()}


def sigma_tablosu(dkb: pd.DataFrame) -> dict:
    g = dkb.drop_duplicates(["hedef", "ufuk"])
    return {(r.hedef, r.ufuk): (r.guven,
            r.aralik_genislik / 3.92 if pd.notna(r.aralik_genislik) else np.nan)
            for r in g.itertuples()}


def uyari_verir_mi(tahmin, sigma, esik, yon, guven) -> tuple[bool, float]:
    """Risk motorunun karar mantigi — agc_risk_motoru ile ayni."""
    if guven == "KAPSAM_DISI":
        return False, np.nan
    if guven == "SAYISAL" and np.isfinite(sigma) and sigma > 0:
        z = (tahmin - esik) / sigma
        p = float(stats.norm.cdf(z) if yon == "yuksek" else stats.norm.cdf(-z))
        return p >= P_ESIK, p
    # KALITATIF: nokta tahmini esigi asiyorsa uyari, olasilik verilmez
    return (tahmin > esik if yon == "yuksek" else tahmin < esik), np.nan


# ----------------------------------------------------------------------
def pencere_gercek(base_dir: Path, hedefler: list[str]) -> pd.DataFrame | None:
    """B yaklasimi: her test penceresi icin cikti araligindaki min/max.

    collect_starts ile ayni siralamayi uretir; window_ix bu sirayla eslesir.
    """
    f = base_dir / "common_core_with_grodan_strict.parquet"
    wf = base_dir / "window_index_grodan.csv"
    if not (f.exists() and wf.exists()):
        print("  UYARI: ham parquet veya pencere indeksi yok -> B yaklasimi atlanacak")
        return None

    df = pd.read_parquet(f, columns=["Time", "greenhouse_id"] + hedefler)
    w = pd.read_csv(wf)
    kayit, ix = [], 0
    for gh, grp in df.groupby("greenhouse_id", sort=False):
        grp = grp.sort_values("Time").reset_index(drop=True)
        arr = grp[hedefler].to_numpy()
        st = w.loc[(w.greenhouse_id == gh) & (w.split == "test"), "input_start"].to_numpy()
        for s in st:
            for ad, adim in ADIM.items():
                dilim = arr[s + GECMIS: s + GECMIS + adim]
                for j, h in enumerate(hedefler):
                    kayit.append({"greenhouse_id": gh, "window_ix": ix,
                                  "horizon": ad, "target": h,
                                  "pencere_min": float(np.nanmin(dilim[:, j])),
                                  "pencere_max": float(np.nanmax(dilim[:, j]))})
            ix += 1
    return pd.DataFrame(kayit)


def olay_var_mi(deger, esik, yon) -> bool:
    return deger > esik if yon == "yuksek" else deger < esik


# ----------------------------------------------------------------------
def calistir(base_dir: Path):
    dkb = pd.read_csv(base_dir / "decision_knowledge_base.csv")
    ham = pd.read_parquet(base_dir / "kalibrasyon_ham.parquet")
    test = ham[ham.split == "test"].copy()

    sec = en_iyi_modeller(dkb, ham)
    sig = sigma_tablosu(dkb)
    hedefler = sorted(dkb.hedef.unique())

    print("Pencere ici gercek degerler cikariliyor (B yaklasimi)...")
    pen = pencere_gercek(base_dir, hedefler)

    # sera bazli zarf + ortak hasar kurallari
    kurallar = dkb[["hedef", "ufuk", "sera", "esik_turu", "esik", "yon",
                    "guven", "aksiyon"]].drop_duplicates()

    print("Backtest calisiyor...\n")
    sat = []
    for (h, u), model in sec.items():
        guven, sigma = sig.get((h, u), ("KAPSAM_DISI", np.nan))
        alt = test[(test.target == h) & (test.horizon == u) & (test.model == model)]
        if alt.empty:
            continue
        kr = kurallar[(kurallar.hedef == h) & (kurallar.ufuk == u)]

        for _, k in kr.iterrows():
            hedef_sera = None if k.sera == "TUMU" else k.sera
            a = alt if hedef_sera is None else alt[alt.greenhouse_id == hedef_sera]
            if a.empty:
                continue

            uyari, olas = zip(*[uyari_verir_mi(v, sigma, k.esik, k.yon, guven)
                                for v in a.y_pred])
            uyari = np.array(uyari)
            gercekA = np.array([olay_var_mi(v, k.esik, k.yon) for v in a.y_true])

            gercekB = None
            if pen is not None:
                m = pen[(pen.target == h) & (pen.horizon == u)]
                if hedef_sera:
                    m = m[m.greenhouse_id == hedef_sera]
                m = m.set_index(["greenhouse_id", "window_ix"])
                idx = list(zip(a.greenhouse_id, a.window_ix))
                ort = m.reindex(idx)
                deg = ort.pencere_max.to_numpy() if k.yon == "yuksek" else ort.pencere_min.to_numpy()
                gercekB = np.array([olay_var_mi(v, k.esik, k.yon) if np.isfinite(v) else False
                                    for v in deg])

            for etiket, gercek in [("A_terminal", gercekA)] + \
                                  ([("B_pencere", gercekB)] if gercekB is not None else []):
                TP = int((uyari & gercek).sum()); FP = int((uyari & ~gercek).sum())
                FN = int((~uyari & gercek).sum()); TN = int((~uyari & ~gercek).sum())
                sat.append({"hedef": h, "ufuk": u, "sera": k.sera, "esik_turu": k.esik_turu,
                            "yon": k.yon, "esik": k.esik, "guven": guven, "yaklasim": etiket,
                            "n": len(a), "TP": TP, "FP": FP, "FN": FN, "TN": TN,
                            "olay_orani": float(gercek.mean()),
                            "uyari_orani": float(uyari.mean())})

    d = pd.DataFrame(sat)
    if d.empty:
        print("Sonuc uretilemedi."); return None
    d["precision"] = d.TP / (d.TP + d.FP).replace(0, np.nan)
    d["recall"] = d.TP / (d.TP + d.FN).replace(0, np.nan)
    d["F1"] = 2 * d.precision * d.recall / (d.precision + d.recall)
    d["yanlis_alarm_orani"] = d.FP / (d.FP + d.TN).replace(0, np.nan)
    d["kazanc"] = d.precision / d.olay_orani.replace(0, np.nan)   # temel orana gore kat
    d.to_csv(base_dir / "backtest_detay.csv", index=False)

    # ---------------- Ozetler ----------------
    print("=" * 92)
    print("1. GENEL PERFORMANS — yaklasim ve guven seviyesine gore")
    print("=" * 92)
    for y in sorted(d.yaklasim.unique()):
        s = d[d.yaklasim == y]
        g = s.groupby("guven").agg(
            kural=("hedef", "size"), TP=("TP", "sum"), FP=("FP", "sum"),
            FN=("FN", "sum"), TN=("TN", "sum"))
        g["precision"] = (g.TP / (g.TP + g.FP)).round(3)
        g["recall"] = (g.TP / (g.TP + g.FN)).round(3)
        g["F1"] = (2 * g.precision * g.recall / (g.precision + g.recall)).round(3)
        print(f"\n--- {y} ---")
        print(g.to_string())

    print("\n" + "=" * 92)
    print("2. HEDEF BAZINDA (zarf kurallari, B yaklasimi varsa onunla)")
    print("=" * 92)
    tercih = "B_pencere" if "B_pencere" in d.yaklasim.values else "A_terminal"
    z = d[(d.yaklasim == tercih) & (d.esik_turu == "ZARF")]
    hz = z.groupby(["hedef", "ufuk", "guven"]).agg(
        TP=("TP", "sum"), FP=("FP", "sum"), FN=("FN", "sum"), TN=("TN", "sum"),
        olay=("olay_orani", "mean"))
    hz["precision"] = (hz.TP / (hz.TP + hz.FP)).round(3)
    hz["recall"] = (hz.TP / (hz.TP + hz.FN)).round(3)
    hz["temel_oran"] = hz.olay.round(3)
    hz["kazanc_kat"] = (hz.precision / hz.temel_oran).round(1)
    print(hz[["TP", "FP", "FN", "TN", "temel_oran", "precision", "recall", "kazanc_kat"]]
          .sort_values("precision", ascending=False).to_string())

    print("\n" + "=" * 92)
    print("3. HASAR ESIKLERI — koruma kurallari ne kadar tetiklendi?")
    print("=" * 92)
    hs = d[(d.yaklasim == tercih) & (d.esik_turu == "HASAR")]
    if len(hs):
        hh = hs.groupby(["hedef", "yon", "esik"]).agg(
            TP=("TP", "sum"), FP=("FP", "sum"), FN=("FN", "sum"),
            olay=("olay_orani", "mean")).round(4)
        print(hh.to_string())
        print(f"\n  Toplam gercek hasar olayi: {int(hs.TP.sum()+hs.FN.sum())}")
    else:
        print("  Hasar kurali degerlendirilemedi")

    # ---------------- A vs B karsilastirmasi ----------------
    if "B_pencere" in d.yaklasim.values:
        print("\n" + "=" * 92)
        print("4. TERMINAL vs PENCERE — terminal adima bakmak neyi kaciriyor?")
        print("=" * 92)
        p = d.pivot_table(index=["hedef", "ufuk"], columns="yaklasim",
                          values="olay_orani", aggfunc="mean")
        if {"A_terminal", "B_pencere"}.issubset(p.columns):
            p["kacirilan_kat"] = (p.B_pencere / p.A_terminal.replace(0, np.nan)).round(2)
            print(p.round(4).sort_values("kacirilan_kat", ascending=False).to_string())
            ort = p.kacirilan_kat.mean()
            print(f"\n  Ortalama: pencere ici olay orani, terminal adimin {ort:.2f} kati")
            print("  -> Terminal adima bakmak, olaylarin onemli kismini gormuyor.")
        p.to_csv(base_dir / "backtest_karsilastirma.csv")

    # ---------------- Nihai ozet ----------------
    print("\n" + "=" * 92)
    print("5. NIHAI TABLO")
    print("=" * 92)
    s = d[d.yaklasim == tercih]
    TP, FP, FN, TN = int(s.TP.sum()), int(s.FP.sum()), int(s.FN.sum()), int(s.TN.sum())
    print(f"   {'':22s}{'Gercekten oldu':>16s}{'Olmadi':>12s}")
    print(f"   {'Uyari verdi':22s}{TP:>16,}{FP:>12,}")
    print(f"   {'Uyari vermedi':22s}{FN:>16,}{TN:>12,}")
    pr = TP / max(TP + FP, 1); rc = TP / max(TP + FN, 1)
    print(f"\n   Precision (uyarilarin dogruluk orani) : {pr:.3f}")
    print(f"   Recall    (olaylarin yakalanma orani)  : {rc:.3f}")
    print(f"   F1                                     : {2*pr*rc/max(pr+rc,1e-9):.3f}")
    print(f"   Temel olay orani                       : {s.olay_orani.mean():.3f}")
    print(f"   -> precision temel orana gore {pr/max(s.olay_orani.mean(),1e-9):.1f} kat iyi")

    d.to_csv(base_dir / "backtest_ozet.csv", index=False)
    print(f"\nKaydedildi: backtest_detay.csv · backtest_ozet.csv")
    return d


if __name__ == "__main__":
    BASE_DIR = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")
    calistir(BASE_DIR)
