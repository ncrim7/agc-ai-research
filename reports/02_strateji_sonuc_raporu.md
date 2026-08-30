# Altı Kontrol Stratejisi, Altı Farklı Sonuç
### Autonomous Greenhouse Challenge 2. Edisyon — Kaynak, Üretim ve Kalite Betimsel Analizi

**Tarih:** Ağustos 2026 · **Sürüm:** 2 (ekonomik düzeltmelerle) · **Kapsam:** AGC 2. Edisyon, kullanılmayan veri setleri
**İlişki:** Bu rapor, *Sera İkliminde Kısa Vadeli Tahmin* ve *Uzun Vadeli Tahmin* raporlarının tamamlayıcısıdır. Tahmin sonuçlarını değiştirmez; onların cevaplamadığı bir soruyu cevaplar.

> **Sürüm 2 notu:** Bu rapor ilk yazıldığında kaynak tüketimi **fiziksel birimlerle** karşılaştırılmıştı (MJ ısı, kWh elektrik). Sonradan `Economics.pdf` ve `ReadMe.pdf` resmi belgeleri incelendi ve tüm kalemler **euro cinsine** çevrildi. Bu, raporun ana bulgusunu değiştirdi: ısıtma farkı ekonomik olarak küçük, elektrik farkı belirleyici. Değişen bölümler 2, 3.5, 4.1, 4.2, 5 ve Ek C'dir; kalite bulguları (bölüm 3.4, 4.3, 4.4) etkilenmemiştir. Ayrıntılı ekonomik analiz için bkz. *Sera İşletmesinin Ekonomisi* raporu.

> **Bu belge nasıl okunmalı:** Ana gövde teknik ön bilgi gerektirmez. Ekler, veri onarımları ve yöntem ayrıntılarını içerir. Bu bir **betimsel analizdir** — model kurulmamıştır, çünkü hedef değişkenlerin örneklem sayısı (23 hasat olayı, 8 kalite ölçümü) modellemeye yetmez.

---

# ANA GÖVDE

## 1. Neden bu analiz?

Önceki iki rapor şu soruyu cevapladı: *"Sera durumu gelecekte ne olacak ve bunu ne kadar doğru tahmin edebiliyoruz?"*

Ancak Autonomous Greenhouse Challenge yarışmasının **asıl hedefi tahmin doğruluğu değildi.** Yarışma **net kâr** üzerinden değerlendirildi: üretimin değeri eksi kaynak maliyeti. Tahmin çalışması bu boyuta hiç bakmadı.

Veri setinde bu boyutu ölçen üç dosya vardı ve hiç kullanılmamıştı: kaynak tüketimi (`Resources`), üretim (`Production`) ve meyve kalitesi (`TomQuality`). Bu rapor onları kullanarak şu soruyu cevaplıyor:

**Altı takım hangi stratejiyi izledi, ve bu stratejiler gerçekte ne üretti?**

## 2. Ana bulgu

**Takımlar benzer miktarda üretti (1,11 kat fark) ama farklı maliyetle.** Ancak maliyet farkının nerede olduğu, hangi birimle baktığınıza göre tamamen değişiyor.

| Ölçüt | En düşük | En yüksek | Oran |
|---|---|---|---|
| Toplam üretim (kg/m²) | 13,48 (IUACAAS) | 14,92 (Automatoes) | 1,11× |
| Isıtma tüketimi (MJ) | 173 (Digilog) | 472 (Reference) | **2,7×** |
| Elektrik tüketimi (kWh) | 228 (IUACAAS) | 323 (Digilog) | 1,4× |
| **Birim üretim maliyeti (€/kg)** | **1,29 (Automatoes)** | **1,60 (Digilog)** | **1,24×** |

Fiziksel birimlerle bakıldığında en çarpıcı fark ısıtmadadır (2,7 kat). **Ancak euro cinsinden ısıtma toplam değişken maliyetin yalnızca %6–18'idir; elektrik %79–90'ıdır.**

Bunun sonucu şu tabloda görülüyor — hangi verimlilik ölçütü net kârı öngörüyor?

