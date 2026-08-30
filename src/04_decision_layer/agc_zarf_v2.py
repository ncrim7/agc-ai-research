"""
AGC - ZARF ESIKLERI v2: MEVSIM-ICI DUZELTME
==============================================
DUZELTILEN HATA (Faz 6 raporuyla bulundu, bkz. Karar Gunlugu Bolum 5)

agc_decision_kb.py'deki zarf_hesapla yalnizca GUNDUZ/GECE ayrimi yapiyordu,
MEVSIM ayrimi yoktu. p5/p95 TUM SEZONDAN hesaplaninca, sistematik olarak
donen degiskenlerde (orn. Rhair kista yuksek, ilkbaharda dusuk) esikler
bir mevsimde HIC tetiklenmiyor, digerinde SUREKLI tetikleniyordu.

Faz 6 raporu bunu olcup dogruladi: tum-sezon esiklerinde kurallarin %3'u
tasarim oraninda, %45'i hic, %32'si tasarimin 4 katindan fazla tetiklenmis
(dengesizlik medyani 153.6x). Mevsim ici yuzdeliklere gecince 1.5x'e indi.

YONTEM — kac bloga bolmeli, TAHMIN degil OLCUM
-------------------------------------------------
Sezon N bloga bolunur (aday: 2,3,4,6,8,12). Her aday icin CAPRAZ DOGRULAMA:
blogun ILK YARISINDAN esik hesaplanir, IKINCI YARISINDA asim orani olculur.
Doğru N, asim oranini tasarim hedefine (%10, p5+p95 oldugu icin) en yakin
tutan VE ornek kuculmesinden gurultulenmeyen noktadir. Bu, HER HEDEF icin
AYRI hesaplanir -- yavas degisen (EC_slab) ve hizli degisen (Rhair)
degiskenler farkli optimal blok sayisina sahip olabilir.

Sentetik on-testte (mevsimsel donen tek degisken) N=6 civari optimal
cikti, ama bu GERCEK veride HER HEDEF icin dogrulanmalidir -- script bunu
otomatik yapar, sabit N varsaymaz.

CIKTI: dkb_zarf_v2.csv (blok bilgisiyle) + zarf_blok_secimi_rapor.csv
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HEDEFLER = ["Tair", "Rhair", "CO2air", "HumDef", "Tot_PAR",
            "EC_slab1", "EC_slab2", "WC_slab1", "WC_slab2", "t_slab1", "t_slab2"]
ADAY_BLOK = [1, 2, 3, 4, 6, 8, 12]
TASARIM_ORANI = 0.10          # p5 + p95 -> toplam %10 asim beklenir
MIN_ORNEKLEM = 300            # capraz dogrulamada train yarisi icin alt sinir


def capraz_dogrulama(deger: np.ndarray, n_blok: int) -> dict:
    """Bir hedef-sera dizisi icin, n_blok semasinin ne kadar iyi genelledigini
    olcer. Her blogun ilk yarisindan esik, ikinci yarisinda test."""
    n = len(deger)
    sinir = np.linspace(0, n, n_blok + 1).astype(int)
    asimlar, orneklem = [], []
    for b in range(n_blok):
        blok = deger[sinir[b]:sinir[b + 1]]
        if len(blok) < MIN_ORNEKLEM * 2:
            continue
        yari = len(blok) // 2
        egt, tst = blok[:yari], blok[yari:]
        alt, ust = np.percentile(egt, 5), np.percentile(egt, 95)
        asim = float(((tst < alt) | (tst > ust)).mean())
        asimlar.append(asim)
        orneklem.append(len(egt))
    if len(asimlar) < max(2, n_blok // 2):
        return {"gecerli": False}
    asimlar = np.array(asimlar)
    sapma = float(np.abs(asimlar - TASARIM_ORANI).mean())       # tasarimdan ort. sapma
    dengesizlik = float(asimlar.max() / max(asimlar.min(), 1e-6))
    return {"gecerli": True, "sapma": sapma, "dengesizlik": dengesizlik,
            "min_orneklem": min(orneklem), "n_gecerli_blok": len(asimlar)}


def en_iyi_blok_sec(deger: np.ndarray) -> tuple[int, pd.DataFrame]:
    """Her aday blok sayisi icin capraz dogrulama, en dusuk 'sapma'yi veren
    N secilir (esit sapmada daha az blok -> daha guvenilir orneklem tercih)."""
    sat = []
    for nb in ADAY_BLOK:
        r = capraz_dogrulama(deger, nb)
        if r.get("gecerli"):
            sat.append({"n_blok": nb, **r})
    if not sat:
        return 1, pd.DataFrame()
    d = pd.DataFrame(sat)
    # tasarimdan sapma en dusuk olan; esitlikte daha az blok tercih edilir
    d = d.sort_values(["sapma", "n_blok"])
    return int(d.iloc[0].n_blok), d


def zarf_hesapla_v2(df: pd.DataFrame, hedefler: list[str], alt=5, ust=95) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Her sera x hedef icin, CAPRAZ DOGRULAMAYLA secilen blok sayisiyla
    mevsim-ici zarf. 'tumu' (blok=0, tum sezon) DE saklanir -- KIYAS icin,
    KULLANIM icin degil."""
    df = df.copy()
    df["gunduz"] = df["Tot_PAR"] > 20
    zarf_sat, secim_sat = [], []

    for h in hedefler:
        if h not in df.columns:
            continue
        for gh, g in df.groupby("greenhouse_id", sort=False):
            g = g.sort_values("Time").reset_index(drop=True)
            deger = g[h].to_numpy(dtype=float)
            gecerli = np.isfinite(deger)
            if gecerli.sum() < MIN_ORNEKLEM * 4:
                continue

            n_blok, rapor = en_iyi_blok_sec(deger[gecerli])
            secim_sat.append({"hedef": h, "sera": gh, "secilen_n_blok": n_blok,
                              **{f"sapma_blok{r.n_blok}": r.sapma for _, r in rapor.iterrows()}})

            # --- ESKI (hatali) referans: tum sezon, tumu/gunduz/gece ---
            for donem, alt_g in [("tumu", g), ("gunduz", g[g.gunduz]), ("gece", g[~g.gunduz])]:
                s = alt_g[h].dropna()
                if len(s) < 200:
                    continue
                zarf_sat.append({"hedef": h, "sera": gh, "donem": donem, "blok": -1,
                                 "n": len(s), "zarf_alt": float(np.percentile(s, alt)),
                                 "zarf_ust": float(np.percentile(s, ust)),
                                 "medyan": float(s.median()),
                                 "p1": float(np.percentile(s, 1)),
                                 "p99": float(np.percentile(s, 99))})

            # --- YENI (duzeltilmis): secilen blok sayisiyla mevsim-ici ---
            n = len(g)
            sinir = np.linspace(0, n, n_blok + 1).astype(int)
            for b in range(n_blok):
                blok_df = g.iloc[sinir[b]:sinir[b + 1]]
                t_bas, t_bit = blok_df.Time.min(), blok_df.Time.max()
                for donem, alt_g in [("tumu", blok_df), ("gunduz", blok_df[blok_df.gunduz]),
                                     ("gece", blok_df[~blok_df.gunduz])]:
                    s = alt_g[h].dropna()
                    if len(s) < 100:
                        continue
                    zarf_sat.append({"hedef": h, "sera": gh, "donem": donem, "blok": b,
                                     "n": len(s), "zarf_alt": float(np.percentile(s, alt)),
                                     "zarf_ust": float(np.percentile(s, ust)),
                                     "medyan": float(s.median()),
                                     "p1": float(np.percentile(s, 1)),
                                     "p99": float(np.percentile(s, 99)),
                                     "blok_baslangic": t_bas, "blok_bitis": t_bit})

    return pd.DataFrame(zarf_sat), pd.DataFrame(secim_sat)


