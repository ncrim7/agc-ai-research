"""
AGC — ACIKLAYICI AJAN (KATMAN 2) · OpenAI
==========================================
Karar katmaninin TEK LLM bileseni. Iki isi var:

  anlat(kayit)        -> karar kaydini insan diline cevirir
  sor(kayit, soru)    -> "neden bu uyari?" sorularini YALNIZCA kayittan cevaplar

HESAP YAPMAZ. SAYI URETMEZ. KAYITTA OLMAYANI SOYLEMEZ.

NEDEN TEK AJAN
---------------
Yol haritasindaki dort ajanli plan (izleme/risk/oneri/aciklama) olculdu ve
gerekcesi bulunamadi. Muzakere gerekcesi: sulama catismasi sezonda 0 adim,
havalandirma 133 adim / 8 olay, CO2 senaryosunun parasal bahsi 0.00034 €/m².
Geriye kalan iki gerekce (dogal dil + "neden bu uyari") ayni yetenegi ister.

MODEL SECIMI — TAHMIN DEGIL, OLCUM
-----------------------------------
Varsayilan GPT-5.6 Luna (ucuz uc; ~0.0005 USD/cagri bizim istem boyutunda).
Kucuk modeller siki kisit takibinde tokezleyebilir. Bunu tahmin etmiyoruz:
agc_dogrulayici.py zaten her ciktiyi denetliyor, dolayisiyla DENETLEYICI MODEL
SECIMININ HAKEMIDIR.

  - Luna denetimden gecemezse kod otomatik olarak MODEL_MERDIVENI'nde bir ust
    modele yukselir (Terra), o da gecemezse sablona duser.
  - model_karsilastir() ile hangi modelin daha sik gectigi OLCULEBILIR.
    Demo oncesi bir kez kosulup karar buna gore verilmeli.

Model adlari degisir; MODEL_MERDIVENI bilincli olarak tek yerde tutulur.
Guncel liste: platform.openai.com/docs/models

PLAN B — API YOKSA / COKERSE
-----------------------------
sablon_anlati() devreye girer. Anlati zayiflar; KARAR YOLU HIC DEGISMEZ.
Bu dususun mumkun olmasi, LLM'in karar yolunda olmadiginin testidir.

429 HAKKINDA
-------------
Iki farkli sorun ayni kodu dondurur:
  insufficient_quota   -> bakiye sifir ya da harcama siniri doldu (bekleyerek gecmez)
  rate_limit_exceeded  -> dakikalik istek/token penceresi doldu (bekleyerek gecer)
Kod ikisini ayirir ve yalnizca ikincisinde bekleyip yeniden dener.
Kademe/limit kontrolu: platform.openai.com -> Settings -> Organization -> Limits

KULLANIM — NOT DEFTERI
-----------------------
    exec(open(BASE_DIR / "agc_aciklayici_ajan.py").read(), globals())
    ajan = AciklayiciAjan(api_key=API_KEY)
    c = ajan.anlat(kayit)
    print(c.metin); print(c.denetim.rapor()); print(c.kaynak, c.model)
"""



from __future__ import annotations

SURUM = "2026-08-24.1"   # prompt: karar_degeri zorunlu

import json
import os
import random
import time
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field

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

_tazele("agc_risk_motoru", "agc_dogrulayici", "agc_karar_kaydi")

from agc_dogrulayici import (denetle, kapsama, eksik_kapsama,
                             KAPSAMA_ACIKLAMA, DenetimSonucu)
from agc_karar_kaydi import ozet_metni

API_URL = "https://api.openai.com/v1/chat/completions"

# Ucuzdan pahaliya. Denetimden gecemeyen model bir ustune devreder.
# Agustos 2026 fiyatlari (USD / 1M token, giris/cikis):
#   gpt-5.6-luna  0.20 / 1.20     gpt-5.6-terra  2.00 / 12.00
# Guncel liste ve adlar degisebilir: platform.openai.com/docs/models
MODEL_MERDIVENI = ("gpt-5.6-luna", "gpt-5.6-terra")

