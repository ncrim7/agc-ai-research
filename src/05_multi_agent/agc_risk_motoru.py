"""
AGC - RISK MOTORU
===================
Karar katmaninin calisan cekirdegi. Tahmin + belirsizlik + DKB -> uyari.

    tahmin  +  kalibre aralik  +  esik  ->  RISK BAYRAGI  +  gerekce
                                              + aksiyon ailesi
                                              + takim referansi

IKI RISK KATMANI
----------------
FIZYOLOJIK : bitki stresi / hasar. Zarf sapmasi (sera bazinda) ve
             hasar esigi (literatur) olarak iki turdedir.
ECONOMIK   : dort deterministik kural. (1) toplam degisken birim maliyet
             — €/kg, alti gercek takimin olculmus degerine kiyaslanir;
             (2) tarife verimliligi — pik-saat elektrik tuketim payi;
             (3) CO2 esik egilimi — kumulatif dozajin sezon sonu projeksiyonu;
             (4) lamba kullanimi — mevsime duyarli referansa kiyasla kWh/m².
             Tumu Economics.pdf + ReadMe.pdf'den turetilmis, %0.2-2.2 hatayla
             dogrulanmis (bkz. Ekonomi raporu).

GUVEN SEVIYESINE GORE CIKTI
----------------------------
SAYISAL    : "%94 ihtimalle esigi asacak"  (yalnizca EC_slab, WC_slab 6h)
KALITATIF  : "yukselis egiliminde, esige yaklasiyor"  (olasilik verilmez)
KAPSAM_DISI: hicbir uyari uretilmez

Bu ayrim kalibrasyon olcumunden gelir; sistem bilmedigini bildiginde susar.

AKSIYON ONERISI SINIRI
-----------------------
Model nedensel DEGILDIR. Aksiyonun YONU fizikten ve alti takimin gercek
pratiginden gelir; BUYUKLUGU iddia edilmez. Her oneriye "bu takim boyle
yapmisti ve su sonucu almisti" referansi eklenir.

KULLANIM
--------
    motor = RiskMotoru(BASE_DIR)
    uyarilar = motor.degerlendir(tahminler)     # DataFrame
    print(motor.rapor(uyarilar))
"""



from __future__ import annotations

SURUM = "2026-08-24.1"   # karar_degeri: kriterin esikle karsilastirdigi deger

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

# Ekonomi raporundan: alti takimin toplam DEGISKEN birim maliyeti (€/kg).
# NOT: eski surumde burada isitma/kg (MJ/kg) kullaniliyordu. Net karla
# korelasyonu olculdugunde ISITMA/KG icin Spearman rho = -0.09 (ongoru gucu
# YOK) cikti; EURO/KG icin rho = -1.00 (mukemmel siralama) cikti. Bu yuzden
# referans euro cinsine cevrildi (bkz. Ekonomi raporu Bolum 2, Strateji
# raporu Surum 2).
REFERANS_VERIMLILIK = {          # €/kg, degisken maliyet (isi+elektrik+CO2) / uretim
    "Automatoes": 1.294, "AICU": 1.401, "IUACAAS": 1.407,
    "Reference": 1.501, "TheAutomators": 1.570, "Digilog": 1.603,
}
# Ekonomi raporundan: kis donemi pik-saat elektrik TUKETIM payi (zaman
# payi degil -- pik saatler sabit 16/24=0.667'dir, ayirt edici olan
# TUKETIMIN o saatlere denk gelen kismidir)
REFERANS_PIK_PAYI = {
    "Automatoes": 57.6, "Reference": 58.5, "TheAutomators": 62.0,
    "Digilog": 62.8, "IUACAAS": 66.8, "AICU": 67.8,
}
# Ekonomi raporundan: sezon sonu kumulatif CO2 dozaji (kg/m²)
REFERANS_CO2_SEZON = {
    "IUACAAS": 7.28, "Reference": 8.63, "Automatoes": 9.07,
    "Digilog": 9.66, "AICU": 10.15, "TheAutomators": 12.50,
}
# Mevsime gore haftalik lamba elektrik tuketimi (kWh/m²), alti takim ortalamasi
REFERANS_LAMBA_HAFTALIK = {"kis": 15.28, "yaz": 3.70}
ELEK_PIK, ELEK_DUS = 0.08, 0.04            # €/kWh, Economics.pdf
CO2_UCUZ, CO2_PAHALI, CO2_ESIK = 0.08, 0.20, 12.0
PIK_BAS, PIK_BIT = 7, 23
# Strateji raporundan: aksiyon onerilerine eklenecek takim referanslari
TAKIM_REFERANS = {
    ("EC_slab1", "yuksek"): "AICU drenaj oranini 0.43'e cikararak yonetiyor (alti takimin en yuksegi)",
    ("EC_slab2", "yuksek"): "AICU drenaj oranini 0.43'e cikararak yonetiyor",
    ("WC_slab1", "dusuk"):  "IUACAAS en yuksek sulamayi uyguluyor (867 birim/sezon)",
    ("WC_slab2", "dusuk"):  "IUACAAS en yuksek sulamayi uyguluyor",
    ("Tair", "dusuk"):      "Automatoes en sicak serayi en dusuk ikinci isitmayla isletti (23.3C / 185 birim)",
    ("Tair", "yuksek"):     "Digilog en serin rejimi uyguladi ve en yuksek briks/tat skorunu aldi",
    ("t_slab1", "dusuk"):   "Kok bolgesi yavas tepki verir; Automatoes erken mudahale profili gosteriyor",
    ("t_slab2", "dusuk"):   "Kok bolgesi yavas tepki verir; erken mudahale gerekir",
}


