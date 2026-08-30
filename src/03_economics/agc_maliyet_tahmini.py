"""
AGC - MALIYET TAHMINI ve POLITIKA KARSILASTIRMASI
===================================================
Projenin modelleme emegini ekonomiye baglar.

TEMEL SORU VE TASARIM GEREKCESI
--------------------------------
Maliyet fizik degil, KONTROL KARARIDIR: elektrik=lamba, isi=boru setpoint,
CO2=dozaj. "Maliyeti tahmin etmek" = "kontrolcunun ne yapacagini tahmin etmek".

Girdi yalnizca DIS HAVA ile sinirlandirilirsa (alti sera ayni havayi yasadi ve
hava politikadan etkilenmez — DISSAL), ogrenilen sey su olur:

    "Bu hava kosullarinda, BU TAKIMIN politikasi ne kadar harcar?"

Bu, alti politikayi AYNI hava uzerinde capraz uygulamayi mumkun kilar:

    "Automatoes'un kontrolcusu bu kosullarda ne harcardi?"

Nedensel iddia YOKTUR — mudahale etkisi degil, politika karsilastirmasi yapilir.

HEDEF: onumuzdeki 6 saatin toplam maliyeti (cent/m²), skaler.
GIRDI: son 24 saatin (288 adim) hava ozetleri + tahmin penceresinin pik payi.

NOT — hour_sin/hour_cos KULLANILMAZ (proje karari, kapsam disi). Bunun yerine
"pik_pay" kullanilir: tahmin penceresinin yuzde kaci 07:00-23:00 tarifesine
denk geliyor. Bu dongusel bir zaman kodlamasi degil, dogrudan ekonomik bir
buyukluktur ve gelecek icin KESIN olarak bilinir.

IKI GIRDI VARYANTI
------------------
A) YALNIZCA HAVA   : capraz uygulama icin temiz (hava dissal)
B) HAVA + SON MALIYET : daha dogru ama capraz uygulanamaz (takima ozgu durum)

BASELINE'LAR (proje standardi)
  persistence     : onceki 6 saatin maliyeti
  seasonal_naive  : dun ayni saatteki 6 saatin maliyeti
  ortalama        : egitim setinin ortalamasi

CIKTI: maliyet_tahmin_sonuclari.csv · politika_capraz.csv
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

GECMIS, GELECEK, STRIDE = 288, 72, 12
TRAIN_FRAC, VAL_FRAC = 0.70, 0.15
HAVA = ["Tout", "Rhout", "Iglob", "Windsp", "RadSum", "Winddir",
        "Rain", "PARout", "Pyrgeo", "AbsHumOut"]
PIK_BAS, PIK_BIT = 7, 23
SEED = 42


def pencereler(n: int):
    son = n - (GECMIS + GELECEK)
    sinir = {"train": (0, int(n * TRAIN_FRAC)),
             "val": (int(n * TRAIN_FRAC), int(n * (TRAIN_FRAC + VAL_FRAC))),
             "test": (int(n * (TRAIN_FRAC + VAL_FRAC)), n)}
    out = []
    for s in range(0, son + 1, STRIDE):
        bit = s + GECMIS + GELECEK
        for ad, (lo, hi) in sinir.items():
            if lo <= s < hi:
                if bit <= hi:                      # sinir purge
                    out.append((s, ad))
                break
    return out


def oznitelik(hava: np.ndarray, s: int) -> np.ndarray:
    """288 adimlik hava penceresinden ozet oznitelikler."""
    w = hava[s:s + GECMIS]
    adim = np.arange(GECMIS, dtype=np.float64)
    ac = adim - adim.mean(); av = (ac ** 2).sum()
    egim = (ac[:, None] * (w - w.mean(0))).sum(0) / av
    # son 6 saatin ortalamasi da eklenir (yakin gecmis daha bilgilendirici)
    return np.concatenate([w.mean(0), w.std(0), w[-1], egim, w[-72:].mean(0)])


def kur(base_dir: Path):
    kol = ["Time", "greenhouse_id"] + HAVA
    df = pd.read_parquet(base_dir / "common_core_with_grodan_strict.parquet")
    yok = [c for c in HAVA if c not in df.columns]
    if yok:
        print(f"  UYARI: bulunamayan hava kolonlari {yok}")
    hv = [c for c in HAVA if c in df.columns]
    mal = pd.read_parquet(base_dir / "maliyet_serisi.parquet")
    mal["co2_eur"] = mal.co2_dos * (5 / 60) * 0.08              # duzeltilmis birim
    mal["toplam"] = mal.isi_eur + mal.elek_eur + mal.co2_eur

    veri = {}
    for gh, g in df.groupby("greenhouse_id", sort=False):
        g = g.sort_values("Time").reset_index(drop=True)
        m = mal[mal.greenhouse_id == gh].sort_values("Time").reset_index(drop=True)
        n = min(len(g), len(m))
        veri[gh] = {"hava": g[hv].to_numpy(np.float64)[:n],
                    "maliyet": m.toplam.to_numpy(np.float64)[:n] * 100,   # cent/m²
                    "saat": g.Time.dt.hour.to_numpy()[:n], "n": n}
    return veri, hv


def veri_seti(v: dict, gh: str):
    """Pencere uretimi — PROJE STANDARDI NaN politikasi:
       * CIKTI araliginda NaN varsa pencere ELENIR (uydurma hedef uretilmez)
       * GIRDI tarafindaki NaN, EGITIM bolmesi ortalamasiyla doldurulur (sizinti yok)

    Kaynak: 29-30 Mart 2020 (yaz saati gecisi) sera basina 6 satir bos —
    Tair, PipeLow, PipeGrow, AssimLight. Verinin %0.01'i, ama 72 adimlik
    pencerelere yayilinca hedefi NaN yapiyor.
    """
    d = v[gh]
    hava = np.array(d["hava"], dtype=np.float64, copy=True)
    mal = np.asarray(d["maliyet"], dtype=np.float64)

    # --- Girdi NaN'lari: yalnizca EGITIM bolmesinden hesaplanan ortalama ---
    tr_son = int(d["n"] * TRAIN_FRAC)
    ort = np.nanmean(hava[:tr_son], axis=0)
    ort = np.where(np.isfinite(ort), ort, 0.0)
    bos = ~np.isfinite(hava)
    if bos.any():
        idx = np.where(bos)
        hava[idx] = ort[idx[1]]

    X, y, sp, ps, pers, sez = [], [], [], [], [], []
    elenen = 0
    for s, split in pencereler(d["n"]):
        c0 = s + GECMIS
        cikti = mal[c0:c0 + GELECEK]
        if not np.isfinite(cikti).all():          # CIKTI NaN -> pencereyi ele
            elenen += 1
            continue
        X.append(oznitelik(hava, s))
        y.append(float(cikti.sum()))
        sp.append(split)
        st = d["saat"][c0:c0 + GELECEK]
        ps.append(float(((st >= PIK_BAS) & (st < PIK_BIT)).mean()))
        pers.append(float(np.nansum(mal[c0 - GELECEK:c0])))     # onceki 6 saat
        sez.append(float(np.nansum(mal[s:s + GELECEK])))        # dun ayni saat
    if elenen:
        print(f"    {gh}: cikti NaN nedeniyle {elenen} pencere elendi")
    X = np.array(X); ps = np.array(ps)[:, None]
    return (np.hstack([X, ps]), np.array(y), np.array(sp),
            np.array(pers), np.array(sez))


def egit(Xtr, ytr, Xva, yva):
    # Guvenlik agi — buraya NaN ulasmamali
    if not (np.isfinite(Xtr).all() and np.isfinite(ytr).all()):
        raise ValueError(f"Egitim verisinde NaN: X {np.isnan(Xtr).sum()} · y {np.isnan(ytr).sum()}")
    modeller = {}
    sc = StandardScaler().fit(Xtr)
    modeller["ridge"] = ("ridge", Ridge(alpha=10.0).fit(sc.transform(Xtr), ytr), sc)
    g = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.06,
                                      max_depth=6, l2_regularization=1.0,
                                      early_stopping=True, validation_fraction=0.15,
                                      random_state=SEED).fit(Xtr, ytr)
    modeller["gbm"] = ("gbm", g, None)
    return modeller


def olc(y, p):
    e = p - y
    ss = ((y - y.mean()) ** 2).sum()
    return dict(MAE=float(np.abs(e).mean()), RMSE=float(np.sqrt((e ** 2).mean())),
                R2=float(1 - (e ** 2).sum() / max(ss, 1e-12)))


def run(base_dir: Path):
    v, hv = kur(base_dir)
    print(f"Seralar: {list(v)} · hava kolonu {len(hv)}\n")

    sonuc, modeller_kayit = [], {}
    for gh in v:
        X, y, sp, pers, sez = veri_seti(v, gh)
        tr, va, te = sp == "train", sp == "val", sp == "test"
        print(f"{gh:15s} train {tr.sum():4d} · val {va.sum():3d} · test {te.sum():3d} · "
              f"hedef ort {y[tr].mean():.2f} cent")

        for ad, p in [("persistence", pers[te]), ("seasonal_naive", sez[te]),
                      ("ortalama", np.full(te.sum(), y[tr].mean()))]:
            sonuc.append({"sera": gh, "model": ad, **olc(y[te], p)})

        ms = egit(X[tr], y[tr], X[va], y[va])
        for ad, (_, mdl, sc) in ms.items():
            p = mdl.predict(sc.transform(X[te]) if sc else X[te])
            sonuc.append({"sera": gh, "model": ad, **olc(y[te], p)})
        modeller_kayit[gh] = (ms, X, y, sp)

    d = pd.DataFrame(sonuc)
    d.to_csv(base_dir / "maliyet_tahmin_sonuclari.csv", index=False)

    print("\n" + "=" * 78)
    print("1. MALIYET TAHMINI — 6 saatlik toplam (cent/m²)")
    print("=" * 78)
    p = d.pivot_table(index="sera", columns="model", values="MAE")
    sira = ["ortalama", "persistence", "seasonal_naive", "ridge", "gbm"]
    p = p[[c for c in sira if c in p.columns]]
    p["en_iyi"] = p.idxmin(axis=1)
    print(p.round(3).to_string())
    print("\nR²:")
    print(d.pivot_table(index="sera", columns="model", values="R2")[
        [c for c in sira if c in p.columns]].round(3).to_string())

    ort = d.groupby("model")[["MAE", "R2"]].mean().round(3).sort_values("MAE")
    print("\nOrtalama:")
    print(ort.to_string())
    eniyi = ort.index[0]
    baz = ort.loc[["persistence", "seasonal_naive"], "MAE"].min()
    print(f"\n  En iyi: {eniyi} · baseline'a gore "
          f"%{(1 - ort.loc[eniyi, 'MAE'] / baz) * 100:.1f} iyilesme")

    # ---------- POLITIKA CAPRAZ UYGULAMASI ----------
    print("\n" + "=" * 78)
    print("2. POLITIKA CAPRAZ UYGULAMASI")
    print("   'X'in kontrolcusu, Y'nin hava kosullarinda ne harcardi?'")
    print("   Hava DISSALDIR (alti sera ayni havayi yasadi) — bu yuzden temiz.")
    print("=" * 78)
    sat = []
    for kaynak in v:
        ms, _, _, _ = modeller_kayit[kaynak]
        _, mdl, sc = ms["gbm"]
        for hedef in v:
            X, y, sp, *_ = veri_seti(v, hedef)
            te = sp == "test"
            tah = mdl.predict(sc.transform(X[te]) if sc else X[te])
            sat.append({"politika": kaynak, "kosullar": hedef,
                        "tahmin_cent": float(tah.mean()),
                        "gercek_cent": float(y[te].mean())})
    c = pd.DataFrame(sat)
    c.to_csv(base_dir / "politika_capraz.csv", index=False)
    M = c.pivot_table(index="politika", columns="kosullar", values="tahmin_cent")
    print("\nSatir = politika · Sutun = hava kosullari · deger = 6 saatlik ort. maliyet (cent/m²)")
    print(M.round(2).to_string())
    print("\n  Politika ortalamasi (tum kosullarda) — DUSUK = UCUZ POLITIKA:")
    pol = M.mean(axis=1).sort_values()
    for k, val in pol.items():
        gercek = c[(c.politika == k) & (c.kosullar == k)].gercek_cent.iloc[0]
        print(f"    {k:15s} {val:6.2f} cent   (kendi kosullarindaki GERCEK: {gercek:.2f})")
    print(f"\n  En ucuz politika {pol.index[0]} · en pahali {pol.index[-1]} · "
          f"fark %{(pol.iloc[-1] / pol.iloc[0] - 1) * 100:.0f}")
    print("\n  DOGRULAMA: bu siralama, hesaplanan net kar siralamasiyla tutarli mi?")
    print("  (net kar: Automatoes 8.15 > AICU 6.50 > IUACAAS 4.87 > Reference 4.77")
    print("            > TheAutomators 4.64 > Digilog 2.60)")

    print("\n" + "=" * 78)
    print("SINIRLAR")
    print("=" * 78)
    print("  * Girdi yalnizca hava; sera durumu ve kontrol eylemleri DISARIDA.")
    print("    Bu, capraz uygulamayi temiz kilar ama tahmin dogrulugunu sinirlar.")
    print("  * Politika farkinin bir kismi sera donaniminin ayni olmasindan gelir;")
    print("    farkli donanimda ayni politika farkli maliyet uretebilir.")
    print("  * Nedensel iddia yoktur: 'su politikaya gecersen su kadar tasarruf edersin'")
    print("    DENMEZ. Yalnizca 'bu politika bu kosullarda su kadar harcadi' denir.")
    return d, c


if __name__ == "__main__":
    BASE_DIR = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")
    run(BASE_DIR)