SISTEM = """Sen bir sera iklim karar destek sisteminin ACIKLAYICI katmanisin.

Sana verilen KARAR KAYDI, deterministik bir motor tarafindan uretilmistir.
Senin isin onu Turkce, akici ve kisa bir metne cevirmektir. BASKA HICBIR SEY.

KAYITTA "UYARI YOK" YAZIYORSA
Asagidaki zorunlu oge listesini UYGULAMA. O durumda su uc seyi yaz, baska
bir sey yazma:
  1. Hangi serada, hangi saatte, izlenen degerlerin normal aralikta oldugu
  2. Hangi kurallarin bu yapilandirmada bilincli susturuldugu
  3. Kriterin ne oldugu (pencerenin tamami / herhangi bir ani)
EKSIK ALAN LISTELEME. "esik degeri kayitta yoktur" gibi cumleler YASAK --
uyari olmadigi icin o alanlarin bulunmamasi normaldir, eksiklik degildir.
En fazla 60 kelime.

MUTLAKA YAZMAN GEREKENLER (yalnizca UYARI VARSA, en oncelikli uyari icin)
  - hedefin adi (ornegin EC_slab2) ve ufku (3h/6h)
  - ESIK degeri ve KARARI VEREN DEGER (kayitta "KARARI VEREN DEGER" olarak yazili)
  - OLCULMUS ISABET, yuzde olarak (0.817 -> %82)
  - KISIT metni
  - modelin nedensel olmadigi / buyuklugun bilinemedigi uyarisi
Bu bes ogeden biri eksikse metin REDDEDILIR. Sayilardan KACINMA -- kayitta
olan sayilari yazmak zorundasin. Kacinmak da bir hatadir.

MUTLAK KURALLAR
1. Metninde gecen HER SAYI karar kaydinda aynen bulunmalidir. Kayitta olmayan
   hicbir sayiyi yazma. Hesaplama yapma, ortalama alma, oran turetme.
   Tek izin: 0-1 arasi bir degeri yuzdeye cevirmek (0.817 -> %82).
2. BUYUKLUK IDDIASINDA BULUNMA. "Sulamayi %15 artir", "2 derece duser",
   "3 saatte normale doner" gibi ifadeler YASAK. Model nedensel degildir:
   aksiyonun yalnizca YONU bilinir.
3. Kayitta olmayan sera adi, takim adi, tarih veya olcum uydurma.
4. Kayitta "aralik" alani yoksa sayisal aralik verme. "olasilik" alani yoksa
   olasilik verme. Bu alanlarin yoklugu bilincli bir karardir.
4b. TERMINAL TAHMIN ile KARARI VEREN DEGER farklidir. Kriter, pencerenin bir UC
   NOKTASINI esikle karsilastirir; terminal deger karari VERMEZ ve uyarilarin
   yaklasik besde birinde esigin TERS tarafindadir. Metinde KARARI VEREN DEGERI
   kullan. Terminal degeri anacaksan acikca "pencere sonundaki tahmin" diye
   nitele; asla "tahmin 19.9 ama esik 17.7, isitmayi artir" gibi celiskili
   okunacak bicimde yazma.
5. Kaydin SINIRLAR bolumundeki uyarilardan en az birini metne dogal bicimde yedir.
6. Ilk uyarinin KISIT alanini mutlaka an.
7. Emin olmadigin bir sey icin "kayitta yok" de. Tahmin yurutme.

USLUP
- Profesyonel, sakin, abartisiz. Pazarlama dili yok.
- En fazla 150 kelime. Duz paragraf, madde isareti kullanma.
- Once en oncelikli uyari, sonra digerleri kisaca.
- Okuyucu bir ziraat muhendisi ya da akademisyen."""

SORU_SISTEMI = """Sen bir sera iklim karar destek sisteminin ACIKLAYICI katmanisin.
Sana bir KARAR KAYDI ve bir SORU veriliyor.

Soruyu YALNIZCA karar kaydindaki bilgiyle cevapla.

MUTLAK KURALLAR
1. Metninde gecen HER SAYI kayitta bulunmalidir.
2. Cevap kayitta YOKSA acikca soyle: "Bu bilgi karar kaydinda yok." Sonra
   kayitta ne oldugunu kisaca belirt. Tahmin yurutme, genel bilgiden konusma.
3. "Uymazsam ne olur?", "ne kadar degisir?" gibi BUYUKLUK/SONUC sorularinda
   cevap sudur: model nedensel degildir, yalnizca yon bilinir. Bunu net soyle.
4. "Neden su uyariyi vermedin?" sorulari kaydin SUSAN KURALLAR bolumunden
   cevaplanir.
5. En fazla 120 kelime. Sakin ve dogrudan."""