# Tanimsal fiziksel sinirlar. Bunlar LITERATUR degeri degil, degiskenin TANIMIDIR:
# bagil nem %0-100 arasindadir, nem acigi ve EC negatif olamaz, hacimsel su
# icerigi %0-100'dur. None = tanimsal sinir yok (sicakliklar, CO2 ust siniri).
# Neden gerekli: aralik "tahmin +- 1.96*sigma" ile kuruluyor ve sigma genis olan
# hedeflerde bu sinirin disina tasiyor. Olculdu (Automatoes + TheAutomators,
# 47.809'ar adim): Rhair 3h/6h adimlarin %64-88'inde, HumDef %79-87'sinde
# tasiyor. Basilan "nem %119" veya "nem acigi -5" gibi degerler sistemin
# guvenilirligini bozar.
FIZIKSEL_SINIR = {
    "Rhair": (0.0, 100.0), "WC_slab1": (0.0, 100.0), "WC_slab2": (0.0, 100.0),
    "HumDef": (0.0, None), "Tot_PAR": (0.0, None), "CO2air": (0.0, None),
    "EC_slab1": (0.0, None), "EC_slab2": (0.0, None),
}


@dataclass
class Uyari:
    zaman: object
    sera: str
    hedef: str
    ufuk: str
    katman: str          # FIZYOLOJIK / EKONOMIK
    esik_turu: str       # ZARF / HASAR / VERIMLILIK
    seviye: str          # KRITIK / ORTA / BILGI
    guven: str           # SAYISAL / KALITATIF
    mesaj: str
    tahmin: float = np.nan
    aralik_alt: float = np.nan
    aralik_ust: float = np.nan
    esik: float = np.nan
    olasilik: float = np.nan
    aksiyon: str = ""
    kisit: str = ""
    referans: str = ""
    # --- YENI: aralik seffafligi ---
    # aralik_gosterilebilir: aralik insana/ajana SUNULABILIR mi. SAYISAL disindaki
    #   guven seviyelerinde False. Gerekce: KALITATIF'in tanimi "olasilik verilemez,
    #   yalnizca yon" (Karar Katmani Raporu 4.1). Sayisal bir aralik basmak, verilemez
    #   denen seyi baska bicimde vermektir. Aralik yine de saklanir cunku "esige
    #   yaklasiyor" karari onu kullanir -- karar izlenebilir kalmali.
    # aralik_kirpildi: aralik tanimsal fiziksel sinira dayandigi icin kesildi mi.
    #   True ise Gauss varsayimi o vaka icin gorunur bicimde basarisiz demektir.
    aralik_gosterilebilir: bool = True
    aralik_kirpildi: bool = False
    # KARARI VEREN DEGER: kriterin esikle karsilastirdigi deger.
    #   dokunma + yuksek -> pencere MAKSIMUMU · dokunma + dusuk -> MINIMUM
    #   surekli + yuksek -> pencere MINIMUMU  · surekli + dusuk -> MAKSIMUM
    # 'tahmin' terminal degerdir ve KARARI VERMEZ. Ikisini ayirmadan ekranda
    # "esik 958 · tahmin 880 · esigi asiyor" gibi anlamsiz satirlar cikiyor.
    karar_degeri: float = np.nan
    karar_yonu: str = ""          # 'yuksek' | 'dusuk'  (kuralin yonu)


