"""
AGC — YAPILANDIRMA ve KARAR KAYDI
==================================
Ajan katmaninin OMURGASI. Iki is yapar:

  1) Yapilandirmayi gizli bir varsayilan olmaktan cikarip ADI OLAN bir nesneye
     cevirir. Sekiz kombinasyonun hepsi erisilebilir kalir; hangisinin
     kullanildigi her ciktiya damgalanir.
  2) Risk motorunun ciktisini, LLM'in okuyabilecegi YAPILANDIRILMIS bir karar
     kaydina cevirir.

TASARIM KURALI — LLM ASLA KARAR YOLUNDA DEGILDIR
-------------------------------------------------
Karar (esik karsilastirmasi, kriter, oncelik, olculmus isabet) burada,
deterministik kodda uretilir. LLM yalnizca bu kaydi ANLATIR. Sayi uretmez.
Boylece demo bit-bit tekrarlanabilir ve "bu sayiyi nereden buldun" sorusunun
cevabi her zaman kayittadir.

2026 pratigiyle uyumlu: once erisim sonra uretim; iddialar kaynaga karsi
dogrulanir (bkz. agc_dogrulayici.py); cikti kisa ve yapilandirilmis tutulur.

KULLANIM — NOT DEFTERI
-----------------------
    exec(open(BASE_DIR / "agc_karar_kaydi.py").read(), globals())

    y = YAPILANDIRMALAR["demo"]              # varsayilan secim
    kayit = karar_kaydi(BASE_DIR, girdi_df, y)
    print(ozet_metni(kayit))                 # LLM'e verilecek metin
    import json; print(json.dumps(kayit, ensure_ascii=False, indent=2)[:2000])

Baska bir yapilandirma denemek icin (fikir degisirse tek satir):

    y = Yapilandirma(ad="deneme", mevsim_modu="tumu", kriter="dokunma",
                     sessiz_hedefler=())
"""



from __future__ import annotations

SURUM = "2026-08-24.7"   # ayni hedef iki yonde -> zamansal belirsizlik notu

from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np
import pandas as pd

# --- kardes modulleri DISKTEN TAZELE ---------------------------------------
# Colab'da dosyalar exec(open(...).read(), globals()) ile yeniden yuklenir ama
# exec sys.modules'i GUNCELLEMEZ. Bu yuzden 'from agc_x import yeni_fonksiyon'
# satiri eski, onbellekteki modulu bulur ve ImportError verir.
# Asagidaki blok, kardes modulu diskten yeniden okuyarak bunu onler:
# yeni bir dosya gonderildiginde cekirdegi yeniden baslatmaya gerek kalmaz.
def _tazele(*adlar):
    import importlib
    import sys as _sys
    for _ad in adlar:
        if _ad in _sys.modules:
            try:
                importlib.reload(_sys.modules[_ad])
            except Exception:                                     # noqa: BLE001
                _sys.modules.pop(_ad, None)

_tazele("agc_risk_motoru")

from agc_risk_motoru import RiskMotoru

# Kok bolgesi vs hava ayrimi. Kriter='surekli' altinda hava hedefleri olculmus
# precision 0.288 (kok bolgesi 0.747) veriyor ve net zararli: +90 dogru uyariya
# karsilik +223 yanlis alarm. Bkz. kural_guvenilirlik.csv, backtest adim 3.
HAVA_HEDEFLERI = ("Tair", "Rhair", "HumDef", "CO2air", "Tot_PAR")
KOK_HEDEFLERI = ("EC_slab1", "EC_slab2", "WC_slab1", "WC_slab2", "t_slab1", "t_slab2")

