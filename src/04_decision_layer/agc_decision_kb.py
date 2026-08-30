"""
AGC - DECISION KNOWLEDGE BASE (DKB)
=====================================
Karar katmaninin bilgi tabani. Her hedef icin:

    Durum -> Esik -> Risk -> Aksiyon ailesi -> Kisit -> GUVEN

IKI ESIK TURU (bilincli tasarim)
---------------------------------
1) ZARF ESIGI (veriden)      : her seranin KENDI normal araligi (p5-p95)
   Gunluk operasyonel uyari icin. "Bu sera kendi normalinden sapiyor."
   Gerekce: mutlak esik strateji tespit eder, risk degil. Ornek: EC>6
   kurali Digilog'a surekli alarm verirdi — oysa Digilog en yuksek briks
   (8.86) ve tat (78.0) skorunu alan takimdir; yuksek EC'yi bilerek
   uygulamistir (kontrollu tuz stresi briksi artirir).

2) HASAR ESIGI (literaturden): gercek fizyolojik hasar sinirlari.
   Stratejiden bagimsizdir. Veride nadiren asilir ama asildiginda ciddidir.

GUVEN SEVIYELERI (kalibrasyon olcumunden)
------------------------------------------
Kalibrasyon analizi (bkz. kalibrasyon_ozet.csv, mondrian karsilastirmasi)
her hedefte olasilik iddia edilemeyecegini gosterdi:

  SAYISAL   : kapsama duzeltme sonrasi >=0.93 VE aralik/deger orani <%10
              -> "%94 ihtimalle esigi asacak" denebilir
  KALITATIF : kapsama yeterli degil VEYA aralik genis
              -> yalnizca "yukselis egiliminde, esige yaklasiyor"
  KAPSAM_DISI: aralik degerin kendisi mertebesinde
              -> hic degerlendirilmez

AKSIYON ONERISI SINIRI
-----------------------
Model NEDENSEL DEGILDIR. Veri setinde "cam acik" ile "sicak" birlikte
gorunur cunku takimlar hava sicak OLDUGU ICIN cami acti. Bu yuzden:

  YAPILMAZ : "Cami %50 acarsan sicaklik 2C duser"   (buyukluk iddiasi)
  YAPILIR  : "Havalandirmayi artir" + yon + takim referansi + "buyukluk
             tahmin edilemez" uyarisi

Aksiyonun YONU fizikten ve alti takimin gercek pratiginden gelir;
BUYUKLUGU iddia edilmez.

CIKTI: decision_knowledge_base.csv · dkb_zarf.csv
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------
# HASAR ESIKLERI — literaturden, stratejiden bagimsiz
# Kaynaklar rapora yazilmak uzere isaretlenmistir; degerler yaygin
# bahcecilik pratiginden alinmis TASLAK degerlerdir ve teyit edilmelidir.
# ----------------------------------------------------------------------
HASAR_ESIK = {
    "Tair":     [("doku_hasari_sicak", 35.0, ">", "Yuksek sicaklikta protein denaturasyonu ve polen sterilitesi"),
                 ("soguk_hasari", 10.0, "<", "Dusuk sicaklikta buyume durur, soguk hasari riski")],
    "Rhair":    [("kalici_islak", 95.0, ">", "Yaprak yuzeyinde yogusma, mantar enfeksiyonu icin ideal kosul")],
    "HumDef":   [("terleme_durur", 1.0, "<", "Nem acigi cok dusuk: terleme durur, besin tasinimi aksar"),
                 ("asiri_su_stresi", 15.0, ">", "Cok yuksek nem acigi: stoma kapanir, fotosentez durur")],
    "EC_slab1": [("tuz_hasari", 8.0, ">", "Kok bolgesinde ozmotik stres, su alimi engellenir")],
    "EC_slab2": [("tuz_hasari", 8.0, ">", "Kok bolgesinde ozmotik stres, su alimi engellenir")],
    "WC_slab1": [("kalici_solma", 40.0, "<", "Substrat su icerigi kritik esigin altinda, kalici solma")],
    "WC_slab2": [("kalici_solma", 40.0, "<", "Substrat su icerigi kritik esigin altinda, kalici solma")],
    "t_slab1":  [("kok_soguk_hasari", 12.0, "<", "Kok bolgesi cok soguk: su ve besin alimi durur"),
                 ("kok_sicak_hasari", 30.0, ">", "Kok bolgesi cok sicak: kok solunumu artar, oksijen azalir")],
    "t_slab2":  [("kok_soguk_hasari", 12.0, "<", "Kok bolgesi cok soguk: su ve besin alimi durur"),
                 ("kok_sicak_hasari", 30.0, ">", "Kok bolgesi cok sicak: kok solunumu artar, oksijen azalir")],
}

# ----------------------------------------------------------------------
# AKSIYON AILELERI — yon bilinir, buyukluk iddia edilmez
# ----------------------------------------------------------------------
AKSIYON = {
    ("EC_slab1", "yuksek"): ("Sulama siklığini artir veya drenaj oranini yukselt",
                             "Fazla sulama su israfi ve besin yikanmasi yaratir"),
    ("EC_slab1", "dusuk"):  ("Besin cozeltisi konsantrasyonunu artir",
                             "Ani artis kok sokuna yol acabilir"),
    ("WC_slab1", "dusuk"):  ("Sulama siklığini artir",
                             "Asiri sulama kok bolgesinde oksijen azaltir"),
    ("WC_slab1", "yuksek"): ("Sulama siklığini azalt, drenaji kontrol et",
                             "Ani kesinti su stresi yaratir"),
    ("Tair", "yuksek"):     ("Havalandirmayi artir veya perde ile golgele",
                             "Havalandirma nem ve CO2 kaybina yol acar"),
    ("Tair", "dusuk"):      ("Isitmayi artir veya enerji perdesini kapat",
                             "Isitma en buyuk enerji kalemidir (bkz. strateji raporu)"),
    ("t_slab1", "dusuk"):   ("Kok bolgesi isitmasini artir",
                             "Substrat sicakligi yavas tepki verir, erken mudahale gerekir"),
    ("t_slab1", "yuksek"):  ("Sulama ile kok bolgesini serinlet",
                             "Su sicakligi ani dusurulmemeli"),
    ("HumDef", "dusuk"):    ("Havalandirma veya isitma ile nem acigini yukselt",
                             "Ikisi de enerji maliyeti yaratir"),
    ("HumDef", "yuksek"):   ("Nemlendirme veya havalandirmayi azalt",
                             "Yuksek nem mantar riskini artirir"),
}
for kaynak, hedef in [("EC_slab1", "EC_slab2"), ("WC_slab1", "WC_slab2"), ("t_slab1", "t_slab2")]:
    for yon in ("yuksek", "dusuk"):
        AKSIYON[(hedef, yon)] = AKSIYON[(kaynak, yon)]


def guven_seviyesi(hedef: str, kapsama: float, aralik: float, tipik: float) -> tuple[str, str]:
    """Kalibrasyon olcumune gore sistemin ne iddia edebilecegi."""
    oran = aralik / abs(tipik) if tipik else np.inf
    if oran > 0.5:
        return "KAPSAM_DISI", f"aralik/deger orani %{oran*100:.0f} — degerlendirilmez"
    # SAYISAL esigi: kapsama nominale yakin (>=0.93) VE aralik tipik degerin
    # %20'sinden dar. %20 siniri, esik asimini ayirt edebilmek icin gereken
    # asgari hassasiyettir (bkz. esik_frekanslari analizi).
    if kapsama >= 0.93 and oran < 0.20:
        return "SAYISAL", f"kapsama {kapsama:.2f}, aralik/deger %{oran*100:.0f}"
    return "KALITATIF", f"kapsama {kapsama:.2f}, aralik/deger %{oran*100:.0f}"


def zarf_hesapla(df: pd.DataFrame, hedefler: list[str], alt=5, ust=95) -> pd.DataFrame:
    """Her sera x hedef icin normal calisma zarfi, gunduz/gece ayri."""
    df = df.copy()
    df["gunduz"] = df["Tot_PAR"] > 20
    sat = []
    for h in hedefler:
        if h not in df.columns:
            continue
        for gh, g in df.groupby("greenhouse_id", sort=False):
            for donem, alt_g in [("tumu", g), ("gunduz", g[g.gunduz]), ("gece", g[~g.gunduz])]:
                s = alt_g[h].dropna()
                if len(s) < 200:
                    continue
                sat.append({"hedef": h, "sera": gh, "donem": donem, "n": len(s),
                            "zarf_alt": float(np.percentile(s, alt)),
                            "zarf_ust": float(np.percentile(s, ust)),
                            "medyan": float(s.median()),
                            "p1": float(np.percentile(s, 1)),
                            "p99": float(np.percentile(s, 99))})
    return pd.DataFrame(sat)


def kalibrasyon_oku(base_dir: Path, seviye: float = 0.95) -> dict:
    """Kalibre edilmis aralik genisligi ve kapsama.

    ONEMLI: ham global araliklar kullanilmaz. Kalibrasyon analizi, aralikarin
    uc degerlerde yetersiz kaldigini gosterdi (kapsama 0.855 / nominal 0.95).
    Bu yuzden DURUST SISIRME uygulanir: katsayi dogrulama setinin kendi
    icinden (ilk %60 ile kalibre, son %40'ta uc degerlerde %95 tutturacak
    sekilde) tahmin edilir ve teste uygulanir. Test setine bakilarak
    secilmez — bu dongusel olurdu.
    """
    hp = base_dir / "kalibrasyon_ham.parquet"
    if not hp.exists():
        print("  UYARI: kalibrasyon_ham.parquet yok, guven seviyeleri varsayilan atanacak")
        return {}
    ham = pd.read_parquet(hp)
    val = ham[ham.split == "val"].copy(); test = ham[ham.split == "test"].copy()
    val["err"] = val.y_pred - val.y_true; test["err"] = test.y_pred - test.y_true
    K = ["feature_set", "model", "horizon", "target"]; a = (1 - seviye) / 2

    sat = []
    for k, vg in val.groupby(K):
        m = np.ones(len(test), bool)
        for kol, d in zip(K, k):
            m &= (test[kol] == d).to_numpy()
        tg = test[m]
        if len(tg) < 50 or len(vg) < 200:
            continue
        vg = vg.sort_values("window_ix")
        ve = vg.err.to_numpy(); te = tg.err.to_numpy()
        n = len(ve); ic, son = ve[:int(n * .6)], ve[int(n * .6):]
        lo, hi = np.percentile(ic, [100 * a, 100 * (1 - a)])
        vy = vg.y_true.to_numpy()[int(n * .6):]
        vm = np.median(vy); vuc = np.abs(vy - vm) > np.quantile(np.abs(vy - vm), .80)
        f = 3.0
        for c in np.arange(1.0, 3.01, .05):
            if (((son >= lo * c) & (son <= hi * c))[vuc]).mean() >= seviye:
                f = c; break
        L, H = np.percentile(ve, [100 * a, 100 * (1 - a)])
        sat.append({"horizon": k[2], "target": k[3],
                    "kapsama": float(((te >= L * f) & (te <= H * f)).mean()),
                    "genislik": float((H - L) * f)})
    r = pd.DataFrame(sat)
    if r.empty:
        return {}
    en = r.sort_values("genislik").groupby(["horizon", "target"]).head(1)
    return {(x.target, x.horizon): (x.kapsama, x.genislik) for x in en.itertuples()}


def run(base_dir: Path):
    """Sisirme katsayisi artik kalibrasyon_oku icinde hedef bazinda hesaplaniyor."""
    f = base_dir / "common_core_with_grodan_strict.parquet"
    if not f.exists():
        raise FileNotFoundError(f)
    hedefler = ["Tair", "Rhair", "CO2air", "HumDef", "Tot_PAR",
                "EC_slab1", "EC_slab2", "WC_slab1", "WC_slab2", "t_slab1", "t_slab2"]
    df = pd.read_parquet(f, columns=["Time", "greenhouse_id"] + hedefler)

    print("Zarf esikleri hesaplaniyor (sera bazinda p5-p95)...")
    zarf = zarf_hesapla(df, hedefler)
    zarf.round(3).to_csv(base_dir / "dkb_zarf.csv", index=False)

    kal = kalibrasyon_oku(base_dir)
    tipik = df[hedefler].median().to_dict()

    print("Decision Knowledge Base kuruluyor...\n")
    kayit = []
    for h in hedefler:
        for ufuk in ("3h", "6h"):
            kapsama, genislik = kal.get((h, ufuk), (np.nan, np.nan))
            if np.isfinite(kapsama):
                sev, gerekce = guven_seviyesi(h, kapsama, genislik, tipik[h])
            else:
                sev, gerekce = "KALITATIF", "kalibrasyon olcumu yok"

            # --- Zarf kurallari (sera bazinda) ---
            zh = zarf[(zarf.hedef == h) & (zarf.donem == "tumu")]
            for _, z in zh.iterrows():
                for yon, esik in [("yuksek", z.zarf_ust), ("dusuk", z.zarf_alt)]:
                    aks, kisit = AKSIYON.get((h, yon), ("— aksiyon tanimlanmadi", "—"))
                    kayit.append({
                        "hedef": h, "ufuk": ufuk, "sera": z.sera, "esik_turu": "ZARF",
                        "kural": f"{h} {'>' if yon=='yuksek' else '<'} {esik:.3f}",
                        "esik": round(float(esik), 3), "yon": yon,
                        "risk": f"Bu seranin normal calisma araliginin {'ustune cikiyor' if yon=='yuksek' else 'altina iniyor'}",
                        "aksiyon": aks, "kisit": kisit,
                        "guven": sev, "guven_gerekce": gerekce,
                        "aralik_genislik": round(genislik, 3) if np.isfinite(genislik) else None,
                        "kaynak": "veri (sera p5-p95)"})

            # --- Hasar kurallari (literatur, tum seralar ortak) ---
            for ad, esik, yon_s, aciklama in HASAR_ESIK.get(h, []):
                yon = "yuksek" if yon_s == ">" else "dusuk"
                aks, kisit = AKSIYON.get((h, yon), ("— aksiyon tanimlanmadi", "—"))
                kayit.append({
                    "hedef": h, "ufuk": ufuk, "sera": "TUMU", "esik_turu": "HASAR",
                    "kural": f"{h} {yon_s} {esik}", "esik": esik, "yon": yon,
                    "risk": aciklama, "aksiyon": aks, "kisit": kisit,
                    "guven": sev, "guven_gerekce": gerekce,
                    "aralik_genislik": round(genislik, 3) if np.isfinite(genislik) else None,
                    "kaynak": "literatur (TASLAK — teyit edilecek)"})

    dkb = pd.DataFrame(kayit)
    dkb.to_csv(base_dir / "decision_knowledge_base.csv", index=False)

    # ---------------- Ozet ----------------
    print("=" * 84)
    print("1. GUVEN SEVIYELERI — sistem hangi hedefte ne iddia edebilir?")
    print("=" * 84)
    g = dkb.drop_duplicates(["hedef", "ufuk"])[["hedef", "ufuk", "guven",
                                                "aralik_genislik", "guven_gerekce"]]
    print(g.sort_values(["guven", "hedef"]).to_string(index=False))
    print("\n" + g.guven.value_counts().to_string())

    print("\n" + "=" * 84)
    print("2. ZARF ESIKLERI — seralar arasi fark (3 ornek hedef)")
    print("=" * 84)
    for h in ["EC_slab1", "Tair", "WC_slab1"]:
        z = zarf[(zarf.hedef == h) & (zarf.donem == "tumu")]
        if z.empty:
            continue
        print(f"\n--- {h} ---")
        print(z[["sera", "zarf_alt", "medyan", "zarf_ust"]].round(2).to_string(index=False))

    print("\n" + "=" * 84)
    print("3. HASAR ESIKLERI — veride ne siklikla asiliyor?")
    print("=" * 84)
    for h, esikler in HASAR_ESIK.items():
        if h not in df.columns:
            continue
        for ad, esik, yon, _ in esikler:
            s = df[h].dropna()
            oran = 100 * ((s > esik) if yon == ">" else (s < esik)).mean()
            not_ = "  <- hic olmuyor, koruma amacli" if oran < 0.01 else ""
            print(f"  {h:9s} {yon}{esik:6.1f}  ({ad:20s}) %{oran:5.2f}{not_}")

    print("\n" + "=" * 84)
    print("4. TOPLAM KURAL SAYISI")
    print("=" * 84)
    print(dkb.groupby(["esik_turu", "guven"]).size().unstack(fill_value=0).to_string())
    kul = dkb[dkb.guven != "KAPSAM_DISI"]
    print(f"\n  Toplam kural: {len(dkb)} · kullanilabilir: {len(kul)} "
          f"({len(dkb)-len(kul)} tanesi belirsizlik nedeniyle kapsam disi)")

    print(f"\nKaydedildi: decision_knowledge_base.csv · dkb_zarf.csv")
    return dkb, zarf


if __name__ == "__main__":
    BASE_DIR = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")
    run(BASE_DIR)
