"""
AGC - HAVA ORACLE, COK TOHUMLU TEKRAR
=======================================
NEDEN: Tek kosuluk oracle deneyi SONUCSUZ kaldi.

  Iki mimari ayni yonu gosterme orani : 11/22  (sansla beklenen 11)
  Mimariler arasi korelasyon          : -0.58  (gercek etki olsa POZITIF olurdu)
  Fiziksel kontrol (Tot_PAR)          : TCN +11.2%, GRU -4.6%  -> celisik

Sebep: konfigurasyon basina TEK kosu. Ayni konfigurasyonun iki bagimsiz
kosusu arasinda daha once %0.3-16.3 fark olctuk (GPU non-determinizmi +
erken durdurma epoch farki). Yani +-%10'luk farklar gurultuden ayirt
edilemez ve gozlenen farklarin cogu o aralikta.

TASARIM
-------
Her tohum icin TEMEL ve KAHIN modeli AYNI tohumla egitilir:
  - ayni agirlik baslatmasi
  - ayni veri karistirma sirasi
  -> fark ESLESTIRILMIS olur, baslatma varyansi devreden cikar
  -> kalan varyans yalnizca GPU non-determinizmidir

Sonra tohumlar arasi eslestirilmis farklarin dagilimina bakilir:

  ortalama fark ± standart hata
  |ortalama| > 2 x SH  ->  etki gercek
  aksi halde           ->  etki gurultuden ayirt edilemiyor

Bu, "ise yaramadi" ile "olcemedik" arasindaki farki nihayet ayirir.

COKMEYE DAYANIKLI: her kosu bittiginde CSV'ye eklenir, tekrar
calistirildiginda tamamlananlar atlanir.

ON KOSUL: agc_all_in_one.py ve agc_hava_oracle.py exec edilmis olmali.
SURE: mimari basina 10 kosu (5 tohum x 2 varyant) ~ 1.5 saat.
CIKTI: hava_oracle_cok_tohum.csv
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def _g():
    eksik = [k for k in ["bir_kosu", "OracleSequence", "SEED"] if k not in globals()]
    if eksik:
        raise RuntimeError("Once agc_all_in_one.py ve agc_hava_oracle.py'yi exec edin. "
                           "Eksik: " + ", ".join(eksik))
    return globals()


def tohumlu_kosu(base_dir: Path, fs_name: str, mimari: str, kahin: bool, tohum: int):
    """bir_kosu'yu belirtilen tohumla calistirir.

    SEED global'i gecici olarak degistirilir; hem model baslatmasi hem
    OracleSequence'in karistirma rng'si bu degeri okur. Boylece TEMEL ve
    KAHIN ayni tohumda birebir ayni baslangic kosullarini paylasir.
    """
    g = globals()
    eski = g["SEED"]
    try:
        g["SEED"] = tohum
        return g["bir_kosu"](base_dir, fs_name, mimari, kahin)
    finally:
        g["SEED"] = eski


def run(base_dir: Path, feature_sets=("core_grodan",), mimariler=("tcn", "gru"),
        tohumlar=(42, 7, 123, 2024, 31337), cikti="hava_oracle_cok_tohum.csv"):
    _g()
    yol = base_dir / cikti
    tamam = set()
    if yol.exists():
        onc = pd.read_csv(yol)
        tamam = {(r.feature_set, r.mimari, r.varyant, r.tohum) for r in onc.itertuples()}
        print(f"Mevcut dosya: {len(onc)} satir · {len(tamam)} kosu atlanacak\n")

    plan = [(fs, m, t, k) for fs in feature_sets for m in mimariler
            for t in tohumlar for k in (False, True)]
    print(f"Planlanan kosu: {len(plan)}\n")

    for i, (fs, m, t, kahin) in enumerate(plan, 1):
        var = "kahin" if kahin else "temel"
        anahtar = (fs, m, var, t)
        etiket = f"{fs}/{m}/{var}/tohum={t}"
        if anahtar in tamam:
            print(f"[{i}/{len(plan)}] ATLANDI: {etiket}")
            continue
        print(f"\n{'='*66}\n[{i}/{len(plan)}] {etiket}\n{'='*66}")
        try:
            satir = tohumlu_kosu(base_dir, fs, m, kahin, t)
            for s in satir:
                s["tohum"] = t
            pd.DataFrame(satir).to_csv(yol, mode="a", header=not yol.exists(), index=False)
            tamam.add(anahtar)
            print(f"  -> kaydedildi ({len(satir)} satir)")
        except Exception as exc:
            print(f"  HATA: {exc}")

    if not yol.exists():
        print("Hic sonuc uretilmedi.")
        return None
    return analiz(pd.read_csv(yol))


def analiz(d: pd.DataFrame):
    """Eslestirilmis fark dagilimi — etki gercek mi, gurultu mu?"""
    pd.set_option("display.width", 210)
    p = d.pivot_table(index=["feature_set", "mimari", "horizon", "target", "tohum"],
                      columns="varyant", values="MAE")
    p = p.dropna()
    if p.empty:
        print("Eslesen temel/kahin cifti yok."); return d
    p["fark_%"] = (p["temel"] - p["kahin"]) / p["temel"] * 100   # pozitif = kahin iyi

    print("\n" + "=" * 86)
    print("ESLESTIRILMIS FARK — tohumlar arasi dagilim")
    print("  Pozitif = gelecek hava bilgisi hatayi AZALTTI")
    print("=" * 86)

    o = (p.groupby(["mimari", "horizon", "target"])["fark_%"]
           .agg(n="size", ortalama="mean", std="std").reset_index())
    o["SH"] = o["std"] / np.sqrt(o["n"])
    o["t"] = o.ortalama / o.SH.replace(0, np.nan)
    o["karar"] = np.where(o.t.abs() > 2,
                          np.where(o.ortalama > 0, "GERCEK — hava yardim ediyor",
                                                    "GERCEK — hava ZARAR veriyor"),
                          "gurultuden ayirt edilemiyor")
    for m in o.mimari.unique():
        print(f"\n--- {m.upper()} ---")
        s = o[o.mimari == m].sort_values(["horizon", "ortalama"], ascending=[True, False])
        print(s[["horizon", "target", "n", "ortalama", "std", "SH", "t", "karar"]]
              .round(2).to_string(index=False))

    print("\n" + "=" * 86)
    print("OZET")
    print("=" * 86)
    print(o.karar.value_counts().to_string())
    gercek = o[o.karar.str.startswith("GERCEK")]
    if len(gercek):
        print("\nGercek bulunan etkiler:")
        print(gercek[["mimari", "horizon", "target", "ortalama", "SH", "t"]]
              .round(2).to_string(index=False))
    else:
        print("\nHicbir hedefte etki gurultuden ayirt edilemedi.")

    # Mimariler arasi tutarlilik — gercek etkinin en guclu gostergesi
    if o.mimari.nunique() > 1:
        w = o.pivot_table(index=["horizon", "target"], columns="mimari", values="ortalama")
        w = w.dropna()
        if len(w) and w.shape[1] == 2:
            a, b = w.columns
            r = w[a].corr(w[b], method="spearman")
            uy = (np.sign(w[a]) == np.sign(w[b])).sum()
            print(f"\nMimariler arasi tutarlilik: ayni yon {uy}/{len(w)} · Spearman {r:+.2f}")
            print("  (gercek etki -> yuksek uyum ve POZITIF korelasyon)")

    print("\nEGITIM GURULTUSU REFERANSI — ayni konfigurasyonun tohumlar arasi sacilimi:")
    gur = p.groupby(["mimari", "horizon", "target"])["temel"].agg(
        ort="mean", std="std")
    gur["degisim_%"] = (gur["std"] / gur["ort"] * 100).round(1)
    print(f"  ortalama %{gur['degisim_%'].mean():.1f} · en yuksek %{gur['degisim_%'].max():.1f}")
    print("  -> etkinin gercek sayilabilmesi icin bu mertebeyi asmasi gerekir")
    return o


if __name__ == "__main__":
    BASE_DIR = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")
    run(BASE_DIR)