# ----------------------------------------------------------------------------
def temizle_anahtar(k: str | None) -> str | None:
    """Anahtardaki gorunmez karakterleri temizler ve bicimi dogrular.

    GERCEK VAKA: Colab kasasindan okunan anahtarin BASINDA '\r\n' vardi.
    HTTP basligi satir sonu kabul etmedigi icin istek aga hic cikmadan
    'ValueError: Invalid header value' ile patliyordu -- ve hata mesaji
    ANAHTARIN TAMAMINI iceriyordu. Iki ayri kusur: bicim ve sizinti.
    """
    if k is None:
        return None
    t = k.strip().strip('"').strip("'").strip()
    if not t:
        raise ValueError("API anahtari bos.")
    if any(c in t for c in " \t\r\n"):
        raise ValueError(
            "API anahtarinin ICINDE bosluk/satir sonu var. Kasadaki degeri "
            "yeniden yapistirin (bas ve son bosluksuz).")
    if not t.startswith("sk-"):
        raise ValueError(
            f"API anahtari 'sk-' ile baslamiyor (baslangic: {t[:4]!r}). "
            "Yanlis degeri okumus olabilirsiniz.")
    return t


def maskele(metin: str, *anahtarlar) -> str:
    """Ciktidaki anahtarlari maskeler.

    Teshis araclari ham hata mesaji basar; o mesaj anahtari icerebilir.
    Bu fonksiyon olmadan bir teshis kosusu sirri sohbete/loga dusurur.
    """
    m = metin
    for a in anahtarlar:
        if a and len(a) > 12:
            m = m.replace(a, f"{a[:7]}...***MASKELENDI***")
    # kacan her sk- dizesini de yakala
    m = re.sub(r"sk-[A-Za-z0-9_\-]{12,}", "sk-***MASKELENDI***", m)
    return m


def surumler() -> dict:
    """Hangi surumler YUKLU? Colab'da exec ile yeniden yukleme sirasinda
    eski sinif/nesne kullanmak bu projede uc kez hataya yol acti; bu fonksiyon
    hangi dosyanin gercekten yuklendigini gorunur kilar."""
    import sys as _s
    d = {"agc_aciklayici_ajan": SURUM}
    for ad in ("agc_risk_motoru", "agc_dogrulayici", "agc_karar_kaydi"):
        m = _s.modules.get(ad)
        d[ad] = getattr(m, "SURUM", "?") if m else "yuklu degil"
    return d


class KotaHatasi(RuntimeError):
    """insufficient_quota — beklemekle gecmez, bakiye/limit sorunudur."""


class BosYanitHatasi(RuntimeError):
    """Model bos icerik dondurdu.

    En yaygin sebep: 'max_completion_tokens' DUSUNME tokenlerini de sayar.
    Butce dusuk kalirsa model dusunmede tuketir ve content bos gelir
    (finish_reason='length'). Bu bir basari degil, kesilmis bir cagridir --
    ayri bir hata olarak ele alinir ki butce artirilarak yeniden denenebilsin.
    """
    def __init__(self, finish_reason: str, usage: dict, butce: int):
        self.finish_reason, self.usage, self.butce = finish_reason, usage, butce
        super().__init__(f"bos icerik · finish_reason={finish_reason} · "
                         f"butce={butce} · usage={usage}")