def dogrulama_karsilastir(df: pd.DataFrame, zarf: pd.DataFrame, hedefler: list[str]) -> pd.DataFrame:
    """ESKI (blok=-1, tum sezon) ile YENI (blok-ozgu) semanin, TAM VERIDE
    (capraz dogrulama disi) tetiklenme dengesizligini karsilastirir --
    Faz 6 raporundaki 'eski 153.6x -> yeni 1.5x' olcumunun bu veri setinde
    tekrarlanip tekrarlanmadigini gosterir."""
    df = df.copy()
    df["gunduz"] = df["Tot_PAR"] > 20
    sonuc = []
    for h in hedefler:
        if h not in df.columns:
            continue
        for gh, g in df.groupby("greenhouse_id", sort=False):
            g = g.sort_values("Time").reset_index(drop=True)
            n = len(g)

            esk = zarf[(zarf.hedef == h) & (zarf.sera == gh) &
                      (zarf.donem == "tumu") & (zarf.blok == -1)]
            if esk.empty:
                continue
            e_alt, e_ust = esk.zarf_alt.iloc[0], esk.zarf_ust.iloc[0]

            yen = zarf[(zarf.hedef == h) & (zarf.sera == gh) &
                      (zarf.donem == "tumu") & (zarf.blok >= 0)].sort_values("blok")
            if yen.empty:
                continue
            n_blok = len(yen)
            sinir = np.linspace(0, n, n_blok + 1).astype(int)

            esk_asim, yen_asim = [], []
            for b, (_, r) in enumerate(yen.iterrows()):
                blok_deger = g[h].iloc[sinir[b]:sinir[b + 1]].dropna()
                if len(blok_deger) < 50:
                    continue
                esk_asim.append(float(((blok_deger < e_alt) | (blok_deger > e_ust)).mean()))
                yen_asim.append(float(((blok_deger < r.zarf_alt) | (blok_deger > r.zarf_ust)).mean()))

            if len(esk_asim) < 2:
                continue
            esk_asim, yen_asim = np.array(esk_asim), np.array(yen_asim)
            sonuc.append({
                "hedef": h, "sera": gh, "n_blok": n_blok,
                "eski_dengesizlik": float(esk_asim.max() / max(esk_asim.min(), 1e-6)),
                "yeni_dengesizlik": float(yen_asim.max() / max(yen_asim.min(), 1e-6)),
                "eski_sapma": float(np.abs(esk_asim - TASARIM_ORANI).mean()),
                "yeni_sapma": float(np.abs(yen_asim - TASARIM_ORANI).mean()),
            })
    return pd.DataFrame(sonuc)


