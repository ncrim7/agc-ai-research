"""
AGC - STRATEJI PARMAK IZI ve AUTOMATOES HIPOTEZI TESTI
========================================================
TEST EDILEN IDDIA (nihai raporda su an SPEKULASYON olarak duruyor):

  "Automatoes en zor genellenen seradir cunku kontrol politikasi diger
   bes takimdan en farkli olandir; ozellikle sulama politikasi."

Bu iddiayi destekleyen mevcut kanit DOLAYLI: LOTO zorlugu kok bolgesinde
yogunlasiyor (1.458) hava hedeflerinden (1.126) belirgin yuksek. Ama
sulama politikasinin gercekten farkli oldugu OLCULMEDI.

YONTEM — LOTO ile birebir paralel kurulum:
  Her takim T icin, T'nin gunluk kaynak profili ile DIGER BES takimin
  ortalama profili arasindaki uzaklik hesaplanir (leave-one-out centroid
  mesafesi). Bu, LOTO'nun "diger beste egit, T'de test et" mantiginin
  veri uzayindaki karsiligidir.

  Metrikler uc gruba ayrilir:
    SULAMA  : Irr, Drain, drenaj orani (Drain/Irr)
    IKLIM   : Heat_cons, CO2_cons, ElecHigh+ElecLow
    TUMU    : hepsi

KESKIN TAHMIN: Hipotez dogruysa Automatoes'un SULAMA uzakligi en yuksek
olmali; IKLIM uzakligi ayni derecede yuksek olmak zorunda degil.
Eger iklim uzakligi da ayni derecede yuksekse, "sulama politikasi"
aciklamasi degil "genel olarak farkli" aciklamasi gecerli olur.

CIKTI: strateji_parmak_izi.csv, drenaj_ec_iliskisi.csv
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

TAKIMLAR = ["AICU", "Automatoes", "Digilog", "IUACAAS", "Reference", "TheAutomators"]
KOK_HEDEF = ["EC_slab1", "EC_slab2", "WC_slab1", "WC_slab2", "t_slab1", "t_slab2"]


def yukle(base: Path) -> pd.DataFrame:
    p = []
    for t in TAKIMLAR:
        aday = list(base.glob(f"{t}_Resources.csv")) or list((base / t).glob("*Resources*"))
        if not aday:
            print(f"  UYARI: {t} Resources bulunamadi")
            continue
        x = pd.read_csv(aday[0], skipinitialspace=True)
        x.columns = x.columns.str.strip()
        x = x.loc[:, ~x.columns.str.startswith("Unnamed")]        # IUACAAS'taki bos kolonlar
        zc = [c for c in x.columns if "time" in c.lower()][0]
        x["Time"] = pd.Timestamp("1899-12-30") + pd.to_timedelta(
            pd.to_numeric(x[zc], errors="coerce"), unit="D")
        x = x.drop(columns=[zc])
        x["takim"] = t
        p.append(x)
    return pd.concat(p, ignore_index=True)


def profil(df: pd.DataFrame) -> pd.DataFrame:
    """Gunluk turetilmis metrikler."""
    d = df.copy()
    d["Elec"] = d["ElecHigh"] + d["ElecLow"]
    # Drenaj orani: sulamanin ne kadari drene oluyor. Sulama sifirsa tanimsiz.
    d["drenaj_orani"] = np.where(d["Irr"] > 0.01, d["Drain"] / d["Irr"], np.nan)
    d["net_su"] = d["Irr"] - d["Drain"]
    return d


def uzaklik(d: pd.DataFrame, metrikler: list[str]) -> pd.Series:
    """Leave-one-out centroid mesafesi: her takimin, DIGER beslerin
    ortalamasindan standartlastirilmis Oklid uzakligi."""
    z = d[metrikler].copy()
    z = (z - z.mean()) / z.std(ddof=0)                     # tum veri uzerinde standartlastir
    z["takim"] = d["takim"].values
    ort = z.groupby("takim")[metrikler].mean()

    out = {}
    for t in ort.index:
        digerleri = ort.drop(index=t).mean()               # diger beslerin merkezi
        out[t] = float(np.linalg.norm(ort.loc[t] - digerleri))
    return pd.Series(out).sort_values(ascending=False)


def loto_zorluk(base: Path) -> pd.DataFrame | None:
    p = base / "loto_results.csv"
    if not p.exists():
        return None
    l = pd.read_csv(p)
    B = l[(l.test_set == "B_hava_gorulmemis") & (l.horizon == "3h") &
          (l.feature_set == "core_grodan")]
    piv = B.pivot_table(index="target", columns="held_out_team", values="MAE")
    norm = piv.div(piv.mean(axis=1), axis=0)
    kok = [t for t in norm.index if t in KOK_HEDEF]
    hava = [t for t in norm.index if t not in KOK_HEDEF]
    ec = [t for t in norm.index if t.startswith("EC_slab")]
    return pd.DataFrame({"zorluk_tum": norm.mean(),
                         "zorluk_kok": norm.loc[kok].mean(),
                         "zorluk_hava": norm.loc[hava].mean(),
                         "zorluk_EC": norm.loc[ec].mean()})


def run(base_dir: Path):
    print("Resources yukleniyor...")
    ham = yukle(base_dir)
    d = profil(ham)
    print(f"  {len(d)} satir, {d.takim.nunique()} takim, "
          f"{d.Time.min():%Y-%m-%d} – {d.Time.max():%Y-%m-%d}\n")

    print("=" * 78)
    print("1. TAKIM BAZINDA GUNLUK KAYNAK PROFILI (ortalama)")
    print("=" * 78)
    ozet = d.groupby("takim").agg(
        Sulama=("Irr", "mean"), Drenaj=("Drain", "mean"),
        Drenaj_orani=("drenaj_orani", "mean"), Net_su=("net_su", "mean"),
        Isitma=("Heat_cons", "mean"), CO2=("CO2_cons", "mean"), Elektrik=("Elec", "mean"))
    print(ozet.round(3).to_string())

    print("\n" + "=" * 78)
    print("2. STRATEJI UZAKLIGI — her takim, diger beslerin merkezinden")
    print("=" * 78)
    gruplar = {
        "SULAMA": ["Irr", "Drain", "drenaj_orani", "net_su"],
        "IKLIM": ["Heat_cons", "CO2_cons", "Elec"],
        "TUMU": ["Irr", "Drain", "drenaj_orani", "net_su", "Heat_cons", "CO2_cons", "Elec"],
    }
    u = {}
    for ad, m in gruplar.items():
        gecerli = d.dropna(subset=m)
        u[ad] = uzaklik(gecerli, m)
    U = pd.DataFrame(u)
    U["SULAMA_sira"] = U["SULAMA"].rank(ascending=False).astype(int)
    U["IKLIM_sira"] = U["IKLIM"].rank(ascending=False).astype(int)
    print(U.round(3).to_string())

    print("\n" + "=" * 78)
    print("3. HIPOTEZ TESTI")
    print("=" * 78)
    s_sira = int(U.loc["Automatoes", "SULAMA_sira"])
    i_sira = int(U.loc["Automatoes", "IKLIM_sira"])
    print(f"  Automatoes SULAMA uzakligi sirasi : {s_sira}/6")
    print(f"  Automatoes IKLIM  uzakligi sirasi : {i_sira}/6")
    if s_sira == 1 and i_sira > 2:
        karar = "DESTEKLENDI — sulamada en uzak, iklimde degil. Aciklama spesifik."
    elif s_sira == 1:
        karar = "KISMEN — sulamada en uzak ama iklimde de uzak. 'Genel olarak farkli' de olabilir."
    elif s_sira <= 2:
        karar = "ZAYIF DESTEK — sulamada en uzaklardan ama birinci degil."
    else:
        karar = "DESTEKLENMEDI — sulama uzakligi yuksek degil. Aciklama gozden gecirilmeli."
    print(f"\n  SONUC: {karar}")

    # --- LOTO zorlugu ile karsilastirma ---
    z = loto_zorluk(base_dir)
    if z is not None:
        k = U.join(z)
        print("\n" + "=" * 78)
        print("4. STRATEJI UZAKLIGI ile LOTO ZORLUGU ILISKISI")
        print("=" * 78)
        print(k[["SULAMA", "IKLIM", "TUMU", "zorluk_kok", "zorluk_hava", "zorluk_tum"]]
              .round(3).to_string())
        print("\n  Spearman korelasyonlari (n=6, guc dusuk — yon gostergesi):")
        for a in ["SULAMA", "IKLIM", "TUMU"]:
            for b in ["zorluk_kok", "zorluk_hava", "zorluk_tum"]:
                r = k[a].corr(k[b], method="spearman")
                yildiz = " <--" if a == "SULAMA" and b == "zorluk_kok" else ""
                print(f"    {a:7s} ~ {b:12s}  rho = {r:+.2f}{yildiz}")
        k.to_csv(base_dir / "strateji_parmak_izi.csv")

        print("\n" + "=" * 78)
        print("5. DRENAJ ORANI ile EC TAHMIN EDILEBILIRLIGI")
        print("=" * 78)
        print("  Iddia: yuksek drenaj = aktif EC yonetimi = daha hareketli, daha zor EC")
        dd = ozet[["Drenaj_orani"]].join(z[["zorluk_EC"]]).sort_values("Drenaj_orani")
        print(dd.round(3).to_string())
        r = dd["Drenaj_orani"].corr(dd["zorluk_EC"], method="spearman")
        print(f"\n  Spearman rho = {r:+.2f}  (n=6)")
        print("  " + ("Iddia ile TUTARLI yon" if r > 0.3 else
                      "Iddia ile TERS yon" if r < -0.3 else "Belirgin iliski YOK"))
        dd.to_csv(base_dir / "drenaj_ec_iliskisi.csv")

    print("\n" + "=" * 78)
    print("UYARI: n=6 takim. Korelasyonlar yon gostergesidir, kanit degildir.")
    print("Uzaklik siralamasi ise dogrudan olcumdur ve yorumlanabilir.")
    print("=" * 78)
    return U, ozet


if __name__ == "__main__":
    BASE_DIR = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")
    run(BASE_DIR)
