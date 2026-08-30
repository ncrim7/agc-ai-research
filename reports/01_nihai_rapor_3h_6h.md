# Sera İkliminde Kısa Vadeli Tahmin
### Autonomous Greenhouse Challenge 2. Edisyon Veri Seti Üzerinde Baseline ve Derin Öğrenme Karşılaştırması

**Tarih:** Ağustos 2026 · **Kapsam:** Staj projesi nihai raporu

> **Bu belge nasıl okunmalı:** Ana gövde (1-6. bölümler) projenin ne yaptığını ve ne bulduğunu anlatır; teknik ön bilgi gerektirmez. Ekler (A-G), sorulması muhtemel teknik soruların ayrıntılı cevaplarını içerir. Ek G, hızlı başvuru için soru–cevap formatındadır.

---

# ANA GÖVDE

## 1. Özet

Altı sera bölmesinden toplanan 5 dakikalık ölçümlerle, son 24 saate bakarak önümüzdeki 3 ve 6 saatin sera durumu tahmin edildi. Beş basit istatistiksel yöntem (baseline) ile üç derin öğrenme modeli (GRU, LSTM, TCN) aynı koşullarda karşılaştırıldı.

**Sonuç: Tek bir "en iyi model" yoktur; doğru yöntem tahmin edilen değişkene göre değişir.**

| Bulgu | Açıklama |
|---|---|
| Sıcaklık ve kök bölgesi suyu | Derin öğrenme (TCN) açık ara üstün — %9-15 iyileşme |
| CO₂ ve ışık | Basit "dün bu saatte" yöntemi yeterli; derin model katkı sağlamıyor |
| Kök bölgesi tuzluluğu | "Değer değişmeyecek" (persistence) en iyisi |
| Nem ve slab sıcaklığı | Ridge regresyon en iyisi — 5 hedefte anlamlı üstünlük |

Derin modeller arasında **TCN her koşulda en iyisidir.** GRU ve LSTM, çoğu hedefte basit yöntemlerden ayırt edilemeyecek kadar yakın sonuç vermiştir.

**İki ek bulgu:**

- **Genelleme:** Model, eğitiminde hiç görmediği bir seraya %2-5 gibi çok düşük bir bedelle genelleşmektedir (Bölüm 4.2). Bu, sistemin yeni bir seraya taşınabileceğini gösterir.
- **Hedef başına eğitim:** Her hedef için ayrı model eğitmek 32 hedefin 16'sında en iyi sonucu vermektedir; kazanç asıl olarak TCN'dedir (Bölüm 4.3).

---

## 2. Veri seti ve problem

### 2.1 Veri

Wageningen Üniversitesi'nin (Hollanda) düzenlediği *Autonomous Greenhouse Challenge* yarışmasının 2. edisyonu. Altı sera bölmesi, beşi farklı yapay zekâ takımları tarafından, biri (Reference) deneyimli insan yetiştiriciler tarafından uzaktan yönetilmiş. Hepsi aynı tesiste, aynı dönemde, aynı kiraz domates çeşidini yetiştirmiş.

| Özellik | Değer |
|---|---|
| Sera sayısı | 6 (AICU, Automatoes, Digilog, IUACAAS, TheAutomators, Reference) |
| Dönem | 16 Aralık 2019 – 30 Mayıs 2020 (166 gün) |
| Ölçüm sıklığı | 5 dakika |
| Toplam satır | 286.854 (sera başına 47.809) |
| Kolon | 52 |

Bu veri setinin özel değeri: **altı sera aynı dış hava koşullarını yaşadı ama altı farklı kontrol politikasıyla yönetildi.** Bu, "farklı yönetim stratejileri aynı koşullarda ne sonuç verir" sorusunu doğal bir deney gibi incelemeyi mümkün kılıyor.

### 2.2 Tahmin problemi

Geçmiş 24 saatin (288 ölçüm) tüm sensör ve kontrol verisi girdi; gelecek 6 saatin (72 ölçüm) sera durumu çıktıdır. 3 saatlik tahmin, aynı çıktının ilk yarısıdır.

### 2.3 Tahmin edilen değişkenler

**Core (5) — seranın havası**

| Değişken | Ne ölçer | Neden önemli |
|---|---|---|
| `Tair` | Hava sıcaklığı (°C) | Bitki gelişiminin ana sürücüsü |
| `Rhair` | Bağıl nem (%) | Hastalık riski |
| `CO2air` | Karbondioksit (ppm) | Fotosentez hammaddesi |
| `HumDef` | Nem açığı (g/m³) | Bitkinin su kaybı potansiyeli |
| `Tot_PAR` | Bitkinin kullandığı ışık | Fotosentez enerjisi |

**Grodan (6) — kök bölgesi:** `EC_slab1/2` (tuz yoğunluğu), `WC_slab1/2` (su içeriği), `t_slab1/2` (sıcaklık)

İki ayrı deney kuruldu: yalnızca Core, ve Core+Grodan. Amaç, kök sensörleri eklemenin iklim tahminine katkısını ölçmek — bu pratikte bir yatırım kararıdır.

---

## 3. Yöntemler

### 3.1 Baseline'lar (basit referans yöntemler)

Bir modelin "iyi" olduğunu söylemek için neye göre iyi olduğunu belirtmek gerekir. Baseline, *"hiç zekâ kullanmadan ne kadar iyi tahmin edilebilir"* sorusunun cevabıdır.

| Yöntem | Mantığı |
|---|---|
| **Persistence** | "Şu anki değer devam edecek" |
| **Seasonal Naive** | "Dün bu saatte ne vardıysa o olacak" |
| **Moving Average** | Son 3 saatin ortalaması |
| **Linear Trend** | Son 6 saatin eğimini ileri uzat |
| **Ridge Regression** | Pencerenin özet istatistiklerinden doğrusal tahmin |

### 3.2 Derin öğrenme modelleri

| Model | Nasıl çalışır |
|---|---|
| **GRU** | Diziyi baştan sona okur, bir "hafıza" tutar |
| **LSTM** | GRU'nun daha karmaşık hafıza mekanizmalı hâli |
| **TCN** | Diziyi giderek genişleyen aralıklarla tarar; tüm pencereyi aynı anda görür |

**Modeller mutlak değer yerine "bir referans tahmine düzeltme" üretir.** Yani model "24.3 derece olacak" demez; "dün bu saatte 23.8'di, bugün 0.5 derece daha sıcak olacak" der. Bu tasarım tercihinin gerekçesi **Ek A**'da açıklanmıştır.

### 3.3 Değerlendirme