| Verimlilik ölçütü | Net kârla Spearman ρ |
|---|---|
| Isıtma / kg | **−0,09** (öngörü gücü yok) |
| Elektrik / kg | −0,83 |
| **Euro / kg** | **−1,00** (mükemmel sıralama) |

**Isıtma verimliliği net kârı hiç öngörmüyor. Euro cinsinden birim maliyet mükemmel öngörüyor.**

> **Sürüm 1'in hatası:** İlk sürümde "kaynak tüketiminde 2,7 kat fark" ana bulgu olarak sunulmuştu ve bu ısıtmayı kastediyordu. Ekonomik olarak yanıltıcıydı: gerçek birim maliyet farkı 1,24 kattır ve kaynağı elektriktir.

## 3. Altı strateji, yan yana

### 3.1 İklim rejimi — takımlar seraları nasıl işletti?

| Takım | Sıcaklık (°C) | Sıcaklık oynaklığı | Nem (%) | Nem açığı | CO₂ (ppm) | Işık |
|---|---|---|---|---|---|---|
| **Automatoes** | **23,26** | **4,39** | **84,93** | 3,41 | 692 | 215 |
| Reference | 22,72 | 3,92 | 81,77 | **3,90** | 649 | 221 |
| AICU | 22,06 | **2,99** | 84,17 | 3,26 | **765** | 201 |
| Digilog | 21,39 | 3,63 | 81,35 | 3,66 | **605** | **236** |
| TheAutomators | 21,35 | 2,98 | **80,76** | 3,87 | 741 | 219 |
| IUACAAS | **21,32** | 4,17 | 84,18 | **3,25** | 639 | 205 |

Sıcaklık aralığı 2 °C — küçük görünür ama sera fizyolojisinde büyüktür. Automatoes en sıcak ve **en oynak** serayı işletmiş.

### 3.2 Kaynak tüketimi

| Takım | Isıtma | Elektrik | Sulama | Drenaj | Drenaj oranı | CO₂ |
|---|---|---|---|---|---|---|
| Digilog | **173** | **323** | 741 | **183** | **0,25** | 9,7 |
| Automatoes | 185 | 270 | 789 | 324 | 0,35 | 9,1 |
| AICU | 252 | 240 | **554** | 211 | 0,43 | 10,2 |
| IUACAAS | 335 | **228** | **867** | 296 | 0,31 | **7,3** |
| TheAutomators | 363 | 285 | 723 | 268 | **0,48** | **12,5** |
| Reference | **472** | 267 | 789 | 350 | 0,39 | 8,6 |

### 3.3 Üretim sonucu

| Takım | Toplam üretim | A sınıfı payı | Salkım gelişim süresi (gün) |
|---|---|---|---|
| **Automatoes** | **14,92** | 96,3% | 48,4 |
| TheAutomators | 14,36 | 99,9% | 49,9 |
| Reference | 14,30 | **100,0%** | **46,4** |
| Digilog | 14,21 | 95,1% | **52,5** |
| AICU | 13,76 | 99,3% | 47,7 |
| IUACAAS | **13,48** | 95,6% | 51,3 |

Salkım gelişim süresi 46,4 ile 52,5 gün arasında değişiyor — **%13 fark.** Aynı çeşit, aynı tesis, aynı dönem. Farkı yaratan tek şey iklim rejimi.

### 3.4 Meyve kalitesi

| Takım | Tat (panel) | Briks | Asit | Sertlik | Meyve ağırlığı |
|---|---|---|---|---|---|
| **Digilog** | **78,0** | **8,86** | 13,19 | 223 | 10,26 |
| Automatoes | 77,1 | 8,52 | 12,74 | 215 | 10,45 |
| TheAutomators | 77,1 | 8,79 | 13,74 | **272** | **9,61** |
| IUACAAS | 75,5 | 8,55 | **14,00** | 249 | 9,79 |
| AICU | 75,3 | 8,69 | **12,76** | 254 | **11,22** |
| Reference | **74,6** | **8,46** | 12,91 | **214** | 10,31 |

### 3.5 Verimlilik — fiziksel ve ekonomik

**Fiziksel birimlerle** (birim üretim başına kaynak):

