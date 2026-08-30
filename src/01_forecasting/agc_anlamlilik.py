"""
AGC - ISTATISTIKSEL ANLAMLILIK TESTI
=====================================
SORU: Tablolardaki farklar gercek mi, gurultu mu?
  "TCN Tair'de %10.7 kazandi"  -> muhtemelen gercek
  "TCN CO2air'de %1.8 kazandi" -> gurultu olabilir

GIRDI: pencere_hatalari.parquet (dogrulanmis pencere basina hatalar)

UC YONTEM, BILINCLI OLARAK BIRLIKTE RAPORLANIYOR
-------------------------------------------------
1) NAIF Diebold-Mariano
   Gozlemlerin BAGIMSIZ oldugunu varsayar. Bizim pencerelerimiz stride=12
   ile uretildi ve 360 adim uzunlugunda -> ardisik ~30 pencere ORTUSUYOR.
   Bu varsayim ihlal edildigi icin naif test HER FARKI anlamli bulur.
   Yanlis oldugunu bile bile raporluyoruz: dogru testle arasindaki fark,
   ortusen pencere probleminin buyuklugunu gosteren bir BULGUDUR.

2) HAC-duzeltmeli DM (Newey-West)
   Otokorelasyonu varyans tahmininde hesaba katar. Gecikme sayisi
   pencere ortusmesinden turetilir: (288+72)/12 = 30 pencere.

3) BLOK BOOTSTRAP guven araligi
   Ardisik pencereleri BLOK halinde ornekler, boylece otokorelasyon
   yapisini korur. Dagilim varsayimi gerektirmez; en saglam yontem.

COKLU KARSILASTIRMA
-------------------
32 hedef-ufuk kombinasyonu test ediliyor. Duzeltme yapilmazsa saf sansla
~1-2 yanlis pozitif beklenir. Benjamini-Hochberg FDR uygulaniyor.

CIKTI: anlamlilik_sonuclari.csv
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

# Pencere ortusmesi: (girdi 288 + cikti 72) / stride 12 = 30 pencere
ORTUSME_PENCERE = 30
BLOK_BOYUTU = 60          # ortusmenin 2 kati - guvenli taraf
N_BOOTSTRAP = 2000
ALFA = 0.05


# ----------------------------------------------------------------------
def newey_west_varyans(d: np.ndarray, gecikme: int) -> float:
    """d dizisinin ORTALAMASININ HAC-duzeltmeli varyansi."""
    n = len(d)
    d = d - d.mean()
    gamma0 = (d @ d) / n
    toplam = gamma0
    for k in range(1, min(gecikme, n - 1) + 1):
        gk = (d[k:] @ d[:-k]) / n
        agirlik = 1.0 - k / (gecikme + 1.0)        # Bartlett cekirdegi
        toplam += 2.0 * agirlik * gk
    return max(toplam / n, 1e-300)


def dm_testi(hata_a: np.ndarray, hata_b: np.ndarray, gecikme: int = 0):
    """Diebold-Mariano. Negatif istatistik = A daha iyi (hatasi dusuk)."""
    from scipy import stats
    d = hata_a - hata_b
    n = len(d)
    ort = d.mean()
    if gecikme > 0:
        var = newey_west_varyans(d, gecikme)
    else:
        var = d.var(ddof=1) / n
    if var <= 0:
        return np.nan, np.nan
    ist = ort / np.sqrt(var)
    p = 2 * (1 - stats.norm.cdf(abs(ist)))
    return float(ist), float(p)


def blok_bootstrap(hata_a: np.ndarray, hata_b: np.ndarray,
                   blok: int = BLOK_BOYUTU, n_boot: int = N_BOOTSTRAP, seed: int = 42):
    """Fark ortalamasi icin blok bootstrap %95 guven araligi."""
    rng = np.random.default_rng(seed)
    d = hata_a - hata_b
    n = len(d)
    n_blok = int(np.ceil(n / blok))
    basla_max = max(n - blok, 0)
    ortalamalar = np.empty(n_boot)
    for b in range(n_boot):
        idx = rng.integers(0, basla_max + 1, n_blok)
        ornek = np.concatenate([d[i:i + blok] for i in idx])[:n]
        ortalamalar[b] = ornek.mean()
    alt, ust = np.percentile(ortalamalar, [2.5, 97.5])
    # p-degeri: sifirin dagilimin hangi kuyrugunda kaldigi
    p = 2 * min((ortalamalar >= 0).mean(), (ortalamalar <= 0).mean())
    return float(alt), float(ust), float(min(p, 1.0))


def bh_fdr(p: np.ndarray, alfa: float = ALFA):
    """Benjamini-Hochberg: reddedilenler ve duzeltilmis esik."""
    p = np.asarray(p, float)
    gecerli = np.isfinite(p)
    out = np.zeros(len(p), bool)
    if gecerli.sum() == 0:
        return out, np.nan
    pv = p[gecerli]
    sira = np.argsort(pv)
    m = len(pv)
    esikler = alfa * (np.arange(1, m + 1) / m)
    altinda = pv[sira] <= esikler
    if not altinda.any():
        return out, 0.0
    k = np.max(np.where(altinda)[0])
    kritik = pv[sira][k]
    tmp = np.zeros(m, bool); tmp[pv <= kritik] = True
    out[gecerli] = tmp
    return out, float(kritik)


# ----------------------------------------------------------------------
def calistir(base_dir: Path, dosya: str = "pencere_hatalari.parquet"):
    df = pd.read_parquet(base_dir / dosya)
    print(f"Yuklendi: {len(df):,} satir")
    print(f"Modeller: {df.model.nunique()} | hedefler: {df.target.nunique()}\n")

    satirlar = []
    for (fs, hor, tgt), grp in df.groupby(["feature_set", "horizon", "target"]):
        # Pencere sirasina gore hizala (otokorelasyon yapisini korumak icin sart)
        genis = grp.pivot_table(index=["greenhouse_id", "window_ix"],
                                columns="model", values="abs_error").sort_index()
        if genis.shape[1] < 2:
            continue

        derin = [c for c in genis.columns if "resid" in c]
        baz = [c for c in genis.columns if "resid" not in c]
        if not derin or not baz:
            continue

        en_iyi_derin = genis[derin].mean().idxmin()
        en_iyi_baz = genis[baz].mean().idxmin()
        a = genis[en_iyi_derin].to_numpy()
        b = genis[en_iyi_baz].to_numpy()
        gecerli = np.isfinite(a) & np.isfinite(b)
        a, b = a[gecerli], b[gecerli]
        if len(a) < 50:
            continue

        _, p_naif = dm_testi(a, b, gecikme=0)
        ist_hac, p_hac = dm_testi(a, b, gecikme=ORTUSME_PENCERE)
        alt, ust, p_boot = blok_bootstrap(a, b)

        satirlar.append({
            "feature_set": fs, "horizon": hor, "target": tgt,
            "en_iyi_derin": en_iyi_derin, "derin_MAE": round(float(a.mean()), 4),
            "en_iyi_baseline": en_iyi_baz, "baseline_MAE": round(float(b.mean()), 4),
            "fark": round(float(a.mean() - b.mean()), 4),
            "kazanc_%": round((b.mean() - a.mean()) / b.mean() * 100, 1),
            "n": len(a),
            "p_naif": p_naif, "p_HAC": p_hac, "p_bootstrap": p_boot,
            "GA_alt": round(alt, 4), "GA_ust": round(ust, 4),
            "GA_sifir_iceriyor": bool(alt <= 0 <= ust),
        })

    r = pd.DataFrame(satirlar)
    if r.empty:
        print("Karsilastirilacak cift bulunamadi.")
        return r

    for kol in ("p_naif", "p_HAC", "p_bootstrap"):
        red, _ = bh_fdr(r[kol].to_numpy())
        r[kol.replace("p_", "anlamli_")] = red

    r["SONUC"] = np.where(
        r.anlamli_HAC & r.anlamli_bootstrap & ~r.GA_sifir_iceriyor,
        np.where(r.fark < 0, "DERIN kazandi", "BASELINE kazandi"),
        "FARK YOK")

    r = r.sort_values(["feature_set", "horizon", "kazanc_%"], ascending=[True, True, False])
    r.to_csv(base_dir / "anlamlilik_sonuclari.csv", index=False)

    print("=" * 96)
    print("ANLAMLILIK SONUCLARI  (HAC + bootstrap, Benjamini-Hochberg FDR duzeltmeli)")
    print("=" * 96)
    for fs in r.feature_set.unique():
        for h in ("3h", "6h"):
            s = r[(r.feature_set == fs) & (r.horizon == h)]
            if s.empty:
                continue
            print(f"\n--- {fs} / {h} ---")
            print(s[["target", "en_iyi_derin", "derin_MAE", "en_iyi_baseline",
                     "baseline_MAE", "kazanc_%", "p_HAC", "p_bootstrap",
                     "GA_alt", "GA_ust", "SONUC"]].to_string(index=False))

    print("\n" + "=" * 96)
    print("OZET")
    print("=" * 96)
    print(r.SONUC.value_counts().to_string())
    print(f"\nNaif test anlamli bulduklari      : {r.anlamli_naif.sum()} / {len(r)}")
    print(f"HAC-duzeltmeli test anlamli       : {r.anlamli_HAC.sum()} / {len(r)}")
    print(f"Blok bootstrap anlamli            : {r.anlamli_bootstrap.sum()} / {len(r)}")
    fark = int(r.anlamli_naif.sum() - r.anlamli_HAC.sum())
    print(f"\n-> Naif test {fark} fazladan 'anlamli' uretti.")
    print("   Bu, ortusen pencerelerin bagimsizlik varsayimini nasil bozdugunun")
    print("   dogrudan olcumudur ve raporlanabilir bir bulgudur.")
    print(f"\nKaydedildi: anlamlilik_sonuclari.csv")
    return r


if __name__ == "__main__":
    BASE_DIR = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")
    calistir(BASE_DIR)