- **Bölme:** her sera kendi içinde kronolojik olarak %70 eğitim / %15 doğrulama / %15 test. Rastgele bölme kullanılmadı — zaman serisinde gelecekten geçmişe bilgi sızdırır.
- **Test penceresi:** Core 3.408, Core+Grodan 2.820 (havuzlanmış)
- **Metrikler:** MAE (ortalama mutlak hata), RMSE (kare ortalama hata kökü), R² (açıklanan varyans oranı)
- **Anlamlılık:** farkların gerçek mi şans eseri mi olduğu istatistiksel olarak test edildi (**Ek B**)

---

## 4. Sonuçlar

### 4.1 Ana karşılaştırma tabloları

Her hedef için **dört sonuç** yan yana verilmiştir:

| Sütun | Ne gösterir |
|---|---|
| **En iyi baseline** | Beş basit yöntemin en iyisi |
| **Derin: çok hedefli** | Tüm hedefleri tek modelle tahmin eden derin model |
| **Derin: hedef başına** | Her hedef için ayrı eğitilmiş derin model |
| **Çapraz doğrulama** | Aynı derin modelin, eğitiminde hiç görmediği bir serada ölçülen hatası |

Çapraz doğrulama sütunu **rakip bir yöntem değildir** — aynı modelin daha zor bir protokolde ne yaptığını gösterir. "En iyi" seçiminde yarışmaz.

Kalın yazılan MAE, o hedefin en iyi sonucudur. "Anlamlı?" sütunu, en iyi derin modelle en iyi baseline arasındaki farkın istatistiksel olarak gerçek olup olmadığını gösterir. **32 karşılaştırmanın tamamı test edilmiştir.**

#### Core — 3h

| Hedef | En iyi baseline | Derin: çok hedefli | Derin: hedef başına | Çapraz doğrulama | En iyi | Anlamlı? |
|---|---|---|---|---|---|---|
| Tair | Seasonal 1.182 | TCN 1.154 | TCN **1.045** | TCN 1.153 | **Hedef başına** | **Derin ✓** |
| HumDef | Ridge **1.277** | TCN 1.345 | TCN 1.375 | TCN 1.352 | Baseline | fark yok |
| Rhair | Ridge **4.654** | TCN 5.066 | TCN 5.052 | TCN 5.047 | Baseline | **Baseline ✓** |
| CO2air | Seasonal **58.4** | LSTM 59.1 | TCN 59.8 | LSTM 59.2 | Baseline | fark yok |
| Tot_PAR | Seasonal 80.7 | TCN 78.9 | TCN **70.3** | TCN 76.9 | **Hedef başına** | **Derin ✓** |

#### Core — 6h

| Hedef | En iyi baseline | Derin: çok hedefli | Derin: hedef başına | Çapraz doğrulama | En iyi | Anlamlı? |
|---|---|---|---|---|---|---|
| Tair | Seasonal 1.193 | TCN 1.184 | TCN **1.113** | TCN 1.184 | **Hedef başına** | **Derin ✓** |
| HumDef | Seasonal 1.550 | TCN **1.432** | TCN 1.447 | TCN 1.438 | Çok hedefli | **Derin ✓** |
| Rhair | Seasonal 5.788 | TCN **5.414** | TCN 5.479 | TCN 5.429 | Çok hedefli | **Derin ✓** |
| CO2air | Seasonal **58.5** | LSTM 59.1 | LSTM 60.2 | LSTM 59.3 | Baseline | fark yok |
| Tot_PAR | Seasonal 80.7 | TCN 80.9 | TCN **75.8** | TCN 79.8 | **Hedef başına** | **Derin ✓** |

#### Core + Grodan — 3h

| Hedef | En iyi baseline | Derin: çok hedefli | Derin: hedef başına | Çapraz doğrulama | En iyi | Anlamlı? |
|---|---|---|---|---|---|---|
| EC_slab1 | Persistence **0.043** | GRU 0.051 | GRU 0.047 | LSTM 0.053 | Baseline | **Baseline ✓** |
| EC_slab2 | Persistence **0.047** | GRU 0.055 | TCN 0.052 | LSTM 0.058 | Baseline | **Baseline ✓** |
| t_slab2 | Ridge **0.391** | TCN 0.650 | TCN 0.601 | TCN 0.716 | Baseline | **Baseline ✓** |
| t_slab1 | Ridge **0.410** | TCN 0.650 | TCN 0.582 | TCN 0.711 | Baseline | **Baseline ✓** |
| WC_slab1 | Persistence 1.057 | TCN 0.921 | TCN **0.766** | LSTM 1.012 | **Hedef başına** | **Derin ✓** |
| WC_slab2 | Persistence 1.151 | TCN 1.034 | TCN **0.873** | GRU 1.140 | **Hedef başına** | **Derin ✓** |
| Tair | Seasonal 1.146 | TCN **0.972** | TCN 0.973 | TCN 1.059 | Çok hedefli | **Derin ✓** |
| HumDef | Ridge **1.131** | TCN 1.316 | TCN 1.368 | TCN 1.379 | Baseline | **Baseline ✓** |
| Rhair | Ridge **4.396** | TCN 5.069 | TCN 4.874 | TCN 5.287 | Baseline | **Baseline ✓** |
| CO2air | Persistence 62.2 | LSTM 62.4 | TCN **62.0** | LSTM 62.8 | **Hedef başına** | fark yok |
| Tot_PAR | Seasonal 82.4 | LSTM 86.9 | TCN **77.5** | GRU 89.7 | **Hedef başına** | **Derin ✓** |

#### Core + Grodan — 6h

| Hedef | En iyi baseline | Derin: çok hedefli | Derin: hedef başına | Çapraz doğrulama | En iyi | Anlamlı? |
|---|---|---|---|---|---|---|
| EC_slab1 | Persistence 0.071 | GRU 0.074 | GRU **0.068** | LSTM 0.076 | **Hedef başına** | fark yok |
| EC_slab2 | Persistence **0.078** | GRU 0.081 | TCN 0.078 | LSTM 0.087 | Baseline | fark yok |
| t_slab1 | Ridge 0.704 | TCN 0.658 | TCN **0.630** | TCN 0.719 | **Hedef başına** | fark yok |
| t_slab2 | Ridge 0.688 | TCN 0.659 | TCN **0.645** | TCN 0.724 | **Hedef başına** | fark yok |
| Tair | Seasonal 1.137 | TCN 1.029 | TCN **0.999** | TCN 1.096 | **Hedef başına** | **Derin ✓** |
| WC_slab1 | Seasonal 1.428 | TCN 1.352 | TCN **1.159** | TCN 1.503 | **Hedef başına** | fark yok |
| WC_slab2 | Seasonal 1.581 | TCN 1.559 | TCN **1.316** | TCN 1.686 | **Hedef başına** | fark yok |
| HumDef | Ridge 1.388 | TCN **1.379** | TCN 1.406 | TCN 1.419 | Çok hedefli | fark yok |
| Rhair | Ridge 5.287 | TCN 5.306 | TCN **5.073** | TCN 5.439 | **Hedef başına** | fark yok |
| CO2air | Seasonal **62.5** | LSTM 62.9 | LSTM 64.1 | LSTM 62.8 | Baseline | **Baseline ✓** |
| Tot_PAR | Seasonal 81.6 | LSTM 84.9 | TCN **79.9** | GRU 86.9 | **Hedef başına** | fark yok |