# --- IKI AYRI PROBLEM, IKI AYRI CETVEL --------------------------------------
# Kok bolgesi ve iklim degiskenleri FARKLI zaman sabitlerine sahip. Ayni kriterle
# olculmeleri yanlisti; ayni metrikte toplanmalari da yanlis olur.
#
# Olculdu (2 sera, ilkbahar, esik asim sureleri):
#   KOK   : medyan 57.5 dk · %37'si 3 saati asiyor  -> "surekli sapma" uygun
#   IKLIM : medyan 12.5 dk · %9'u  3 saati asiyor   -> "dokunma" uygun
#
# Backtest (adim 2 ve 3, C_pen_pen, KAPSAM_DISI haric, ZAMAN DAMGALI
# trajektori dosyasiyla yeniden kosuldu):
#   KOK   + surekli : precision 0.722 · recall 0.801 · isabet medyani 0.714
#   IKLIM + dokunma : precision 0.698 · recall 0.658 · isabet medyani 0.705
#   IKLIM + surekli : precision 0.291  <- kriter uyumsuzlugunun bedeli
#
# IKI AILE ESIT GUVENILIRLIKTE. Onceki turda "iklim kurallari net zararli,
# susturalim" denmisti; o olcum iklimi YANLIS KRITERLE olcuyordu. Dogru
# kriterle Tair 6h (0.808) tum kurallar arasinda IKINCI sirada.
#
# DIKKAT: bu iki sayi BIRLESTIRILMEZ. Farkli olay tanimlarini tek paydada
# toplamak elma ile armudu ortalamaktir. Rapor ve ekran iki AYRI satir gosterir.
AILELER = {"KOK": KOK_HEDEFLERI, "IKLIM": HAVA_HEDEFLERI}
AILE_KRITERI = {"KOK": "surekli", "IKLIM": "dokunma"}
AILE_OLCUM = {   # backtest adim 2/3'ten, kendi kriteriyle, zaman damgali dosya
    "KOK":   {"kriter": "surekli", "precision": 0.722, "recall": 0.801,
              "kural": 12, "isabet_medyani": 0.714},
    "IKLIM": {"kriter": "dokunma", "precision": 0.698, "recall": 0.658,
              "kural": 8, "isabet_medyani": 0.705},
}


def aile_of(hedef: str) -> str:
    for ad, uyeler in AILELER.items():
        if hedef in uyeler:
            return ad
    return "DIGER"


def kriter_sozlugu(kok: str = "surekli", iklim: str = "dokunma") -> dict:
    """Hedef bazinda kriter sozlugu uretir. Motora dogrudan verilir."""
    d = {h: kok for h in KOK_HEDEFLERI}
    d.update({h: iklim for h in HAVA_HEDEFLERI})
    return d


@dataclass(frozen=True)
class Yapilandirma:
    """Sistemin nasil konustugunu belirleyen tum ayarlar, tek yerde.

    HICBIRI KILITLI DEGILDIR. Sekiz kombinasyonun hepsi calisir; secim
    denemeye aciktir ve her ciktiya damgalandigi icin geri donus ucuzdur.
    """
    ad: str
    dkb_dosya: str = "decision_knowledge_base_v5.csv"
    mevsim_modu: str = "tumu"           # 'tumu' | 'mevsimsel'
    kriter: str = "surekli"             # 'surekli' | 'dokunma'
    sessiz_hedefler: tuple = ()         # bilincli susturulanlar
    yaklasma_uyarisi: bool = False      # "esige yaklasiyor" (BILGI) dali
    p_esik: float = 0.50                # SAYISAL uyarilar icin olasilik esigi
    gerekce: str = ""                   # bu secim NEDEN yapildi

    def motor(self, base_dir) -> RiskMotoru:
        return RiskMotoru(Path(base_dir), dkb_dosya=self.dkb_dosya,
                          mevsim_modu=self.mevsim_modu, kriter=self.kriter,
                          sessiz_hedefler=self.sessiz_hedefler,
                          yaklasma_uyarisi=self.yaklasma_uyarisi,
                          p_esik=self.p_esik)


