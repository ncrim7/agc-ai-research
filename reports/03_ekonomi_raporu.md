# Sera İşletmesinin Ekonomisi
### AGC 2. Edisyon — Net Kâr Hesabı, Maliyet Ayrıştırması ve Aydınlatma Ekonomisi

**Tarih:** Ağustos 2026 · **Kapsam:** Resmi fiyat ve formüllerle ekonomik analiz
**İlişki:** *Kısa Vadeli Tahmin*, *Uzun Vadeli Tahmin* ve *Altı Kontrol Stratejisi* raporlarının devamı. Önceki raporlar tahmin doğruluğuna ve kaynak kullanımına baktı; bu rapor **paraya** bakıyor.

> **Bu belge nasıl okunmalı:** Ana gövde bulguları ve gerekçelerini anlatır. Ekler, doğrulama adımlarını, düzeltilen hataları ve sınırlamaları içerir. Her sayının kaynağı belirtilmiştir: **resmi belge**, **deterministik hesap** veya **ölçülmüş ilişki**.

---

# ANA GÖVDE

## 1. Zemin: artık tahmin etmiyoruz, hesaplıyoruz

Önceki raporlarda ekonomik yorumlar dolaylıydı ("Automatoes daha az ısıtma kullandı"). Bu raporda iki resmi belge kullanıldı:

**`Economics.pdf`** — yarışmanın net kâr formülü ve fiyatları:

| Kalem | Değer |
|---|---|
| Isı | 0.0083 €/MJ |
| Elektrik | 0.08 €/kWh (07:00–23:00) · **0.04 €/kWh** dışında |
| CO₂ | 0.08 €/kg ilk 12 kg/m², sonra **0.20 €/kg** |
| İşçilik | 0.0085 €/gövde/m²/gün |
| Bitki | 2.20 €/bitki (2 gövdeli) |
| Gelir | Brix ve tarihe bağlı; **B sınıfı yarım fiyat** |

**`ReadMe.pdf`** — deterministik formüller:

```
Isı akısı = (t_rail − t_air)·2.1 + (t_grow − t_air)·0.62   [W/m²]
Elektrik  = HPS 81 W/m² + LED (mavi 7.27, kırmızı 25.3,
            uzak-kırmızı 6.23, beyaz 22.72 W/m²)
```

Bu formüllerle **5 dakikalık çözünürlükte maliyet serisi** yeniden inşa edildi ve resmi `Resources.csv` değerleriyle karşılaştırıldı:

| Kalem | Yeniden inşa hatası |
|---|---|
| Isıtma | **%0.2** |
| Elektrik | %2.2 |
| CO₂ | %1.2 |

Yani bu raporun maliyet tarafındaki her sayı **hesaptır, tahmin değildir.**

## 2. Net kâr — ve yarışma sonucunun doğrulanması

| Takım | Gelir | Isıtma | **Elektrik** | CO₂ | İşçilik | Bitki | **NET KÂR** |
|---|---|---|---|---|---|---|---|
| **Automatoes** | 36.49 | 1.54 | 17.04 | 0.73 | 5.08 | 3.96 | **8.15** |
| AICU | 34.83 | 2.09 | 16.38 | 0.81 | 5.08 | 3.96 | 6.50 |
| IUACAAS | 32.87 | 2.78 | 15.60 | 0.58 | 5.08 | 3.96 | 4.87 |
| Reference | 35.28 | 3.91 | 16.87 | 0.69 | 5.08 | 3.96 | 4.77 |
| TheAutomators | 36.22 | 3.01 | 18.48 | 1.06 | 5.08 | 3.96 | 4.64 |
| Digilog | 34.42 | 1.44 | 20.57 | 0.77 | 5.08 | 3.96 | **2.60** |

*(€/m², sezon toplamı)*

**Automatoes birinci, ikinciden %25 önde — gerçek yarışma sonucuyla aynı.** Bu, hesabın bağımsız doğrulamasıdır.

### 2.1 Elektrik baskın kalem

| Kalem | Payı |
|---|---|
| **Elektrik** | **%55–65** |
| İşçilik | %18 (sabit) |
| Bitki | %14 (sabit) |
| Isıtma | **%5–12** |
| CO₂ | %2–4 |