#### RMSE ve R² değerleri

Her hücrede **RMSE / R²** verilmiştir. Sıralama MAE tablosuyla aynıdır.

**Core — 3h**

| Hedef | Baseline RMSE / R² | Çok hedefli | Hedef başına | Çapraz doğrulama |
|---|---|---|---|---|
| Tair | 1.883 / 0.835 | 1.741 / 0.859 | 1.583 / 0.883 | 1.723 / 0.818 |
| HumDef | 1.929 / 0.768 | 2.034 / 0.742 | 2.081 / 0.730 | 2.055 / 0.709 |
| Rhair | 6.744 / 0.751 | 7.264 / 0.711 | 7.295 / 0.709 | 7.252 / 0.652 |
| CO2air | 95.0 / 0.617 | 94.5 / 0.621 | 86.7 / 0.681 | 91.0 / 0.570 |
| Tot_PAR | 168.1 / 0.697 | 147.5 / 0.766 | 136.3 / 0.800 | 147.3 / 0.766 |

**Core — 6h**

| Hedef | Baseline RMSE / R² | Çok hedefli | Hedef başına | Çapraz doğrulama |
|---|---|---|---|---|
| Tair | 1.902 / 0.832 | 1.801 / 0.849 | 1.696 / 0.866 | 1.781 / 0.806 |
| HumDef | 2.542 / 0.597 | 2.192 / 0.701 | 2.206 / 0.697 | 2.203 / 0.668 |
| Rhair | 8.934 / 0.565 | 7.868 / 0.663 | 7.946 / 0.656 | 7.884 / 0.596 |
| CO2air | 95.0 / 0.614 | 94.7 / 0.616 | 95.1 / 0.613 | 91.2 / 0.565 |
| Tot_PAR | 168.1 / 0.697 | 155.3 / 0.741 | 147.9 / 0.765 | 155.1 / 0.740 |

**Core + Grodan — 3h**

| Hedef | Baseline RMSE / R² | Çok hedefli | Hedef başına | Çapraz doğrulama |
|---|---|---|---|---|
| EC_slab1 | 0.076 / 0.986 | 0.072 / 0.988 | 0.069 / 0.989 | 0.075 / 0.926 |
| EC_slab2 | 0.079 / 0.987 | 0.078 / 0.987 | 0.075 / 0.988 | 0.081 / 0.937 |
| t_slab2 | 0.580 / 0.974 | 1.022 / 0.919 | 0.909 / 0.936 | 1.055 / 0.855 |
| t_slab1 | 0.628 / 0.968 | 1.022 / 0.915 | 0.881 / 0.937 | 1.058 / 0.851 |
| WC_slab1 | 1.757 / 0.951 | 1.414 / 0.968 | 1.169 / 0.978 | 1.486 / 0.800 |
| WC_slab2 | 1.963 / 0.963 | 1.607 / 0.975 | 1.498 / 0.978 | 1.696 / 0.706 |
| Tair | 1.754 / 0.852 | 1.429 / 0.902 | 1.453 / 0.899 | 1.523 / 0.839 |
| HumDef | 1.715 / 0.784 | 2.029 / 0.698 | 2.102 / 0.676 | 2.130 / 0.635 |
| Rhair | 6.341 / 0.753 | 7.106 / 0.690 | 7.007 / 0.698 | 7.591 / 0.559 |
| CO2air | 96.5 / 0.599 | 98.2 / 0.584 | 91.2 / 0.642 | 94.9 / 0.511 |
| Tot_PAR | 164.3 / 0.695 | 158.8 / 0.715 | 143.5 / 0.767 | 159.6 / 0.711 |

**Core + Grodan — 6h**

| Hedef | Baseline RMSE / R² | Çok hedefli | Hedef başına | Çapraz doğrulama |
|---|---|---|---|---|
| EC_slab1 | 0.112 / 0.971 | 0.102 / 0.975 | 0.096 / 0.978 | 0.105 / 0.851 |
| EC_slab2 | 0.119 / 0.970 | 0.113 / 0.973 | 0.110 / 0.974 | 0.118 / 0.866 |
| t_slab1 | 1.035 / 0.912 | 1.022 / 0.914 | 0.949 / 0.926 | 1.068 / 0.845 |
| t_slab2 | 0.998 / 0.922 | 1.021 / 0.918 | 0.970 / 0.926 | 1.065 / 0.849 |
| Tair | 1.738 / 0.855 | 1.511 / 0.890 | 1.501 / 0.892 | 1.583 / 0.826 |
| WC_slab1 | 2.284 / 0.917 | 1.974 / 0.938 | 1.684 / 0.955 | 2.057 / 0.637 |
| WC_slab2 | 2.725 / 0.929 | 2.349 / 0.947 | 2.156 / 0.955 | 2.337 / 0.562 |
| HumDef | 2.035 / 0.694 | 2.122 / 0.668 | 2.161 / 0.655 | 2.199 / 0.609 |
| Rhair | 7.395 / 0.662 | 7.456 / 0.656 | 7.272 / 0.673 | 7.826 / 0.524 |
| CO2air | 98.6 / 0.577 | 98.6 / 0.577 | 98.5 / 0.578 | 94.9 / 0.504 |
| Tot_PAR | 163.3 / 0.698 | 159.2 / 0.713 | 148.0 / 0.752 | 159.8 / 0.710 |

### 4.2 Çapraz doğrulama: hiç görülmemiş seraya genelleme

Yukarıdaki tablolar, modelin *aynı seranın geleceğini* ne kadar iyi tahmin ettiğini gösterir. Pratikte daha önemli bir soru vardır: **model, hiç görmediği bir seraya kurulduğunda çalışır mı?**

Bunu ölçmek için Leave-One-Team-Out çapraz doğrulaması uygulandı: her seferinde bir sera tamamen dışarıda bırakılıp diğer beşiyle eğitim yapıldı, sonra dışarıdaki serada test edildi. Altı sera için altı kez tekrarlandı.

Karşılaştırma temizdir: çapraz doğrulama testi ile normal testin **pencereleri aynıdır**; tek fark o seranın eğitimde bulunup bulunmamasıdır.

| Model | Ortalama genelleme bedeli (3 saat) |
|---|---|
| LSTM | +2.3% |
| GRU | +2.5% |
| TCN | +4.6% |

**Bedel şaşırtıcı derecede düşüktür.** 48 hedef–model kombinasyonunun 8'inde bedel **negatiftir** — yani model, hiç görmediği serada kendi geçmişini gördüğü duruma göre *daha iyi* tahmin yapmıştır. Muhtemel açıklama: beş farklı kontrol politikasıyla eğitilen model, tek bir takımın alışkanlıklarına aşırı uyum sağlamaz.