YAPILANDIRMALAR: dict = {
    "demo": Yapilandirma(
        ad="demo",
        mevsim_modu="mevsimsel", kriter=kriter_sozlugu(), sessiz_hedefler=(),
        gerekce=("VARSAYILAN. Her degisken KENDI zaman sabitine uygun kriterle "
                 "olculur: kok bolgesi surekli sapma (esik asimlarinin medyani "
                 "57.5 dk), iklim dokunma (medyan 12.5 dk). Olculdu: kok "
                 "precision 0.722 / recall 0.801 (12 kural, isabet medyani 0.714), "
                 "iklim 0.698 / 0.658 (8 kural, medyan 0.705). Iki aile ESIT "
                 "guvenilirlikte; Tair 6h (0.808) tum kurallar arasinda ikinci. "
                 "Metrikler aile bazinda AYRI raporlanir, BIRLESTIRILMEZ -- farkli "
                 "olay tanimlarini tek paydada toplamak yanlis olur.")),
    "dar": Yapilandirma(
        ad="dar",
        mevsim_modu="mevsimsel", kriter="surekli", sessiz_hedefler=HAVA_HEDEFLERI,
        gerekce=("TERK EDILDI, karsilastirma icin korunuyor. Iklim hedefleri "
                 "susturulmustu; o karar iklimi YANLIS KRITERLE (surekli sapma) "
                 "olcen bir sonuca dayaniyordu -- precision 0.291 gorunuyordu. "
                 "Kendi kriteriyle (dokunma) ayni hedefler 0.698 veriyor. "
                 "Dusuk performans degiskenin degil, KRITER-DEGISKEN "
                 "UYUMSUZLUGUNUN sonucuydu.")),
    "taban": Yapilandirma(
        ad="taban",
        dkb_dosya="decision_knowledge_base.csv", mevsim_modu="tumu",
        kriter="dokunma", sessiz_hedefler=(), yaklasma_uyarisi=True,
        gerekce=("Yayimlanan yapilandirma. Karar Katmani Raporu Bolum 5'teki "
                 "precision 0.820 / recall 0.829 sayilarini ureten ayar. "
                 "Zaman damgali trajektori dosyasiyla yeniden kosuldugunda "
                 "0.815 / 0.835 veriyor (GPU belirsizligi + model secimi "
                 "beraberligi). Karsilastirma tabani olarak korunur.")),
    "guven": Yapilandirma(
        ad="guven", mevsim_modu="tumu", kriter="dokunma",
        gerekce="Yalnizca DKB surumu duzeltildi (v1 -> v5). Backtest adim 1."),
    "esik": Yapilandirma(
        ad="esik", mevsim_modu="mevsimsel", kriter="dokunma",
        gerekce="v5 + mevsim ici esikler. Backtest adim 2."),
    "kriter": Yapilandirma(
        ad="kriter", mevsim_modu="mevsimsel", kriter="surekli",
        gerekce="v5 + mevsimsel + surekli sapma, iklim hedefleri ACIK. Backtest adim 3."),
}


# ----------------------------------------------------------------------------
def guvenilirlik_yukle(base_dir) -> dict:
    """kural_guvenilirlik.csv -> {(hedef, ufuk): {...}}

    Backtest adim 3'ten gelen, TUTULMUS VERIYLE olculmus kural isabeti.
    Oncelik siralamasinin ucuncu anahtari ve anlatinin dayanagi budur.
    prec_alt_sinir: Wilson %95 alt siniri -- kucuk orneklemde durust olsun diye.
    """
    yol = Path(base_dir) / "kural_guvenilirlik.csv"
    if not yol.exists():
        return {}
    g = pd.read_csv(yol)
    return {(r.hedef, r.ufuk): {"precision": float(r.precision),
                                "prec_alt_sinir": float(r.prec_alt_sinir),
                                "recall": float(r.recall),
                                "olay": int(r.olay)}
            for r in g.itertuples()}


