"""
AGC - KOSULLU KALIBRASYON DUZELTMESI (Mondrian Conformal)
===========================================================
SORUN: Global tahmin araliklari, kosullu kapsamada cokuyor.

  Uc degerlerde ortalama kapsama : 0.855  (nominal 0.95)
  Oglen saatlerinde              : 0.70-0.82
  Automatoes / WC_slab2 / 6h     : 0.530

Karar katmani uyariyi tam olarak uc degerlerde verir. Orada aralik
yaniltiyorsa, sistemin urettigi tum olasiliklar gecersizdir.

TESHIS — uc ayri heteroskedastisite kaynagi:
  1) Donemsel : dogrulama Nisan, test Mayis (mevsimsel kayma)
  2) Saat     : ogleyin hata buyuk, gece kucuk
  3) Sera     : oynak seralarda (Automatoes) hata buyuk

COZUM — Mondrian Conformal Prediction
--------------------------------------
Tek bir global yuzdelik yerine, DOGRULAMA hatalarini gruplara ayirip her
grup icinde ayri yuzdelik alinir. Tahmin sirasinda pencerenin ait oldugu
grubun yuzdeligi kullanilir.

    grup = (sera, gunduz/gece)   ->  12 katman

Bu, kosullu kapsamayi TANIM GEREGI duzeltir: her grup kendi hata
dagilimindan kalibre edilir. Klasik conformal prediction'in gruplu
(Mondrian) varyantidir; dagilim varsayimi gerektirmez.

KATMAN BOYUTU KONTROLU: dogrulama setinde ~3.276 pencere var, 12 katmana
bolununce ~273 kaliyor. %95 yuzdeligi icin yeterli; daha ince kirilim
(orn. 4 saat dilimi -> 24 katman, ~137) kuyrukta guvenilmez olurdu.

KULLANIM: girdi kalibrasyon_ham.parquet (yeniden cikarim GEREKMEZ)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

SEVIYELER = [0.50, 0.80, 0.90, 0.95, 0.99]
MIN_KATMAN = 60          # bu sayidan az orneği olan katman global'e duser


def gunduz_mu(saat: pd.Series) -> pd.Series:
    return (saat >= 6) & (saat < 18)


def global_aralik(v_err: np.ndarray, s: float) -> tuple[float, float]:
    a = (1 - s) / 2
    return tuple(np.percentile(v_err, [100 * a, 100 * (1 - a)]))


def mondrian_kapsama(val: pd.DataFrame, test: pd.DataFrame, seviye: float = 0.95):
    """Her (hedef, ufuk, model) icin: global vs Mondrian kapsama karsilastirmasi."""
    anahtar = ["feature_set", "model", "horizon", "target"]
    satir, detay = [], []

    for k, vg in val.groupby(anahtar):
        maske = np.ones(len(test), bool)
        for kol, deg in zip(anahtar, k):
            maske &= (test[kol] == deg).to_numpy()
        tg = test[maske]
        if len(tg) < 50 or len(vg) < 100:
            continue

        vg = vg.assign(err=vg.y_pred - vg.y_true, grup=list(zip(
            vg.greenhouse_id, np.where(gunduz_mu(vg.saat), "gunduz", "gece"))))
        tg = tg.assign(err=tg.y_pred - tg.y_true, grup=list(zip(
            tg.greenhouse_id, np.where(gunduz_mu(tg.saat), "gunduz", "gece"))))

        # --- Global ---
        g_lo, g_hi = global_aralik(vg.err.to_numpy(), seviye)
        g_ic = (tg.err >= g_lo) & (tg.err <= g_hi)

        # --- Mondrian ---
        sinirlar, dusen = {}, 0
        for grup, gg in vg.groupby("grup"):
            if len(gg) >= MIN_KATMAN:
                sinirlar[grup] = global_aralik(gg.err.to_numpy(), seviye)
            else:
                sinirlar[grup] = (g_lo, g_hi); dusen += 1
        m_lo = tg.grup.map(lambda x: sinirlar.get(x, (g_lo, g_hi))[0]).to_numpy()
        m_hi = tg.grup.map(lambda x: sinirlar.get(x, (g_lo, g_hi))[1]).to_numpy()
        m_ic = (tg.err.to_numpy() >= m_lo) & (tg.err.to_numpy() <= m_hi)

        # --- Uc degerlerde kapsama (asil onemli olan) ---
        med = tg.y_true.median()
        uc = (tg.y_true - med).abs() > (tg.y_true - med).abs().quantile(.80)

        satir.append({**dict(zip(anahtar, k)), "n_test": len(tg), "n_dusen_katman": dusen,
                      "global_kapsama": float(g_ic.mean()),
                      "mondrian_kapsama": float(m_ic.mean()),
                      "global_uc": float(g_ic[uc.to_numpy()].mean()),
                      "mondrian_uc": float(m_ic[uc.to_numpy()].mean()),
                      "global_genislik": float(g_hi - g_lo),
                      "mondrian_genislik": float((m_hi - m_lo).mean())})

        for grup in sorted(set(tg.grup)):
            gm = (tg.grup == grup).to_numpy()
            if gm.sum() < 20:
                continue
            detay.append({**dict(zip(anahtar, k)), "sera": grup[0], "donem": grup[1],
                          "n": int(gm.sum()), "global": float(g_ic[gm].mean()),
                          "mondrian": float(m_ic[gm].mean())})
    return pd.DataFrame(satir), pd.DataFrame(detay)


def run(ham_yolu: Path, cikti_dizin: Path | None = None, seviye: float = 0.95):
    ham = pd.read_parquet(ham_yolu)
    val = ham[ham.split == "val"]; test = ham[ham.split == "test"]
    print(f"dogrulama {len(val):,} · test {len(test):,}\n")

    ozet, detay = mondrian_kapsama(val, test, seviye)

    # En dar global aralikli modeli sec (kalibrasyon raporuyla tutarli)
    eniyi = ozet.sort_values("global_genislik").groupby(["horizon", "target"]).head(1)

    print("=" * 92)
    print(f"GLOBAL vs MONDRIAN — nominal {seviye:.0%}")
    print("=" * 92)
    g = eniyi[["horizon", "target", "global_kapsama", "mondrian_kapsama",
               "global_uc", "mondrian_uc", "global_genislik", "mondrian_genislik"]]
    g = g.assign(kazanc_uc=(g.mondrian_uc - g.global_uc).round(3))
    print(g.sort_values(["horizon", "kazanc_uc"], ascending=[True, False])
          .round(3).to_string(index=False))

    print("\n" + "=" * 92)
    print("OZET")
    print("=" * 92)
    for ad, a, b in [("Marjinal kapsama", "global_kapsama", "mondrian_kapsama"),
                     ("UC DEGERLERDE kapsama", "global_uc", "mondrian_uc"),
                     ("Aralik genisligi", "global_genislik", "mondrian_genislik")]:
        o1, o2 = eniyi[a].mean(), eniyi[b].mean()
        ok = "" if ad.startswith("Aralik") else ("  <-- iyilesme" if o2 > o1 else "")
        print(f"  {ad:24s} global {o1:.3f}  ->  mondrian {o2:.3f}{ok}")

    print(f"\n  Nominal hedef: {seviye:.3f}")
    print(f"  Uc degerlerde global sapma  : {eniyi.global_uc.mean()-seviye:+.3f}")
    print(f"  Uc degerlerde mondrian sapma: {eniyi.mondrian_uc.mean()-seviye:+.3f}")

    if len(detay):
        dm = detay.merge(eniyi[["horizon", "target", "model"]], on=["horizon", "target", "model"])
        print("\n" + "=" * 92)
        print("EN KOTU KATMANLAR (global kapsamasi en dusuk 10)")
        print("=" * 92)
        w = dm.nsmallest(10, "global")[["horizon", "target", "sera", "donem", "n", "global", "mondrian"]]
        w = w.assign(fark=(w.mondrian - w["global"]).round(3))
        print(w.round(3).to_string(index=False))
        print(f"\n  Bu 10 katmanda ortalama: global {w['global'].mean():.3f} -> "
              f"mondrian {w.mondrian.mean():.3f}")

    if cikti_dizin:
        ozet.to_csv(cikti_dizin / "mondrian_ozet.csv", index=False)
        detay.to_csv(cikti_dizin / "mondrian_katman.csv", index=False)
        print(f"\nKaydedildi: {cikti_dizin}")
    return ozet, detay


if __name__ == "__main__":
    BASE = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")
    run(BASE / "kalibrasyon_ham.parquet", BASE)
