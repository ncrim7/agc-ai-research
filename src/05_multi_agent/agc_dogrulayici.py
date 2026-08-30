"""
AGC — SAYI DENETLEYICISI (LLM DEGIL, KOD)
==========================================
Aciklayici ajanin urettigi metindeki HER sayiyi ayiklar ve karar kaydinda
karsiligi var mi diye bakar. Yoksa metni reddeder.

NEDEN AJAN DEGIL DE KOD
------------------------
Bir LLM'i baska bir LLM'e denetlettirmek yaygin bir kalip ama sayisal iddialar
icin gereksiz: kayit yapilandirilmis, sayilar sonlu ve tam eslesme aranabilir.
Kodla denetim %100 kesin, milisaniye mertebesinde ve bedava. Ikinci bir ajanin
gerekcesi ancak buradan gecen ama yine de yanlis olan iddialar olcuIdukten
sonra dogar -- once bu olculmeli.

2026 pratigiyle uyumlu: riskin yuksek oldugu yerde modeli kaynaga baglamak ve
iddiayi kaynaga karsi dogrulamak. Burada "kaynak" karar kaydidir.

NE DENETLER / NE DENETLEMEZ
----------------------------
DENETLER  : metindeki sayisal iddialar kayitta var mi
DENETLEMEZ: cumlenin anlami dogru mu (bunun icin elle ornekleme gerekir --
            bkz. degerlendirme tasarimi, "iddia sadakati")

Yani bu bir HALUSINASYON FILTRESI degil, SAYI UYDURMA filtresidir. Ikisini
karistirmamak onemli; rapora da boyle yazilmali.
"""



from __future__ import annotations

SURUM = "2026-08-24.2"   # sayi ayiklama: 4+ haneli sayilar parcalanmiyor

import re
from dataclasses import dataclass, field

# Anlati icinde serbestce kullanilabilecek, kayittan gelmesi gerekmeyen sayilar:
# ufuk etiketleri ve kucuk sira sayilari.
SERBEST = {0.0, 1.0, 2.0, 3.0, 6.0, 12.0, 24.0, 100.0}
# HATA (duzeltildi): onceki desen `\d{1,3}(?:[.,]\d{3})*...` idi ve binlik
# ayraci OLMAYAN dort+ haneli sayilari PARCALIYORDU:
#     "1014.0" -> ["101", "4.0"]      "47809" -> ["478", "09"]
# Sonuc: CO2air (400-1500) ve Tot_PAR (0-700+) degerleri hic dogrulanmiyordu.
# Iki yonlu zarar: metindeki gercek sayi bulunamayip UYDURMA sayilir, ve
# kayittan uretilen havuza 101/4.0 gibi sahte degerler girip alakasiz
# sayilarin GECMESINE yol acar.
# Yeni desen sirali: (1) binlik AYRACLI bicim (en az bir grup sart),
# (2) duz basamak dizisi + istege bagli ondalik, (3) bas noktali ondalik.
SAYI = re.compile(
    r"[-+]?\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?"   # 1.234,5 · 1,234.5
    r"|[-+]?\d+(?:[.,]\d+)?"                     # 1014.0 · 958 · 0.817
    r"|[-+]?[.,]\d+")                             # .5


def _sayilar(metin: str) -> list:
    """Metindeki sayilari cikarir. Turkce/Ingilizce ondalik ayraci ikisini de kabul eder."""
    out = []
    for m in SAYI.finditer(metin):
        ham = m.group()
        t = ham.replace(" ", "")
        # 1.234,5 (tr) veya 1,234.5 (en) -> binlik ayracini at
        if "," in t and "." in t:
            t = t.replace("." if t.rindex(",") > t.rindex(".") else ",", "")
        t = t.replace(",", ".")
        try:
            out.append((ham, float(t)))
        except ValueError:
            continue
    return out


def _kayit_sayilari(kayit: dict) -> set:
    """Kayitta gecen tum sayilari toplar -- yuzde ve yuvarlanmis bicimleriyle."""
    s = set()

    def ekle(v):
        if v is None:
            return
        try:
            f = float(v)
        except (TypeError, ValueError):
            return
        s.add(round(f, 6))
        s.add(round(f, 3))
        s.add(round(f, 2))
        s.add(round(f, 1))
        s.add(float(round(f)))
        # olasilik/isabet gibi 0-1 arasi degerler metinde yuzde olarak gecebilir
        if 0.0 <= f <= 1.0:
            for p in (f * 100,):
                s.add(round(p, 2))
                s.add(round(p, 1))
                s.add(float(round(p)))

    def gez(d):
        if isinstance(d, dict):
            for v in d.values():
                gez(v)
        elif isinstance(d, (list, tuple)):
            for v in d:
                gez(v)
        elif isinstance(d, (int, float)):
            ekle(d)
        elif isinstance(d, str):
            for _, f in _sayilar(d):     # metin alanlarindaki sayilar da gecerli
                ekle(f)

    gez(kayit)
    return s