# --- AKTUATOR YONU ----------------------------------------------------------
# Ayni aktuatoru ZIT yonde suren uyarilar cakisabilir. Bu, elle inceleme
# sirasinda bulundu: 8 vakanin 3'unde kok bolgesi hem "sulama ile serinlet"
# hem "sulama sikligini azalt" diyordu ve anlati ikisini tek yonmus gibi
# sundu. Karar kaydi celiskiyi HIC tasimadigi icin ajan da goremedi.
#
# Olculdu (demo yapilandirmasi, Mayis, 4 saatte bir):
#   Automatoes    72 uyarili an -> 6 tanesinde zit sulama aksiyonu (%8)
#   TheAutomators 37 uyarili an -> 9 tanesinde (%24)
# 15 catismanin 10'u mevcut oncelik kuraliyla ayrilabiliyor (HASAR>ZARF,
# sonra guven seviyesi); 5'inde iki taraf ESIT -> sistem "karar veremiyorum"
# demeli, sahte bir cozum uydurmamali.
# DKB v5'te YALNIZCA 14 farkli aksiyon metni var. Sezgisel kelime aramasi
# yerine ACIK TABLO kullanilir: denetlenebilir ve yanlis eslesme imkansiz.
#
# Ilk denemede kalip aramasi kullanilmisti ve "Havalandirmayi ARTIR" metnindeki
# "artir" kelimesi SULAMA sanildi -- iklim uyarilari sulama catismasina
# karisti. 14 satirlik tablo bu hatayi yapisal olarak engelliyor.
#
# +1 = aktuatoru ARTIR · -1 = AZALT · yoksa o aktuatoru surmuyor
AKSIYON_AKTUATOR = {
    "Besin cozeltisi konsantrasyonunu artir":                   {},
    "Sulama ile kok bolgesini serinlet":                        {"SULAMA": +1},
    "Sulama siklığini artir":                                   {"SULAMA": +1},
    "Sulama siklığini artir veya drenaj oranini yukselt":       {"SULAMA": +1},
    "Sulama siklığini azalt, drenaji kontrol et":               {"SULAMA": -1},
    "Havalandirmayi artir veya perde ile golgele":              {"HAVALANDIRMA": +1},
    "Havalandirma veya isitma ile bagil nemi dusur.":           {"HAVALANDIRMA": +1, "ISITMA": +1},
    "Havalandirma veya isitma ile nem acigini yukselt":         {"HAVALANDIRMA": +1, "ISITMA": +1},
    "Nemlendirme veya havalandirmayi azalt":                    {"HAVALANDIRMA": -1},
    "Nemlendirme yap veya havalandirmayi azalt.":               {"HAVALANDIRMA": -1},
    "Isitmayi artir veya enerji perdesini kapat":               {"ISITMA": +1},
    "Kok bolgesi isitmasini artir":                             {"ISITMA": +1},
    # Bilgi/inceleme aksiyonlari -- aktuatoru DOGRUDAN surmezler
    "Dozaj hizini gozden gecir: dusuk isikta biriken CO2 bitki tarafindan "
    "kullanilamaz, maliyeti kalir.":                            {},
    "Once havalandirma konumuna bak: pencereler genis acikken dozlanan CO2 "
    "disari kacar, dozaj artirma. Dozaji yalnizca pencereler kapaliyken VE "
    "isik varken artir.":                                       {},
}
AKTUATORLER = ("SULAMA", "HAVALANDIRMA", "ISITMA")


def _aktuator_yonu(aksiyon: str) -> dict:
    """Aksiyon metninden aktuator yonlerini okur. Tabloda yoksa BOS doner --
    tahmin yurutulmez. Yeni aksiyon eklenirse tabloya da eklenmelidir."""
    return dict(AKSIYON_AKTUATOR.get((aksiyon or "").strip(), {}))


def bilinmeyen_aksiyonlar(dkb) -> list:
    """Tabloda karsiligi olmayan aksiyonlar. Sessiz kalmasin diye."""
    var = set(AKSIYON_AKTUATOR)
    return sorted({a for a in dkb.aksiyon.unique()
                   if a != "— aksiyon tanimlanmadi" and a.strip() not in var})


# Iki taraf "esit" sayilmadan once olculmus isabette aranan EN AZ fark.
# Bunun altindaki farklar olcum gurultusu sayilir ve celiski COZULMEZ ilan
# edilir -- kil payi bir farkla aksiyon secmek sahte kesinlik uretir.
ISABET_FARKI = 0.05