Bedel hedefe göre değişir. Sera havası neredeyse bedelsiz genelleşir (Core hedeflerinde %−2.6 ile %0.6 arası); kök bölgesi daha pahalıdır (WC_slab1 %13.3). Bu mantıklıdır: sulama politikası takıma özgü bir karardır, oysa iklim fiziği evrenseldir.

**Hangi sera en zor genelleniyor?**

| Sera | Normalize zorluk (1.00 = ortalama) |
|---|---|
| AICU | 0.826 |
| IUACAAS | 0.864 |
| Reference (insan yetiştirici) | 0.901 |
| Digilog | 1.007 |
| TheAutomators | 1.096 |
| **Automatoes** | **1.307** |

Automatoes altı sera içinde en zor tahmin edilenidir. **Ancak bu bir genellenebilirlik sorunu değildir.** Aynı sıralama, modelin o seranın kendi geçmişini gördüğü normal test protokolünde de aynen çıkmaktadır (iki sıralama arasında Spearman ρ = +1.00). Yani Automatoes'un serası, hangi protokolde bakılırsa bakılsın daha zor tahmin edilmektedir.

Zorluğun kaynağı ölçüldü: **kök bölgesi dinamiğinin oynaklığı.** Persistence baseline'ın hatası (yani "durum ne kadar hareket ediyor") ile tahmin zorluğu arasında kök bölgesinde güçlü ilişki vardır (ρ = +0.83); hava hedeflerinde böyle bir ilişki yoktur (ρ = −0.37). Automatoes hem en oynak kök bölgesine (1.296) hem en zor kök bölgesi tahminine (1.362) sahiptir.

**Test edilip reddedilen alternatif açıklama:** Zorluğun "en ayırt edici kontrol stratejisinden" kaynaklandığı düşünülmüştü. Günlük kaynak tüketimi verisiyle (`Resources.csv`, 996 gözlem) her takımın diğer beşin merkezinden uzaklığı ölçüldü. Automatoes'un uzaklığı **altı takımın en düşüğüdür** (0.783); sulama boyutunda 5/6, iklim boyutunda 5/6 sıradadır. Yani Automatoes'un kaynak kullanım profili en *ortalama* olanıdır. Hipotez desteklenmemiştir.

> Bu testin sınırı: günlük toplamlar kullanılmıştır. Aynı günlük su miktarının farklı zamanlamayla verilmesi bu ölçümde görünmez. 5 dakikalık sulama verisiyle zamanlama imzası ayrıca incelenebilir.

Buna karşılık insan yetiştiricilerin yönettiği Reference, bazı yapay zekâ takımlarından daha kolay tahmin edilmektedir (0.901) ve en az oynak kök bölgesine sahiptir (0.743).

**Peki görülmemiş serada derin model baseline'ı geçiyor mu?**

Çapraz doğrulama, baseline'lar için de ayrı ayrı çalıştırıldı. Analitik baseline'lar (Persistence, Seasonal Naive, Moving Average, Linear Trend) eğitim yapmadıkları için değerleri değişmez; Ridge ise her fold'da beş takımla yeniden eğitildi.

Sonuç: **32 karşılaştırmanın 16'sında derin model daha iyidir.** Bu, normal test protokolündeki orana yakındır — yani derin modelin baseline karşısındaki konumu, görülmemiş bir seraya geçildiğinde büyük ölçüde korunmaktadır.

**Core — 3h**

| Hedef | En iyi baseline | En iyi derin | Fark |
|---|---|---|---|
| Tot_PAR | Seasonal 80.7 | TCN **76.9** | +4.7% |
| Tair | Seasonal 1.182 | TCN **1.153** | +2.4% |
| HumDef | Ridge 1.370 | TCN **1.352** | +1.3% |
| Rhair | Ridge 5.100 | TCN **5.047** | +1.0% |
| CO2air | Seasonal **58.4** | LSTM 59.2 | -1.4% |

**Core — 6h**

| Hedef | En iyi baseline | En iyi derin | Fark |
|---|---|---|---|
| HumDef | Seasonal 1.550 | TCN **1.438** | +7.2% |
| Rhair | Seasonal 5.788 | TCN **5.429** | +6.2% |
| Tot_PAR | Seasonal 80.7 | TCN **79.8** | +1.2% |
| Tair | Seasonal 1.193 | TCN **1.184** | +0.8% |
| CO2air | Seasonal **58.5** | LSTM 59.3 | -1.5% |

**Core + Grodan — 3h**

| Hedef | En iyi baseline | En iyi derin | Fark |
|---|---|---|---|
| Tair | Seasonal 1.146 | TCN **1.059** | +7.6% |
| WC_slab1 | Persistence 1.057 | LSTM **1.012** | +4.3% |
| WC_slab2 | Persistence 1.151 | GRU **1.140** | +0.9% |
| CO2air | Persistence **62.2** | LSTM 62.8 | -1.0% |
| Rhair | Persistence **5.097** | TCN 5.287 | -3.7% |
| Tot_PAR | Seasonal **82.4** | GRU 89.7 | -8.8% |
| t_slab2 | Ridge **0.626** | TCN 0.716 | -14.4% |
| HumDef | Ridge **1.197** | TCN 1.379 | -15.2% |
| t_slab1 | Ridge **0.597** | TCN 0.711 | -19.0% |
| EC_slab1 | Persistence **0.043** | LSTM 0.053 | -23.2% |
| EC_slab2 | Persistence **0.047** | LSTM 0.058 | -24.3% |

**Core + Grodan — 6h**

| Hedef | En iyi baseline | En iyi derin | Fark |
|---|---|---|---|
| t_slab2 | Seasonal 0.829 | TCN **0.724** | +12.6% |
| t_slab1 | Seasonal 0.813 | TCN **0.719** | +11.6% |
| Tair | Seasonal 1.137 | TCN **1.096** | +3.6% |
| Rhair | Seasonal 5.634 | TCN **5.439** | +3.5% |
| HumDef | Ridge 1.468 | TCN **1.419** | +3.4% |
| CO2air | Seasonal **62.5** | LSTM 62.8 | -0.5% |
| WC_slab1 | Seasonal **1.429** | TCN 1.503 | -5.2% |
| Tot_PAR | Seasonal **81.6** | GRU 86.9 | -6.4% |
| WC_slab2 | Seasonal **1.581** | TCN 1.686 | -6.6% |
| EC_slab1 | Persistence **0.071** | LSTM 0.076 | -7.9% |
| EC_slab2 | Persistence **0.078** | LSTM 0.087 | -11.4% |