> **Önceki raporun düzeltilmesi:** *Altı Kontrol Stratejisi* raporunda "Automatoes en sıcak serayı Reference'ın üçte biri kadar ısıtmayla işletti" bulgusu ana verimlilik göstergesi olarak sunulmuştu. Euro cinsinden bu fark **2.4 €/m²** — toplam maliyetin %8'i. Asıl belirleyici kalem elektriktir.

Digilog bunun canlı kanıtı: en düşük ısıtma (1.44 €), en yüksek elektrik (20.57 €), tek negatif net kâr. En yüksek Brix ve tat skorunu almasına rağmen zarar etmiş.

## 3. Yarışmayı kış işletme maliyeti belirledi

Kış dönemi (13 Ocak – 4 Nisan) maliyeti ile net kâr arasındaki ilişki:

| Takım | Kış maliyeti (cent/m²/6 saat) | Net kâr |
|---|---|---|
| AICU | 3.784 | 6.50 |
| Automatoes | 3.788 | 8.15 |
| IUACAAS | 4.253 | 4.87 |
| Reference | 4.472 | 4.77 |
| TheAutomators | 4.555 | 4.64 |
| Digilog | 4.677 | 2.60 |

**Spearman ρ = −0.94.** Sıralama neredeyse birebir (tek "sapma" AICU/Automatoes ve aralarında 0.004 cent var).

**Nicelik de tutuyor:** 6 saatte 0.89 cent fark × 664 pencere = **5.93 €/m²**. Gerçek net kâr farkı **5.55 €/m²**. Açıklama oranı **%107**.

Yani en iyi ile en kötü arasındaki tüm kâr farkı, kış boyunca 6 saatte 0.89 centlik bir farktan doğuyor.

## 4. Farkın kaynağı: lamba saatleri

Kış maliyet farkının bileşen dökümü (AICU vs Digilog):

| Bileşen | Katkı |
|---|---|
| **Elektrik** | **+%112** |
| Isıtma | −%12 (Digilog daha az ısıtmış) |
| CO₂ | +%0.3 |

Elektrik farkı da ikiye ayrılıyor:

| Kaldıraç | Katkı |
|---|---|
| **Lamba süresi** (14.7 → 18.7 saat/gün) | **+%113** |
| Tarife zamanlaması | −%13 |

**Lamba yoğunluğu herkeste aynı** (~%99.9, ikili aç/kapa). Fark yalnızca **kaç saat** çalıştıkları.

### 4.1 Tarife zamanlaması — kaçırılan ikincil kaldıraç

Elektrik tarifesi 07:00–23:00 arası iki kat pahalı. Takımların pik saatteki elektrik payı:

| Takım | Pik payı | En iyi zamanlamaya geçse kazanç |
|---|---|---|
| **Automatoes** | **%57.6** | — (zaten en iyi) |
| Reference | %58.5 | 0.07 €/m² |
| TheAutomators | %62.0 | 0.34 |
| Digilog | %62.8 | 0.45 |
| IUACAAS | %66.8 | 0.66 |
| **AICU** | **%67.8** | **0.66** |

Altı sera toplamı: **2.18 €/m²** kaçırılmış tasarruf. Ve bu **saf yeniden fiyatlamadır** — aynı kWh, farklı saat. Nedensel iddia gerektirmez.

AICU için 0.66 €/m², net kârının **%10'u** — hiç ışık azaltmadan.

## 5. Aydınlatma kendini amorti etmedi

Altı takım üzerinden regresyon (1000 lamba saati başına):

| İlişki | Etki | R² | Güven aralığı |
|---|---|---|---|
| Lamba → **elektrik maliyeti** | **+6.98 €/m²** | **0.86** | sıfırı içermiyor |
| Lamba → üretim değeri | +3.09 €/m² | 0.36 | **sıfırı içeriyor** |
| Lamba → Brix değeri | +2.23 €/m² | 0.39 | **sıfırı içeriyor** |
| **Net** | **−1.67 €/m²** | | |

**Maliyet tarafı kesin, fayda tarafı bu örneklemle kurulamıyor.**

Nokta tahminleri lambanın zarar ettiğini söylüyor. Doğrudan regresyon (lamba saati → net kâr) −3.67 €/m² veriyor, R² = 0.21.