def catismalari_bul(uyarilar: list) -> list:
    """Ayni aktuatoru zit yonde suren uyari ciftlerini bulur ve COZMEYE calisir.

    ONCELIK SIRASI (oncelik siralamasiyla AYNI mantik):
      1) HASAR > ZARF                    geri donussuz risk once
      2) olculmus isabet (alt sinir)     daha cok ihtimalle HAKLI olan
      3) SAYISAL > KALITATIF             olasilik verilebilen
      4) aksi halde COZULEMEDI

    ILK SURUMDEKI TUTARSIZLIK: cozucu 2. adimi atlayip dogrudan guven
    seviyesine bakiyordu. Sonuc, siralamayla celisiyordu -- Reference'taki
    catismada EC_slab2 3h (isabet 0.805) SAYISAL oldugu icin kazaniyor,
    oysa WC_slab2 3h (0.832) olculebilir sekilde daha isabetli. Celiskide
    secilecek olcut "olasilik verebiliyor muyum" degil, "daha cok ihtimalle
    hakli miyim" olmalidir.

    Alt sinir (Wilson %95) kullanilir: az olayli bir kuralin yuksek gorunen
    isabeti, cok olayli saglam bir kurali yenmesin diye.
    """
    out = []
    for akt in AKTUATORLER:
        arti = [u for u in uyarilar if _aktuator_yonu(u["aksiyon"]).get(akt) == +1]
        eksi = [u for u in uyarilar if _aktuator_yonu(u["aksiyon"]).get(akt) == -1]
        if not (arti and eksi):
            continue
        def isabet(u):
            v = u.get("olculmus_isabet_alt_sinir")
            return v if v is not None else (u.get("olculmus_isabet") or 0.0)

        # HER YONUN EN GUCLU TEMSILCISI secilir -- oncelik sirasindaki ILKI degil.
        # Oncelik siralamasi HASAR ve guven seviyesini de tartar; bir yonun
        # basinda dusuk isabetli ama SAYISAL bir uyari durabilir. Gercek vaka:
        # azalt yonu [WC_slab1 6h %66, WC_slab2 3h %83, WC_slab1 3h %80] iken
        # karsilastirma %66 ile yapiliyordu. O tarafin en iyisi %83'tu.
        def temsilci(g):
            return max(g, key=lambda u: (u["esik_turu"] == "HASAR", isabet(u)))

        a, e = temsilci(arti), temsilci(eksi)

        # AYNI HEDEF HER IKI YONDE MI? 'dokunma' kriterinde bir pencere hem ust
        # hem alt zarfa degebilir (surekli kriterinde imkansiz). O zaman ayni
        # hedef ayni anda "artir" ve "azalt" tarafinda gorunur.
        #
        # BU MUHTEMELEN GERCEK BIR CATISMA DEGILDIR: sapmalar pencerenin FARKLI
        # anlarinda olabilir (yuksek 2. saatte, dusuk 5. saatte) -- yani ardisik,
        # es zamanli degil. Karar kaydi sapma ZAMANINI tasimadigi icin sistem
        # bunu ayirt EDEMEZ. Uydurmak yerine acikca soylenir.
        iki_yonlu = sorted({u["hedef"] for u in arti} & {u["hedef"] for u in eksi})
        zaman_notu = ("" if not iki_yonlu else
                      f" DIKKAT: {', '.join(iki_yonlu)} her iki yonde de gorunuyor; "
                      f"pencere hem ust hem alt esige degmis olabilir. Sapmalar "
                      f"pencerenin FARKLI anlarinda olabilir (ardisik), yani bu "
                      f"es zamanli bir catisma OLMAYABILIR. Karar kaydi sapma "
                      f"zamanini tasimaz; sistem ayirt edemez.")

        if a["esik_turu"] != e["esik_turu"]:
            kazanan = a if a["esik_turu"] == "HASAR" else e
            gerekce = "hasar esigi zarf esigini yener (geri donussuz risk once)" + zaman_notu
        elif abs(isabet(a) - isabet(e)) >= ISABET_FARKI:
            kazanan = a if isabet(a) > isabet(e) else e
            gerekce = (f"olculmus isabet farki belirgin: {kazanan['hedef']} "
                       f"{kazanan['ufuk']} alt sinir {max(isabet(a), isabet(e)):.3f} "
                       f"vs {min(isabet(a), isabet(e)):.3f}") + zaman_notu
        else:
            # BERABERLIKTE SECIM YAPILMAZ.
            #
            # Onceki surumde burada "SAYISAL guven KALITATIF'i yener" vardi ve
            # duzeltilmeye calisilan tutarsizligi geri getiriyordu: EC_slab2 3h
            # (%80, SAYISAL) kazaniyor, WC_slab2 3h (%83, KALITATIF) kaybediyordu.
            # Yani OLCULEMEYEN bir ustunluk, OLCULEN bir ustunlugu yeniyordu.
            #
            # Iki olcut de mesru ama farkli seyler soyluyor: olculmus isabet
            # kuralin ORTALAMA guvenilirligi, SAYISAL ise BU ANDAKI tahminin
            # dar oldugu. Hangisinin oncelikli oldugunu gosteren bir olcumumuz
            # YOK. Olcumu olmayan bir siralamayi uydurmak, bu projenin
            # kimligine aykiridir. Sistem susar ve OKUYUCUYA karar icin gereken
            # bilgiyi verir.
            kazanan = None
            gerekce = (f"olculmus isabetler yakin ({isabet(a):.3f} vs {isabet(e):.3f}, "
                       f"fark {abs(isabet(a)-isabet(e)):.3f} < {ISABET_FARKI}). "
                       f"Artir yonu: {a['hedef']} {a['ufuk']} ({a['guven']}), "
                       f"azalt yonu: {e['hedef']} {e['ufuk']} ({e['guven']}). "
                       f"Sistem hangisinin oncelikli oldugunu SOYLEYEMEZ -- "
                       f"bu siralamayi destekleyen bir olcum yok.") + zaman_notu
        out.append({
            "aktuator": akt,
            "artir_yonu": [{"hedef": u["hedef"], "ufuk": u["ufuk"],
                            "seviye": u["seviye"], "aksiyon": u["aksiyon"],
                            "isabet": u.get("olculmus_isabet")} for u in arti],
            "azalt_yonu": [{"hedef": u["hedef"], "ufuk": u["ufuk"],
                            "seviye": u["seviye"], "aksiyon": u["aksiyon"],
                            "isabet": u.get("olculmus_isabet")} for u in eksi],
            "iki_yonlu_hedefler": iki_yonlu,
            "cozuldu": kazanan is not None,
            "oncelikli": (None if kazanan is None
                          else {"hedef": kazanan["hedef"], "ufuk": kazanan["ufuk"],
                                "aksiyon": kazanan["aksiyon"],
                                "isabet": kazanan.get("olculmus_isabet")}),
            "gerekce": gerekce,
        })
    return out