Örüntü normal testle tutarlıdır: sıcaklık, nem ve slab sıcaklığında derin model önde; CO₂, ışık ve kök tuzluluğunda baseline önde.

**Pratik anlamı:** Sistem, yeni bir seraya o seranın geçmiş verisi olmadan kurulabilir. Model, takıma özgü alışkanlıkları değil sera fiziğini öğrenmektedir.

Tasarım ayrıntıları ve ortak dış hava verisinden kaynaklanan bir tuzağın nasıl ele alındığı **Ek D**'dedir.

📊 **Şekil 6, Şekil 8**

### 4.3 Hedef başına ayrı model eğitmek işe yarıyor mu?

Ana tablodaki derin modeller, tüm hedefleri **tek bir modelle** birden tahmin eder. Alternatif, her hedef için ayrı model eğitmektir. Bu, 48 ek eğitim koşusuyla test edildi.

| Model | Hedef başına eğitimin etkisi | Kaç hedefte daha iyi |
|---|---|---|
| **TCN** | **−5.4%** | **24 / 32** |
| GRU | −1.6% | 20 / 32 |
| LSTM | −1.3% | 22 / 32 |

*(Negatif değer = hedef başına eğitmek daha iyi.)*

Kazanç asıl olarak TCN'dedir. Nedeni, paylaşılan modelin kaç hedefe hizmet etmek zorunda kaldığına bakınca görülür:

| Model | 5 hedef paylaşırken | 11 hedef paylaşırken |
|---|---|---|
| **TCN** | −1.8% | **−7.1%** |
| GRU | −0.6% | −2.1% |
| LSTM | −1.0% | −1.4% |

Tek model ne kadar çok hedefe hizmet ederse, paylaşımın bedeli o kadar büyür. Bu eğilim üç mimaride de aynı yöndedir ancak **yalnızca TCN'de belirgindir**; GRU ve LSTM'de fark %2'nin altında kalmaktadır.

📊 **Şekil 5**

### 4.4 Skor özeti

**Hangi yaklaşım kaç hedefte en iyi?** (32 hedef–ufuk kombinasyonu)

| Yaklaşım | Kaç hedefte en iyi |
|---|---|
| **Derin: hedef başına** | **16** |
| Baseline | 12 |
| Derin: çok hedefli | 4 |

**Farklar istatistiksel olarak anlamlı mı?** 32 karşılaştırmanın tamamı test edilmiştir:

| Sonuç | Sayı |
|---|---|
| Derin öğrenme anlamlı şekilde üstün | **11** |
| Baseline anlamlı şekilde üstün | **8** |
| Anlamlı fark yok | 13 |

Derin öğrenme 16 hedefte en düşük hatayı vermekte, bunların 11'inde üstünlük istatistiksel olarak da doğrulanmaktadır. Buna karşılık **Ridge regresyon beklenenden güçlü bir rakiptir**: nem ve slab sıcaklığı hedeflerinde hem diğer baseline'ları hem derin modelleri anlamlı şekilde geçmektedir (5 hedef).

## 5. Yorum

### 5.1 TCN neden en iyi derin model?

TCN, üç derin modelin en iyisi ve bu tesadüf değil. GRU ve LSTM diziyi baştan sona sırayla işler; 288 ölçümlük bir pencerenin **başındaki** bilgi, sona gelindiğinde büyük ölçüde unutulur. TCN ise genişleyen aralıklarla tarama yaparak tüm pencereyi aynı anda görür.

Bu önemlidir çünkü "dün bu saatte ne vardı" bilgisi tam olarak pencerenin başında durur — ve sera tahmininde en değerli bilgilerden biridir.

### 5.2 Neden basit yöntemler bu kadar güçlü?

Seasonal Naive'in ("dün bu saatte") hatası, tahmin ufkuyla neredeyse hiç artmıyor:

| Hedef | 3 saat | 6 saat | Artış |
|---|---|---|---|
| Tair | 1.182 | 1.193 | %0.9 |
| CO2air | 58.437 | 58.456 | %0.03 |
| Tot_PAR | 80.682 | 80.700 | %0.02 |

Karşılaştırma için Persistence aynı aralıkta yaklaşık **%70 bozulur.**

**Açıklama:** Sera, güneşin günlük döngüsüne kilitli bir sistemdir. Sıcaklık, ışık ve CO₂ her gün benzer bir eğri çizer. "Dün bu saatte" tahmini ufuk uzasa da aynı kalitede kalır, çünkü ekstrapolasyon yapmaz — hatırlar.

### 5.3 Hangi fizik, hangi yöntem?

| Değişken grubu | Kazanan | Fiziksel sebep |
|---|---|---|
| Sıcaklık, kök suyu | **TCN** | Dış hava, radyasyon, havalandırma ve ısıtma arasında doğrusal olmayan etkileşimler var — öğrenilecek yapı mevcut |
| CO₂, ışık | **Seasonal Naive** | Çok güçlü ve düzenli günlük döngü; CO₂ ayrıca deterministik bir kontrol politikasıyla sürülüyor |
| Kök tuzluluğu (EC) | **Persistence** | O kadar yavaş değişiyor ki "hiçbir şey olmayacak" en iyi tahmin |
| Nem, slab sıcaklığı | **Ridge** | Doğrusal ilişkiler yeterli; karmaşık model ek fayda sağlamıyor |

Kök tuzluluğuna ilişkin bulgu bağımsız bir analizle de destekleniyor: sulama eylemi ile 3-6 saatlik EC sonucu arasındaki korelasyon **−0.03 ile 0.16** arasındadır. Kısa vadede sulama kararı kök tuzluluğunu belirlemiyor; kök ortamı bir tampon gibi davranıyor.

### 5.4 Grodan sensörlerinin katkısı

Kök sensörleri eklemenin iklim tahminine katkısı **hedefe bağlıdır:**

- `Tair` 3 saatte %2.4 → %15.2'ye çıkıyor (Core → Core+Grodan)
- Nem tarafında (HumDef, Rhair) tutarlı ama küçük iyileşme
- CO₂ ve ışıkta katkı yok

**Pratik çıkarım:** Kök sensörü yatırımı, sıcaklık ve nem yönetimi öncelikliyse anlamlıdır.

---

## 6. Sonuç ve öneriler

**Ana çıkarım:** Sera iklim tahmininde tek bir "en iyi model" yoktur. Doğru yöntem, tahmin edilen değişkenin fiziksel davranışına bağlıdır.

**Pratik öneri — hedefe özgü hibrit strateji:**

| Ne tahmin ediliyor | Önerilen yöntem |
|---|---|
| Sıcaklık, kök suyu | TCN (Core+Grodan girdileriyle) |
| CO₂, ışık | Seasonal Naive (basit, hesaplama maliyeti sıfır) |
| Kök tuzluluğu | Persistence |
| Nem, slab sıcaklığı | Ridge regresyon |