@dataclass
class DenetimSonucu:
    gecti: bool
    toplam_sayi: int = 0
    dogrulanan: int = 0
    kayitta_olmayan: list = field(default_factory=list)
    uyarilar: list = field(default_factory=list)

    def rapor(self) -> str:
        d = (f"sayi denetimi: {self.dogrulanan}/{self.toplam_sayi} dogrulandi"
             f" -> {'GECTI' if self.gecti else 'REDDEDILDI'}")
        if self.kayitta_olmayan:
            d += "\n  kayitta bulunmayan: " + ", ".join(
                f"'{h}'" for h, _ in self.kayitta_olmayan)
        for u in self.uyarilar:
            d += f"\n  UYARI: {u}"
        return d


# Anlamli bir anlati/cevap icin en az kac kelime beklenir.
# GERCEK VAKA: model bos metin dondurdugunde denetim "0/0 dogrulandi -> GECTI"
# basiyordu. Sifir sayi denetlemek, denetimden GECMEK degildir. Bos cikti
# demoda ekrani bos birakir ve sistem basarili raporlar -- sessiz basarisizlik.
MIN_KELIME = 8


def denetle(metin: str, kayit: dict, tolerans: float = 0.005,
            min_kelime: int = MIN_KELIME) -> DenetimSonucu:
    """Metindeki her sayi kayitta var mi? Ve metin ANLAMLI uzunlukta mi?

    tolerans: bagil tolerans (yuvarlama farklarina izin verir, ornegin
              0.8168 -> "%82" gecerli sayilir).
    """
    kelime = len(metin.split())
    if kelime < min_kelime:
        s = DenetimSonucu(gecti=False, toplam_sayi=0, dogrulanan=0)
        s.uyarilar.append(
            f"cikti bos ya da cok kisa ({kelime} kelime, en az {min_kelime} "
            f"bekleniyor) -- bu bir GECIS DEGILDIR")
        return s

    havuz = _kayit_sayilari(kayit)
    bulunan = _sayilar(metin)
    eksik = []
    for ham, f in bulunan:
        if round(f, 6) in havuz or f in SERBEST:
            continue
        if any(abs(f - k) <= max(tolerans * max(abs(k), 1.0), 1e-9) for k in havuz):
            continue
        eksik.append((ham, f))

    sonuc = DenetimSonucu(gecti=not eksik, toplam_sayi=len(bulunan),
                          dogrulanan=len(bulunan) - len(eksik), kayitta_olmayan=eksik)

    # --- icerik denetimleri (sayisal degil, kural bazli) ---------------------
    dusuk = metin.lower()
    for yasak, sebep in [
        ("derece düşer", "buyukluk iddiasi -- model nedensel degil"),
        ("azalır", None), ("artar", None),
    ]:
        if yasak == "derece düşer" and yasak in dusuk:
            sonuc.uyarilar.append(sebep)
    if any(x["guven"] == "KALITATIF" for x in kayit.get("uyarilar", [])) \
            and re.search(r"olasıl[ıi]k\s*%?\s*\d", dusuk):
        sonuc.uyarilar.append(
            "KALITATIF uyari icin olasilik ifadesi gecmis olabilir -- kontrol et")
    return sonuc


# Turkce aksan katlama tablosu.
# GERCEK VAKA: DKB metinleri AKSANSIZ yazilmis ("sicakligi"), LLM ise dogru
# Turkce yaziyor ("sicakligi" -> "sıcaklığı"). Duz alt-dize karsilastirmasi
# tutmadi ve kisit YAZILDIGI HALDE "eksik" sayildi. 30 kosuluk olcumde dort
# yanlis red, bir gereksiz sablona dusme buradan geldi.
_AKSAN = str.maketrans("çğıİöşüÇĞıIÖŞÜâîû", "cgiiosucgiiosuaiu")


