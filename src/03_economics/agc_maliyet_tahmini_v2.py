"""
AGC - MALIYET TAHMINI v2: KAYAN BASLANGICLI DEGERLENDIRME
============================================================
v1'DEKI TEMEL SORUN

Tek kronolojik bolme (%70/15/15) iklim tahmini icin dogruydu ama MALIYET icin
felaket: sezon maliyetinin dagilimi

    egitim  %90.2      (16 Ara - 10 Nis, gunluk 15.16 cent/m²)
    dogrula  %8.1      (10 Nis -  5 May, gunluk  6.19 cent/m²)
    TEST     %1.7      ( 5 May - 30 May, gunluk  1.13 cent/m²)

Test doneminde gunler uzun, lambalar kapali, isitma yok — tahmin edilecek
maliyet YOK. Sonuc: ortalama tahmin edicinin R²'si -161, ML modelleri
seasonal naive'den 20 kat kotu. Model kotu degil, DEGERLENDIRME anlamsiz.

COZUM: KAYAN BASLANGIC (rolling origin)
---------------------------------------
Sezon ardisik bloklara bolunur. Her katmanda gecmis bloklarla egitilip
SONRAKI blokta test edilir:

    kat 1: blok 1        -> test blok 2   (Ocak)
    kat 2: blok 1-2      -> test blok 3   (Subat)
    ...
    kat 5: blok 1-5      -> test blok 6   (Mayis)

Zamansal siralama KORUNUR (gelecekten gecmise sizinti yok) ama kis artik
test setlerinde. Her katman ayri raporlanir; boylece "kis mi yaz mi daha
tahmin edilebilir" sorusu da cevaplanir.

POLITIKA CAPRAZ UYGULAMASI
--------------------------
Girdi yalnizca DIS HAVA (dissal, alti sera ayni havayi yasadi). Boylece
takim modelleri capraz uygulanabilir: "X'in kontrolcusu Y'nin kosullarinda
ne harcardi?" Nedensel iddia yok — politika karsilastirmasi.

CIKTI: maliyet_v2_katmanlar.csv · maliyet_v2_politika.csv
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
HAVA = ["Tout", "Rhout", "Iglob", "Windsp", "RadSum", "Winddir",
        "Rain", "PARout", "Pyrgeo", "AbsHumOut"]
PIK_BAS, PIK_BIT = 7, 23
SEED = 42


def oznitelik(hava: np.ndarray, s: int) -> np.ndarray:
    w = hava[s:s + GECMIS]
    a = np.arange(GECMIS, dtype=np.float64)
    ac = a - a.mean(); av = (ac ** 2).sum()
    egim = (ac[:, None] * (w - w.mean(0))).sum(0) / av
    return np.concatenate([w.mean(0), w.std(0), w[-1], egim, w[-72:].mean(0)])


def kur(base_dir: Path):
    df = pd.read_parquet(base_dir / "common_core_with_grodan_strict.parquet")
    hv = [c for c in HAVA if c in df.columns]
    yok = [c for c in HAVA if c not in df.columns]
    if yok:
        print(f"  UYARI: bulunamayan hava kolonlari {yok}")
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


def pencere_tablosu(v: dict, gh: str) -> dict:
    """Tum pencereleri uretir, blok etiketi ile. NaN politikasi projeyle ayni."""
    d = v[gh]
    n = d["n"]
    hava = np.array(d["hava"], dtype=np.float64, copy=True)
    mal = np.asarray(d["maliyet"], dtype=np.float64)

    # Girdi NaN -> ilk blogun ortalamasi (her zaman gecmiste kalir)
    ilk = n // N_BLOK
    ort = np.nanmean(hava[:ilk], axis=0)
    ort = np.where(np.isfinite(ort), ort, 0.0)
    bos = ~np.isfinite(hava)
    if bos.any():
        i = np.where(bos); hava[i] = ort[i[1]]

    sinir = [int(n * k / N_BLOK) for k in range(N_BLOK + 1)]
    X, y, blok, pers, sez, zam = [], [], [], [], [], []
    elenen = 0
    for s in range(0, n - (GECMIS + GELECEK) + 1, STRIDE):
        c0 = s + GECMIS; c1 = c0 + GELECEK
        b = next(k for k in range(N_BLOK) if sinir[k] <= s < sinir[k + 1])
        if c1 > sinir[b + 1]:          # blok sinirini asan pencere elenir
            continue
        cikti = mal[c0:c1]
        if not np.isfinite(cikti).all():
            elenen += 1; continue
        X.append(oznitelik(hava, s))
        y.append(float(cikti.sum()))
        blok.append(b)
        st = d["saat"][c0:c1]
        pik = float(((st >= PIK_BAS) & (st < PIK_BIT)).mean())
        pers.append(float(np.nansum(mal[c0 - GELECEK:c0])))
        sez.append(float(np.nansum(mal[s:s + GELECEK])))
        zam.append(d["zaman"][c0])
        X[-1] = np.append(X[-1], pik)
    return dict(X=np.array(X), y=np.array(y), blok=np.array(blok),
                pers=np.array(pers), sez=np.array(sez),
                zaman=pd.to_datetime(zam), elenen=elenen)


def olc(y, p):
    e = p - y; ss = ((y - y.mean()) ** 2).sum()
    return float(np.abs(e).mean()), float(1 - (e ** 2).sum() / max(ss, 1e-12))


def run(base_dir: Path):
    v, hv = kur(base_dir)
    print(f"Seralar: {list(v)} · hava kolonu {len(hv)}\n")

    tablo, modeller = {}, {}
    sat = []
    for gh in v:
        t = pencere_tablosu(v, gh)
        tablo[gh] = t
        if t["elenen"]:
            print(f"  {gh}: {t['elenen']} pencere elendi (cikti NaN)")

        for k in range(1, N_BLOK):
            tr = t["blok"] < k
            te = t["blok"] == k
            if tr.sum() < 100 or te.sum() < 20:
                continue
            Xtr, ytr, Xte, yte = t["X"][tr], t["y"][tr], t["X"][te], t["y"][te]
            don = f"{t['zaman'][te].min():%m-%d}–{t['zaman'][te].max():%m-%d}"

            for ad, p in [("ortalama", np.full(te.sum(), ytr.mean())),
                          ("persistence", t["pers"][te]),
                          ("seasonal_naive", t["sez"][te])]:
                mae, r2 = olc(yte, p)
                sat.append(dict(sera=gh, kat=k, donem=don, model=ad, MAE=mae, R2=r2,
                                test_ort=float(yte.mean()), n=int(te.sum())))

            sc = StandardScaler().fit(Xtr)
            rg = Ridge(alpha=10.0).fit(sc.transform(Xtr), ytr)
            mae, r2 = olc(yte, rg.predict(sc.transform(Xte)))
            sat.append(dict(sera=gh, kat=k, donem=don, model="ridge", MAE=mae, R2=r2,
                            test_ort=float(yte.mean()), n=int(te.sum())))
            gb = HistGradientBoostingRegressor(max_iter=250, learning_rate=.07,
                    max_depth=6, l2_regularization=1.0, random_state=SEED).fit(Xtr, ytr)
            mae, r2 = olc(yte, gb.predict(Xte))
            sat.append(dict(sera=gh, kat=k, donem=don, model="gbm", MAE=mae, R2=r2,
                            test_ort=float(yte.mean()), n=int(te.sum())))
            if k == N_BLOK - 1:
                modeller[gh] = (gb, sc, rg)

    d = pd.DataFrame(sat)
    d.to_csv(base_dir / "maliyet_v2_katmanlar.csv", index=False)

    print("\n" + "=" * 84)
    print("1. KATMAN BAZINDA — hangi donemde tahmin edilebilir?")
    print("=" * 84)
    p = d.pivot_table(index=["kat", "donem"], columns="model", values="MAE")
    o = d.pivot_table(index=["kat", "donem"], values="test_ort")
    p = p[[c for c in ["ortalama", "persistence", "seasonal_naive", "ridge", "gbm"] if c in p]]
    p.insert(0, "test_ort_cent", o.test_ort.round(2))
    p["en_iyi"] = p.drop(columns="test_ort_cent").idxmin(axis=1)
    print(p.round(3).to_string())

    print("\n" + "=" * 84)
    print("2. GENEL — tum katmanlar")
    print("=" * 84)
    g = d.groupby("model")[["MAE", "R2"]].mean().round(3)
    print(g.sort_values("MAE").to_string())
    baz = g.loc[["persistence", "seasonal_naive"], "MAE"].min()
    en = g.MAE.min(); enad = g.MAE.idxmin()
    print(f"\n  En iyi: {enad} ({en:.3f}) · en iyi baseline {baz:.3f} · "
          f"iyilesme %{(1 - en / baz) * 100:+.1f}")

    print("\n" + "=" * 84)
    print("3. KIS vs ILKBAHAR — model nerede ise yariyor?")
    print("=" * 84)
    d["donem_tip"] = np.where(d.kat <= 2, "kis", np.where(d.kat <= 3, "gecis", "ilkbahar"))
    k = d.pivot_table(index="donem_tip", columns="model", values="MAE")
    k = k[[c for c in ["persistence", "seasonal_naive", "ridge", "gbm"] if c in k]]
    k["test_ort"] = d.groupby("donem_tip").test_ort.mean().round(2)
    print(k.round(3).to_string())

    # ---------- POLITIKA CAPRAZ ----------
    if modeller:
        print("\n" + "=" * 84)
        print("4. POLITIKA CAPRAZ UYGULAMASI (son katman modeli)")
        print("   'X'in kontrolcusu, Y'nin kosullarinda ne harcardi?'")
        print("=" * 84)
        c = []
        for kay, (gb, sc, rg) in modeller.items():
            for hed, t in tablo.items():
                te = t["blok"] == N_BLOK - 1
                if te.sum() < 20:
                    continue
                c.append(dict(politika=kay, kosullar=hed,
                              tahmin=float(gb.predict(t["X"][te]).mean()),
                              gercek=float(t["y"][te].mean())))
        cd = pd.DataFrame(c)
        cd.to_csv(base_dir / "maliyet_v2_politika.csv", index=False)
        M = cd.pivot_table(index="politika", columns="kosullar", values="tahmin")
        print(M.round(2).to_string())
        pol = M.mean(axis=1).sort_values()
        print("\n  Politika ortalamasi (dusuk = ucuz):")
        for a, b in pol.items():
            print(f"    {a:15s} {b:6.2f} cent")
        print("\n  Net kar siralamasi: Automatoes > AICU > IUACAAS > Reference "
              "> TheAutomators > Digilog")
        print("  Tutarli mi? (ucuz politika -> yuksek net kar beklenir)")

    print("\n" + "=" * 84)
    print("SINIRLAR")
    print("=" * 84)
    print("  * Girdi yalnizca hava. Sera durumu ve kontrol eylemleri disarida —")
    print("    capraz uygulamayi temiz kilar, dogrulugu sinirlar.")
    print("  * Son katman (Mayis) ekonomik olarak onemsiz: gunluk 1.13 cent/m².")
    print("    Politika karsilastirmasi icin kis katmanlari daha bilgilendiricidir.")
    print("  * Nedensel iddia yok: 'su politikaya gecersen su kadar tasarruf edersin'")
    print("    DENMEZ; yalnizca 'bu politika bu kosullarda su kadar harcadi' denir.")
    return d


if __name__ == "__main__":
    BASE_DIR = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")
    run(BASE_DIR)