| Takım | Isıtma / kg (MJ) | Elektrik / kg (kWh) | Su / kg (L) | CO₂ / kg |
|---|---|---|---|---|
| **Digilog** | **12,2** | **22,7** | 52,1 | 0,68 |
| **Automatoes** | **12,4** | 18,1 | 52,9 | 0,61 |
| AICU | 18,3 | 17,5 | **40,2** | 0,74 |
| IUACAAS | 24,8 | **16,9** | **64,3** | **0,54** |
| TheAutomators | 25,2 | 19,8 | 50,4 | **0,87** |
| **Reference** | **33,0** | 18,7 | 55,1 | 0,60 |

**Euro cinsinden** (`Economics.pdf` fiyatlarıyla, €/m² sezon toplamı):

| Takım | Isıtma | Elektrik | CO₂ | Toplam değişken | **€/kg** | Isıtmanın payı |
|---|---|---|---|---|---|---|
| **Automatoes** | 1,54 | 17,04 | 0,73 | 19,31 | **1,294** | %8,0 |
| AICU | 2,09 | 16,38 | 0,81 | 19,28 | 1,401 | %10,8 |
| IUACAAS | 2,78 | 15,60 | 0,58 | 18,96 | 1,407 | %14,7 |
| Reference | 3,91 | 16,87 | 0,69 | 21,47 | 1,501 | %18,2 |
| TheAutomators | 3,01 | 18,48 | 1,06 | 22,55 | 1,570 | %13,3 |
| **Digilog** | 1,44 | 20,57 | 0,77 | 22,78 | **1,603** | %6,3 |

**İki tablo taban tabana zıt sıralama veriyor.** Digilog fiziksel ısıtma verimliliğinde birinci, euro cinsinden birim maliyette sonuncu. Sebebi: en düşük gazı kullanmış ama en yüksek elektriği — ve elektrik 10 kat daha pahalı bir kalem.

📊 **Şekil 13**

---

## 4. Bulgular

### 4.1 Enerji paradoksu — gerçek ama ekonomik olarak küçük

**Automatoes en sıcak serayı, Reference'ın üçte biri kadar gazla işletti.**

| | Automatoes | Reference | Fark |
|---|---|---|---|
| Ortalama sıcaklık | 23,26 °C | 22,72 °C | +0,54 °C |
| Isıtma tüketimi | 185 MJ | 472 MJ | **2,5 kat** |
| Isıtma maliyeti | 1,54 € | 3,91 € | **2,37 €/m²** |
| Toplam üretim | 14,92 | 14,30 | +%4,3 |

Gözlem doğrudur ve fiziksel olarak dikkat çekicidir. **Ancak euro cinsinden fark 2,37 €/m² — toplam değişken maliyetin yalnızca %11'i.**

Karşılaştırma için: aynı iki takım arasındaki elektrik farkı 0,17 €/m², ama en ucuz (IUACAAS 15,60) ile en pahalı (Digilog 20,57) arasındaki elektrik farkı **4,97 €/m²** — ısıtma farkının iki katı.

> **Sürüm 1'de bu bulgu ana verimlilik göstergesi olarak sunulmuştu.** Fiziksel olarak ilginç olması, ekonomik olarak belirleyici olduğu anlamına gelmiyor.