class RiskMotoru:
    DKB_DOSYA = "decision_knowledge_base_v5.csv"   # GUNCEL SURUM (v5: mevsim boyutu eklendi; v4 satirlari mevsim="tumu" olarak aynen korunur)

    def __init__(self, base_dir: Path, hassasiyet: str = "orta",
                 dkb_dosya: str | None = None,
                 yaklasma_uyarisi: bool | None = None,
                 p_esik: float | None = None,
                 mevsim_modu: str = "tumu",
                 kriter: str = "surekli",
                 sessiz_hedefler: tuple = ()):
        """hassasiyet: 'kritik' (yalnizca yuksek guvenli) veya 'orta' (daha cok uyari)

        DUZELTME 1 (4. tekrar onleme): eski surum sabit olarak
        'decision_knowledge_base.csv' okuyordu; bu v1'dir ve CO2air/HumDef/
        Rhair(6h) icin guven=KAPSAM_DISI tasir -> motor bu hedeflerde SESSIZ
        kalir. v3 ile v1 arasindaki tek fark 'guven' ve 'guven_gerekce'
        kolonlarindadir (65 satir); esik/yon/aksiyon/aralik_genislik
        birebir aynidir. Dosya bulunamazsa SESSIZCE eskiye DUSMEZ.

        DUZELTME 2 (alarm yorgunlugu, ikinci kapi): 'hassasiyet' tek bir anahtarla
        BIRBIRINDEN BAGIMSIZ iki seyi kontrol ediyordu:
          (a) SAYISAL uyarilar icin olasilik esigi (0.50 / 0.75)
          (b) KALITATIF hedeflerde "esige yaklasiyor" (BILGI) dalinin acik olmasi
        Ikisi ayri parametreye bolundu. (b) artik VARSAYILAN OLARAK KAPALI.

        Neden kapali — olculdu (Automatoes + TheAutomators, tam sezon 47.809 adim,
        oracle tahmin):
          mevcut (aralik-yaklasiyor acik) : 24.00 sa/gun aktif · ayni anda ~15-16 uyari
          dokunma tabanli ara secenek     : 20.1-20.5 sa/gun (zaten reddedilmis olan
                                            21.9 sa/gun ile ayni mertebede)
          yalnizca surekli sapma          :  5.0- 5.3 sa/gun · ayni anda 0.6-0.8 uyari
        Uretilen uyarilarin %95'i bu daldan geliyordu. Dal yalnizca KALITATIF
        seviyede vardir -- yani gerekcesi, motorun kendi tasariminda "sunulamaz"
        sayilan araligin ta kendisidir (bkz. aralik_gosterilebilir). Sunulamaz bir
        sayiya dayanan uyari uretmek tutarsizdir.

        Zarf-genisligine gore "yakinlik" tanimlamak DENENMEDI, cunku zarf genisligi
        mevsime gore 2 kata kadar degisiyor (HumDef ilkbahar/kis = 1.94-2.09,
        WC_slab1 = 0.46-0.57) -- bu, projede dort kez tekrarlanan "mevsimsel
        referans karistirma" hatasinin bes incisi olurdu.

        Eski davranis kaybolmadi: yaklasma_uyarisi=True ile geri acilir.
        """
        self.base = Path(base_dir)
        self.hassasiyet = hassasiyet
        yol = self.base / (dkb_dosya or self.DKB_DOSYA)
        if not yol.exists():
            raise FileNotFoundError(
                f"DKB bulunamadi: {yol}. Eski surume (decision_knowledge_base.csv) "
                "kasitli olarak dusulmez -- o dosya v1'dir."
            )
        self.dkb = pd.read_csv(yol)
        self.dkb_kaynak = yol.name                       # karar kaydina yazilir
        self.dkb_ozet = self.dkb.guven.value_counts().to_dict()
        self.zarf = pd.read_csv(self.base / "dkb_zarf.csv")
        self.sigma = self._sigma_yukle()
        # --- iki BAGIMSIZ ayar (eskiden ikisi de 'hassasiyet'e bagliydi) ---
        # (a) SAYISAL uyarilar icin olasilik esigi
        self.p_esik = p_esik if p_esik is not None else (0.50 if hassasiyet == "orta" else 0.75)
        # (b) KALITATIF hedeflerde "esige yaklasiyor" (BILGI) dali.
        #     VARSAYILAN KAPALI -- gerekcesi ve olcumu yukaridaki docstring'de.
        self.yaklasma_uyarisi = bool(yaklasma_uyarisi) if yaklasma_uyarisi is not None else False
        # (c) zarf esiklerinin mevsim secimi -- ayrinti icin _fizyolojik icindeki nota bak.
        #     VARSAYILAN "tumu": mevcut/kilitli davranis korunur.
        if mevsim_modu not in ("tumu", "mevsimsel"):
            raise ValueError(f"mevsim_modu 'tumu' ya da 'mevsimsel' olmali, verilen: {mevsim_modu!r}")
        self.mevsim_modu = mevsim_modu
        # (d) uyari kriteri. TEK DEGER ya da HEDEF BAZINDA SOZLUK olabilir.
        #
        # NEDEN HEDEF BAZINDA: kriter degiskenin ZAMAN SABITINE uymali.
        # Olculdu (2 sera, ilkbahar, esik asimlarinin suresi):
        #   kok bolgesi (EC/WC/t_slab) : medyan  57.5 dk · %37'si 3 saati asiyor
        #   iklim (Tair/Rhair/HumDef/CO2air) : medyan 12.5 dk · %9'u 3 saati asiyor
        #   CO2air tek basina           : medyan  10.0 dk · %2.7'si 3 saati asiyor
        # "Pencerenin TAMAMI 3 saat disarida kalsin" kriteri iklim degiskenlerinde
        # neredeyse hic gerceklesmeyen bir sey istiyor. Backtest bunu dogruluyor:
        #   kok  + surekli : precision 0.747   kok  + dokunma : 0.816
        #   iklim+ surekli : precision 0.288   iklim+ dokunma : 0.663
        # Yani iklim degiskenlerinin dusuk performansi DEGISKENIN degil,
        # KRITER-DEGISKEN UYUMSUZLUGUNUN sonucudur.
        if isinstance(kriter, dict):
            kotu = {k: v for k, v in kriter.items() if v not in ("surekli", "dokunma")}
            if kotu:
                raise ValueError(f"gecersiz kriter degerleri: {kotu}")
            self.kriter = dict(kriter)
        elif kriter in ("surekli", "dokunma"):
            self.kriter = kriter
        else:
            raise ValueError(f"kriter 'surekli'/'dokunma' ya da sozluk olmali, "
                             f"verilen: {kriter!r}")
        # (e) bilincli susturulan hedefler. Kural DKB'de durur, degistirilmez;
        #     yalnizca bu kosuda konusmaz. Karar kaydina yazilir.
        #     Gerekce ornegi: kriter='surekli' altinda hava hedefleri olculmus
        #     precision 0.288 veriyor (kok bolgesi 0.747) ve net zararli
        #     (+90 dogru, +223 yanlis alarm) -- bkz. kural_guvenilirlik.csv.
        self.sessiz_hedefler = tuple(sessiz_hedefler)
        if mevsim_modu == "mevsimsel" and "mevsim" not in self.dkb.columns:
            raise ValueError(
                f"mevsim_modu='mevsimsel' istendi ama {self.dkb_kaynak} icinde 'mevsim' "
                "kolonu yok. decision_knowledge_base_v5.csv kullanin.")

    # ---------- kalibre belirsizlik ----------
    def _sigma_yukle(self) -> dict:
        """DKB'deki kalibre aralik genisliginden sigma turetir.
        %95 aralik genisligi = 2 * 1.96 * sigma  ->  sigma = genislik / 3.92"""
        g = self.dkb.drop_duplicates(["hedef", "ufuk"])[
            ["hedef", "ufuk", "guven", "aralik_genislik"]]
        return {(r.hedef, r.ufuk): (r.guven, (r.aralik_genislik / 3.92)
                                    if pd.notna(r.aralik_genislik) else np.nan)
                for r in g.itertuples()}

    def _olasilik(self, tahmin: float, sigma: float, esik: float, yon: str) -> float:
        """Esigin asilma olasiligi — normal yaklasimla."""
        if not np.isfinite(sigma) or sigma <= 0:
            return np.nan
        z = (tahmin - esik) / sigma
        return float(stats.norm.cdf(z) if yon == "yuksek" else stats.norm.cdf(-z))

    def kriter_of(self, hedef: str) -> str:
        """Bu hedef icin gecerli kriter. Sozluk verilmisse hedefe bakar."""
        if isinstance(self.kriter, dict):
            return self.kriter.get(hedef, "surekli")
        return self.kriter

    @staticmethod
    def _mevsim(zaman) -> str | None:
        """Zaman damgasindan mevsim etiketi. Cozulemezse None.

        Ayrim tarihi 2020-03-01. Duyarlilik olculdu (15 Sub / 1 Mar / 15 Mar /
        1 Nis -> mevsimsel dengesizlik medyani 1.54 / 1.54 / 1.83 / 1.38):
        secim kritik degil, bu yuzden sabit tutuldu.
        """
        if zaman is None:
            return None
        try:
            t = pd.Timestamp(zaman)
        except (ValueError, TypeError):
            return None
        if pd.isna(t):
            return None
        return "kis" if t.month in (12, 1, 2) else "ilkbahar"

    @staticmethod
    def _p_metin(p: float) -> str:
        """Olasiligi EKRANA yazarken uc degerleri tavanlar.

        Gerekce: p, normal YAKLASIMDAN gelir (sigma = kalibre aralik / 3.92).
        Yaklasik bir formulun ciktisini "%100" diye basmak, modelin hic sahip
        olmadigi bir kesinligi iddia eder. Depolanan 'olasilik' alani ham kalir;
        yalnizca insana/ajana gosterilen metin tavanlanir.
        """
        if not np.isfinite(p):
            return "olasilik verilemez"
        if p >= 0.995:
            return "olasilik >%99"
        if p <= 0.005:
            return "olasilik <%1"
        return f"olasilik %{p*100:.0f}"

    # ---------- fizyolojik katman ----------
    def _fizyolojik(self, satir: pd.Series) -> list[Uyari]:
        """DUZELTME: backtest'te (agc_backtest_v2.py) TEK NOKTA tahminiyle
        karsilastirmanin ("dokunma") alarm yorgunlugu yarattigi bulundu:
        p5/p95 zarfinda gunde 21.9 saat aktif alarm. "SUREKLI SAPMA" kriteri
        (tahmin edilen PENCERENIN TAMAMI zarf disinda) bunu gunde 7.5 saate
        indirdi (precision 0.701, recall 0.742).

        Bu yuzden satirda 'tahmin_min'/'tahmin_max' (pencere ici uc degerler)
        varsa SUREKLI SAPMA kriteri kullanilir. Yalnizca 'tahmin' (tek nokta)
        verilirse eski DOKUNMA davranisina geriler -- bu durum acikca
        isaretlenir (alarm_modu alaninda), sessizce gecilmez.
        """
        h, u, s = satir["hedef"], satir["ufuk"], satir["sera"]
        guven, sigma = self.sigma.get((h, u), ("KAPSAM_DISI", np.nan))
        if guven == "KAPSAM_DISI":
            return []                      # sistem burada SUSAR

        has_pencere = "tahmin_min" in satir.index and "tahmin_max" in satir.index \
                      and pd.notna(satir.get("tahmin_min")) and pd.notna(satir.get("tahmin_max"))
        tahmin = satir["tahmin_son"] if "tahmin_son" in satir.index and pd.notna(satir.get("tahmin_son")) \
                 else satir["tahmin"]
        alt = tahmin - 1.96 * sigma if np.isfinite(sigma) else np.nan
        ust = tahmin + 1.96 * sigma if np.isfinite(sigma) else np.nan

        # --- YENI: tanimsal fiziksel sinira kirp ---
        # Kirpma KAPSAMA'yi bozmaz, artirir: gercek deger tanimi geregi zaten
        # sinirin icindedir, dolayisiyla disari tasan kuyrugu atmak yalnizca
        # gereksiz genisligi kaldirir. Kilitli kapsama olcumu (uc deger 0.916)
        # bu degisiklikten sonra da gecerli bir ALT SINIR olarak kalir.
        # Olculdu: bu degisiklik "esige yaklasiyor" dalinin tetiklenme hacmini
        # HIC degistirmiyor (23.97 -> 23.97 sa/gun, iki serada da), cunku zarf
        # esikleri (p5/p95) fiziksel sinirlarin cok icinde. Yani salt hijyen.
        aralik_kirpildi = False
        _lo, _hi = FIZIKSEL_SINIR.get(h, (None, None))
        if _lo is not None and np.isfinite(alt) and alt < _lo:
            alt, aralik_kirpildi = _lo, True
        if _hi is not None and np.isfinite(ust) and ust > _hi:
            ust, aralik_kirpildi = _hi, True

        # --- YENI: aralik yalnizca SAYISAL seviyede sunulabilir ---
        # KALITATIF'te aralik HESAPLANIR (esige yaklasma karari onu kullanir)
        # ama SUNULMAZ. Bu, motorun kendi belgelenmis tasarimina donustur:
        # SAYISAL -> olasilik · KALITATIF -> yon · KAPSAM_DISI -> sessizlik.
        gosterilebilir = (guven == "SAYISAL")

        if h in self.sessiz_hedefler:      # bilincli susturuldu
            return []
        kriter = self.kriter_of(h)
        alarm_modu = (kriter.upper() if has_pencere
                      else "TEK NOKTA (pencere yok -- daha az guvenilir)")

        kurallar = self.dkb[(self.dkb.hedef == h) & (self.dkb.ufuk == u) &
                            ((self.dkb.sera == s) | (self.dkb.sera == "TUMU"))]

        # --- YENI: mevsim secimi -------------------------------------------
        # DKB'de 'mevsim' kolonu varsa (v5+), zaman damgasina gore dogru satir
        # secilir. 'mevsim_modu' iki degeri alir:
        #   "tumu"      -> yalnizca mevsim=='tumu' satirlari (v4 davranisi, VARSAYILAN;
        #                  kilitli 0.820/0.829 sayilarini uretmeye devam eder)
        #   "mevsimsel" -> zaman damgasinin dustugu mevsimin satirlari; o mevsim
        #                  icin satir yoksa (ornegin HASAR) 'tumu'ya duser
        # Neden gerekli: tum-sezon p5/p95 esikleri mevsim tespit ediyor, anomali
        # degil. Olculdu (2 sera, 40 kural): mevsimsel dengesizlik medyani 153.6x;
        # mevsim-ici esiklerle 1.5x. Test penceresinde (Mayis) zarf kurallarinin
        # yalnizca %3'u tasarim noktasinda (%2-8) calisiyor; %45'i hic tetiklenmiyor,
        # %32'si %20'nin uzerinde tetikleniyor.
        if "mevsim" in kurallar.columns:
            if self.mevsim_modu == "mevsimsel":
                mv = self._mevsim(satir.get("zaman"))
                if mv is None:                       # zaman yoksa geri dusulur
                    kurallar = kurallar[kurallar.mevsim == "tumu"]
                else:
                    var = kurallar[kurallar.mevsim == mv]
                    yok = kurallar[~kurallar.set_index(["hedef", "sera", "esik_turu", "yon"]).index
                                   .isin(var.set_index(["hedef", "sera", "esik_turu", "yon"]).index)]
                    kurallar = pd.concat([var, yok[yok.mevsim == "tumu"]])
            else:
                kurallar = kurallar[kurallar.mevsim == "tumu"]

        out = []
        for _, k in kurallar.iterrows():
            esik, yon = k["esik"], k["yon"]
            if has_pencere:
                # KRITER SECIMI -- ikisi FARKLI sorulari yanitlar, ikisi de desteklenir:
                #   "surekli" : pencerenin TAMAMI esik disinda mi (varsayilan, motorun
                #               orijinal davranisi). Alarm hacmi 5.0-5.3 sa/gun.
                #   "dokunma" : pencerenin HERHANGI bir ani esik disinda mi. Backtest'in
                #               0.820/0.829 sayisi bu kriterle olculdu. 20.1-20.5 sa/gun.
                # Hangi kriterin kullanildigi karar kaydina yazilir; cikti asla
                # kriteri belirtmeden yorumlanmamalidir.
                if kriter == "dokunma":
                    sinir_deger = satir["tahmin_max"] if yon == "yuksek" else satir["tahmin_min"]
                else:
                    sinir_deger = satir["tahmin_min"] if yon == "yuksek" else satir["tahmin_max"]
                asildi = (sinir_deger > esik) if yon == "yuksek" else (sinir_deger < esik)
                nokta_kontrol = tahmin
            else:
                asildi = tahmin > esik if yon == "yuksek" else tahmin < esik
                nokta_kontrol = tahmin
            p = self._olasilik(nokta_kontrol, sigma, esik, yon)

            if guven == "SAYISAL":
                if not asildi or not np.isfinite(p) or p < self.p_esik:
                    continue
                sev = "KRITIK" if (k.esik_turu == "HASAR" or p > 0.85) else "ORTA"
                _kirp_not = " (aralik fiziksel sinira kirpildi)" if aralik_kirpildi else ""
                mesaj = (f"{h} {u} icinde {'ustune cikacak' if yon=='yuksek' else 'altina inecek'} "
                         f"[{alarm_modu}]: esik {esik:.3f} · tahmin {tahmin:.3f} "
                         f"[{alt:.3f}, {ust:.3f}]{_kirp_not} · {self._p_metin(p)}")
            else:  # KALITATIF — ne olasilik ne sayisal aralik verilir
                if not asildi:
                    kesiyor = (np.isfinite(alt) and alt <= esik <= ust)
                    if not (kesiyor and self.yaklasma_uyarisi):
                        continue
                    sev, ek = "BILGI", "esige yaklasiyor"
                else:
                    sev, ek = ("KRITIK" if k.esik_turu == "HASAR" else "ORTA"), "esigi asiyor"
                mesaj = (f"{h} {u} icinde {ek} ({'yukari' if yon=='yuksek' else 'asagi'} yonde) "
                         f"[{alarm_modu}]: esik {esik:.3f} · tahmin {tahmin:.3f} "
                         f"· OLASILIK VERILEMEZ (belirsizlik cok yuksek, yalnizca egilim; "
                         f"bu guven seviyesinde sayisal aralik VERILMEZ)")
                p = np.nan

            out.append(Uyari(satir.get("zaman"), s, h, u, "FIZYOLOJIK", k.esik_turu,
                             sev, guven, mesaj, tahmin, alt, ust, esik, p,
                             k.aksiyon, k.kisit,
                             TAKIM_REFERANS.get((h, yon), ""),
                             gosterilebilir, aralik_kirpildi,
                             float(sinir_deger if has_pencere else nokta_kontrol), yon))
        return out

    # ---------- ekonomik katman: 4 deterministik kural ----------
    def ekonomik_birim_maliyet(self, sera: str, isi_eur: float, elek_eur: float,
                               co2_eur: float, uretim_kum: float, zaman=None) -> list[Uyari]:
        """Toplam DEGISKEN birim maliyet (€/kg), alti referans takima kiyasla.

        DUZELTME: eski surum yalnizca isitma/kg kullaniyordu (net karla
        rho=-0.09, ongoru gucu yok). Dogrusu toplam degisken maliyet/kg
        (rho=-1.00). Isitma tek basina yaniltici bir gostergedir.
        """
        if uretim_kum <= 0:
            return []
        top = isi_eur + elek_eur + co2_eur
        verim = top / uretim_kum
        sirali = sorted(REFERANS_VERIMLILIK.items(), key=lambda x: x[1])
        eniyi, enkotu = sirali[0], sirali[-1]
        yakin = min(sirali, key=lambda x: abs(x[1] - verim))
        yuzde = 100 * (verim - eniyi[1]) / eniyi[1]
        elek_pay = 100 * elek_eur / max(top, 1e-9)

        if verim <= eniyi[1] * 1.05:
            sev, ek = "BILGI", "verimli rejim"
        elif verim <= eniyi[1] * 1.20:
            sev, ek = "ORTA", "iyilestirme alani var"
        else:
            sev, ek = "KRITIK", "verimlilik dusuk"

        mesaj = (f"Birim uretim maliyeti {verim:.3f} €/kg (elektrik payi %{elek_pay:.0f}) · {ek} · "
                 f"en verimli referans {eniyi[0]} ({eniyi[1]:.3f}), "
                 f"en dusuk {enkotu[0]} ({enkotu[1]:.3f}) · "
                 f"mevcut rejim {yakin[0]} profiline yakin · "
                 f"en iyiye gore %{yuzde:+.1f}")
        return [Uyari(zaman, sera, "birim_maliyet", "sezon", "EKONOMIK",
                      "VERIMLILIK", sev, "OLCUM", mesaj, verim,
                      aksiyon=("Yok" if sev == "BILGI" else
                              "Elektrik toplam maliyetin cogunlugunu olusturur "
                              "(%55-90); once lamba kullanimini incele"),
                      kisit="Isitma verimliligi tek basina yanilticidir "
                            "(net karla korelasyonu yok, rho=-0.09); "
                            "dogru gosterge toplam €/kg'dir.",
                      referans=f"{eniyi[0]} ayni uretimi {enkotu[1]/eniyi[1]:.2f} kat "
                               f"daha dusuk birim maliyetle elde etti")]

    def ekonomik_tarife(self, sera: str, kwh_pik_24h: float, kwh_toplam_24h: float,
                        zaman=None) -> list[Uyari]:
        """Son 24 saatteki pik-elektrik TUKETIM payi (zaman payi DEGIL — o
        her zaman 16/24=0.667 sabittir; ayirt edici olan hangi saatlerde
        ne kadar tuketildigidir)."""
        if kwh_toplam_24h <= 0.01:
            return []
        pay = kwh_pik_24h / kwh_toplam_24h
        en_iyi = min(REFERANS_PIK_PAYI.values()) / 100
        fark = pay - en_iyi
        if fark <= 0.03:
            sev, ek = "BILGI", "verimli"
        elif fark <= 0.10:
            sev, ek = "ORTA", "orta"
        else:
            sev, ek = "ORTA", "iyilestirilebilir"        # asla KRITIK degil: risksiz yeniden fiyatlama
        kazanc = max(fark, 0) * (kwh_toplam_24h) * (ELEK_PIK - ELEK_DUS) * 100
        mesaj = (f"Son 24 saat pik-saat elektrik payi %{pay*100:.1f} ({ek}) · "
                 f"en iyi referans %{en_iyi*100:.1f} ({min(REFERANS_PIK_PAYI, key=REFERANS_PIK_PAYI.get)}) · "
                 f"potansiyel kazanc {kazanc:.2f} cent/gun")
        return [Uyari(zaman, sera, "tarife_verimliligi", "24h", "EKONOMIK",
                      "TARIFE", sev, "DETERMINISTIK", mesaj, pay,
                      aksiyon=("Yok — zaten pik-disina agirlikli" if sev == "BILGI" else
                              "Lamba saatlerini pik-disina (23:00-07:00) kaydirmayi degerlendir"),
                      kisit="Saf yeniden fiyatlama — ayni kWh, farkli saat. Nedensel iddia "
                            "yok. Bitkinin isiga ne zaman ihtiyac duydugu ayri bir sorudur.",
                      referans=f"Automatoes kis donemi pik payi %{REFERANS_PIK_PAYI['Automatoes']:.1f} "
                               "(alti takimin en dusugu)")]

    def ekonomik_co2_esik(self, sera: str, kumulatif_kg_m2: float, gecen_gun: int,
                          zaman=None) -> list[Uyari]:
        """Kumulatif CO2 dozaji 12 kg/m² esigine EGILIM olarak izlenir
        (esik asimi degil — 5/6 takim sezonu hic asmadan tamamladi)."""
        if gecen_gun <= 0:
            return []
        gunluk_ort = kumulatif_kg_m2 / gecen_gun
        gun_kalan = max(166 - gecen_gun, 0)
        projeksiyon = kumulatif_kg_m2 + gunluk_ort * gun_kalan
        if projeksiyon < CO2_ESIK * 0.85:
            sev, seviye = "BILGI", "GUVENLI"
        elif projeksiyon < CO2_ESIK:
            sev, seviye = "ORTA", "IZLE"
        else:
            sev, seviye = "ORTA", "ESIK_ASILACAK"          # ekonomik, hasar degil -> KRITIK degil
        ek_maliyet = max(projeksiyon - CO2_ESIK, 0) * (CO2_PAHALI - CO2_UCUZ)
        mesaj = (f"Kumulatif CO2 {kumulatif_kg_m2:.2f} kg/m² · sezon sonu projeksiyonu "
                 f"{projeksiyon:.2f} kg/m² ({seviye}) · esik {CO2_ESIK:.0f} kg/m²")
        return [Uyari(zaman, sera, "co2_esik_egilimi", "sezon", "EKONOMIK",
                      "ESIK_EGILIMI", sev, "DETERMINISTIK", mesaj, kumulatif_kg_m2,
                      esik=CO2_ESIK,
                      aksiyon=("Yok" if seviye == "GUVENLI" else
                              f"CO2 dozaj hizini gozden gecir; esik sonrasi kg basina "
                              f"maliyet {CO2_PAHALI/CO2_UCUZ:.1f} kat artiyor"),
                      kisit="Projeksiyon dogrusaldir; gercek dozaj mevsimsel degisebilir.",
                      referans="5/6 takim sezonu esigin altinda tamamladi (7.28-10.15 kg/m²); "
                               "yalnizca TheAutomators asti, o da sezonun son 6 gununde")]

    def ekonomik_lamba(self, sera: str, son7gun_kwh_m2: float, mevsim: str = "kis",
                       zaman=None) -> list[Uyari]:
        """Son 7 gunun lamba elektrik tuketimi, MEVSIME DUYARLI referansa
        kiyasla. (Tum-sezon ortalamasiyla kiyaslamak kis donemini hep
        'cok yuksek' gosterirdi — bu proje boyunca tekrarlayan bir hata.)"""
        ref = REFERANS_LAMBA_HAFTALIK.get(mevsim, REFERANS_LAMBA_HAFTALIK["kis"])
        oran = son7gun_kwh_m2 / ref if ref else np.nan
        if oran <= 1.05:
            sev, seviye = "BILGI", "TIPIK"
        elif oran <= 1.3:
            sev, seviye = "ORTA", "YUKSEK"
        else:
            sev, seviye = "ORTA", "COK_YUKSEK"
        sirali = sorted(REFERANS_VERIMLILIK.items(), key=lambda x: x[1])
        eniyi, enkotu = sirali[0], sirali[-1]
        mesaj = (f"Son 7 gun lamba tuketimi {son7gun_kwh_m2:.2f} kWh/m² · "
                 f"{mevsim} referansi {ref:.2f} · oran {oran:.2f} ({seviye})")
        return [Uyari(zaman, sera, "lamba_kullanimi", "7g", "EKONOMIK",
                      "VERIMLILIK", sev, "MALIYET_KESIN_FAYDA_BELIRSIZ", mesaj, son7gun_kwh_m2,
                      aksiyon=("Yok" if seviye == "TIPIK" else
                              "Lamba saatini gozden gecir; ek her 1000 saat sezon boyunca "
                              "~6.98 €/m² elektrik maliyetine karsilik geliyor "
                              "(uretim/Brix katkisi bu orneklemde istatistiksel olarak "
                              "kurulamadi)"),
                      kisit="Fayda tarafi (uretim/Brix artisi) n=6 ile ANLAMLI DEGIL "
                            "(guven araliklari sifiri iceriyor). Yalnizca maliyet "
                            "tarafi kesindir.",
                      referans=f"En verimli {eniyi[0]} ({eniyi[1]:.3f} €/kg) — "
                               f"en dusuk {enkotu[0]} ({enkotu[1]:.3f} €/kg)")]

    def ekonomik_degerlendir(self, gunluk_durum: pd.DataFrame) -> pd.DataFrame:
        """Toplu ekonomik degerlendirme. gunluk_durum kolonlari:
        sera, zaman, isi_eur, elek_eur, co2_eur, uretim_kum, kwh_pik_24h,
        kwh_toplam_24h, co2_kumulatif_kg_m2, gecen_gun, son7gun_kwh_m2, mevsim
        (hepsi opsiyonel — mevcut olanlar degerlendirilir)."""
        u = []
        for _, r in gunluk_durum.iterrows():
            if {"isi_eur", "elek_eur", "co2_eur", "uretim_kum"}.issubset(r.index):
                u += self.ekonomik_birim_maliyet(r.sera, r.isi_eur, r.elek_eur,
                                                 r.co2_eur, r.uretim_kum, r.get("zaman"))
            if {"kwh_pik_24h", "kwh_toplam_24h"}.issubset(r.index):
                u += self.ekonomik_tarife(r.sera, r.kwh_pik_24h, r.kwh_toplam_24h, r.get("zaman"))
            if {"co2_kumulatif_kg_m2", "gecen_gun"}.issubset(r.index):
                u += self.ekonomik_co2_esik(r.sera, r.co2_kumulatif_kg_m2, int(r.gecen_gun), r.get("zaman"))
            if "son7gun_kwh_m2" in r.index:
                u += self.ekonomik_lamba(r.sera, r.son7gun_kwh_m2, r.get("mevsim", "kis"), r.get("zaman"))
        if not u:
            return pd.DataFrame(columns=[f.name for f in Uyari.__dataclass_fields__.values()])
        return pd.DataFrame([vars(x) for x in u])

    # ---------- ana giris ----------
    def degerlendir(self, tahminler: pd.DataFrame) -> pd.DataFrame:
        """tahminler: zaman · sera · hedef · ufuk · tahmin kolonlari"""
        gerekli = {"sera", "hedef", "ufuk", "tahmin"}
        if not gerekli.issubset(tahminler.columns):
            raise ValueError(f"Eksik kolon: {gerekli - set(tahminler.columns)}")
        u = []
        for _, r in tahminler.iterrows():
            u += self._fizyolojik(r)
        if not u:
            return pd.DataFrame(columns=[f.name for f in Uyari.__dataclass_fields__.values()])
        return pd.DataFrame([vars(x) for x in u])

    # ---------- okunabilir rapor ----------
    def rapor(self, uyarilar: pd.DataFrame, en_fazla: int = 12) -> str:
        if uyarilar.empty:
            return "Uyari yok — tum degerler normal calisma zarfinda."
        sira = {"KRITIK": 0, "ORTA": 1, "BILGI": 2}
        u = uyarilar.copy()
        u["_s"] = u.seviye.map(sira)
        u = u.sort_values(["_s", "olasilik"], ascending=[True, False])

        sat = [f"{len(u)} uyari · "
               f"{(u.seviye=='KRITIK').sum()} kritik · "
               f"{(u.seviye=='ORTA').sum()} orta · "
               f"{(u.seviye=='BILGI').sum()} bilgi", ""]
        for _, r in u.head(en_fazla).iterrows():
            im = {"KRITIK": "!!", "ORTA": "! ", "BILGI": "  "}[r.seviye]
            sat.append(f"{im} [{r.seviye}] {r.sera} · {r.katman}/{r.esik_turu}")
            sat.append(f"     {r.mesaj}")
            if r.aksiyon and r.aksiyon != "— aksiyon tanimlanmadi":
                sat.append(f"     AKSIYON  : {r.aksiyon}")
                sat.append(f"     KISIT    : {r.kisit}")
                sat.append("     NOT      : etkinin YONU bilinir, BUYUKLUGU tahmin edilemez "
                           "(model nedensel degil)")
            if r.referans:
                sat.append(f"     REFERANS : {r.referans}")
            sat.append("")
        if len(u) > en_fazla:
            sat.append(f"... +{len(u)-en_fazla} uyari daha")
        return "\n".join(sat)