def _sadelestir(m: str) -> str:
    """Aksanlari katlayip kucult. Karsilastirma HER IKI tarafta buradan gecer."""
    return m.translate(_AKSAN).lower()


def _sayi_geciyor(metin: str, deger, tolerans: float = 0.005) -> bool:
    """Bir sayi metinde geciyor mu? Turkce/Ingilizce ondalik ve yuzde bicimiyle."""
    if deger is None:
        return False
    try:
        d = float(deger)
    except (TypeError, ValueError):
        return False
    # DIKKAT: ham degeri TAM SAYIYA yuvarlamak sahte eslesme uretir.
    # Gercek vaka: esik 5.7 -> round -> 6; metindeki "6h" etiketi eslesti ve
    # kapsama kontrolu esik yazilmamis bir metni "tam" saydi. Ondalik bicimler
    # korunur; tam sayiya yuvarlama YALNIZCA yuzde bicimi icin gecerlidir
    # ("%82" yazmak 0.817 icin dogal ve kabul edilebilir).
    adaylar = [d, round(d, 3), round(d, 2), round(d, 1)]
    if 0.0 <= d <= 1.0:
        adaylar += [d * 100, round(d * 100, 1), float(round(d * 100))]
    for _, f in _sayilar(metin):
        for a in adaylar:
            if abs(f - a) <= max(tolerans * max(abs(a), 1.0), 1e-9):
                return True
    return False


def kapsama(metin: str, kayit: dict) -> dict:
    """Anlati, kaydin ZORUNLU parcalarini aniyor mu?

    NEDEN GEREKLI: denetleyici yalnizca UYDURMAYI yakalar. Ama bir anlati
    hicbir sayi yazmayarak da denetimden gecebilir -- ve bilgi vermez.
    GERCEK VAKA: model "EC_slab2 3h icin kritik uyaridir" yazdi, esigi (5.7),
    tahmini (5.9) ve olculmus isabeti (%82) hic anmadi; denetim 9/9 GECTI dedi.
    Yasak koymak yetmiyor, ZORUNLULUK da gerekiyor.
    """
    d = _sadelestir(metin)
    ilk = kayit["uyarilar"][0] if kayit.get("uyarilar") else None
    if ilk is None:
        return {"uyari_yok": True}
    kisit_kelimeleri = [_sadelestir(k).strip(".,;:")
                        for k in ilk["kisit"].split()[:6] if len(k) > 4]
    return {
        "esik_var": _sayi_geciyor(metin, ilk["esik"]),
        # KARARI VEREN deger aranir, terminal degil. Terminal deger uyarilarin
        # %19'unda esigin ters tarafindadir; onu zorunlu tutmak modeli
        # celiskili cumle kurmaya iter.
        "tahmin_var": _sayi_geciyor(metin, ilk.get("karar_degeri", ilk["tahmin"])),
        "isabet_var": _sayi_geciyor(metin, ilk["olculmus_isabet"]),
        "hedef_var": _sadelestir(ilk["hedef"]) in d,
        # tek kelime eslesmesi zayif: "sulama" gecen her metin kisiti anmis
        # sayilirdi. En az iki anahtar kelime aranir.
        "kisit_var": sum(k in d for k in kisit_kelimeleri) >= 2,
        "nedensellik_uyarisi": ("nedensel" in d or "buyuklug" in d or "buyuklu" in d),
    }


# Anlatida MUTLAKA bulunmasi gerekenler. Eksikse ajana geri bildirilir.
ZORUNLU_KAPSAMA = ("esik_var", "tahmin_var", "isabet_var", "hedef_var",
                   "kisit_var", "nedensellik_uyarisi")


def eksik_kapsama(metin: str, kayit: dict) -> list:
    """Zorunlu ogelerden hangileri eksik? Bos liste = tam."""
    k = kapsama(metin, kayit)
    if k.get("uyari_yok"):
        return []
    return [a for a in ZORUNLU_KAPSAMA if not k.get(a)]


KAPSAMA_ACIKLAMA = {
    "esik_var": "en oncelikli uyarinin ESIK degeri",
    "tahmin_var": "en oncelikli uyarinin TAHMIN degeri",
    "isabet_var": "en oncelikli kuralin OLCULMUS ISABETI (yuzde olarak)",
    "hedef_var": "en oncelikli uyarinin HEDEF adi",
    "kisit_var": "en oncelikli uyarinin KISIT metni",
    "nedensellik_uyarisi": "modelin nedensel olmadigi / buyuklugun bilinemedigi uyarisi",
}