def _oncelik(u: pd.Series, guvenilirlik: dict) -> tuple:
    """Muzakere ajani yerine gecen deterministik siralama.

    Muzakere gerekcesi olculdu ve dustu: sulama catismasi sezonda 0 adim,
    havalandirma 133 adim / 8 olay, CO2 senaryosunun parasal bahsi 0.00034 €/m².
    Yilda 11 saatlik bir cakisma icin ajanlar arasi protokol yerine uc anahtar:

      1) HASAR > ZARF            -- geri donussuz hasar once
      2) SAYISAL > KALITATIF     -- sayabildigimiz once
      3) olculmus isabet (yuksek once) -- keyfi degil, tutulmus veriden

    Esitlikte FIZYOLOJIK > EKONOMIK (fizyolojik hasar geri donussuz, ekonomik
    risk fiyatlanabilir).
    """
    g = guvenilirlik.get((u.hedef, u.ufuk), {})
    return (
        0 if u.esik_turu == "HASAR" else 1,
        0 if u.guven == "SAYISAL" else 1,
        -(g.get("precision") or 0.0),
        0 if u.katman == "FIZYOLOJIK" else 1,
    )


def karar_kaydi(base_dir, girdi: pd.DataFrame, yapilandirma: Yapilandirma,
                ekonomik_girdi: pd.DataFrame | None = None) -> dict:
    """Deterministik cekirdegin tam ciktisi. LLM'in gorecegi TEK sey budur.

    Kayit bilincli olarak SUSAN kurallari da tasir -- 'neden bu uyari?' kadar
    'neden su uyariyi vermedin?' sorusu da cevaplanabilsin diye.
    """
    base_dir = Path(base_dir)
    motor = yapilandirma.motor(base_dir)
    guvenilirlik = guvenilirlik_yukle(base_dir)

    u = motor.degerlendir(girdi)
    if ekonomik_girdi is not None and len(ekonomik_girdi):
        e = motor.ekonomik_degerlendir(ekonomik_girdi)
        u = pd.concat([u, e], ignore_index=True) if len(u) else e

    uyarilar = []
    if len(u):
        u = u.assign(_o=[_oncelik(r, guvenilirlik) for _, r in u.iterrows()])
        u = u.sort_values("_o").drop(columns="_o").reset_index(drop=True)
        for i, r in u.iterrows():
            g = guvenilirlik.get((r.hedef, r.ufuk), {})
            uyarilar.append({
                "sira": i + 1,
                "hedef": r.hedef, "ufuk": r.ufuk, "sera": r.sera,
                "aile": aile_of(r.hedef),
                "kriter": motor.kriter_of(r.hedef) if r.katman == "FIZYOLOJIK" else "-",
                "katman": r.katman, "esik_turu": r.esik_turu,
                "seviye": r.seviye, "guven": r.guven,
                "esik": None if pd.isna(r.esik) else round(float(r.esik), 3),
                "tahmin": None if pd.isna(r.tahmin) else round(float(r.tahmin), 3),
                # kararI VEREN deger (kritere gore pencere uc noktasi)
                "karar_degeri": (None if pd.isna(getattr(r, "karar_degeri", np.nan))
                                 else round(float(r.karar_degeri), 3)),
                "karar_yonu": getattr(r, "karar_yonu", ""),
                "olasilik": None if pd.isna(r.olasilik) else round(float(r.olasilik), 4),
                "aralik": ([round(float(r.aralik_alt), 3), round(float(r.aralik_ust), 3)]
                           if bool(getattr(r, "aralik_gosterilebilir", False))
                           and np.isfinite(r.aralik_alt) else None),
                "aralik_gosterilemez_sebep": (
                    None if bool(getattr(r, "aralik_gosterilebilir", False))
                    else "guven seviyesi SAYISAL degil -- sayisal aralik verilmez"),
                "aksiyon": r.aksiyon, "kisit": r.kisit, "referans": r.referans,
                "olculmus_isabet": g.get("precision"),
                "olculmus_isabet_alt_sinir": g.get("prec_alt_sinir"),
                "olculmus_recall": g.get("recall"),
                "olcum_olay_sayisi": g.get("olay"),
                "mesaj": r.mesaj,
            })

    # --- bilincli susan kurallar -------------------------------------------
    susan = []
    istenen = set(zip(girdi.hedef, girdi.ufuk)) if "hedef" in girdi.columns else set()
    kapsam_disi = motor.dkb[motor.dkb.guven == "KAPSAM_DISI"]
    for h, uf in sorted(istenen):
        if h in yapilandirma.sessiz_hedefler:
            g = guvenilirlik.get((h, uf), {})
            susan.append({"hedef": h, "ufuk": uf, "sebep": "yapilandirma_sustu",
                          "aciklama": (f"'{yapilandirma.ad}' yapilandirmasinda bilincli "
                                       f"susturuldu"),
                          "olculmus_isabet": g.get("precision")})
        elif ((kapsam_disi.hedef == h) & (kapsam_disi.ufuk == uf)).any():
            susan.append({"hedef": h, "ufuk": uf, "sebep": "KAPSAM_DISI",
                          "aciklama": "belirsizlik cok yuksek ya da degisken "
                                      "deterministik hesaplanabilir -- DKB karari"})

    zaman = girdi["zaman"].iloc[0] if "zaman" in girdi.columns and len(girdi) else None
    sera = girdi["sera"].iloc[0] if "sera" in girdi.columns and len(girdi) else None

    catismalar = catismalari_bul([u for u in uyarilar if u["katman"] == "FIZYOLOJIK"])
    aile_ozet = {}
    for ad in AILELER:
        alt = [u for u in uyarilar if u.get("aile") == ad]
        aile_ozet[ad] = {
            "uyari": len(alt),
            "kritik": sum(1 for x in alt if x["seviye"] == "KRITIK"),
            "kriter": AILE_KRITERI[ad],
            "olculmus": AILE_OLCUM[ad],
        }

    return {
        "zaman": str(zaman), "sera": sera,
        "yapilandirma": {**asdict(yapilandirma),
                         "sessiz_hedefler": list(yapilandirma.sessiz_hedefler),
                         "dkb_kaynak": motor.dkb_kaynak,
                         "dkb_guven_dagilimi": motor.dkb_ozet},
        "kriter_aciklamasi": (
            "surekli: tahmin edilen pencerenin TAMAMI esik disinda"
            if yapilandirma.kriter == "surekli"
            else "dokunma: tahmin edilen pencerenin HERHANGI bir ani esik disinda"),
        "uyarilar": uyarilar,
        "aile_ozet": aile_ozet,
        "catismalar": catismalar,
        "susan_kurallar": susan,
        "ozet": {"uyari": len(uyarilar),
                 "kritik": sum(1 for x in uyarilar if x["seviye"] == "KRITIK"),
                 "orta": sum(1 for x in uyarilar if x["seviye"] == "ORTA"),
                 "bilgi": sum(1 for x in uyarilar if x["seviye"] == "BILGI"),
                 "susan": len(susan), "catisma": len(catismalar),
                 "cozulemeyen_catisma": sum(1 for c in catismalar if not c["cozuldu"])},
        "sinirlar": [
            "Model nedensel degildir: aksiyonun YONU bilinir, BUYUKLUGU tahmin edilemez.",
            "Kok bolgesi ve iklim FARKLI kriterle olculur; performanslari AYRI "
            "raporlanir, birlestirilmez.",
            "Olculmus isabet Mayis test penceresinden gelir; kis performansi olculmedi.",
            "Zarf esikleri seranin kendi normal araligidir, mutlak literatur siniri degil.",
        ],
    }