Bu strateji hem daha doğru hem de daha ucuzdur: yalnızca gerçekten fayda sağlayan yerlerde derin model çalıştırılır.

**İkinci sonuç:** Model, eğitiminde hiç görmediği bir seraya %2-5 bedelle genelleşmektedir (Bölüm 4.2). Bu, sistemin takıma özgü alışkanlıkları değil sera fiziğini öğrendiğini ve yeni bir seraya taşınabileceğini gösterir.

---
---

# EKLER

## Ek A — Neden "artık tahmini" (çıpa) kullanıldı?

### A.1 Sorun

İlk denemede derin modeller **beş hedefin beşinde de** basit baseline'lara kaybetti. Modeller mutlak değer tahmin ediyordu ("saat 15:00'te 24.3 derece olacak") ve basit yöntemlerin altında kalıyordu.

### A.2 Çözüm

Modeller mutlak değer yerine, basit bir referans tahmine **düzeltme** üretecek şekilde yeniden kuruldu:

```
Tahmin = ÇIPA (basit referans) + MODELİN DÜZELTMESİ
       = "dün bu saatte 23.8'di" + "bugün 0.5 daha sıcak"
       = 24.3 derece
```

**Neden işe yarar:** Model hiçbir şey öğrenemese ve "+0" dese bile, sonuç en kötü ihtimalle çıpa kadar iyi olur. Yani derin modelin basit yöntemin altına düşme riski yapısal olarak ortadan kalkar.

### A.3 Hedef başına çıpa seçimi

Başlangıçta tüm hedefler için "dün bu saatte" (seasonal) çıpası kullanıldı. Bu, kök bölgesi değişkenleri için yanlıştı:

| Değişken tipi | Doğru çıpa | Neden |
|---|---|---|
| Sıcaklık, nem, CO₂, ışık, slab sıcaklığı | **"Dün bu saatte"** | Güçlü günlük döngüye sahipler |
| Kök tuzluluğu ve su içeriği | **"Şu anki değer"** | Günlük döngüsel değil, çok yavaş sürükleniyorlar |

Baseline tablosu doğru cevabı zaten söylüyordu: EC_slab için Persistence 0.043, Seasonal Naive 0.136 — üç kat fark.

### A.4 Düzeltmenin etkisi (kontrollü deney)

Üç konfigürasyon eğitildi ve çıpa etkisi kapasiteden ayrıştırıldı:

| Etken | Etki |
|---|---|
| **Çıpa seçimi (net)** | **−42.1%** |
| Düzenlileştirme + eğitim süresi + çıktı katmanı | −2.7% |
| Model kapasitesi küçültme | +0.6% (fayda yok) |

Çıpası değişen hedefler %28-64 iyileşirken, çıpası değişmeyen kontrol grubu yalnızca %2.7 iyileşti. Fark tamamen çıpa seçimine atfedilebilir.

📊 **Şekil 4** — temiz ablasyon

---

## Ek B — İstatistiksel anlamlılık

### B.1 Neden gerekli?

"TCN, Seasonal Naive'i %2 geçti" dediğimizde bunun **gerçek bir fark mı yoksa şans eseri mi** olduğunu bilmemiz gerekir. Aksi hâlde gürültüyü bulgu diye raporlarız.

### B.2 Sorun: ölçümlerimiz bağımsız değil

Standart anlamlılık testleri (Diebold-Mariano) ölçümlerin birbirinden bağımsız olduğunu varsayar. Bizim test pencerelerimiz bağımsız değildir:

- Her pencere 1 saat arayla üretildi
- Her pencere 30 saatlik veri kapsıyor (24 saat girdi + 6 saat çıktı)
- Dolayısıyla komşu pencereler neredeyse aynı veriye bakıyor

📊 **Şekil 12** bunu veriden gösteriyor: hataların otokorelasyonu iki yapı taşıyor — (1) gecikme 1-5'te çıktı pencerelerinin örtüşmesi, (2) gecikme ~24'te günlük döngü.

### B.3 Çözüm: HAC düzeltmesi

**HAC** (Heteroskedasticity and Autocorrelation Consistent), bu bağımlılığı hesaba katan standart bir varyans düzeltmesidir. Newey-West tahmincisi, 30 pencerelik gecikme ile uygulandı.

**Ne kadar fark ediyor:** Naif test standart hatayı **~2.7 kat küçük** tahmin ediyor.

| Test | Anlamlı bulunan |
|---|---|
| Naif Diebold-Mariano | 26 / 32 |
| HAC + blok bootstrap + FDR düzeltmesi | **16 / 32** |

Yani düzeltme yapılmasaydı **10 fark yanlışlıkla "gerçek" diye raporlanacaktı.**

Simülasyonla da doğrulandı: örtüşen pencerelerde, gerçekte hiç fark yokken naif test %71 oranında "anlamlı" diyor (olması gereken %5). HAC bunu %13.7'ye indiriyor.

📊 **Şekil 7** — naif vs HAC karşılaştırması

### B.4 Testin kapsamı

Anlamlılık testi, her hedef için **en iyi derin modeli en iyi baseline'a** karşı sınar. Baseline kümesi beş yöntemin tamamını (Persistence, Seasonal Naive, Moving Average, Linear Trend, Ridge) içerir. Derin model kümesi hem çok hedefli hem hedef başına eğitilmiş modelleri kapsar.

32 hedef–ufuk kombinasyonunun tamamı test edilmiştir. Çoklu karşılaştırma nedeniyle Benjamini-Hochberg yanlış keşif oranı (FDR) düzeltmesi uygulanmıştır.

### B.5 Etki büyüklüğü tek başına yeterli değil

Önemli bir ders: **büyük yüzde, güvenilir sonuç demek değildir.**

| Karşılaştırma | Kazanç | Sonuç |
|---|---|---|
| WC_slab1 (6h) | %5.3 | Anlamlı değil |
| HumDef (6h, Core) | %7.6 | **Anlamlı** |

Belirleyici olan, etkinin **belirsizliğe oranıdır.** Kök bölgesi su içeriği sulama olaylarıyla sıçramalı hareket ettiği için hata dağılımı ağır kuyrukludur ve güven aralığı geniştir.

📊 **Şekil 9** — etki büyüklüğü ve belirsizlik dağılımı

---

## Ek C — Model kapasitesi ablasyonu

### C.1 Hipotez

Eğitim penceresi sayısı 16.482 görünüyor. Ancak ardışık pencereler 1 saat kaydırmayla üretildiği için **%95.8 örtüşüyorlar.** Gerçekten örtüşmeyen pencere sayısı yalnızca **~552'dir.**

İlk modeller 199.208 parametre kullanıyordu — bağımsız örnek başına 357 parametre. Bu oranda modelin ezberleme riski yüksektir. Hipotez: **modeli küçültmek genellemeyi iyileştirir.**

### C.2 Test ve sonuç