@dataclass
class Cevap:
    metin: str
    denetim: DenetimSonucu
    kapsama: dict = field(default_factory=dict)
    deneme: int = 1
    kaynak: str = "llm"          # 'llm' | 'sablon'
    model: str = ""              # kabul edilen metni ureten model
    izleme: list = field(default_factory=list)   # her denemenin ozeti
    # --- ILK DENEME olculeri (DUZELTME ONCESI) ---------------------------
    # NEDEN AYRI TUTULUYOR: kabul edilen metnin sadakati TANIM GEREGI %100'dur,
    # cunku dongu gecmeyeni kabul etmez. O sayi model kalitesini OLCMEZ.
    # Katmanin durust olcusu, DUZELTILMEDEN ONCE ne kadarinin dogru oldugudur.
    ilk_sayi: int = 0            # ilk denemede metindeki sayi adedi
    ilk_dogrulanan: int = 0      # bunlarin kaci kayitta vardi
    ilk_eksik_kapsama: list = field(default_factory=list)
    # ilk denemede UYDURULAN ham sayi dizeleri. Dongu duzeltip gectigi icin
    # bu bilgi kayboluyordu; raporda "tek hata suydu" diyebilmek icin saklanir.
    ilk_uydurma: list = field(default_factory=list)
    ilk_gecti: bool = False      # ilk deneme hicbir duzeltme olmadan gecti mi


# ----------------------------------------------------------------------------
def sablon_anlati(kayit: dict) -> str:
    """PLAN B: LLM yokken sablon anlati. Karar yolu degismez, yalnizca uslup duser."""
    if not kayit["uyarilar"]:
        return (f"{kayit['sera']} · {kayit['zaman']}: bu zaman diliminde uyari yok. "
                f"({kayit['ozet']['susan']} kural bilincli olarak susturulmus durumda.)")
    u = kayit["uyarilar"][0]
    yon = "ustune cikacak" if ("ustune" in u["mesaj"] or "yukari" in u["mesaj"]) \
        else "altina inecek"
    s = [f"{kayit['sera']} · {kayit['zaman']}.",
         f"{u['hedef']} degeri {u['ufuk']} icinde {u['esik']} esiginin {yon} "
         f"(tahmin {u['tahmin']})."]
    if u["olculmus_isabet"] is not None:
        s.append(f"Bu kural tutulmus veriyle olculdugunde "
                 f"%{round(u['olculmus_isabet'] * 100)} isabetli "
                 f"({u['olcum_olay_sayisi']} olay uzerinde).")
    s.append(f"Onerilen yon: {u['aksiyon']}.")
    s.append(f"Kisit: {u['kisit']}")
    if u["referans"]:
        s.append(f"Karsilastirma: {u['referans']}.")
    if len(kayit["uyarilar"]) > 1:
        s.append("Ayrica: " + ", ".join(f"{x['hedef']} {x['ufuk']}"
                                        for x in kayit["uyarilar"][1:4]) + ".")
    s.append(kayit["sinirlar"][0])
    return " ".join(s)


def sablon_cevap(kayit: dict, soru: str) -> str:
    """PLAN B — SORU icin. LLM yokken soru CEVAPLANMAZ.

    Anlatiyi basmak, cevap verilmis gibi gorunup aslinda vermemektir. Demoda
    en tehlikeli hata turu budur: sessiz yanlis cevap. Bunun yerine acikca
    "cevaplanamadi" denir ve kayitta NE OLDUGU listelenir; okuyucu kendisi bakar.
    """
    b = [f"[LLM erisilemedi -- soru cevaplanamadi. Asagida karar kaydinin "
         f"ilgili basliklari var, cevap bunlarin icindedir.]",
         f"SORU: {soru}", ""]
    if kayit.get("uyarilar"):
        u = kayit["uyarilar"][0]
        b.append(f"En oncelikli uyari: {u['hedef']} {u['ufuk']} · esik {u['esik']} · "
                 f"tahmin {u['tahmin']} · guven {u['guven']}")
        if u["olculmus_isabet"] is not None:
            b.append(f"Bu kuralin olculmus isabeti: {u['olculmus_isabet']} "
                     f"({u['olcum_olay_sayisi']} olay uzerinde)")
        b.append(f"Aksiyon: {u['aksiyon']}")
        b.append(f"Kisit: {u['kisit']}")
    else:
        b.append("Bu zaman diliminde uyari yok.")
    if kayit.get("susan_kurallar"):
        b.append("Susan kurallar: " + ", ".join(
            f"{x['hedef']} {x['ufuk']}" for x in kayit["susan_kurallar"]))
    y = kayit["yapilandirma"]
    b.append(f"Yapilandirma: {y['ad']} · mevsim={y['mevsim_modu']} · kriter={y['kriter']}")
    b.append("Sinirlar: " + " | ".join(kayit["sinirlar"]))
    return "\n".join(b)