**Digilog karşı örneği:** en düşük ısıtma (1,44 €), en yüksek Brix (8,86) ve tat (78,0) — ama en yüksek elektrik (20,57 €) ve **tek negatif net kâr** (−2,60 €/m²'lik değişken maliyet üstünlüğü kaybı). Isıtma verimliliği tek başına hiçbir şey söylemiyor.

### 4.2 Mekanizma — elektrik tarafı çözüldü, ısıtma tarafı açık kaldı

**Elektrik farkı (çözüldü).** Sonraki analizde 5 dakikalık veriden lamba kullanımı ayrıştırıldı:

| Bileşen | Bulgu |
|---|---|
| Lamba yoğunluğu | Herkeste aynı (~%99,9 — ikili aç/kapa) |
| **Lamba süresi** | **14,7 (AICU) – 18,7 (Digilog) saat/gün** |
| Tarife zamanlaması | Pik saat payı %57,6 (Automatoes) – %67,8 (AICU) |

Kış maliyet farkının **%113'ü lamba süresinden**, −%13'ü tarife zamanlamasından geliyor. Yani fark tamamen **lambaların kaç saat yandığından** kaynaklanıyor.

**Isıtma farkı (açık kaldı).** Isıtma verimliliği farkının kaynağı hâlâ bulunamadı. Test edilen havalandırma hipotezi desteklenmedi: nem açığı ile ısıtma arasında ρ = +0,43 — zayıf, ve Digilog örüntüyü bozuyor (yüksek nem açığı ama en düşük ısıtma). Sıcaklık ile ısıtma arasında da ilişki yok (ρ = −0,14).

Literatürde bir aday mekanizma var: **sıcaklık entegrasyonu** — ısıtma ve havalandırma setpoint'lerini modüle edip 24 saatlik ortalama sıcaklığı korumak. Domatesin sıcaklığı belirli bir süre içinde telafi etme yeteneği yüksektir. Verimizde test edildi ancak desteklenmedi (oynaklık ↔ ısıtma ρ = −0,20).

Perde kullanım stratejisi, boru sıcaklığı rejimi ve ısıtma zamanlaması 5 dakikalık veride mevcuttur ve ayrı bir analizi hak eder. **Ancak ekonomik önceliği düşüktür:** ısıtma toplam değişken maliyetin %6–18'idir.

### 4.3 Üç ders kitabı ilişkisi doğrulandı

Bu, raporun en önemli metodolojik kısmıdır: **bahçecilik literatüründe bilinen ilişkiler, bizim verimizden bağımsız olarak çıkıyor.**

| İlişki | Spearman ρ | Beklenen yön |
|---|---|---|
| Yavaş olgunlaşma → yüksek briks | **+0,71** | ✓ |
| Sıcak sera → hızlı salkım gelişimi | **−0,66** | ✓ |
| Sıcak sera → düşük briks (seyrelme) | **−0,54** | ✓ |

Bunun anlamı: veri seti ve işleme hattımız **dış bilgiyle doğrulanmış** oluyor. Sadece kendi metriklerimizle tutarlı değil, alanın bilinen fizyolojisiyle de tutarlı.

Fizyolojik açıklama: yüksek sıcaklık meyve gelişimini hızlandırır; hızlı gelişen meyve daha az kuru madde biriktirir, dolayısıyla briks düşer. Digilog en soğuk seralardan birini işletmiş, en uzun olgunlaşma süresine (52,5 gün) ve **en yüksek briks ile tada** ulaşmış.

### 4.4 Verim–kalite ödünleşimi görülmedi

Klasik beklenti: çok üretirsen kalite düşer. **Veri bunu desteklemiyor.**

| | Spearman ρ |
|---|---|
| Üretim ~ Tat | +0,29 |
| Üretim ~ Briks | −0,20 |

Automatoes hem en yüksek üretimi elde etmiş hem tat sıralamasında ikinci. Yani ödünleşim kaçınılmaz değildir; iyi bir rejim ikisini birden verebilir.

### 4.5 Işık–üretim ilişkisi beklendiği kadar güçlü değil

Bahçecilikte bilinen kural: **%1 daha fazla ışık ≈ %1 daha fazla üretim.** Verimizde ρ = +0,37 — yön doğru ama zayıf.

Sebebi muhtemelen varyasyon aralığı: takımlar arası ışık farkı yalnızca %17 (201–236), üretim farkı ise %11. Bu dar aralıkta ışık dışındaki faktörler baskın hale geliyor. Kural yanlış değil; bu veri setinde test edilebilir değil.

---

## 5. Sonuç

**Ana çıkarım:** Aynı tesiste, aynı hava koşullarında, aynı çeşitle çalışan altı takım benzer miktarda üretti (1,11 kat fark) ama **birim üretim maliyeti 1,24 kat farklı** çıktı. Ve bu farkın neredeyse tamamı **elektrikten** — yani lambaların kaç saat yandığından — kaynaklanıyor.

**İkincil çıkarım:** İklim rejimi meyve kalitesini ölçülebilir biçimde etkiliyor ve bu etki bilinen fizyolojiyle uyumlu. Serin ve yavaş rejim daha tatlı meyve veriyor; sıcak rejim daha hızlı döngü. *(Bu bulgu sürüm 1'den değişmedi.)*

**Üçüncü çıkarım:** Verim ile kalite arasında zorunlu bir ödünleşim gözlenmedi. *(Değişmedi.)*

**Dördüncü çıkarım — sürüm 2'de eklendi:** Kalite ile maliyet arasında ise bir ödünleşim **var**. Digilog en yüksek Brix ve tat skorunu aldı, ama bunun için harcadığı elektrik kazancını aştı. Kalite ücretsiz değildir.

### 5.1 Karar destek katmanı için anlamı

1. **Ekonomik risk artık hesaplanabilir.** `Economics.pdf` fiyatları ve `ReadMe.pdf` formülleriyle 5 dakikalık maliyet serisi yeniden inşa edildi (%0,2–2,2 hata). Karar katmanı "bu aksiyon şu kadar eder" derken tahmin değil hesap kullanabilir.

2. **En büyük kaldıraç lamba kullanımı, ısıtma değil.** Elektrik toplam değişken maliyetin %79–90'ı. Sürüm 1'in ima ettiği ısıtma odağı ekonomik olarak yanlış önceliktir.

3. **Tarife zamanlaması risksiz bir kazanç.** Elektrik 07:00–23:00 arası iki kat pahalı. Aynı ışığı pik dışına kaydırmak takım başına 0,07–0,66 €/m² kazandırırdı — hiçbir bitki fizyolojisi varsayımı gerektirmeden.

4. **Kalite bir karar değişkenidir.** Salkım gelişim süresi ile briks arasındaki güçlü ilişki (ρ = +0,71), sıcaklık kararlarının kaliteye etkisinin öngörülebilir olduğunu gösteriyor. Ancak Brix'in ekonomik değeri sabittir (0,35 €/kg) ve elektrik maliyetinin yanında küçüktür.

5. **Referans noktaları elimizde.** Altı gerçek strateji, altı ölçülmüş sonuç, altı hesaplanmış net kâr. Bir öneri üretildiğinde "bu rejim hangi takımınkine benziyor ve o ne kazandı" diye sorulabilir.

---
---

# EKLER

## Ek A — Onarılan iki veri hatası

Reference takımının iki dosyasında kullanımı engelleyen hata vardı. İkisi de onarıldı ve onarım doğrulandı.

### A.1 Reference / Production — yıl yazım hatası

Bir satırda `%time = 43510` (Excel serisi), yani **14 Şubat 2019**. Diğer beş takımın ilk ölçümü 43875–43880 aralığında (14–19 Şubat **2020**).

43510 + 365 = 43875 — tam bir yıl. Deney 2019 Aralık'ta başladığı için 2019 Şubat'ında hasat imkânsız.

**Onarım:** +365 gün. **Doğrulama:** Reference'ın tarih aralığı düzeltme sonrası AICU ile birebir aynı (2020-02-14 → 2020-05-29, 24 satır).

### A.2 Reference / TomQuality — yapısal ayraç hatası

Bu bir tarih hatası değil, **kolon kayması** idi. Dosyanın ham hâli:

```
%time,	Flavour, 	TSS,	Acid,	%Juice,	Bite,	Weight	DMC_fruit
43880,	74,	7.9,	15,	58,	187,	7.77,	nan
```

Ayraç virgül + sekme. Başlıkta `Weight` ile `DMC_fruit` arasında **virgül yok, yalnızca sekme var** → başlıkta 7 isim, veride 8 değer. Pandas ilk sütunu indekse atıyor ve tüm kolonlar bir kayıyor.

Belirti: `%time` kolonu [74, 73, 76, 79, 73, 71, 78, 73] değerlerini gösteriyordu — monoton değil, tekrarlı, ve tarih olamayacak kadar küçük. Bunlar aslında `Flavour` skorlarıydı.

**Onarım:** Başlık atlanıp 8 kolon adı elle atandı. **Doğrulama:** Reference'ın `Flavour` ortalaması 74,6 — diğer takımlarla (74,6–78,0) aynı ölçekte. Tarih aralığı diğerleriyle birebir aynı.

> Bu hata, yalnızca tarihe bakılarak fark edilemezdi. "Reference'ın tarihleri bozuk" tespiti ilk teşhisti ve **yanlıştı**; asıl sorun bir sütun aşağı kaymaydı.

## Ek B — Yöntem

**Veri:** `Resources.csv` (günlük, 166 satır/takım, 996 gözlem) · `Production.csv` (hasat olayı, 23–24 satır/takım) · `TomQuality.csv` (8 ölçüm/takım) · iklim rejimi için `common_core_with_grodan_strict.parquet`

**Türetilen metrikler:**
- Drenaj oranı = Drenaj / Sulama (sulama > 0 olan günlerde)
- Birim üretim başına kaynak = sezon toplam kaynak / toplam üretim
- Toplam üretim = ProdA + ProdB

**Dönem farkı:** Kaynak verisi tüm sezonu (16 Ara – 29 May), üretim verisi hasat dönemini (14 Şub – 29 May) kapsar. Verimlilik hesabında **tüm sezon kaynağı** kullanılmıştır, çünkü hasat öncesi ısıtma da gerçek bir maliyettir.

**İstatistik:** Yalnızca Spearman sıra korelasyonu kullanılmıştır. Parametrik test yapılmamıştır.

## Ek C — Sınırlamalar

**C.0 Fiziksel birimlerle karşılaştırma yanıltıcıdır.** Bu raporun sürüm 1'i, kaynakları fiziksel birimlerle (MJ, kWh, L) karşılaştırdı ve ısıtma farkını (2,7 kat) ana bulgu olarak sundu. Euro cinsine çevrildiğinde ısıtmanın net kârla korelasyonu ρ = −0,09 (öngörü gücü yok), euro cinsinden birim maliyetin ise ρ = −1,00 çıktı. **Ders: farklı birimlerdeki kaynaklar ancak ortak bir ölçeğe (para) çevrildikten sonra karşılaştırılabilir.**

**C.1 Örneklem: altı takım.** Tüm korelasyonlar n = 6 üzerindendir. Bunlar **yön göstergesidir, kanıt değildir.** İstatistiksel güç, hiçbir ilişkiyi doğrulamaya yetmez. Rapordaki tüm ρ değerleri bu uyarıyla okunmalıdır.

**C.2 Birimler — SÜRÜM 2'DE ÇÖZÜLDÜ.** Sürüm 1'de `Heat_cons` ve `ElecHigh/Low` birimlerinin farklı olması nedeniyle toplam enerji hesaplanamamış, iki kalem ayrı raporlanmıştı. `ReadMe.pdf` birimleri (MJ ve kWh) ve `Economics.pdf` fiyatları (0,0083 €/MJ ve 0,04–0,08 €/kWh) ile bu sorun çözülmüştür. Artık tüm kalemler euro cinsinden toplanabilmektedir ve bu, raporun ana bulgusunu değiştirmiştir.

**C.3 Nedensellik iddia edilmemektedir.** Takımlar rastgele atanmış rejimlerle çalışmadı; her takım kendi stratejisini seçti. Gözlenen ilişkiler ilişkidir, nedensellik değildir. Örneğin "serin rejim briksi artırır" değil, "serin rejim işleten takımlar daha yüksek briks elde etti" denebilir.

**C.4 Model kurulmadı.** Üretim (23 olay) ve kalite (8 ölçüm) örneklem sayıları tahmin modeli eğitmeye yetmez. Bu bilinçli bir kısıtlamadır; projenin etkin örneklem konusundaki duruşuyla tutarlıdır.

**C.5 Mekanizma — KISMEN ÇÖZÜLDÜ.** Ekonomik olarak baskın olan **elektrik** farkının mekanizması bulundu: lamba süresi (14,7–18,7 saat/gün), yoğunluk değil (herkeste ~%99,9). Bkz. bölüm 4.2.

**Isıtma** farkının mekanizması hâlâ açıktır. Test edilen iki hipotez de desteklenmedi: havalandırma (ρ = +0,43, Digilog örüntüyü bozuyor) ve sıcaklık entegrasyonu (ρ = −0,20). Perde kullanımı, boru sıcaklığı rejimi ve ısıtma zamanlaması 5 dakikalık veride mevcuttur. Ancak ekonomik önceliği düşüktür: ısıtma toplam değişken maliyetin %6–18'idir.