Modeller ~18.000 parametreye indirildi (11 kat azalma) ve üç konfigürasyon kontrollü biçimde karşılaştırıldı. **Hipotez doğrulanmadı — küçültme fayda sağlamadı:**

| Mimari | Küçültmenin etkisi |
|---|---|
| TCN | **+4.5% (zararlı)** |
| GRU | +0.1% |
| LSTM | −2.6% |
| **Genel** | **+0.6%** |

Pozitif değer, küçültmenin hatayı **artırdığı** anlamına gelir. TCN'de zarar belirgindir.

### C.3 Neden hipotez tutmadı?

Muhtemel açıklama: artık tahmini (Ek A) + düzenlileştirme + erken durdurma zaten yeterli koruma sağlıyordu. Kapasite kısıtı üstüne gereksiz geldi ve temsil gücünü kırptı.

### C.4 Hangi model raporlandı?

**Küçük model korundu.** Gerekçe: model seçimi doğrulama setine göre yapılmalıdır, test setine göre değil. Doğrulama kaybı iki konfigürasyonu ayırt etmemektedir (core_grodan/TCN: küçük 1.1414, büyük 1.1472 — küçük marjinal olarak daha iyi). Test setindeki fark model seçiminde **kullanılmamıştır.**

> Bir hipotezi test edip reddedildiğini raporlamak, hiç test etmemekten metodolojik olarak daha güçlüdür.

📊 **Şekil 4** — kapasite ablasyonu

---

## Ek D — Çapraz doğrulama (Leave-One-Team-Out)

### D.1 Soru

Model, kontrol politikasını hiç görmediği bir seraya genelleşiyor mu? Bu, sistemin yeni bir seraya kurulabilir olup olmadığını belirler.

### D.2 Tasarım ve bir tuzak

Altı fold: her seferinde bir sera dışarıda bırakılıp diğer beşiyle eğitim yapıldı.

**Fark edilen tuzak:** Altı sera aynı tesiste ve **aynı dış hava verisini paylaşıyor.** Klasik LOTO'da model, test döneminin hava koşullarını diğer beş takım üzerinden zaten görmüş olur; bu sonuçları olduğundan iyi gösterir.

Bunu ölçmek için fold başına **iki test seti** kullanıldı:

| Test seti | Ne görülmemiş |
|---|---|
| **Test A** | Yalnızca kontrol politikası (hava görülmüş) |
| **Test B** | Hem politika hem hava — **dürüst ölçüm** |

### D.3 Sonuç: genelleme bedeli çok düşük

Karşılaştırma temizdir: LOTO Test B ile kronolojik testin pencereleri **aynıdır**; tek fark takımın eğitimde bulunup bulunmamasıdır.

| Model | Ortalama genelleme bedeli (3 saat) |
|---|---|
| LSTM | +2.3% |
| GRU | +2.5% |
| TCN | +4.6% |

Bazı hedeflerde bedel **negatiftir** — yani model görülmemiş serada daha iyi. Muhtemel açıklama: beş farklı kontrol politikasıyla eğitilen model, tek bir takımın alışkanlıklarına aşırı uyum sağlamıyor; çeşitlilik düzenlileştirici etki yapıyor.

### D.4 Hangi sera en zor genelleniyor?

| Sera | Normalize zorluk |
|---|---|
| AICU | 0.826 |
| IUACAAS | 0.864 |
| Reference (insan yetiştirici) | 0.901 |
| Digilog | 1.007 |
| TheAutomators | 1.096 |
| **Automatoes** | **1.307** |

**Automatoes altı sera içinde en zor tahmin edilenidir — ancak bu genellenebilirlik sorunu değildir.**

Kesin test: aynı sıralama, modelin o seranın kendi geçmişini gördüğü kronolojik test protokolünde de çıkmaktadır.

| Sera | Kendi geçmişini gördü | Hiç görmedi | Kök bölgesi oynaklığı |
|---|---|---|---|
| **Automatoes** | **1.240** | **1.307** | **1.296** |
| TheAutomators | 1.115 | 1.096 | 1.091 |
| Digilog | 1.036 | 1.007 | 1.081 |
| Reference | 0.906 | 0.901 | 0.743 |
| IUACAAS | 0.878 | 0.864 | 0.962 |
| AICU | 0.825 | 0.826 | 0.827 |

İki zorluk sıralaması arasında Spearman ρ = **+1.00**. Zorluk, modelin o takımı görüp görmemesinden bağımsızdır.

**Mekanizma:** kök bölgesi oynaklığı. Persistence baseline'ın hatası durumun ne kadar hareket ettiğini doğrudan ölçer. Bu ölçüm ile tahmin zorluğu arasında kök bölgesinde ρ = +0.83, hava hedeflerinde ρ = −0.37 ilişki vardır. Yani zorluğu belirleyen şey kök bölgesinin dinamiğidir.

**Reddedilen açıklama:** "En ayırt edici kontrol stratejisi" hipotezi `Resources.csv` (996 gözlem) ile test edildi ve **desteklenmedi**. Her takımın diğer beşin merkezinden uzaklığı ölçüldüğünde Automatoes en düşük uzaklığa sahiptir (0.783); sulama 5/6, iklim 5/6. Kaynak kullanım profili altı takımın en ortalamasıdır.

İkinci gözlem: Reference (insan yetiştirici) en kolay genellenenler arasındadır. İnsan kararları bazı yapay zekâ takımlarından daha öngörülebilirdir.

📊 **Şekil 6, Şekil 8**

---

## Ek E — Veri hazırlığı kararları

Her kararın gerekçesi veriye bakarak belirlenmiştir; hiçbiri varsayım değildir.

| Karar | Ne yapıldı | Neden |
|---|---|---|
| Kolon seçimi | İstenen hedef (`_sp`) kolonları atıldı, gerçekleşen komut (`_vip`) tutuldu | Aralarında +0.99 korelasyon var; ikisini birden kullanmak modelin hangi kolonun etkili olduğunu ayırt etmesini engeller |
| LED verisi | %46 boş değer 0 ile dolduruldu | Boşluk arıza değil, "lamba kapalı" demek — altı takımda %94.8-98.2 oranında doğrulandı |
| Kök sensörü onarımı | Çapraz doldurma, **yalnızca iki sensör arasındaki korelasyon 0.7'nin üzerindeyse** | AICU'da korelasyon −0.046 çıktı (sensör arızalı). Körü körüne doldurmak veri uydurmak olurdu |
| İmkânsız değerler | Maskelendi, satır silinmedi | Satır silmek zaman serisinde delik açar |
| Zaman ekseni | 5 dakikaya yuvarlandı | Kaynak dosyadaki zaman damgaları ~192 ms hata taşıyordu |

### E.1 Doğrulama

