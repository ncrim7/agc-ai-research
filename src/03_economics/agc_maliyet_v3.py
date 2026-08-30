"""
AGC - MALIYET v3: ARTIK MIMARISI ve KIS POLITIKA KARSILASTIRMASI
==================================================================
v2 IKI SEY OGRETTI

1) seasonal_naive maliyet tahmininde cok guclu (kis R²=0.930).
   Ama HAKSIZ karsilastirma: takimin KENDI dun maliyetini goruyor,
   yani politikayi dogrudan kodluyor. Hava-yalniz GBM (R²=0.737)
   politikayi sifirdan cikarmak zorunda.

2) Politika capraz matrisinin tum sutunlari AYNI cikti — cunku hava
   alti seranin hepsinde ORTAK. "Farkli kosullar" yok. Matris aslinda
   6 elemanli bir vektor.

BU SCRIPT IKI SORUYU CEVAPLAR
------------------------------
A) ARTIK MIMARISI katki sagliyor mu?
   Iklim modellerinde kullandigimiz yaklasimin aynisi:
       tahmin = seasonal_naive + hava_duzeltmesi
   Model sifir cikti verse bile seasonal_naive kadar iyi olur. Cita
   tabana gomulur; hava bilgisi ancak iyilestirdigi olcude devreye girer.
   Bu, "bizim modelleme katkimiz var mi" sorusunun DOGRU testidir.

B) POLITIKA KARSILASTIRMASI — KIS uzerinde
   v2'de Mayis katmanindan yapilmisti (sezon maliyetinin %1.7'si, herkes
   ~0.2-0.6 cent). Kis katmanlarinda maliyet 12 kat yuksek ve politika
   farki gorunur. Hava ortak oldugu icin karsilastirma dogrudan:
   "ayni hava altinda hangi politika ne harcar?"

CIKTI: maliyet_v3_artik.csv · maliyet_v3_politika_kis.csv
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

GECMIS, GELECEK, STRIDE = 288, 72, 12
N_BLOK = 6
KIS_KATMANLARI = [1, 2, 3]          # Ocak–Nisan basi; maliyetin buyuk kismi
HAVA = ["Tout", "Rhout", "Iglob", "Windsp", "RadSum", "Winddir",
        "Rain", "PARout", "Pyrgeo", "AbsHumOut"]
PIK_BAS, PIK_BIT = 7, 23
SEED = 42


def oznitelik(hava, s):
    w = hava[s:s + GECMIS]
    a = np.arange(GECMIS, dtype=np.float64); ac = a - a.mean(); av = (ac ** 2).sum()
    egim = (ac[:, None] * (w - w.mean(0))).sum(0) / av
    return np.concatenate([w.mean(0), w.std(0), w[-1], egim, w[-72:].mean(0)])


def kur(base_dir: Path):
    df = pd.read_parquet(base_dir / "common_core_with_grodan_strict.parquet")
    hv = [c for c in HAVA if c in df.columns]
    mal = pd.read_parquet(base_dir / "maliyet_serisi.parquet")
    mal["co2_eur"] = mal.co2_dos * (5 / 60) * 0.08
    mal["toplam"] = mal.isi_eur + mal.elek_eur + mal.co2_eur
    v = {}
    for gh, g in df.groupby("greenhouse_id", sort=False):
        g = g.sort_values("Time").reset_index(drop=True)
        m = mal[mal.greenhouse_id == gh].sort_values("Time").reset_index(drop=True)
        n = min(len(g), len(m))
        v[gh] = {"hava": g[hv].to_numpy(np.float64)[:n],
                 "maliyet": m.toplam.to_numpy(np.float64)[:n] * 100,
                 "saat": g.Time.dt.hour.to_numpy()[:n],
                 "zaman": g.Time.to_numpy()[:n], "n": n}
    return v, hv


def tablo(v, gh):
    d = v[gh]; n = d["n"]
    hava = np.array(d["hava"], float, copy=True); mal = np.asarray(d["maliyet"], float)
    ilk = n // N_BLOK
    ort = np.nanmean(hava[:ilk], 0); ort = np.where(np.isfinite(ort), ort, 0.0)
    bos = ~np.isfinite(hava)
    if bos.any():
        i = np.where(bos); hava[i] = ort[i[1]]
    sinir = [int(n * k / N_BLOK) for k in range(N_BLOK + 1)]
    X, y, blok, sez, zam = [], [], [], [], []
    for s in range(0, n - (GECMIS + GELECEK) + 1, STRIDE):
        c0 = s + GECMIS; c1 = c0 + GELECEK
        b = next(k for k in range(N_BLOK) if sinir[k] <= s < sinir[k + 1])
        if c1 > sinir[b + 1]:
            continue
        cik = mal[c0:c1]
        if not np.isfinite(cik).all():
            continue
        st = d["saat"][c0:c1]
        f = oznitelik(hava, s)
        f = np.append(f, float(((st >= PIK_BAS) & (st < PIK_BIT)).mean()))
        X.append(f); y.append(float(cik.sum())); blok.append(b)
        sez.append(float(np.nansum(mal[s:s + GELECEK])))     # cipa: dun ayni saat
        zam.append(d["zaman"][c0])
    return dict(X=np.array(X), y=np.array(y), blok=np.array(blok),
                sez=np.array(sez), zaman=pd.to_datetime(zam))


def olc(y, p):
    e = p - y; ss = ((y - y.mean()) ** 2).sum()
    return float(np.abs(e).mean()), float(1 - (e ** 2).sum() / max(ss, 1e-12))


def run(base_dir: Path):
    v, hv = kur(base_dir)
    T = {gh: tablo(v, gh) for gh in v}
    print(f"Seralar {list(v)} · hava kolonu {len(hv)}\n")

    # ---------- A) ARTIK MIMARISI ----------
    sat = []
    for gh, t in T.items():
        for k in range(1, N_BLOK):
            tr, te = t["blok"] < k, t["blok"] == k
            if tr.sum() < 100 or te.sum() < 20:
                continue
            don = f"{t['zaman'][te].min():%m-%d}–{t['zaman'][te].max():%m-%d}"
            ort = dict(sera=gh, kat=k, donem=don, test_ort=float(t["y"][te].mean()))

            # cipa
            mae, r2 = olc(t["y"][te], t["sez"][te])
            sat.append({**ort, "model": "cipa (seasonal naive)", "MAE": mae, "R2": r2})

            # dogrudan hedef
            sc = StandardScaler().fit(t["X"][tr])
            gb = HistGradientBoostingRegressor(max_iter=250, learning_rate=.07, max_depth=6,
                    l2_regularization=1.0, random_state=SEED).fit(t["X"][tr], t["y"][tr])
            mae, r2 = olc(t["y"][te], gb.predict(t["X"][te]))
            sat.append({**ort, "model": "gbm dogrudan", "MAE": mae, "R2": r2})

            # ARTIK: cipa + hava duzeltmesi
            art_tr = t["y"][tr] - t["sez"][tr]
            gr = HistGradientBoostingRegressor(max_iter=250, learning_rate=.07, max_depth=6,
                    l2_regularization=1.0, random_state=SEED).fit(t["X"][tr], art_tr)
            p = t["sez"][te] + gr.predict(t["X"][te])
            mae, r2 = olc(t["y"][te], p)
            sat.append({**ort, "model": "ARTIK (cipa+hava)", "MAE": mae, "R2": r2})

            rr = Ridge(alpha=10.).fit(sc.transform(t["X"][tr]), art_tr)
            p = t["sez"][te] + rr.predict(sc.transform(t["X"][te]))
            mae, r2 = olc(t["y"][te], p)
            sat.append({**ort, "model": "ARTIK (cipa+ridge)", "MAE": mae, "R2": r2})

    d = pd.DataFrame(sat)
    d.to_csv(base_dir / "maliyet_v3_artik.csv", index=False)
    S = ["cipa (seasonal naive)", "gbm dogrudan", "ARTIK (cipa+hava)", "ARTIK (cipa+ridge)"]

    print("=" * 92)
    print("A) ARTIK MIMARISI — 'modelleme katkimiz var mi?' sorusunun dogru testi")
    print("=" * 92)
    p = d.pivot_table(index=["kat", "donem"], columns="model", values="MAE")[S]
    p.insert(0, "test_ort", d.pivot_table(index=["kat", "donem"], values="test_ort").round(2))
    p["en_iyi"] = p[S].idxmin(axis=1)
    print(p.round(3).to_string())
    print("\nR²:")
    print(d.pivot_table(index=["kat", "donem"], columns="model", values="R2")[S].round(3).to_string())

    g = d.groupby("model")[["MAE", "R2"]].mean().reindex(S).round(3)
    print("\nGENEL:"); print(g.to_string())
    cipa = g.loc["cipa (seasonal naive)", "MAE"]
    for m in S[1:]:
        print(f"  {m:22s} cipaya gore %{(1 - g.loc[m,'MAE']/cipa)*100:+6.1f}")

    kis = d[d.kat.isin(KIS_KATMANLARI)].groupby("model")[["MAE", "R2"]].mean().reindex(S).round(3)
    print("\nYALNIZCA KIS (maliyetin buyuk kismi):")
    print(kis.to_string())
    ck = kis.loc["cipa (seasonal naive)", "MAE"]
    en = kis.MAE.idxmin()
    print(f"  En iyi: {en} · cipaya gore %{(1 - kis.loc[en,'MAE']/ck)*100:+.1f}")

    # ---------- B) KIS POLITIKA KARSILASTIRMASI ----------
    print("\n" + "=" * 92)
    print("B) POLITIKA KARSILASTIRMASI — KIS (hava alti serada ORTAK)")
    print("   'Ayni hava altinda hangi politika ne harcar?'")
    print("=" * 92)
    pol = []
    for gh, t in T.items():
        tr = t["blok"].astype(int) < min(KIS_KATMANLARI)
        te = np.isin(t["blok"], KIS_KATMANLARI)
        if tr.sum() < 100 or te.sum() < 50:
            tr = t["blok"] == 0; te = np.isin(t["blok"], KIS_KATMANLARI)
        gb = HistGradientBoostingRegressor(max_iter=250, learning_rate=.07, max_depth=6,
                l2_regularization=1.0, random_state=SEED).fit(t["X"][tr], t["y"][tr])
        pol.append(dict(politika=gh, tahmin=float(gb.predict(t["X"][te]).mean()),
                        gercek=float(t["y"][te].mean()), n_test=int(te.sum())))
    c = pd.DataFrame(pol).set_index("politika").sort_values("gercek")
    net = {"Automatoes": 8.15, "AICU": 6.50, "IUACAAS": 4.87,
           "Reference": 4.77, "TheAutomators": 4.64, "Digilog": 2.60}
    c["net_kar"] = [net[i] for i in c.index]
    c.to_csv(base_dir / "maliyet_v3_politika_kis.csv")
    print(c.round(2).to_string())
    rho = c.gercek.corr(c.net_kar, method="spearman")
    rho_t = c.tahmin.corr(c.net_kar, method="spearman")
    print(f"\n  GERCEK kis maliyeti ~ net kar : Spearman {rho:+.2f}")
    print(f"  TAHMIN edilen        ~ net kar : Spearman {rho_t:+.2f}")
    print("  Beklenen: NEGATIF (ucuz politika -> yuksek kar)")
    print(f"  Kis maliyet araligi: {c.gercek.min():.2f}–{c.gercek.max():.2f} cent "
          f"({c.gercek.max()/max(c.gercek.min(),1e-9):.1f} kat)")

    print("\n" + "=" * 92)
    print("YORUM ANAHTARI")
    print("=" * 92)
    print("  ARTIK cipadan iyiyse  -> hava bilgisi maliyet tahminine katki sagliyor")
    print("  ARTIK cipaya esitse   -> maliyet tamamen dunun tekrari; hava ek bilgi vermiyor")
    print("  ARTIK cipadan kotuyse -> model gurultu ogreniyor, cipa tek basina kullanilmali")
    return d, c


if __name__ == "__main__":
    BASE_DIR = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")
    run(BASE_DIR)
