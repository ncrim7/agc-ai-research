"""
AGC - KULLANILMAYAN VERI SETLERI ENVANTERI
============================================
Kullanilmayan bes dosya turunu (Resources, Production, CropParameters,
LabAnalysis, TomQuality) tarar ve her biri icin karar vermeye yetecek
ozeti cikarir.

AMAC: "bu veriyle ne yapabiliriz" sorusunu hatirlamayla degil, gercek
satir/kolon sayilariyla cevaplamak.

CIKTI:
  kullanilmayan_envanter.csv   - dosya x takim: satir, kolon, tarih araligi
  kullanilmayan_kolonlar.csv   - her dosyanin kolon sozlugu + doluluk
  ornek_*.csv                  - her dosyadan ilk 20 satir (goz kontrolu icin)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

TAKIMLAR = ["AICU", "Automatoes", "Digilog", "IUACAAS", "Reference", "TheAutomators"]
DOSYALAR = ["Resources", "Production", "CropParameters", "LabAnalysis", "TomQuality"]


def klasor_bul(takim: str, base: Path) -> Path | None:
    d = base / takim
    if d.exists():
        return d
    hedef = takim.replace(" ", "").lower()
    for f in base.iterdir():
        if f.is_dir() and f.name.replace(" ", "").lower() == hedef:
            return f
    return None


def excel_tarih(s: pd.Series) -> pd.Series:
    return pd.Timestamp("1899-12-30") + pd.to_timedelta(pd.to_numeric(s, errors="coerce"), unit="D")


def run(base_dir: Path, out_dirname: str = "kullanilmayan_inceleme"):
    out = base_dir / out_dirname
    out.mkdir(exist_ok=True)
    env, kol = [], []

    for ad in DOSYALAR:
        ornekler = []
        for takim in TAKIMLAR:
            kl = klasor_bul(takim, base_dir)
            if kl is None:
                continue
            adaylar = list(kl.glob(f"*{ad}*"))
            if not adaylar:
                env.append({"dosya": ad, "takim": takim, "durum": "YOK"})
                continue
            try:
                df = pd.read_csv(adaylar[0], skipinitialspace=True)
                df.columns = df.columns.str.strip()
            except Exception as exc:
                env.append({"dosya": ad, "takim": takim, "durum": f"HATA: {exc}"})
                continue

            zaman = [c for c in df.columns if "time" in c.lower() or "date" in c.lower()]
            ilk = son = None
            if zaman:
                t = excel_tarih(df[zaman[0]])
                if t.notna().any():
                    ilk, son = str(t.min())[:10], str(t.max())[:10]

            env.append({"dosya": ad, "takim": takim, "durum": "OK",
                        "satir": len(df), "kolon": df.shape[1],
                        "zaman_kolonu": zaman[0] if zaman else None,
                        "ilk_tarih": ilk, "son_tarih": son,
                        "ortalama_doluluk_%": round(100 * df.notna().mean().mean(), 1)})

            for c in df.columns:
                s = df[c]
                kayit = {"dosya": ad, "takim": takim, "kolon": c,
                         "tip": str(s.dtype), "doluluk_%": round(100 * s.notna().mean(), 1),
                         "essiz": int(s.nunique())}
                sn = pd.to_numeric(s, errors="coerce")
                if sn.notna().any():
                    kayit.update({"min": round(float(sn.min()), 3),
                                  "ortalama": round(float(sn.mean()), 3),
                                  "max": round(float(sn.max()), 3)})
                kayit["ornek"] = ", ".join(map(str, s.dropna().unique()[:3]))
                kol.append(kayit)

            if takim == TAKIMLAR[0]:
                ornekler.append(df.head(20))

        if ornekler:
            ornekler[0].to_csv(out / f"ornek_{ad}.csv", index=False)

    e = pd.DataFrame(env)
    k = pd.DataFrame(kol)
    e.to_csv(out / "kullanilmayan_envanter.csv", index=False)
    k.to_csv(out / "kullanilmayan_kolonlar.csv", index=False)

    print("=" * 78)
    print("ENVANTER — dosya basina satir sayisi")
    print("=" * 78)
    ok = e[e.durum == "OK"]
    if len(ok):
        piv = ok.pivot_table(index="dosya", columns="takim", values="satir", aggfunc="first")
        print(piv.to_string())
        print("\nTarih araliklari (bir takimdan ornek):")
        print(ok[ok.takim == ok.takim.iloc[0]][["dosya", "satir", "kolon", "ilk_tarih",
                                                "son_tarih", "ortalama_doluluk_%"]].to_string(index=False))

    print("\n" + "=" * 78)
    print("KOLONLAR — dosya basina (ilk takimdan)")
    print("=" * 78)
    for ad in DOSYALAR:
        s = k[(k.dosya == ad) & (k.takim == TAKIMLAR[0])]
        if s.empty:
            print(f"\n--- {ad}: bulunamadi ---")
            continue
        print(f"\n--- {ad} ({len(s)} kolon) ---")
        print(s[["kolon", "tip", "doluluk_%", "essiz", "ornek"]].to_string(index=False))

    print("\n" + "=" * 78)
    print("SORUNLU KOLONLAR (doluluk < %50)")
    print("=" * 78)
    bos = k[k["doluluk_%"] < 50]
    if len(bos):
        print(bos.groupby(["dosya", "kolon"])["doluluk_%"].mean().round(1).to_string())
    else:
        print("  yok")

    print(f"\nKaydedildi: {out}")
    return e, k


if __name__ == "__main__":
    BASE_DIR = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")
    run(BASE_DIR)