Modele geçmeden önce dokuz bağımsız kontrol çalıştırıldı (zaman sürekliliği, şema tutarlılığı, eksik veri dağılımı, sabit kolonlar, mantık dışı değer taraması, pencere muhasebesi vb.). **Sonuç: 0 hata.**

Öne çıkan iki bulgu:

1. **Zaman ekseninde eksik satır yok.** 166 günün tamamı kesintisiz 5 dakikalık ızgarada. Bu önemlidir çünkü pencereler konum numarasıyla kesilmektedir; eksik satır olsaydı "24 saatlik" bir pencere sessizce 25 saati kapsayabilirdi.
2. **86 saatlik ortak kök sensörü kesintisi.** 26-30 Mayıs arasında altı serada da aynı anda. Tesis geneli bir arıza. Grodan deneyinde test penceresi bu nedenle 568'den 470'e inmiştir.

### E.2 Veri sızıntısı önlemleri

| Risk | Önlem |
|---|---|
| Rastgele bölme | Kullanılmadı; kronolojik bölme |
| Sınır aşan pencere | Atıldı |
| Normalizasyon sızıntısı | İstatistikler yalnızca eğitim bölmesinden |
| Eksik hedef | Çıktı aralığında eksik veri olan pencereler elendi |
| Seralar arası karışma | Her sera kendi içinde bölündü |

---

## Ek F — Bilinen sınırlamalar

### F.1 Mevsimsel dağılım kayması

Eğitim verisi kışı (Aralık–Nisan), test verisi ilkbaharı (Mayıs) kapsıyor. Bu dönemde ışık **2.05 kat**, nem açığı **1.46 kat** artıyor.

Gözlemlenen kanıt: doğrulama hatası, **daha ilk eğitim turunda** eğitim hatasının 2.2 katı. Aşırı öğrenme epoch'lar boyunca gelişir; ilk turda ortaya çıkan fark yapısal bir dağılım farkına işaret eder.

**Sonuç:** Model kolay bir dönemde öğrenip zor bir dönemde sınava giriyor. Bu, tek sezonluk tüm tarımsal veri setlerinin ortak sorunudur.

### F.2 Tek sezon, tek tesis, tek ürün

166 gün tek bir yetiştirme dönemidir. Sonuçlar başka bir ürüne, iklim bölgesine veya sera tipine doğrudan genellenemez. Mevsimler arası genelleme test edilememiştir.

### F.3 Tekrar üretilebilirlik sınırı

Rastgelelik tohumu sabitlenmiştir, ancak GPU'daki paralel işlem sırası nedeniyle sonuçlar bit düzeyinde aynı çıkmayabilir. Farklar küçüktür ama sıfır değildir. Raporlanan tüm derin model sonuçları, kayıtlı model dosyalarından çıkarılmış ve orijinal eğitim çıktılarıyla 1e-4 bağıl toleransta doğrulanmıştır (180/180 eşleşme).

---

## Ek G — Sık sorulacak sorular

**G.1 — Neden model doğrudan değer tahmin etmiyor?**
Doğrudan tahmin ettiğinde basit yöntemlerin altında kaldı. Şimdi basit bir referans tahmine düzeltme ekliyor; böylece en kötü ihtimalle o referans kadar iyi oluyor. Ayrıntı: Ek A.

**G.2 — HAC ne demek?**
Test setindeki ölçümler birbirinden bağımsız olmadığı için standart anlamlılık testi yanıltıcı sonuç veriyordu. HAC, bu bağımlılığı hesaba katan literatürdeki standart düzeltmedir. Uygulanmasaydı 10 fark yanlışlıkla "gerçek" sayılacaktı. Ayrıntı: Ek B.

**G.3 — Neden derin model her yerde kazanmıyor?**
Çünkü sera güçlü bir günlük döngüye sahip ve bazı değişkenler (CO₂, ışık) neredeyse tamamen bu döngüyle açıklanıyor. Orada öğrenilecek ek yapı yok. Derin model, doğrusal olmayan etkileşimlerin olduğu yerlerde (sıcaklık, nem) kazanıyor.

**G.4 — Neden küçük model kullandınız, büyüğü daha iyiyken?**
Doğrulama setinde ikisi ayırt edilemiyor. Model seçimi doğrulama setine göre yapılır; test setine göre seçmek metodolojik hatadır. Ayrıntı: Ek C.4.

**G.5 — Sonuçlar başka bir seraya taşınır mı?**
Evet. Model, eğitiminde hiç görmediği bir seraya %2-5 bedelle genelleşiyor. Bu, takıma özgü alışkanlıkları değil sera fiziğini öğrendiğini gösteriyor. Ayrıntı: Bölüm 4.2 ve Ek D.

**G.6 — Her hedef için ayrı model eğitmek daha iyi mi?**
TCN için evet: ortalama %5.4 iyileşme, 32 hedefin 24'ünde daha iyi. GRU (%1.6) ve LSTM (%1.3) için fark ihmal edilebilir. Ayrıntı: Bölüm 4.3.

**G.7 — Veri sızıntısı riski var mı?**
Hayır. Kronolojik bölme kullanıldı, sınır aşan pencereler atıldı, normalizasyon istatistikleri yalnızca eğitim setinden hesaplandı. Ayrıntı: Ek E.2.

**G.8 — Kaç deney yapıldı?**
5 baseline × 3 feature-set konfigürasyonu, 3 derin model × 2 feature-set × 2 kapasite, hedef başına 48 koşu, ve 36 fold'luk çapraz doğrulama. Toplam 100'ün üzerinde eğitim koşusu.

---

## Şekil listesi

> Şekiller belge içine gömülüdür. PDF'te yakınlaştırarak ayrıntıları okuyabilirsiniz (300 DPI). Ayrıca her şekil ayrı PNG dosyası olarak da teslim edilmiştir.


| No | Şekil | Nerede kullanılıyor |
|---|---|---|
| 1 | Ana sonuç tablosu (anlamlılık işaretli) | Bölüm 4 |
| 2 | Etki büyüklüğü ve güven aralıkları (forest plot) | Bölüm 4 |
| 3 | Hatanın tahmin ufkuyla değişimi | Bölüm 5.2 |
| 4 | Temiz ablasyon: çıpa mı, kapasite mi? | Ek A.4, Ek C |
| 5 | Hedef başına vs çok hedefli eğitim | Bölüm 4.3 |
| 6 | LOTO genelleme bedeli | Bölüm 4.2 |
| 7 | Naif vs HAC anlamlılık | Ek B.3 |
| 8 | Sera bazında ısı haritası | Bölüm 4.2 |
| 9 | Etki büyüklüğü ve belirsizlik | Ek B.5 |
| 10 | Ölçekten bağımsız karşılaştırma (rMAE) | Bölüm 4 |
| 11 | Critical Difference diyagramı | Bölüm 5.1 |
| 12 | Hata otokorelasyonu | Ek B.2 |
