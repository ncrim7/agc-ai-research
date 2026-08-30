"""
AGC - STRATEJI-SONUC TABLOSU
==============================
Alti takimin kontrol stratejisini SONUCLARIYLA birlikte tek tabloda gosterir:
kaynak tuketimi -> uretim -> meyve kalitesi -> verimlilik.

NEDEN: AGC yarismasinin asil hedefi net kardi (uretim degeri - kaynak maliyeti).
Tahmin calismasi yalnizca dogruluga bakti. Bu tablo, alti stratejinin gercekte
ne uretttigini gosterir. Model YOK, yalnizca betimsel analiz — cunku hedef
degiskenlerin ornek sayisi (23 hasat olayi, 8 kalite olcumu) modellemeye yetmez.

ONARILAN IKI VERI HATASI
------------------------
1) Reference_Production.csv — bir satirda %time = 43510 (2019-02-14).
   Diger takimlarin ilk olcumu 43875 (2020-02-14). Fark tam 365 gun:
   yil yazim hatasi. Duzeltme: +365.

2) Reference_TomQuality.csv — YAPISAL hata (tarih hatasi degil).
   Dosya ayrac olarak virgul+SEKME kullaniyor ve baslikta Weight ile
   DMC_fruit arasinda virgul yok, yalnizca sekme var:
       %time,\\tFlavour, \\tTSS,...,\\tWeight\\tDMC_fruit     -> 7 baslik
       43880,\\t74,\\t7.9,...,\\t7.77,\\tnan                   -> 8 deger
   Pandas ilk sutunu indekse atiyor, tum kolonlar bir kayiyor. Duzeltme:
   basligi atlayip 8 kolon adini elle vermek.

CIKTI: strateji_sonuc_tablosu.csv, strateji_sonuc_ozet.csv
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

TAKIMLAR = ["AICU", "Automatoes", "Digilog", "IUACAAS", "Reference", "TheAutomators"]
EPOCH = pd.Timestamp("1899-12-30")
TQ_KOLONLAR = ["%time", "Flavour", "TSS", "Acid", "%Juice", "Bite", "Weight", "DMC_fruit"]


def _bul(base: Path, takim: str, tip: str) -> Path | None:
    for d in (base, base / takim):
        if d.exists():
            for kalip in (f"{takim}_{tip}.csv", f"*{tip}*"):
                a = list(d.glob(kalip))
                if a:
                    return a[0]
    return None


def _tarih(s: pd.Series) -> pd.Series:
    return EPOCH + pd.to_timedelta(pd.to_numeric(s, errors="coerce"), unit="D")


def oku_resources(base: Path) -> pd.DataFrame:
    p = []
    for t in TAKIMLAR:
        f = _bul(base, t, "Resources")
        if f is None:
            continue
        x = pd.read_csv(f, skipinitialspace=True)
        x.columns = x.columns.str.strip()
        x = x.loc[:, ~x.columns.str.startswith("Unnamed")]
        zc = [c for c in x.columns if "time" in c.lower()][0]
        x["Time"] = _tarih(x[zc]); x = x.drop(columns=[zc])
        x["takim"] = t
        p.append(x)
    return pd.concat(p, ignore_index=True)


def oku_production(base: Path) -> tuple[pd.DataFrame, list[str]]:
    p, log = [], []
    for t in TAKIMLAR:
        f = _bul(base, t, "Production")
        if f is None:
            continue
        x = pd.read_csv(f, skipinitialspace=True)
        x.columns = x.columns.str.strip()
        # ONARIM 1: yil yazim hatasi
        bozuk = x["%time"] < 43800
        if bozuk.any():
            eski = x.loc[bozuk, "%time"].tolist()
            x.loc[bozuk, "%time"] = x.loc[bozuk, "%time"] + 365
            log.append(f"{t}/Production: {len(eski)} satir +365 gun duzeltildi "
                       f"({eski} -> {x.loc[bozuk, '%time'].tolist()})")
        x["Time"] = _tarih(x["%time"]); x = x.drop(columns=["%time"])
        x["takim"] = t
        p.append(x)
    return pd.concat(p, ignore_index=True), log


def oku_tomquality(base: Path) -> tuple[pd.DataFrame, list[str]]:
    p, log = [], []
    for t in TAKIMLAR:
        f = _bul(base, t, "TomQuality")
        if f is None:
            continue
        ham = pd.read_csv(f, skipinitialspace=True)
        ham.columns = [c.strip() for c in ham.columns]
        # ONARIM 2: baslikta sekme ile birlesmis kolon -> kolon kaymasi
        birlesik = any("\t" in c for c in ham.columns)
        if birlesik or len(ham.columns) < len(TQ_KOLONLAR):
            x = pd.read_csv(f, skiprows=1, header=None, names=TQ_KOLONLAR)
            for c in TQ_KOLONLAR:
                x[c] = pd.to_numeric(
                    x[c].astype(str).str.replace("\t", "", regex=False).str.strip(),
                    errors="coerce")
            log.append(f"{t}/TomQuality: baslik sekme ile bozuk, 8 kolon elle atandi "
                       f"(kolon kaymasi giderildi)")
        else:
            x = ham.copy()
            for c in x.columns:
                x[c] = pd.to_numeric(x[c], errors="coerce")
        x["Time"] = _tarih(x["%time"]); x = x.drop(columns=["%time"])
        x["takim"] = t
        p.append(x)
    return pd.concat(p, ignore_index=True), log


def iklim_rejimi(base: Path) -> pd.DataFrame | None:
    """Temizlenmis parquet varsa iklim rejimi kolonlarini ekler."""
    f = base / "common_core_with_grodan_strict.parquet"
    if not f.exists():
        return None
    d = pd.read_parquet(f, columns=["greenhouse_id", "Tair", "Rhair", "CO2air", "Tot_PAR", "HumDef"])
    g = d.groupby("greenhouse_id").agg(
        Tair_ort=("Tair", "mean"), Tair_std=("Tair", "std"),
        Rhair_ort=("Rhair", "mean"), CO2_ort=("CO2air", "mean"),
        PAR_ort=("Tot_PAR", "mean"), HumDef_ort=("HumDef", "mean"))
    g.index.name = "takim"
    return g.round(2)


def run(base_dir: Path):
    print("Dosyalar okunuyor ve onariliyor...\n")
    res = oku_resources(base_dir)
    prod, log1 = oku_production(base_dir)
    tq, log2 = oku_tomquality(base_dir)

    print("=" * 78); print("ONARIM RAPORU"); print("=" * 78)
    for s in log1 + log2:
        print(f"  {s}")
    if not (log1 + log2):
        print("  (onarim gerekmedi)")

    # --- Onarim dogrulamasi ---
    print("\nDogrulama:")
    pt = prod.groupby("takim").Time.agg(["min", "max", "count"])
    print("  Production tarih araliklari:")
    print(pt.to_string().replace("\n", "\n    "))
    tqt = tq.groupby("takim").agg(ilk=("Time", "min"), son=("Time", "max"),
                                  n=("Flavour", "size"), Flavour_ort=("Flavour", "mean"))
    print("\n  TomQuality:")
    print(tqt.round({"Flavour_ort":2}).to_string().replace("\n", "\n    "))

    # --- Strateji ve sonuc metrikleri ---
    res["Elec"] = res["ElecHigh"] + res["ElecLow"]
    res["drenaj_orani"] = np.where(res["Irr"] > .01, res["Drain"] / res["Irr"], np.nan)

    kaynak = res.groupby("takim").agg(
        Sulama_top=("Irr", "sum"), Drenaj_top=("Drain", "sum"),
        Drenaj_orani=("drenaj_orani", "mean"), Isitma_top=("Heat_cons", "sum"),
        CO2_top=("CO2_cons", "sum"), Elektrik_top=("Elec", "sum"))

    urun = prod.groupby("takim").agg(
        ProdA_top=("ProdA", "sum"), ProdB_top=("ProdB", "sum"),
        Salkim_suresi=("Truss development time", "mean"),
        Salkim_sayisi=("avg_nr_harvested_trusses", "mean"))
    urun["Toplam_uretim"] = urun.ProdA_top + urun.ProdB_top
    urun["A_sinifi_pay"] = (urun.ProdA_top / urun.Toplam_uretim * 100).round(1)

    kalite = tq.groupby("takim").agg(
        Tat=("Flavour", "mean"), Briks=("TSS", "mean"),
        Asit=("Acid", "mean"), Sertlik=("Bite", "mean"), Meyve_agirligi=("Weight", "mean"))

    t = kaynak.join(urun).join(kalite)
    t["Enerji_kg_basina"] = (t.Isitma_top / t.Toplam_uretim).round(3)
    t["Su_kg_basina"] = (t.Sulama_top / t.Toplam_uretim).round(3)
    t["CO2_kg_basina"] = (t.CO2_top / t.Toplam_uretim).round(4)
    t["Elektrik_kg_basina"] = (t.Elektrik_top / t.Toplam_uretim).round(3)

    ik = iklim_rejimi(base_dir)
    if ik is not None:
        t = t.join(ik)
        print("\n  (iklim rejimi kolonlari eklendi)")
    else:
        print("\n  UYARI: common_core_with_grodan_strict.parquet bulunamadi, "
              "iklim rejimi kolonlari atlandi")

    t.to_csv(base_dir / "strateji_sonuc_tablosu.csv")

    # ---------------- Ekran ciktilari ----------------
    print("\n" + "=" * 78); print("1. KONTROL STRATEJISI (sezon toplami)"); print("=" * 78)
    print(t[["Sulama_top", "Drenaj_top", "Drenaj_orani", "Isitma_top", "CO2_top", "Elektrik_top"]]
          .round(2).sort_values("Isitma_top").to_string())

    print("\n" + "=" * 78); print("2. URETIM SONUCU"); print("=" * 78)
    print(t[["Toplam_uretim", "ProdA_top", "A_sinifi_pay", "Salkim_suresi", "Salkim_sayisi"]]
          .round(2).sort_values("Toplam_uretim", ascending=False).to_string())

    print("\n" + "=" * 78); print("3. MEYVE KALITESI"); print("=" * 78)
    print(kalite.round(2).sort_values("Tat", ascending=False).to_string())

    print("\n" + "=" * 78); print("4. KAYNAK VERIMLILIGI (birim uretim basina — dusuk = iyi)")
    print("=" * 78)
    v = t[["Enerji_kg_basina", "Su_kg_basina", "CO2_kg_basina", "Elektrik_kg_basina", "Toplam_uretim"]]
    print(v.sort_values("Enerji_kg_basina").to_string())

    print("\n" + "=" * 78); print("5. VERIM-KALITE ODUNLESIMI"); print("=" * 78)
    od = t[["Toplam_uretim", "Tat", "Briks", "Meyve_agirligi", "Enerji_kg_basina"]].copy()
    print(od.round(2).sort_values("Toplam_uretim", ascending=False).to_string())
    r = od.Toplam_uretim.corr(od.Tat, method="spearman")
    r2 = od.Toplam_uretim.corr(od.Briks, method="spearman")
    print(f"\n  Uretim ~ Tat   : Spearman rho = {r:+.2f}")
    print(f"  Uretim ~ Briks : Spearman rho = {r2:+.2f}   (n=6, yon gostergesi)")
    print("  " + ("Yuksek uretim dusuk kalite ile gidiyor (klasik odunlesim)" if r < -0.3
                  else "Belirgin odunlesim GORULMUYOR" if r > -0.3 else ""))

    t.round(4).to_csv(base_dir / "strateji_sonuc_ozet.csv")
    print(f"\nKaydedildi: strateji_sonuc_tablosu.csv")
    print("UYARI: n=6 takim. Korelasyonlar yon gostergesidir, kanit degildir.")
    return t


if __name__ == "__main__":
    BASE_DIR = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")
    run(BASE_DIR)