def run(base_dir: Path):
    f = base_dir / "common_core_with_grodan_strict.parquet"
    df = pd.read_parquet(f, columns=["Time", "greenhouse_id"] + HEDEFLER)
    print(f"Yuklendi: {len(df):,} satir\n")

    print("Blok sayisi seciliyor (capraz dogrulama, her hedef x sera icin)...")
    zarf, secim = zarf_hesapla_v2(df, HEDEFLER)
    zarf.to_csv(base_dir / "dkb_zarf_v2.csv", index=False)
    secim.to_csv(base_dir / "zarf_blok_secimi_rapor.csv", index=False)

    print("\n" + "=" * 80)
    print("1. SECILEN BLOK SAYISI — hedef bazinda dagilim")
    print("=" * 80)
    print(secim.groupby("hedef").secilen_n_blok.agg(["mean", "median", "min", "max"]).round(1).to_string())

    print("\n" + "=" * 80)
    print("2. DOGRULAMA — eski (tum sezon) vs yeni (mevsim-ici) dengesizlik")
    print("   Faz 6 raporundaki olcumun bu veri setinde tekrarlanip")
    print("   tekrarlanmadigini gosterir (orada: 153.6x -> 1.5x)")
    print("=" * 80)
    dog = dogrulama_karsilastir(df, zarf, HEDEFLER)
    dog.to_csv(base_dir / "zarf_dogrulama_karsilastirma.csv", index=False)
    ozet = dog.groupby("hedef")[["eski_dengesizlik", "yeni_dengesizlik",
                                  "eski_sapma", "yeni_sapma"]].median()
    print(ozet.round(2).to_string())
    print(f"\n  GENEL MEDYAN: eski dengesizlik {dog.eski_dengesizlik.median():.1f}x "
          f"-> yeni {dog.yeni_dengesizlik.median():.1f}x")
    print(f"  GENEL MEDYAN: eski sapma {dog.eski_sapma.median():.3f} "
          f"-> yeni {dog.yeni_sapma.median():.3f}  (tasarim hedefi: 0.10 sapma = 0)")

    kotulesen = dog[dog.yeni_dengesizlik > dog.eski_dengesizlik]
    if len(kotulesen):
        print(f"\n  UYARI: {len(kotulesen)} hedef-sera kombinasyonunda YENI sema"
              f" DAHA KOTU dengesizlik verdi:")
        print(kotulesen[["hedef", "sera", "eski_dengesizlik", "yeni_dengesizlik"]]
              .round(2).to_string(index=False))
    else:
        print("\n  Hicbir hedef-sera kombinasyonunda yeni sema eskiden kotu degil.")

    print(f"\nKaydedildi: dkb_zarf_v2.csv · zarf_blok_secimi_rapor.csv · "
          f"zarf_dogrulama_karsilastirma.csv")
    return zarf, secim, dog


if __name__ == "__main__":
    BASE_DIR = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")
    run(BASE_DIR)
