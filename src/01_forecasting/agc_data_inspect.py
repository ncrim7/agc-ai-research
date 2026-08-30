"""
AGC 2. Edisyon - VERI GORUNTULEME / DENETIM
============================================
Amac: veri setini Excel veya Google Sheets'te ACIP GOZLE kontrol edebilmek.
Parquet dosyalari ikili formatta oldugu icin dogrudan acilamiyor; bu script
insan tarafindan okunabilir CSV ozetleri uretir.

Uretilen dosyalar (hepsi Excel/Sheets'te acilir):

  01_ornek_satirlar.csv       Her seradan 200 ardisik satir (gercek veri)
  02_kolon_sozlugu.csv        Her kolon: tip, dolu %, min/ort/max, ornek degerler
  03_gunluk_ozet.csv          Gun bazinda ortalamalar - mevsimsel trendi gorursun
  04_split_siniri.csv         train/val/test tarih araliklari
  05_pencere_ornegi.csv       TEK bir egitim penceresi: 288 girdi + 72 cikti satiri
                              (modelin gercekte ne gordugunu satir satir gosterir)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

CORE_TARGETS = ["Tair", "Rhair", "CO2air", "HumDef", "Tot_PAR"]
GRODAN_TARGETS = ["EC_slab1", "EC_slab2", "WC_slab1", "WC_slab2", "t_slab1", "t_slab2"]


def run(base_dir: Path, parquet="common_core_with_grodan_strict.parquet",
        window_csv="window_index_grodan.csv", out_dirname="veri_inceleme"):

    out_dir = base_dir / out_dirname
    out_dir.mkdir(exist_ok=True)

    df = pd.read_parquet(base_dir / parquet)
    print(f"Yuklendi: {parquet}  ->  {df.shape[0]:,} satir x {df.shape[1]} kolon")
    print(f"Seralar: {sorted(df.greenhouse_id.unique())}")
    print(f"Tarih araligi: {df.Time.min()}  ->  {df.Time.max()}\n")

    # --- 01: Her seradan 200 ardisik gercek satir ---
    parcalar = []
    for gh, grp in df.groupby("greenhouse_id", sort=False):
        grp = grp.sort_values("Time").reset_index(drop=True)
        orta = len(grp) // 2                      # sezon ortasindan al (temsili)
        parcalar.append(grp.iloc[orta : orta + 200])
    pd.concat(parcalar).to_csv(out_dir / "01_ornek_satirlar.csv", index=False)
    print("01_ornek_satirlar.csv       -> 6 sera x 200 satir, sezon ortasindan")

    # --- 02: Kolon sozlugu ---
    satirlar = []
    for col in df.columns:
        s = df[col]
        kayit = {
            "kolon": col,
            "tip": str(s.dtype),
            "dolu_yuzde": round(100 * s.notna().mean(), 2),
            "essiz_deger": int(s.nunique()),
        }
        if pd.api.types.is_numeric_dtype(s):
            kayit.update({
                "min": round(float(s.min()), 3) if s.notna().any() else None,
                "ortalama": round(float(s.mean()), 3) if s.notna().any() else None,
                "max": round(float(s.max()), 3) if s.notna().any() else None,
            })
        kayit["ornek_degerler"] = ", ".join(map(str, s.dropna().unique()[:5]))
        kayit["rol"] = ("HEDEF (Core)" if col in CORE_TARGETS else
                        "HEDEF (Grodan)" if col in GRODAN_TARGETS else
                        "zaman" if col == "Time" else
                        "kimlik" if col == "greenhouse_id" else "girdi")
        satirlar.append(kayit)
    pd.DataFrame(satirlar).to_csv(out_dir / "02_kolon_sozlugu.csv", index=False)
    print("02_kolon_sozlugu.csv        -> her kolonun tipi, doluluk orani, araligi, rolu")

    # --- 03: Gunluk ozet (mevsimsel trend burada gorunur) ---
    say = df.copy()
    say["tarih"] = say["Time"].dt.date
    sayisal = [c for c in say.select_dtypes(include=[np.number]).columns]
    gunluk = say.groupby(["greenhouse_id", "tarih"])[sayisal].mean().round(2).reset_index()
    gunluk.to_csv(out_dir / "03_gunluk_ozet.csv", index=False)
    print("03_gunluk_ozet.csv          -> gun bazinda ortalama; Aralik->Mayis degisimini gosterir")

    # --- 04: Split sinirlari ---
    satirlar = []
    for gh, grp in df.groupby("greenhouse_id", sort=False):
        grp = grp.sort_values("Time").reset_index(drop=True)
        n = len(grp)
        sinir = {"train": (0, int(n * .70)),
                 "val": (int(n * .70), int(n * .70) + int(n * .15)),
                 "test": (int(n * .70) + int(n * .15), n)}
        for isim, (lo, hi) in sinir.items():
            seg = grp.iloc[lo:hi]
            satirlar.append({"sera": gh, "split": isim, "satir": hi - lo,
                             "baslangic": seg.Time.iloc[0], "bitis": seg.Time.iloc[-1],
                             "gun_sayisi": round((seg.Time.iloc[-1] - seg.Time.iloc[0]).total_seconds() / 86400, 1)})
    pd.DataFrame(satirlar).to_csv(out_dir / "04_split_siniri.csv", index=False)
    print("04_split_siniri.csv         -> train/val/test hangi tarihleri kapsiyor")

    # --- 05: TEK bir pencere, satir satir (modelin gordugu sey) ---
    w = pd.read_csv(base_dir / window_csv)
    ilk = w[w.split == "train"].iloc[len(w[w.split == "train"]) // 2]
    gh = ilk.greenhouse_id
    grp = df[df.greenhouse_id == gh].sort_values("Time").reset_index(drop=True)
    pencere = grp.iloc[int(ilk.input_start) : int(ilk.window_end)].copy()
    pencere.insert(0, "pencere_rolu",
                   ["GIRDI (24 saat gecmis)"] * 288 + ["CIKTI (tahmin edilecek)"] * 72)
    pencere.insert(1, "adim", list(range(-287, 1)) + list(range(1, 73)))
    pencere.to_csv(out_dir / "05_pencere_ornegi.csv", index=False)
    print(f"05_pencere_ornegi.csv       -> {gh} serasindan 1 pencere: 288 girdi + 72 cikti satiri")

    # --- Ekrana ozet ---
    print("\n" + "=" * 78)
    print("HIZLI KONTROL")
    print("=" * 78)
    print(f"Toplam satir      : {len(df):,}   (beklenen: 47.809 x 6 = 286.854)")
    print(f"Sera basina satir : {df.groupby('greenhouse_id').size().unique()}")
    print(f"Kolon sayisi      : {df.shape[1]}")
    print(f"Zaman araligi     : {df.Time.min()} -> {df.Time.max()}")
    print(f"Hedef kolonlar    : {[c for c in CORE_TARGETS + GRODAN_TARGETS if c in df.columns]}")
    bos = df.isna().mean() * 100
    print(f"NaN iceren kolon  : {(bos > 0).sum()} / {len(bos)}  (en kotu: {bos.max():.2f}%)")

    print("\n--- Hedeflerin sezon basi vs sezon sonu karsilastirmasi ---")
    print("(Buyuk fark = mevsimsel kayma = modelin kis ogrenip mayis'ta sinava girmesi)")
    ilk_ay = df[df.Time < df.Time.min() + pd.Timedelta(days=30)]
    son_ay = df[df.Time > df.Time.max() - pd.Timedelta(days=30)]
    karsilastir = pd.DataFrame({
        "ilk_30_gun": ilk_ay[CORE_TARGETS].mean().round(1),
        "son_30_gun": son_ay[CORE_TARGETS].mean().round(1),
    })
    karsilastir["oran"] = (karsilastir.son_30_gun / karsilastir.ilk_30_gun).round(2)
    print(karsilastir.to_string())

    print(f"\nTum dosyalar: {out_dir}")
    print("Drive'dan indirip Excel veya Google Sheets ile acabilirsin.")


if __name__ == "__main__":
    BASE_DIR = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")
    run(BASE_DIR)