En az ve en çok lamba kullanan takımların karşılaştırması bunu destekliyor:

| | IUACAAS → Digilog |
|---|---|
| Ek lamba saati | +649 saat/sezon |
| **Ek elektrik maliyeti** | **+5.05 €/m²** |
| Ek üretim değeri | +1.75 €/m² |
| Brix değeri | +1.29 €/m² |
| **Net** | **−2.01 €/m²** |
| *Gerçek net kâr farkı* | *−2.27 €/m²* |

Tahmin ile gerçek arasında %12 fark.

**Başabaş için gereken:** elektriğin %24 ucuzlaması veya domates fiyatının %31 artması.

> **Nedensel iddia yoktur.** Takımlar lamba saatini rastgele seçmedi. Bu, altı gözlem üzerinden bir ilişkidir; "lambayı azaltırsan kârın artar" **denmez**. Denen şey: *"bu örneklemde fazla lamba kullanan takımlar daha az kâr etti ve maliyet farkı kazanç farkını aşıyor."*

---

## 6. Sonuç

**Ana bulgu:** Aynı tesiste, aynı havada, aynı çeşitle çalışan altı takım arasındaki tüm kâr farkı, **kış aylarındaki lamba kullanımından** kaynaklanıyor.

**Karar destek sistemi için üç somut kaldıraç:**

| Kaldıraç | Büyüklük | Tür |
|---|---|---|
| **Lamba süresini azaltmak** | 1000 saat ≈ 1.7–3.7 €/m² | ilişkisel, dikkatli kullanılmalı |
| **Lamba saatlerini pik dışına kaydırmak** | 0.07–0.66 €/m² | **deterministik**, risksiz |
| B sınıfını azaltmak | 0.00–0.84 €/m² | ölçülmüş |

İkincisi özellikle değerli: **hiçbir bitki fizyolojisi varsayımı gerektirmiyor.** Aynı ışık, farklı saat, daha ucuz.

---
---

# EKLER

## Ek A — Düzeltilen üç hata

**A.1 · Net kâr hesabında tip bozulması.** İlk hesap `iterrows()` kullanıyordu; bu, satır bazında tip dönüşümüne yol açıp gelir hesabını bozdu. Digilog'un geliri 29.21 yerine gerçekte **34.42 €/m²** çıktı. Vektörel hesapla düzeltildi. Düzeltme sonrası sıralama gerçek yarışma sonucuyla örtüştü — bu, düzeltmenin doğrulanmasıdır.

**A.2 · CO₂ birimi.** `ReadMe.pdf`, `co2_dos` için "kg/ha hour" diyor. Ampirik doğrulama düzeltme katsayısının **tam 10000** olduğunu gösterdi; gerçek birim kg/m²/saat. Korelasyon 1.000 olduğu için yalnızca ölçek sorunuydu. Bu, resmi dokümantasyondaki bir hatadır.

**A.3 · Yaz saati geçişinde eksik değerler.** 29–30 Mart 2020'de her serada 6 satırda `Tair`, `PipeLow`, `PipeGrow`, `AssimLight` boş. Verinin %0.01'i, ama 72 adımlık pencerelere yayılınca hedefi bozuyordu. Proje standardı uygulandı: çıktıda eksik değer varsa pencere elenir.

> Not: projenin ilk doğrulamasında "yaz saati geçişi kaynaklı atlama yok" bulgusu vardı ve **doğruydu** — zaman ekseninde satır eksikliği yoktu. Eksik olan **değerlerdi**. İki farklı kontrol gerektiren iki farklı sorun.

## Ek B — Maliyet tahmini: negatif sonuç

Maliyet serisi 5 dakikalık çözünürlükte elde edildiğine göre, mevcut tahmin hattımızla 6 saat ileri tahmin edilebilir mi?

**Tasarım:** girdi yalnızca dış hava (dışsal — altı sera aynı havayı yaşadı), hedef sonraki 6 saatin toplam maliyeti. Çıpa olarak "dün aynı saatteki 6 saat" kullanıldı; iklim modellerindeki artık mimarisinin aynısı.

| Model | MAE (cent) | Kış R² |
|---|---|---|
| **Çıpa (seasonal naive)** | **0.370** | **0.809** |
| ARTIK (çıpa + ridge) | 0.604 | 0.786 |
| ARTIK (çıpa + GBM) | 0.637 | 0.773 |
| GBM doğrudan | 1.118 | 0.612 |