if __name__ == "__main__":
    BASE_DIR = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")
    m = RiskMotoru(BASE_DIR)
    ornek = pd.DataFrame([
        {"zaman": "2020-05-20 14:00", "sera": "AICU", "hedef": "EC_slab1", "ufuk": "6h", "tahmin": 6.4},
        {"zaman": "2020-05-20 14:00", "sera": "AICU", "hedef": "Tair", "ufuk": "3h", "tahmin": 29.5},
        {"zaman": "2020-05-20 14:00", "sera": "AICU", "hedef": "HumDef", "ufuk": "3h", "tahmin": 1.2},
    ])
    print(m.rapor(m.degerlendir(ornek)))

    print("\n--- EKONOMIK: 4 DETERMINISTIK KURAL ---")
    gunluk = pd.DataFrame([{
        "sera": "AICU", "zaman": "2020-02-17",
        "isi_eur": 2.09, "elek_eur": 16.38, "co2_eur": 0.81, "uretim_kum": 13.76,
        "kwh_pik_24h": 12.0, "kwh_toplam_24h": 17.7,
        "co2_kumulatif_kg_m2": 4.47, "gecen_gun": 63,
        "son7gun_kwh_m2": 15.06, "mevsim": "kis",
    }])
    print(m.rapor(m.ekonomik_degerlendir(gunluk)))