def ozet_metni(kayit: dict) -> str:
    """Karar kaydinin LLM'e verilecek duz metin hali. Kisa tutulur --
    2026 pratigi: olgusal ciktilarda uzunluk sinirlamak uydurma yuzeyini kucultur."""
    y = kayit["yapilandirma"]
    s = [f"ZAMAN: {kayit['zaman']} · SERA: {kayit['sera']}",
         "AILE OZETI: " + " | ".join(
             f"{ad}: {o['uyari']} uyari (kriter={o['kriter']}, "
             f"olculmus precision={o['olculmus']['precision']})"
             for ad, o in kayit.get("aile_ozet", {}).items() if o["uyari"]),
         f"YAPILANDIRMA: {y['ad']} (dkb={y['dkb_kaynak']}, mevsim={y['mevsim_modu']}, "
         f"kriter={y['kriter']})",
         f"KRITER: {kayit['kriter_aciklamasi']}", ""]
    if not kayit["uyarilar"]:
        # Acik ifade sart: model "UYARI YOK" gorup zorunlu oge listesini
        # uygulamaya calisti ve "esik degeri kayitta yoktur" gibi anlamsiz
        # cumleler yazdi. Anlarin %73'u uyarisiz oldugu icin bu EN SIK
        # gorulen ekran; metni burada netlestirmek gerekiyor.
        s.append("UYARI YOK -- izlenen tum hedefler bu serada normal calisma "
                 "araliginin icinde. Esik/tahmin/isabet alanlari BULUNMAMASI "
                 "normaldir; eksiklik degildir, uyari olmadigi anlamina gelir.")
    for x in kayit["uyarilar"]:
        s.append(f"[{x['sira']}] {x['hedef']} {x['ufuk']} · {x.get('aile','-')} · "
                 f"{x['seviye']} · {x['guven']} · {x['esik_turu']} · "
                 f"kriter={x.get('kriter','-')}")
        # KARARI VEREN deger ONCE. Terminal deger ikincildir ve uyarilarin
        # %19'unda esigin TERS tarafindadir -- one cikarilirsa anlati celiskili
        # okunur ("esik 17.7, tahmin 19.9, isitmayi artir").
        s.append(f"    esik={x['esik']} · KARARI VEREN DEGER={x.get('karar_degeri')} "
                 f"({x.get('karar_yonu')} yonde, kriter: {x.get('kriter')}) "
                 f"· [ikincil: terminal tahmin={x['tahmin']}]"
                 + (f" aralik={x['aralik']}" if x["aralik"] else "")
                 + (f" olasilik={x['olasilik']}" if x["olasilik"] is not None else ""))
        if x["olculmus_isabet"] is not None:
            s.append(f"    olculmus isabet={x['olculmus_isabet']} "
                     f"(alt sinir {x['olculmus_isabet_alt_sinir']}, "
                     f"{x['olcum_olay_sayisi']} olay uzerinde)")
        s.append(f"    aksiyon: {x['aksiyon']}")
        s.append(f"    kisit: {x['kisit']}")
        if x["referans"]:
            s.append(f"    referans: {x['referans']}")
    if kayit.get("catismalar"):
        s.append("")
        s.append("ZIT AKSIYON UYARISI:")
        for c in kayit["catismalar"]:
            ar = ", ".join(f"{x['hedef']} {x['ufuk']}" for x in c["artir_yonu"])
            az = ", ".join(f"{x['hedef']} {x['ufuk']}" for x in c["azalt_yonu"])
            s.append(f"    {c['aktuator']}: ARTIR yonu [{ar}] <-> AZALT yonu [{az}]")
            if c["cozuldu"]:
                s.append(f"      -> oncelikli: {c['oncelikli']['hedef']} "
                         f"{c['oncelikli']['ufuk']} ({c['gerekce']})")
            else:
                s.append(f"      -> COZULEMEDI: {c['gerekce']}")
    if kayit["susan_kurallar"]:
        s.append("")
        s.append("BILINCLI SUSAN KURALLAR:")
        for x in kayit["susan_kurallar"]:
            s.append(f"    {x['hedef']} {x['ufuk']} -- {x['sebep']}: {x['aciklama']}")
    s.append("")
    s.append("SINIRLAR:")
    s += [f"    - {x}" for x in kayit["sinirlar"]]
    return "\n".join(s)