**Beş katmanın hepsinde çıpa kazandı.** Hava bilgisi eklemek %63–72 kötüleştirdi.

**Açıklama:** hava günden güne otokorelasyonlu, kontrol politikası kararlı. "Dün aynı saatte ne harcadın" zaten hem havayı hem politikayı kodluyor; ham hava eklemek gürültü ekliyor.

Bu sonuç, hava kâhini deneyiyle **tutarlıdır**: orada da gelecek havayı vermek iklim tahminini iyileştirmemişti. İki bağımsız deney aynı yapısal gerçeği gösteriyor.

**Pratik çıkarım:** maliyet tahmini için makine öğrenmesi gerekmiyor. Değer, tahminde değil **politika karşılaştırmasında** ve **risk tespitinde**.

## Ek C — Değerlendirme dönemi sınırlaması

Sezon maliyetinin bölmelere dağılımı:

| Bölme | Dönem | Sezon maliyetinin payı | Günlük maliyet |
|---|---|---|---|
| Eğitim | 16 Ara – 10 Nis | **%90.2** | 15.16 cent/m² |
| Doğrulama | 10 Nis – 5 May | %8.1 | 6.19 |
| **Test** | **5 – 30 May** | **%1.7** | **1.13** |

**Bu, yalnızca ekonomik analizi değil, projedeki tüm modelleri ilgilendiriyor.** İklim tahmin modelleri ve karar katmanının geriye dönük değerlendirmesi de aynı test bölmesinde yapıldı. Yani tüm modeller, sezon maliyetinin %1.7'sinin oluştuğu dönemde doğrulandı.

Kronolojik bölme metodolojik olarak doğru tercihti (rastgele bölme zaman serisinde sızıntı yaratır). Ancak sonucu budur ve raporlanması gerekir.

**Bu raporda alınan önlem:** ekonomik analizler için **kayan başlangıçlı değerlendirme** kullanıldı — sezon altı bloğa bölünüp her katmanda geçmiş bloklarla eğitilip sonraki blokta test edildi. Zamansal sıralama korundu (sızıntı yok) ve kış test setlerine girdi.

## Ek D — Sınırlamalar

**D.1 · Örneklem altı takım.** Tüm takımlar arası ilişkiler n = 6 üzerindendir. Yön göstergesidir, kanıt değildir. Aydınlatma ekonomisindeki fayda tarafının güven aralıkları sıfırı içermektedir.

**D.2 · Nedensellik iddia edilmemektedir.** Takımlar rastgele atanmış rejimlerle çalışmadı; her takım kendi stratejisini seçti. "Lambayı azaltırsan kârın artar" denemez.

**D.3 · Tarife zamanlaması istisnası.** Bölüm 4.1'deki hesap **saf yeniden fiyatlamadır** — aynı kWh, farklı saatte fiyatlanır. Nedensel varsayım içermez. Ancak bitkinin ışığa ne zaman ihtiyaç duyduğu ayrı bir sorudur ve bu analiz onu cevaplamaz.

**D.4 · İşçilik ve bitki maliyeti sabit alındı.** Gövde yoğunluğu takımlar arası farklılık gösterebilir; `CropParameters` içindeki `stem_dens` kullanılmadı. Bu kalemler toplam maliyetin %32'sini oluşturur ve sabit varsayılmıştır. Farklılık varsa net kâr sıralaması marjinal olarak değişebilir.

**D.5 · Brix ara değerlemesi.** Kalite ölçümleri iki haftada bir yapılmıştır; hasat tarihlerindeki Brix doğrusal ara değerlemeyle bulunmuştur. Gerçek Brix eğrisi doğrusal olmayabilir.

**D.6 · EC → Brix ilişkisi ölçülemedi.** Literatür yüksek EC'nin Brix'i artırdığını söyler. Bizim tasarımımızın tespit edebileceği minimum etki 0.445 Brix/(dS/m); literatürdeki tipik etki ~0.40. Sınırın hemen altında kalıyor. Ayrıca verimizdeki EC aralığı (4.2–7.3 dS/m) literatürün test ettiği aralıktan (2.5–5.0) yüksektir.
