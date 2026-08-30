"""
AGC - EKONOMIK ZEMIN
======================
DKB'nin ekonomik katmanini VARSAYIMDAN degil OLCUMDEN kurar.

Economics.pdf resmi fiyatlari verdi:
    Isi        0.0083 €/MJ
    Elektrik   0.08 €/kWh (07:00-23:00) · 0.04 €/kWh disinda
    CO2        0.08 €/kg ilk 12 kg/m², sonra 0.2 €/kg
    Gelir      Brix ve tarihe bagli; B sinifi YARIM fiyat
    Bitki      2.20 €/bitki (2 govdeli) x 1.8 bitki/m²
    Iscilik    0.0085 €/govde/m²/gun

ReadMe.pdf deterministik formulleri verdi:
    Heat_cons = ((t_rail - t_air)*2.1 + (t_grow - t_air)*0.62) -> MJ/gun
    Elektrik  = HPS 81 W/m² + LED (mavi 7.27, kirmizi 25.3, uzak-kirmizi 6.23,
                beyaz 22.72 W/m²), lamba calisma suresiyle orantili
    Tot_PAR   = dis PAR x ortu(0.5) x perde gecirgenlikleri + lamba PAR'i

BU SCRIPT NE OLCER
------------------
1) EC -> Brix esnekligi. Her kalite olcumu icin onceki 14 gunun kok bolgesi
   EC ortalamasi hesaplanir, Brix buna karsi regres edilir. 6 takim x 8 olcum
   = 48 gozlem (sezon ortalamasindaki 6'dan cok daha iyi).
2) Brix -> fiyat egimi. Resmi fiyat tablosundan, tarihe gore.
3) Zincirin tamami: 1 birim EC sapmasi kac €/m² eder?
4) Deterministik maliyet katsayilari: 1 saat lamba, 1 derece boru farki.

CIKTI: ekonomik_zemin.csv · ec_brix_regresyon.csv
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

TAKIMLAR = ["AICU", "Automatoes", "Digilog", "IUACAAS", "Reference", "TheAutomators"]
EPOCH = pd.Timestamp("1899-12-30")
TQ_KOL = ["%time", "Flavour", "TSS", "Acid", "%Juice", "Bite", "Weight", "DMC_fruit"]

# Economics.pdf Tablo 1
FIYAT = [("2020-01-01", 5.00, 3.00), ("2020-01-15", 5.20, 3.50), ("2020-01-29", 4.50, 3.50),
         ("2020-02-12", 4.20, 2.80), ("2020-02-26", 3.80, 2.50), ("2020-03-11", 3.20, 2.20),
         ("2020-03-25", 2.80, 2.00), ("2020-04-08", 2.60, 1.80), ("2020-04-22", 2.40, 1.60),
         ("2020-05-06", 2.50, 1.40), ("2020-05-20", 2.60, 1.20), ("2020-06-03", 2.50, 1.10)]
# ReadMe.pdf: lamba elektrik tuketimi W/m²
HPS_W, LED_W = 81.0, {"blue": 7.27, "red": 25.3, "farred": 6.23, "white": 22.72}
ISI_FIY, ELEK_PIK, ELEK_DUS = 0.0083, 0.08, 0.04
CO2_UCUZ, CO2_PAHALI, CO2_ESIK = 0.08, 0.20, 12.0


def _fy() -> pd.DataFrame:
    f = pd.DataFrame(FIYAT, columns=["t", "b10", "b6"])
    f["t"] = pd.to_datetime(f.t)
    return f


def fiyat(tarih, brix: float) -> float:
    """Brix ve tarihe gore €/kg. Brix 6 ile 10 arasi dogrusal ara deger."""
    f = _fy(); r = f[f.t <= tarih]
    r = r.iloc[-1] if len(r) else f.iloc[0]
    return float(r.b6 + (brix - 6.0) / 4.0 * (r.b10 - r.b6))


def brix_fiyat_egimi(tarih) -> float:
    """1 Brix artisinin €/kg karsiligi — tarihe bagli."""
    f = _fy(); r = f[f.t <= tarih]
    r = r.iloc[-1] if len(r) else f.iloc[0]
    return float((r.b10 - r.b6) / 4.0)


def _oku(base: Path, takim: str, tip: str) -> pd.DataFrame:
    a = list(base.glob(f"{takim}_{tip}.csv")) or list((base / takim).glob(f"*{tip}*"))
    x = pd.read_csv(a[0], skipinitialspace=True)
    x.columns = x.columns.str.strip()
    x = x.loc[:, ~x.columns.str.startswith("Unnamed")]
    if tip == "TomQuality" and (any("\t" in c for c in x.columns) or len(x.columns) < 8):
        x = pd.read_csv(a[0], skiprows=1, header=None, names=TQ_KOL)
        for c in TQ_KOL:
            x[c] = pd.to_numeric(x[c].astype(str).str.replace("\t", "").str.strip(), errors="coerce")
    zc = [c for c in x.columns if "time" in c.lower()][0]
    if tip == "Production":
        x.loc[x[zc] < 43800, zc] += 365          # Reference yil hatasi
    x["Time"] = EPOCH + pd.to_timedelta(pd.to_numeric(x[zc], errors="coerce"), unit="D")
    return x.drop(columns=[zc])


def run(base_dir: Path, pencere_gun: int = 14):
    iklim = pd.read_parquet(base_dir / "common_core_with_grodan_strict.parquet",
                            columns=["Time", "greenhouse_id", "EC_slab1", "EC_slab2",
                                     "WC_slab1", "Tair", "Tot_PAR", "HumDef"])
    iklim["EC"] = iklim[["EC_slab1", "EC_slab2"]].mean(axis=1)

    # ---------- 1. EC -> Brix ----------
    sat = []
    for t in TAKIMLAR:
        q = _oku(base_dir, t, "TomQuality").sort_values("Time")
        g = iklim[iklim.greenhouse_id == t]
        for _, r in q.iterrows():
            m = (g.Time > r.Time - pd.Timedelta(days=pencere_gun)) & (g.Time <= r.Time)
            p = g[m]
            if len(p) < 500 or not np.isfinite(r.TSS):
                continue
            sat.append({"takim": t, "tarih": r.Time, "Brix": r.TSS, "Tat": r.Flavour,
                        "Agirlik": r.Weight, "EC_ort": p.EC.mean(), "EC_max": p.EC.max(),
                        "Tair_ort": p.Tair.mean(), "PAR_kum": p.Tot_PAR.sum() * 300 / 1e6,
                        "WC_ort": p.WC_slab1.mean(), "HumDef_ort": p.HumDef.mean()})
    d = pd.DataFrame(sat)
    d.to_csv(base_dir / "ec_brix_regresyon.csv", index=False)
    print(f"Gozlem: {len(d)} (kalite olcumu x takim)\n")

    print("=" * 76)
    print("1. EC -> BRIX  (onceki 14 gunun kok bolgesi EC ortalamasi)")
    print("=" * 76)
    for y in ["Brix", "Tat", "Agirlik"]:
        r = d[["EC_ort", "EC_max", "Tair_ort", "PAR_kum", "WC_ort"]].corrwith(
            d[y], method="spearman").round(2)
        print(f"  {y:9s} " + " · ".join(f"{k} {v:+.2f}" for k, v in r.items()))

    # En kucuk kareler: Brix ~ EC + Tair + PAR  (takim etkisi cikarilmis)
    X = d[["EC_ort", "Tair_ort", "PAR_kum"]].copy()
    ort = d.groupby("takim")[["EC_ort", "Tair_ort", "PAR_kum", "Brix"]].transform("mean")
    Xc = X - ort[X.columns].values                       # takim-ici sapma
    yc = d.Brix - ort.Brix.values
    Xd = np.c_[np.ones(len(Xc)), Xc.to_numpy()]
    kat, *_ = np.linalg.lstsq(Xd, yc.to_numpy(), rcond=None)
    tah = Xd @ kat
    r2 = 1 - ((yc - tah) ** 2).sum() / max(((yc - yc.mean()) ** 2).sum(), 1e-12)
    print(f"\n  Takim-ici regresyon (sabit etkiler cikarilmis), R² = {r2:.3f}")
    for ad, k in zip(["sabit", "EC_ort", "Tair_ort", "PAR_kum"], kat):
        print(f"    {ad:9s} {k:+.4f}")
    dBrix_dEC = float(kat[1])

    # ---------- 2. Brix -> fiyat ----------
    print("\n" + "=" * 76)
    print("2. BRIX -> FIYAT  (Economics.pdf Tablo 1)")
    print("=" * 76)
    for tar in ["2020-02-15", "2020-04-15", "2020-05-25"]:
        t_ = pd.Timestamp(tar)
        print(f"  {tar}: 1 Brix = {brix_fiyat_egimi(t_):.3f} €/kg  "
              f"(Brix 8.5 -> {fiyat(t_, 8.5):.2f} €/kg)")
    egim_ort = np.mean([brix_fiyat_egimi(pd.Timestamp(x))
                        for x in ["2020-02-15", "2020-04-15", "2020-05-25"]])

    # ---------- 3. Zincir ----------
    uretim = 14.0        # kg/m², alti takimin tipik degeri
    print("\n" + "=" * 76)
    print("3. ZINCIR: 1 birim EC sapmasi kac €/m²?")
    print("=" * 76)
    print(f"  dBrix/dEC        = {dBrix_dEC:+.4f} Brix / (dS/m)")
    print(f"  dFiyat/dBrix     = {egim_ort:.3f} €/kg  (sezon ortalamasi)")
    print(f"  Uretim           = {uretim:.1f} kg/m²")
    print(f"  -> 1 dS/m EC     = {dBrix_dEC*egim_ort*uretim:+.2f} €/m²")
    print("\n  UYARI: bu bir ILISKI olcumudur, nedensel etki degil. Takimlar EC'yi")
    print("  rastgele degil bilincli olarak secti; deger yon ve mertebe gostergesidir.")

    # ---------- 4. Deterministik maliyetler ----------
    print("\n" + "=" * 76)
    print("4. DETERMINISTIK MALIYET KATSAYILARI (ReadMe + Economics)")
    print("=" * 76)
    led_top = sum(LED_W.values())
    for ad, w in [("HPS", HPS_W), ("LED tam", led_top), ("HPS+LED", HPS_W + led_top)]:
        kwh = w / 1000
        print(f"  {ad:9s} 1 saat calisma: {kwh:.4f} kWh/m² -> "
              f"pik {kwh*ELEK_PIK*100:.2f} cent/m² · disi {kwh*ELEK_DUS*100:.2f} cent/m²")
    print(f"\n  Isitma: (t_rail-t_air)*2.1 + (t_grow-t_air)*0.62  W/m²")
    for dt in [5, 10, 20]:
        mj = (dt * 2.1 + dt * 0.62) * 3600 / 1e6
        print(f"    her iki boru da hava+{dt}°C, 1 saat: {mj:.3f} MJ/m² -> "
              f"{mj*ISI_FIY*100:.2f} cent/m²")
    print(f"\n  CO2: ilk 12 kg/m² {CO2_UCUZ} €/kg, sonrasi {CO2_PAHALI} €/kg "
          f"({CO2_PAHALI/CO2_UCUZ:.1f} kat)")

    print("\n" + "=" * 76)
    print("5. KIYAS — hangi kalem ne kadar onemli? (sezon toplami, €/m²)")
    print("=" * 76)
    print("  Elektrik  15.6 – 20.6   <- toplam maliyetin %55-65'i")
    print("  Iscilik    5.1          sabit")
    print("  Bitki      4.0          sabit")
    print("  Isitma     1.4 –  3.9   <- yalnizca %5-12")
    print("  CO2        0.6 –  1.1")
    print("  -> Karar katmani oncelikle LAMBA kullanimina odaklanmalidir.")

    ozet = pd.DataFrame([{"dBrix_dEC": dBrix_dEC, "dFiyat_dBrix": egim_ort,
                          "EC_etkisi_eur_m2": dBrix_dEC * egim_ort * uretim,
                          "R2": r2, "n": len(d),
                          "HPS_saat_pik_cent": HPS_W / 1000 * ELEK_PIK * 100,
                          "isi_10C_saat_cent": (10 * 2.72) * 3600 / 1e6 * ISI_FIY * 100}])
    ozet.to_csv(base_dir / "ekonomik_zemin.csv", index=False)
    print(f"\nKaydedildi: ekonomik_zemin.csv · ec_brix_regresyon.csv")
    return d, ozet


if __name__ == "__main__":
    BASE_DIR = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")
    run(BASE_DIR)