def tani(api_key: str, model: str = MODEL_MERDIVENI[0], zaman_asimi: int = 60) -> None:
    """API cagrisini CIPLAK yapar ve ham sonucu MASKELEYEREK basar.

    Amaci: sorunun ag/anahtar/model tarafinda mi yoksa bizim kodda mi oldugunu
    ayirmak. Ajan katmanina hic girmez.

    GUVENLIK: butun cikti maskele()'den gecer. Bir onceki surum ham hata
    izlemesini basiyordu ve o iz anahtarin TAMAMINI iceriyordu -- teshis araci
    sir sizdirmamalidir.
    """
    ham_anahtar = api_key
    print(f"model      : {model}")
    print(f"url        : {API_URL}")
    try:
        api_key = temizle_anahtar(api_key)
    except ValueError as e:
        print(f"ANAHTAR HATASI: {e}")
        print(f"  ham uzunluk : {len(ham_anahtar or '')}")
        print(f"  temizlenmis : {len((ham_anahtar or '').strip())}")
        gorunmez = [repr(c) for c in (ham_anahtar or '') if c in " \t\r\n"]
        if gorunmez:
            print(f"  gorunmez karakterler: {gorunmez[:8]}")
        return
    print(f"anahtar    : {len(api_key)} karakter, '{api_key[:7]}...' ile basliyor "
          f"(temizlendi)")
    govde = json.dumps({"model": model,
                        "messages": [{"role": "user", "content": "Merhaba de."}],
                        "max_completion_tokens": 20}).encode("utf-8")
    istek = urllib.request.Request(
        API_URL, data=govde,
        headers={"content-type": "application/json",
                 "authorization": f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(istek, timeout=zaman_asimi) as y:
            ham = y.read().decode("utf-8", "replace")
        print("HTTP       : 200 OK")
        print(f"ham yanit  : {maskele(ham, api_key, ham_anahtar)[:400]}")
    except urllib.error.HTTPError as e:
        govde_h = e.read().decode("utf-8", "replace")
        print(f"HTTP HATASI: {e.code}")
        print(f"ham govde  : {maskele(govde_h, api_key, ham_anahtar)[:400]}")
    except urllib.error.URLError as e:
        print(f"AG HATASI  : {type(e).__name__}: {maskele(str(e.reason), api_key, ham_anahtar)}")
    except Exception as e:                                        # noqa: BLE001
        print(f"BEKLENMEYEN: {type(e).__name__}: "
              f"{maskele(str(e), api_key, ham_anahtar)[:300]}")


def modelleri_listele(api_key: str) -> list:
    """Hesabin erisebildigi model adlarini dondurur. Model adlari degisir;
    tahmin etmek yerine kaynaktan okumak icin."""
    api_key = temizle_anahtar(api_key)
    r = urllib.request.Request("https://api.openai.com/v1/models",
                               headers={"authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(r, timeout=30) as y:
        d = json.loads(y.read())
    return sorted(x["id"] for x in d.get("data", []))


# ----------------------------------------------------------------------------
class AciklayiciAjan:
    """Tek LLM bileseni. api_key verilmezse sablon moduna duser."""

    def __init__(self, api_key: str | None = None,
                 model: str | None = None,
                 model_merdiveni: tuple | None = None,
                 max_deneme: int = 2, zaman_asimi: int = 60,
                 max_429_deneme: int = 4,
                 max_cikti: int = 2000, max_butce: int = 8000):
        self.api_key = temizle_anahtar(api_key or os.environ.get("OPENAI_API_KEY"))
        if model_merdiveni is not None:
            self.merdiven = tuple(model_merdiveni)
        elif model is not None:
            self.merdiven = (model,)
        else:
            self.merdiven = MODEL_MERDIVENI
        self.max_deneme = max_deneme
        self.zaman_asimi = zaman_asimi
        self.max_429_deneme = max_429_deneme
        # max_completion_tokens DUSUNME tokenlerini de sayar; anlati istemi
        # soru-cevaptan uzun oldugu icin baslangic butcesi genis tutulur.
        # Bos yanit gelirse butce max_butce'ye kadar ikiye katlanir.
        self.max_cikti = max_cikti
        self.max_butce = max_butce

    # -- dusuk seviye ------------------------------------------------------
    def _govde(self, model: str, sistem: str, mesajlar: list, max_cikti: int,
               yeni_alan: bool) -> bytes:
        """max_completion_tokens / max_tokens ikilemi:
        yeni modeller birincisini, eski modeller ikincisini bekler. Once yeni
        alan denenir, 400 gelirse eskiye dusulur (bkz. _cagir)."""
        d = {"model": model,
             "messages": [{"role": "system", "content": sistem}] + mesajlar}
        d["max_completion_tokens" if yeni_alan else "max_tokens"] = max_cikti
        return json.dumps(d, ensure_ascii=False).encode("utf-8")

    def _cagir(self, model: str, sistem: str, mesajlar: list,
               max_cikti: int = 2000) -> str:
        yeni_alan = True
        for _429 in range(self.max_429_deneme + 1):
            istek = urllib.request.Request(
                API_URL, data=self._govde(model, sistem, mesajlar, max_cikti, yeni_alan),
                headers={"content-type": "application/json",
                         "authorization": f"Bearer {self.api_key}"})
            try:
                with urllib.request.urlopen(istek, timeout=self.zaman_asimi) as y:
                    veri = json.loads(y.read())
                secim = veri["choices"][0]
                metin = (secim["message"].get("content") or "").strip()
                if not metin:
                    raise BosYanitHatasi(secim.get("finish_reason", "?"),
                                         veri.get("usage", {}), max_cikti)
                return metin
            except urllib.error.HTTPError as e:
                govde = e.read().decode("utf-8", "replace")
                if e.code == 400 and "max_completion_tokens" in govde and yeni_alan:
                    yeni_alan = False           # PLAN B: eski alan adina dus
                    continue
                if e.code == 429:
                    if "insufficient_quota" in govde:
                        raise KotaHatasi(
                            "insufficient_quota: bakiye sifir ya da harcama siniri "
                            "dolu. Beklemek COZMEZ. platform.openai.com -> Settings "
                            "-> Billing / Limits") from e
                    bekle = e.headers.get("retry-after") or \
                        e.headers.get("retry-after-ms")
                    try:
                        sn = float(bekle) / (1000 if "ms" in str(bekle).lower() else 1)
                    except (TypeError, ValueError):
                        sn = 2 ** _429
                    time.sleep(min(sn, 30) + random.random())
                    continue
                raise RuntimeError(f"OpenAI HTTP {e.code}: {govde[:200]}") from e
        raise RuntimeError("429 tekrar tekrar alindi; rate limit gecmedi")

    def _geri_cekil(self, kayit: dict, soru: str | None) -> str:
        """LLM yoksa/gecemezse ne basilacak.

        KRITIK: soru sorulduysa ANLATI BASILMAZ. Anlati basmak, soruya cevap
        verilmis gibi gorunup aslinda vermemektir -- demoda en tehlikeli hata
        turu budur (sessiz yanlis cevap).
        """
        if soru is None:
            return sablon_anlati(kayit)
        return sablon_cevap(kayit, soru)

    def _denetimli(self, sistem: str, ilk_istem: str, kayit: dict,
                   soru: str | None = None) -> Cevap:
        """Uret -> denetle -> gecmezse EKSIK SAYILARI bildir -> yeniden yazdir.
        Model denetimden gecemezse merdivende bir ust modele devret."""
        if not self.api_key:
            m = self._geri_cekil(kayit, soru)
            return Cevap(m, denetle(m, kayit), kapsama(m, kayit), 1, "sablon", "-")

        izleme, son, ilk = [], None, None
        for model in self.merdiven:
            mesajlar = [{"role": "user", "content": ilk_istem}]
            butce = self.max_cikti
            for deneme in range(1, self.max_deneme + 2):
                try:
                    metin = self._cagir(model, sistem, mesajlar, butce)
                except BosYanitHatasi as e:
                    # Butceyi ikiye katlayip AYNI denemeyi tekrarla; bu bir
                    # icerik hatasi degil, kesilmis cagridir.
                    izleme.append(f"{model} d{deneme}: BOS YANIT "
                                  f"(finish_reason={e.finish_reason}, butce={butce})")
                    if butce < self.max_butce:
                        butce = min(butce * 2, self.max_butce)
                        izleme.append(f"{model}: butce {butce}'e cikarildi, tekrar")
                        continue
                    break                                        # sonraki modele
                except KotaHatasi as e:
                    m = self._geri_cekil(kayit, soru)
                    c = Cevap(m, denetle(m, kayit), kapsama(m, kayit), deneme,
                              "sablon", "-", izleme)
                    c.denetim.uyarilar.append(str(e))
                    return c
                except Exception as e:                          # noqa: BLE001
                    # Mesaji da sakla: "HATA ValueError" teshis edilemez.
                    izleme.append(f"{model} d{deneme}: HATA "
                                  f"{type(e).__name__}: "
                                  f"{maskele(str(e), self.api_key)[:200]}")
                    break                                        # sonraki modele
                d = denetle(metin, kayit)
                # Anlatida kapsama da ZORUNLU: uydurma yoksa ama bilgi de yoksa
                # metin denetimden gecmis sayilmaz.
                eks = eksik_kapsama(metin, kayit) if soru is None else []
                izleme.append(f"{model} d{deneme}: "
                              f"{d.dogrulanan}/{d.toplam_sayi} "
                              f"{'sayi-OK' if d.gecti else 'sayi-RED'}"
                              + (f" · eksik: {','.join(eks)}" if eks else " · kapsama-OK"))
                son = Cevap(metin, d, kapsama(metin, kayit), deneme, "llm",
                            model, list(izleme))
                if ilk is None:              # merdivendeki ILK modelin ILK denemesi
                    ilk = {"sayi": d.toplam_sayi, "dogrulanan": d.dogrulanan,
                           "eksik": list(eks), "gecti": bool(d.gecti and not eks),
                           "uydurma": [h for h, _ in d.kayitta_olmayan]}
                son.ilk_sayi = ilk["sayi"]; son.ilk_dogrulanan = ilk["dogrulanan"]
                son.ilk_eksik_kapsama = ilk["eksik"]; son.ilk_gecti = ilk["gecti"]
                son.ilk_uydurma = ilk["uydurma"]
                if d.gecti and not eks:
                    return son

                geri = []
                if not d.gecti and d.kayitta_olmayan:
                    geri.append("Su sayilar karar kaydinda YOK: "
                                + ", ".join(f"'{h}'" for h, _ in d.kayitta_olmayan)
                                + ". Bunlari cikar ya da kayittaki dogru degerle degistir.")
                if not d.gecti and not d.kayitta_olmayan:
                    geri.append("Cikti bos ya da cok kisa. Yeniden yaz.")
                if eks:
                    geri.append("Su ZORUNLU ogeler metinde yok: "
                                + "; ".join(KAPSAMA_ACIKLAMA[a] for a in eks)
                                + ". Bunlari karar kaydindaki DEGERLERIYLE ekle. "
                                  "Sayilardan kacinma.")
                mesajlar += [
                    {"role": "assistant", "content": metin},
                    {"role": "user", "content": " ".join(geri)
                        + " Yeni sayi uydurma. Metni yeniden yaz."}]

        m = self._geri_cekil(kayit, soru)
        c = Cevap(m, denetle(m, kayit), kapsama(m, kayit),
                  self.max_deneme + 1, "sablon", "-", izleme)
        if ilk:
            c.ilk_sayi, c.ilk_dogrulanan = ilk["sayi"], ilk["dogrulanan"]
            c.ilk_eksik_kapsama, c.ilk_gecti = ilk["eksik"], ilk["gecti"]
            c.ilk_uydurma = ilk["uydurma"]
        # Sebep API hatasi mi, denetim basarisizligi mi? Ikisi cok farkli
        # sorunlardir ve ayni mesaji basmak teshisi zorlastirir.
        api_hatasi = [x for x in izleme if "HATA" in x]
        bos_yanit = [x for x in izleme if "BOS YANIT" in x]
        red = [x for x in izleme if "RED" in x]
        if bos_yanit and not red and not api_hatasi:
            c.denetim.uyarilar.append(
                "Model butce tavaninda bile BOS icerik dondurdu -> sablon anlati. "
                "Muhtemel sebep: dusunme tokenleri butceyi tuketiyor. "
                f"max_butce'yi yukseltmeyi deneyin (su an {self.max_butce}). "
                f"Ayrinti: {'; '.join(bos_yanit)}")
        elif api_hatasi and not red and not bos_yanit:
            c.denetim.uyarilar.append(
                f"API cagrilari basarisiz oldu -> sablon anlatiya dusuldu. "
                f"Ayrinti: {'; '.join(api_hatasi)}")
        elif api_hatasi or bos_yanit:
            c.denetim.uyarilar.append(
                f"Karisik basarisizlik (API/bos yanit/denetim) -> sablon anlati. "
                f"Ayrinti: {'; '.join(izleme)}")
        else:
            c.denetim.uyarilar.append(
                "Hicbir model denetimden gecemedi -> sablon anlatiya dusuldu")
        return c

    # -- genel arayuz ------------------------------------------------------
    def anlat(self, kayit: dict) -> Cevap:
        return self._denetimli(
            SISTEM, "Asagidaki karar kaydini anlat.\n\n=== KARAR KAYDI ===\n"
            + ozet_metni(kayit), kayit)

    def sor(self, kayit: dict, soru: str) -> Cevap:
        return self._denetimli(
            SORU_SISTEMI, "=== KARAR KAYDI ===\n" + ozet_metni(kayit)
            + f"\n\n=== SORU ===\n{soru}", kayit, soru=soru)


# ----------------------------------------------------------------------------
def model_karsilastir(api_key: str, kayitlar: list,
                      modeller: tuple = MODEL_MERDIVENI, tekrar: int = 1):
    """Hangi model denetimden daha sik geciyor? Demo oncesi BIR KEZ kosulur.

    Model secimini his ile degil olcumle yapmak icin. Ciktisi bir DataFrame:
    model basina gecme orani, ortalama denetlenen sayi, ortalama deneme sayisi.
    """
    import pandas as pd
    sat = []
    for m in modeller:
        ajan = AciklayiciAjan(api_key=api_key, model_merdiveni=(m,))
        for k in kayitlar:
            for _ in range(tekrar):
                c = ajan.anlat(k)
                sat.append({"model": m, "gecti": c.denetim.gecti,
                            "kaynak": c.kaynak, "deneme": c.deneme,
                            "sayi": c.denetim.toplam_sayi,
                            "dogrulanan": c.denetim.dogrulanan,
                            "kelime": len(c.metin.split()),
                            "kapsama": sum(c.kapsama.values())})
    d = pd.DataFrame(sat)
    # DIKKAT: sablon anlati denetimden HER ZAMAN gecer (zaten kayittan uretilir).
    # Bu yuzden 'gecti' tek basina yaniltici olur -- llm_gecme_orani YALNIZCA
    # gercekten LLM'den gelen cevaplar uzerinden hesaplanir.
    d["llm_gecti"] = (d.kaynak == "llm") & d.gecti
    ozet = d.groupby("model").agg(
        kosu=("gecti", "size"),
        llm_gecme_orani=("llm_gecti", "mean"),
        sablona_dusme=("kaynak", lambda s: (s == "sablon").mean()),
        ort_deneme=("deneme", "mean"), ort_kelime=("kelime", "mean"),
        ort_kapsama=("kapsama", "mean")).round(3)
    if (ozet.sablona_dusme == 1.0).all():
        print("UYARI: hicbir API cagrisi basarili olmadi -- tablo model kalitesi "
              "hakkinda BILGI VERMEZ. Once tani(API_KEY) calistirin.")
    return ozet, d
