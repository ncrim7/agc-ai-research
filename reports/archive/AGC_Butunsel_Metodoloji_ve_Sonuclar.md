# AGC 2. Edisyon — Bütünsel Metodoloji ve Sonuç Belgesi

**Sürüm:** 1.0 · **Tarih:** 30 Temmuz 2026 · **Kapsam:** Veri hazırlığından sonuç yorumuna kadar tüm süreç

> **Bu belge nasıl okunmalı:** Her bölüm önce *"ne yaptık"*, sonra *"neden böyle yaptık"*, sonra *"bu ne anlama geliyor"* sırasıyla ilerler. Konuya hiç aşina olmayan bir okuyucu da takip edebilir; teknik detaylar açıklamalarıyla birlikte verilmiştir.

---

# BÖLÜM 1 — Problem ve veri

## 1.1 Sera nedir, neyi tahmin ediyoruz?

Modern bir sera, kapalı bir tarım sistemidir. İçerideki sıcaklık, nem, karbondioksit ve ışık, bilgisayar kontrollü ekipmanlarla (ısıtma boruları, pencereler, perdeler, LED lambalar, CO₂ dozajlama, sulama) sürekli ayarlanır. Yetiştirici veya bir yapay zekâ, her 5 dakikada bir bu ekipmanlara **hedef değerler** (setpoint) gönderir; proses bilgisayarı da dış hava koşullarına göre bunları gerçekleştirir.

Bizim sorumuz şu: **Son 24 saatin tüm ölçümlerine bakarak, önümüzdeki 3 ve 6 saatte seranın içi ne olacak?**

Bu pratikte neden değerli: 6 saat sonrasını bilebilen bir sistem, "şu an ısıtmayı açmalı mıyım" gibi kararları öngörüyle verebilir; enerji tasarrufu ve bitki stresinin önlenmesi buna bağlıdır.

## 1.2 Veri seti

**Kaynak:** Wageningen Üniversitesi (Hollanda) — *Autonomous Greenhouse Challenge, 2. Edisyon*. Uluslararası bir yarışma: beş yapay zekâ takımı, kendi algoritmalarıyla birer sera bölmesini uzaktan yönetmiş; altıncı bölme (Reference) deneyimli insan yetiştiriciler tarafından yönetilmiş. Hepsi aynı tesiste, aynı dönemde, aynı domates çeşidini (cherry, Axiany) yetiştirmiş.

| Özellik | Değer |
|---|---|
| Sera sayısı | 6 (AICU, Automatoes, Digilog, IUACAAS, TheAutomators, Reference) |
| Dönem | 16 Aralık 2019 – 30 Mayıs 2020 (166 gün) |
| Ölçüm sıklığı | 5 dakika |
| Sera başına satır | 47.809 |
| Toplam satır | 286.854 |
| Kolon | 52 |

**Bu veri setinin özel değeri:** Altı sera **aynı dış hava koşullarını** yaşadı ama **altı farklı kontrol politikasıyla** yönetildi. Yani "farklı yönetim stratejileri aynı koşullarda ne sonuç verir" sorusunu doğal bir deney gibi inceleyebiliyoruz. Açık sera veri setleri arasında bu nadir bir özellik.

## 1.3 Tahmin edilen değişkenler

İki gruba ayrıldı:

**Core (5 değişken) — seranın havası:**
| Değişken | Ne ölçer | Neden önemli |
|---|---|---|
| `Tair` | Hava sıcaklığı (°C) | Bitki gelişiminin ana sürücüsü |
| `Rhair` | Bağıl nem (%) | Hastalık riski ve terleme |
| `CO2air` | Karbondioksit (ppm) | Fotosentez hammaddesi |
| `HumDef` | Nem açığı (g/m³) | Bitkinin su kaybı potansiyeli |
| `Tot_PAR` | Bitkinin kullandığı ışık | Fotosentez enerjisi |

**Grodan (6 değişken) — kök bölgesi:**
| Değişken | Ne ölçer |
|---|---|
| `EC_slab1/2` | Kök ortamındaki tuz yoğunluğu |
| `WC_slab1/2` | Kök ortamındaki su içeriği |
| `t_slab1/2` | Kök ortamı sıcaklığı |

**Neden iki grup?** Kök sensörleri pahalı ve her serada bulunmaz. "Bunları eklemek iklim tahminini iyileştiriyor mu?" sorusunun cevabı, pratikte yatırım kararı demektir. Bu yüzden iki ayrı deney kurduk.

---

# BÖLÜM 2 — Veri temizliği: her karar ve gerekçesi

Ham veri doğrudan modele verilemez. Aşağıdaki kararların her biri, **veriye bakarak** alındı; hiçbiri varsayım değil.

## 2.1 Hangi kolonlar "eylem" sayılır?

Veri setinde iki tür kontrol kolonu var:
- `*_sp` (setpoint): takımın **istediği** hedef
- `*_vip`: proses bilgisayarına **fiilen giden** komut

**Karar:** `_sp` kolonları atıldı, `_vip` tutuldu.

**Gerekçe:** İkisi arasında +0.99 korelasyon ölçüldü — yani neredeyse aynı bilgiyi taşıyorlar. İkisini birden modele vermek *çoklu bağlantı* (multicollinearity) yaratır: model hangi kolonun etkili olduğunu ayırt edemez, katsayılar kararsızlaşır. Ayrıca `_sp` kolonları bazı takımlarda %1–14 doluyken bazılarında %95+ dolu; ortak bir tanım kurulamıyor.

## 2.2 LED verisindeki boşluklar

Yapay aydınlatma kolonlarının (`int_*_vip`) %46'sı boştu.

**Karar:** Boşluklar 0 ile dolduruldu.

**Gerekçe:** Boşluk "sensör arızası" değil, "lamba kapalı" anlamına geliyor olabilirdi. Bunu varsaymak yerine **doğruladık**: boş satırlarda toplam lamba çıkışının (`AssimLight`) gerçekten sıfır olup olmadığına baktık. Altı takımda %94.8–98.2 uyum çıktı. Yani varsayım verilerle desteklendi.

## 2.3 Kök sensörü onarımı

Her serada iki adet kök sensörü var (slab1, slab2). Birinde boşluk varken diğerinde veri olabiliyor.

**Karar:** Çapraz doldurma yapıldı — **ancak yalnızca iki sensör arasındaki korelasyon 0.7'nin üzerindeyse.**

**Gerekçe:** Automatoes'ta bu korelasyon +0.99'du, yani sensörler aynı şeyi ölçüyordu; doldurmak güvenli. Ama bunu tüm takımlara körü körüne uygulamak hataydı: **AICU'da korelasyon −0.046 çıktı** (yani sensörlerden biri arızalı), Digilog'da 0.481, TheAutomators'ta 0.631. Bu üç yerde doldurma yapılmadı — yapılsaydı veri uydurmuş olurduk.

> **Bu, belgenin genel prensibini gösteriyor:** bir seradaki gözlem diğerlerine otomatik genellenmedi; her adım her takımda ayrı doğrulandı.

## 2.4 Fiziksel olarak imkânsız değerler

**Karar:** İmkânsız değerler (ör. sera içi −1 °C, negatif nem) NaN yapıldı; **satır silinmedi.**

**Gerekçe:** Satır silmek zaman serisinde delik açar ve sonraki pencereleme adımını bozar. Değeri maskelemek, o hücreyi "bilinmiyor" yapar ama zaman eksenini korur. Reference serasında 8 ihlal bulundu; diğerlerinde yok.

## 2.5 Zaman ekseni düzeltmesi

**Sorun:** Kaynak dosyalardaki zaman damgaları Excel seri numarası olarak saklanmış ve ~5 ondalık basamağa yuvarlanmış. Bu, her adımın tam 5 dakika değil, 4 dakika 59.808 saniye görünmesine yol açıyordu.

**Karar:** Zaman damgaları 5 dakikaya yuvarlandı.

**Gerekçe — ve bu neden kritik:** Sonraki adımda pencereleri **konum numarasıyla** kesiyoruz ("288 satır al = 24 saat"). Bu, satırların kesintisiz eşit aralıklı olduğunu varsayar. Varsayım doğrulanmadan kullanılırsa, bir saatlik kesinti olan yerde "24 saatlik" pencere aslında 25 saati kapsar ve model bunu asla haber vermez — sessizce yanlış öğrenir.

**Doğrulama sonucu:** Zaman ekseninde **hiç eksik satır yok**. 166 günün tamamı kesintisiz 5 dakikalık ızgarada. Yaz saati geçişi (29 Mart) kaynaklı atlama da yok — veri sabit saat diliminde kaydedilmiş. Yani konumsal kesme güvenli.

## 2.6 Doğrulama kapısı

Modele geçmeden önce 9 bağımsız kontrol çalıştırıldı: zaman sürekliliği, duplike zaman damgası, şema tutarlılığı, kolon bazlı eksik veri, sabit kolonlar, mantık dışı değer taraması, boşluk konumu, hedef dağılımı, pencere muhasebesi.

**Sonuç: 0 hata.** Uyarı olarak çıkan her madde tek tek incelendi ve hiçbirinin veri sorunu olmadığı görüldü (ayrıntı: Bölüm 8).

### Bulunan iki önemli veri olgusu

**a) 86 saatlik ortak kök sensörü kesintisi.** 26–30 Mayıs arasında, **altı serada da aynı anda**, kök sensörleri veri vermemiş. Tesis geneli bir arıza. Bu dönem test setine düştüğü için, Grodan deneyinde test penceresi 568'den 470'e iniyor.

**b) Mevsimsel kayma.** Sezonun ilk 30 günü ile son 30 günü karşılaştırıldığında:

| Değişken | İlk 30 gün | Son 30 gün | Oran |
|---|---|---|---|
| Tot_PAR (ışık) | 133.9 | 273.9 | **2.05×** |
| HumDef (nem açığı) | 3.7 | 5.4 | **1.46×** |
| Tair (sıcaklık) | 20.6 | 23.9 | +3.3 °C |

Bu, ilerideki tüm sonuçların yorumunu etkileyecek — Bölüm 7'de dönülecek.

---

# BÖLÜM 3 — Pencere üretimi ve veri sızıntısının önlenmesi

## 3.1 Pencere nedir?

Modele "geçmiş" ve "gelecek" çiftleri veriyoruz:

```
[  288 satır = 24 saat GİRDİ  ][  72 satır = 6 saat ÇIKTI  ]
```

Her 12 satırda (1 saat) bir yeni pencere üretilir. 3 saatlik tahmin, 72 adımlık çıktının ilk 36 adımı olarak elde edilir.

**Neden ayrı 3h modeli eğitmiyoruz?** 3 saat zaten 6 saatin alt kümesi. Ayrı eğitmek hesaplama maliyetini iki katına çıkarır, hiçbir bilgi kazandırmaz.

## 3.2 Veri sızıntısı ve alınan önlemler

**Veri sızıntısı nedir?** Modelin, gerçek kullanımda erişemeyeceği bilgiyi eğitim sırasında görmesi. Sızıntı olan bir model testte harika görünür, gerçekte çuvallar. Zaman serilerinde en sık yapılan hatadır.

| Risk | Alınan önlem |
|---|---|
| Rastgele bölme | **Kullanılmadı.** Kronolojik bölme: ilk %70 eğitim, sonraki %15 doğrulama, son %15 test. Rastgele bölme gelecekten geçmişe bilgi sızdırır. |
| Sınır aşan pencere | Bir pencere iki bölmenin sınırını aşıyorsa **atılır** |
| Normalizasyon sızıntısı | Ortalama/standart sapma **yalnızca eğitim bölmesinden** hesaplanır |
| Eksik hedef | Çıktı aralığında eksik veri olan pencereler elenir |
| Seralar arası karışma | Her sera kendi içinde bölünür; pencere sera sınırını aşmaz |

## 3.3 Sonuç pencere sayıları

| Feature-set | Eğitim | Doğrulama | Test | Toplam |
|---|---|---|---|---|
| Core | 16.482 | 3.408 | 3.408 | 23.298 |
| Core+Grodan | 16.056 | 3.276 | 2.820 | 22.152 |

## 3.4 Adil karşılaştırma sorunu ve çözümü

Core ve Core+Grodan **farklı test setleri** kullanıyor (86 saatlik boşluk yüzünden 3.408'e karşı 2.820). Farklı test setlerinde ölçülen iki sayıyı karşılaştırmak geçersizdir.

**Çözüm:** `core_matched` adında üçüncü bir koşu eklendi — Core öznitelikleri, Grodan'ın pencere alt kümesinde değerlendirildi. Böylece "Grodan eklemek işe yarıyor mu?" sorusu aynı pencerelerde cevaplanabildi.

> **Doğrulama:** Öznitelik kullanmayan baseline'lar (persistence, seasonal) `core_matched` ve `core_grodan`'da **birebir aynı** sayıları verdi. Bu, pencere hizalamasının doğru olduğunu kanıtlar.

---

# BÖLÜM 4 — Karşılaştırılan yöntemler

## 4.1 Baseline'lar: neden gerekli?

Bir modelin "iyi" olduğunu söylemek için neye göre iyi olduğunu belirtmek gerekir. Baseline, "hiç zekâ kullanmadan ne kadar iyi tahmin edilebilir" sorusunun cevabıdır. Derin öğrenme modeli bunları geçemiyorsa, karmaşıklık boşunadır.

| Baseline | Mantığı | Neyi test eder |
|---|---|---|
| **Persistence** | "Şu anki değer devam edecek" | Sistemin ne kadar hareketsiz olduğu |
| **Seasonal Naive** | "Dün bu saatte ne vardıysa o olacak" | Günlük döngünün gücü |
| **Moving Average** | Son 3 saatin ortalaması | Kısa vadeli düzleştirme |
| **Linear Trend** | Son 6 saatin eğimini uzat | Doğrusal gidişin yeterliliği |
| **Ridge Regression** | Özet istatistiklerden doğrusal tahmin | Doğrusal ilişkilerin yeterliliği |

**Ridge'de önemli bir tasarım kararı:** 288×46'lık ham pencereyi düz vektöre çevirip (16.416 boyut) modele vermedik. Bunun yerine her kolon için 4 özet (ortalama, standart sapma, son değer, eğim) hesapladık → ~184 boyut. Ham hâliyle verilseydi, ~550 bağımsız örnekle 16.416 boyutlu bir doğrusal model kurmuş olurduk; bu kesin aşırı uyum demektir.

## 4.2 Derin öğrenme modelleri

| Model | Nasıl çalışır | Beklenen avantaj |
|---|---|---|
| **GRU** | Diziyi baştan sona tek tek okur, bir "hafıza" tutar | Hafif, hızlı |
| **LSTM** | GRU'nun daha karmaşık hafıza mekanizmalı hâli | Uzun bağımlılıkları daha iyi tutabilir |
| **TCN** | Diziyi konvolüsyonla, giderek genişleyen aralıklarla tarar | **Tüm pencereyi aynı anda görür** |

**Neden TCN'in avantajlı olması bekleniyordu:** GRU ve LSTM diziyi sırayla işler; 288 adımlık bir pencerenin *başındaki* bilgi, sona geldiğinde büyük ölçüde unutulmuş olur (bu olguya *recency bias* denir). Oysa "dün bu saatte ne vardı" bilgisi tam olarak pencerenin başında durur. TCN'in alıcı alanı 509 adım — 288 adımlık pencerenin tamamını kapsar, unutma sorunu yoktur.

*Bu beklenti sonuçlarla doğrulandı (Bölüm 6).*

## 4.3 Kritik mimari karar: artık (residual) tahmin

Modeller mutlak değer yerine **bir baseline'a göre farkı** tahmin edecek şekilde kuruldu:

```
tahmin = çıpa (baseline) + modelin düzeltmesi
```

**Neden:** Model hiçbir şey öğrenemese ve sıfır çıktı verse bile, sonuç tam olarak baseline kadar iyi olur. Yani çıta tabana gömülür; model ancak baseline'ı iyileştirdiği ölçüde ondan sapar. Bu, "derin model basit yöntemden kötü çıktı" riskini yapısal olarak ortadan kaldırır.

### Çıpa seçimi: yapılan hata ve düzeltilmesi

İlk denemede **tüm hedefler** seasonal çıpaya bağlandı. Bu, kök bölgesi değişkenleri için yanlıştı:

| | Doğru çıpa | Neden |
|---|---|---|
| Tair, Rhair, CO2air, HumDef, Tot_PAR, t_slab | **seasonal** | Güçlü günlük döngüye sahipler |
| EC_slab, WC_slab | **persistence** | Günlük döngüsel değil, yavaş sürüklenen büyüklükler |

Baseline tablosu doğru cevabı zaten söylüyordu: EC_slab için persistence 0.043, seasonal 0.136 — üç kat fark. Yanlış çıpa kullanıldığında model önce bu hatayı geri almak zorunda kalıyordu.

**Düzeltmenin etkisi (TCN, 3 saat):**

| Hedef | Yanlış çıpa | Doğru çıpa | İyileşme |
|---|---|---|---|
| EC_slab2 | 0.203 | 0.060 | **%70** |
| EC_slab1 | 0.153 | 0.055 | **%64** |
| WC_slab1 | 1.604 | 0.921 | **%43** |
| WC_slab2 | 1.742 | 1.034 | **%41** |

## 4.4 İkinci kritik karar: model boyutu

İlk denemede modeller büyük tutuldu (TCN 199.208 parametre) ve hepsi baseline'lara kaybetti. Sebep, **etkin örneklem büyüklüğüydü.**

**Etkin örneklem nedir?** Eğitimde 16.482 pencere var görünüyor. Ancak ardışık pencereler 1 saat kaydırmayla üretildiği için birbirleriyle **%95.8 örtüşüyorlar** — neredeyse aynı veriyi tekrar tekrar gösteriyoruz. Gerçekten örtüşmeyen pencere sayısı:

```
sera başına eğitim satırı 33.466 ÷ pencere aralığı 360 ≈ 93
93 × 6 sera ≈ 552 bağımsız örnek
```

199.208 parametre ÷ 552 bağımsız örnek = **örnek başına 357 parametre.** Bu oranda hiçbir model genelleme yapamaz; ezberler.

**Düzeltme:** Modeller ~15.000–27.000 parametreye indirildi (oran 26–50), L2 düzenlileştirme eklendi.

| Model | Önce | Sonra | Azalma |
|---|---|---|---|
| GRU | 75.816 | 14.640 | 5.2× |
| LSTM | 89.064 | 16.224 | 5.5× |
| TCN | 199.208 | 18.088 | 11.0× |

> **Yan bulgu — danışman önerisinin test edilmesi:** "Modelin 100–150 epoch'a kadar ilerlemesi lazım" önerisi uygulandı; üst sınır 60'tan 150'ye çıkarıldı, sabır (patience) 8'den 20'ye. **Modeller yine 25–80 epoch'ta kendiliğinden durdu.** Yani eğitim süresi darboğaz değildi — bu, öneriyi reddederek değil, uygulayıp ölçerek gösterildi.

---

# BÖLÜM 5 — Deney tasarımı

Dört ayrı deney kuruldu. Her biri **farklı bir soruyu** cevaplıyor:

| # | Deney | Cevapladığı soru | Durum |
|---|---|---|---|
| 1 | Baseline'lar | Zekâ kullanmadan ne kadar iyi tahmin edilir? | ✅ Tamam |
| 2 | Kronolojik + çok hedefli | Derin model geleceği tahmin edebiliyor mu? | ✅ Tamam |
| 3 | Kapasite ablasyonu | Model boyutu genellemeyi nasıl etkiliyor? | ✅ Kısmen (large/small) |
| 4 | **Leave-One-Team-Out** | Model **hiç görmediği** bir seraya genelleşiyor mu? | ✅ Tamam |
| 5 | Hedef başına ayrı model | Her hedefe özel model daha mı iyi? | ⏳ Planlandı |

## 5.1 Leave-One-Team-Out (LOTO) ve ortak hava sorunu

**Standart yaklaşım:** 5 takımla eğit, 6. takımla test et. Altı kez tekrarla. Bu, modelin görülmemiş bir kontrol politikasına genellenip genellenmediğini ölçer.

**Fark ettiğimiz sorun:** Altı sera **aynı tesiste** ve **aynı hava verisini** paylaşıyor. Klasik LOTO'da model, test takımının dönemindeki dış hava koşullarını diğer 5 takım üzerinden zaten görmüş olur. Sera iklimi büyük ölçüde dış havayla sürüldüğü için bu, sonuçları olduğundan iyi gösterir.

**Kurduğumuz tasarım — fold başına tek eğitim, iki test seti:**

```
Tutulan takım = T
  EĞİTİM     : diğer 5 takımın eğitim dönemi
  DOĞRULAMA  : diğer 5 takımın doğrulama dönemi
  TEST A     : T'nin eğitim dönemi   → hava görülmüş, politika görülmemiş
  TEST B     : T'nin test dönemi     → ne hava ne politika görülmemiş  ← dürüst ölçüm
```

> **Dürüst uyarı:** A ile B arasındaki fark **yalnızca** hava sızıntısını ölçmez; A kış-ilkbahar, B Mayıs dönemine denk geldiği için mevsimsel zorluk farkı da karışır. İkisi ayrıştırılamaz. Bu yüzden sızıntı sorusunun temiz cevabı, aşağıdaki *kronolojik vs LOTO-B* karşılaştırmasıdır — her ikisi de aynı Mayıs pencerelerinde ölçüldüğü için mevsim sabittir.

---

# BÖLÜM 6 — Sonuçlar

## 6.1 En iyi baseline vs en iyi derin model

*(MAE = ortalama mutlak hata; düşük olan iyidir)*

### Core — 3 saat
| Hedef | En iyi baseline | MAE | En iyi derin | MAE | Kazanan |
|---|---|---|---|---|---|
| Tair | Seasonal | 1.182 | **TCN** | **1.154** | Derin (−2.4%) |
| Tot_PAR | Seasonal | 80.682 | **TCN** | **78.919** | Derin (−2.2%) |
| CO2air | **Seasonal** | **58.437** | LSTM | 59.116 | Baseline |
| HumDef | **Ridge** | **1.277** | TCN | 1.345 | Baseline |
| Rhair | **Ridge** | **4.654** | TCN | 5.066 | Baseline |

### Core — 6 saat
| Hedef | En iyi baseline | MAE | En iyi derin | MAE | Kazanan |
|---|---|---|---|---|---|
| HumDef | Seasonal | 1.550 | **TCN** | **1.432** | Derin (−7.6%) |
| Rhair | Seasonal | 5.788 | **TCN** | **5.414** | Derin (−6.5%) |
| Tair | Seasonal | 1.193 | **TCN** | **1.184** | Derin (−0.8%) |
| CO2air | **Seasonal** | **58.456** | LSTM | 59.112 | Baseline |
| Tot_PAR | **Seasonal** | **80.700** | TCN | 80.890 | Baseline |

### Core+Grodan — 3 saat (öne çıkanlar)
| Hedef | En iyi baseline | MAE | En iyi derin | MAE | Kazanan |
|---|---|---|---|---|---|
| Tair | Seasonal | 1.146 | **TCN** | **0.972** | Derin (−15.2%) |
| WC_slab1 | Persistence | 1.057 | **TCN** | **0.921** | Derin (−12.9%) |
| WC_slab2 | Persistence | 1.151 | **TCN** | **1.034** | Derin (−10.2%) |
| EC_slab1 | **Persistence** | **0.043** | GRU | 0.051 | Baseline |
| t_slab1 | **Ridge** | **0.410** | TCN | 0.650 | Baseline |

### Core+Grodan — 6 saat (öne çıkanlar)
| Hedef | En iyi baseline | MAE | En iyi derin | MAE | Kazanan |
|---|---|---|---|---|---|
| Tair | Seasonal | 1.137 | **TCN** | **1.029** | Derin (−9.5%) |
| t_slab1 | Ridge | 0.704 | **TCN** | **0.658** | Derin (−6.5%) |
| WC_slab1 | Seasonal | 1.428 | **TCN** | **1.352** | Derin (−5.3%) |
| EC_slab1 | **Persistence** | **0.071** | GRU | 0.074 | Baseline |
| CO2air | **Seasonal** | **62.530** | LSTM | 62.862 | Baseline |

**Genel skor:** 32 hedef-ufuk kombinasyonunun **14'ünde derin öğrenme**, 18'inde baseline üstün.

## 6.2 Model aileleri karşılaştırması

**TCN, derin modeller arasında açık ara en iyisi.** Bu, iki bağımsız deneyde de doğrulandı:

| Deney | TCN | LSTM | GRU |
|---|---|---|---|
| Kronolojik (32 kombinasyon) | çoğunlukla | — | — |
| **LOTO (32 kombinasyon)** | **20 galibiyet** | 9 | 3 |

**Yorum:** TCN'in üstünlüğü tesadüf değil, mimari bir avantaj. Genişletilmiş konvolüsyon, 288 adımlık pencerenin tamamını görüyor; GRU/LSTM pencerenin başındaki bilgiyi kaybediyor. Bu, Bölüm 4.2'deki teorik beklentinin ampirik doğrulanmasıdır.

**İstisna:** CO₂ ve EC_slab'de LSTM önde. Bu iki değişken de yüksek oranda rejim-anahtarlamalı (CO₂ dozajlama açık/kapalı, EC yavaş kayma); LSTM'in kapı mekanizması bu tür süreçlerde avantajlı olabilir.

## 6.3 LOTO — genelleme sonuçları

**Ana bulgu: model, hiç görmediği bir seraya neredeyse bedelsiz genelleşiyor.**

Karşılaştırma temiz: LOTO Test B'nin pencereleri, kronolojik testin pencereleriyle **birebir aynı**. Tek fark, o takımın eğitimde bulunup bulunmaması.

### TCN, Core feature-set — genelleme bedeli
| Hedef | Kendi geçmişini gördü | Hiç görmedi | Bedel |
|---|---|---|---|
| Tot_PAR | 78.919 | 76.871 | **−2.6%** |
| Rhair | 5.066 | 5.047 | **−0.4%** |
| CO2air | 59.916 | 59.877 | −0.1% |
| Tair | 1.154 | 1.153 | −0.1% |
| HumDef | 1.345 | 1.352 | +0.5% |

**Üç hedefte LOTO daha iyi sonuç verdi.** Muhtemel açıklama: 5 farklı kontrol politikasıyla eğitilen model, tek bir takımın alışkanlıklarına aşırı uyum sağlamıyor — çeşitlilik düzenlileştirici etki yapıyor.

### Ortalama genelleme bedeli (tüm hedefler)
| Model | Ortalama | Medyan |
|---|---|---|
| LSTM | +2.0% | +1.4% |
| GRU | +2.5% | +1.6% |
| TCN | +4.3% | +3.5% |

**Kök bölgesinde bedel daha yüksek** (WC_slab1 +12.2%, t_slab2 +10.0%). Mantıklı: sulama politikası takıma özgü bir karardır, oysa iklim fiziği evrenseldir.

**Bu ne anlama geliyor:** Model, takıma özgü kontrol alışkanlıklarını ezberlemiyor; **sera fiziğini** öğreniyor. Yeni bir seraya kurulduğunda, o seranın geçmiş verisi olmadan da çalışabilir. Pratikte bu, sistemin taşınabilir olduğu anlamına gelir.

## 6.4 Hangi sera genellemesi en zor?

11 hedefin tamamında normalize edilmiş zorluk skoru (1.00 = ortalama):

| Sera | Skor |
|---|---|
| AICU | 0.835 |
| IUACAAS | 0.877 |
| Reference (insan yetiştirici) | 0.896 |
| Digilog | 1.010 |
| TheAutomators | 1.093 |
| **Automatoes** | **1.289** |

**Automatoes en zor genellenen sera** — ve Automatoes yarışmanın kazananı. En ayırt edici ve başarılı kontrol politikasına sahip olan, diğerlerinden öğrenen bir model için en öngörülemez olanı. 

İlginç ikinci gözlem: **Reference (insan yetiştirici) en kolay genellenenler arasında.** İnsan yetiştiricilerin kararları, yapay zekâ takımlarının bazılarından daha öngörülebilir.

## 6.5 Açıklanan varyans (R², TCN, Test B, 3h)

R², modelin değişkenliğin ne kadarını açıkladığını gösterir (1.0 = mükemmel, 0 = ortalama tahmin kadar):

| Hedef | R² | Yorum |
|---|---|---|
| EC_slab1/2 | 0.91 | Çok yüksek — ama değişken zaten çok yavaş |
| t_slab1/2 | 0.85 | Yüksek |
| Tair | 0.83 | Yüksek — pratik kullanıma uygun |
| WC_slab1/2 | 0.79 | İyi |
| Tot_PAR | 0.75 | İyi |
| HumDef | 0.67 | Orta |
| Rhair | 0.61 | Orta |
| **CO2air** | **0.54** | **En zayıf** |

CO₂'nin en zor tahmin edilen değişken olması tutarlı bir bulgu: dozajlama açık/kapalı rejimleri ve havalandırmayla ani kayıplar, sürekli bir dinamik değil sıçramalı bir süreç yaratıyor.

## 6.6 Grodan sensörlerinin katkısı

Eşleştirilmiş pencerelerde (aynı test seti) Ridge ile ölçülen katkı:

| Hedef | 3h | 6h | Yorum |
|---|---|---|---|
| HumDef | −5.8% | −7.8% | **Tutarlı iyileşme** |
| Rhair | −2.6% | −4.7% | **Tutarlı iyileşme** |
| Tot_PAR | −4.3% | −2.4% | İyileşme |
| CO2air | +1.2% | −3.7% | Karışık |
| Tair | +3.5% | +5.4% | **Kötüleşme** |

**Yorum:** Katkı marjinal ama fiziksel olarak anlamlı. Kök bölgesindeki su içeriği bitkinin terlemesini, terleme de havadaki nemi doğrudan etkiler — bu yüzden nem tarafında (HumDef, Rhair) tutarlı iyileşme var. Sıcaklıkta katkı yok, hatta zarar var; sıcaklık kök bölgesinden değil ısıtma ve radyasyondan sürülüyor.

**Pratik çıkarım:** Kök sensörü yatırımı, nem yönetimi öncelikliyse anlamlı; yalnızca sıcaklık tahmini hedefleniyorsa gereksiz.

> **Önemli teknik ayrım:** Grodan yüzünden kaybedilen %17'lik test penceresi, bu sensörleri **öznitelik olarak kullanmanın** değil, **hedef olarak tahmin etmenin** bedelidir. Yalnızca iklim tahmini isteniyorsa Grodan girdi olarak eklenip tam test seti korunabilir.

---

# BÖLÜM 7 — Sonuçların yorumu

## 7.1 Neden basit yöntemler bu kadar güçlü?

Seasonal naive'in ("dün bu saatte ne vardıysa o") hatası, tahmin ufkuyla neredeyse hiç artmıyor:

| Hedef | 3 saat | 6 saat | Artış |
|---|---|---|---|
| Tair | 1.182 | 1.193 | %0.9 |
| CO2air | 58.437 | 58.456 | %0.03 |
| Tot_PAR | 80.682 | 80.700 | %0.02 |

Karşılaştırma için persistence ("şu anki değer devam edecek") aynı aralıkta %70 bozuluyor.

**Açıklama:** Sera, güneşin günlük döngüsüne kilitli bir sistemdir. Sıcaklık, ışık ve CO₂ her gün benzer bir eğri çizer. "Dün bu saatte" tahmini, ufuk uzasa da aynı kalitede kalır çünkü ekstrapolasyon yapmaz, hatırlar.

**Bu, projenin merkezi bulgusudur:** Güçlü periyodik yapıya sahip bir sistemde, öğrenen modelin aşması gereken çıta sanıldığından çok yüksektir.

## 7.2 Mevsimsel dağılım kayması

Eğitim verisi kışı (Aralık–Nisan), test verisi ilkbaharı (Mayıs) kapsıyor. Bu dönemde ışık 2.05 kat, nem açığı 1.46 kat artıyor.

**Gözlemlenen kanıt:** Doğrulama hatası, **daha ilk eğitim turunda** eğitim hatasının 2.2 katı. Aşırı uyum (overfitting) epoch'lar boyunca gelişir; ilk turda ortaya çıkan fark yapısal bir dağılım farkına işaret eder.

**Sonuç:** Model kolay bir dönemde öğrenip zor bir dönemde sınava giriyor. Bu, tek sezonluk tüm tarımsal veri setlerinin ortak sorunudur ve raporlanan hataların bir kısmı buradan gelir.

## 7.3 Hangi model, hangi fizik?

| Değişken grubu | Kazanan yaklaşım | Fiziksel sebep |
|---|---|---|
| Sıcaklık, nem (Tair, Rhair, HumDef) | **TCN** | Dış hava, radyasyon, havalandırma ve ısıtma arasında doğrusal olmayan etkileşimler var — öğrenilecek yapı mevcut |
| CO₂, ışık (CO2air, Tot_PAR) | **Seasonal Naive** | Çok güçlü ve düzenli günlük döngü; CO₂ ayrıca deterministik bir kontrol politikasıyla sürülüyor |
| Kök tuzluluğu (EC_slab) | **Persistence** | O kadar yavaş değişiyor ki "hiçbir şey olmayacak" en iyi tahmin |
| Kök suyu ve sıcaklığı (WC, t_slab) | **TCN** | İklimle güçlü bağlı, dinamiği var |

Kök tuzluluğuna ilişkin bu bulgu bağımsız bir analizle de destekleniyor: sulama eylemi ile 3–6 saatlik EC sonucu arasındaki korelasyon **−0.03 ile 0.16** arasında. Yani kısa vadede sulama kararı kök tuzluluğunu belirlemiyor — kök ortamı bir tampon gibi davranıyor.

---

# BÖLÜM 8 — Sınırlamalar ve dürüst uyarılar

## 8.1 İstatistiksel anlamlılık henüz test edilmedi

Tablolardaki %1–3'lük farkların gerçek mi gürültü mü olduğu test edilmedi. Diebold-Mariano testi veya bootstrap güven aralığı eklenmeli. **%10 üzeri farklar (Tair −15.2%, EC_slab −64%) muhtemelen gerçektir; %2'lik farklara güvenilmemelidir.**

## 8.2 İki müdahale birlikte uygulandı

Çıpa düzeltmesi ve kapasite azaltma aynı anda yapıldı; katkıları ayrıştırılamıyor. Dolaylı kanıt güçlü (kök hedefleri %40–70, diğerleri %1–17 iyileşti — kapasite değişimi tüm hedefleri benzer etkilerdi), ama temiz ablasyon için tek değişkenli bir koşu gerekir (~30 dakika, 6 koşu).

## 8.3 Etkin örneklem küçük

Raporlanan 16.482 eğitim penceresi bağımsız örnek sayısı değil (~552). Güven aralıkları olduğundan dar görünür; bu, madde 8.1'i daha da önemli kılar.

## 8.4 Tek sezon, tek tesis, tek çeşit

Sonuçlar başka bir ürüne, iklim bölgesine veya sera tipine doğrudan genellenemez. 166 gün tek bir yetiştirme dönemidir; mevsimler arası genelleme test edilemez.

## 8.5 Test A / Test B farkı yalnızca sızıntı değil

LOTO'daki `B/A` oranı hem hava sızıntısını hem mevsimsel zorluk farkını içerir; ikisi ayrıştırılamaz. Sızıntı sorusunun temiz cevabı, kronolojik ile LOTO-B'nin karşılaştırmasıdır (Bölüm 6.3).

## 8.6 Tekrar üretilebilirlik sınırı

Rastgelelik tohumu sabitlendi (42), ancak GPU'daki paralel işlem sırası nedeniyle sonuçlar bit düzeyinde aynı çıkmayabilir. Farklar küçüktür ama sıfır değildir.

---

# BÖLÜM 9 — Ana çıkarım

Bu çalışmanın en savunulabilir sonucu bir model sıralaması değil, bir **metodolojik gözlemdir:**

> **Sera iklim tahmininde tek bir "en iyi model" yoktur. Doğru yöntem, hedef değişkenin fiziksel dinamiğine bağlıdır.**
>
> - Güçlü günlük döngüye sahip değişkenlerde (CO₂, ışık) basit mevsimsel yöntemler yeterlidir.
> - Doğrusal olmayan etkileşimlerle sürülen değişkenlerde (sıcaklık, nem) genişletilmiş konvolüsyonlu derin modeller (TCN) üstündür.
> - Çok yavaş değişen değişkenlerde (kök tuzluluğu) persistence en iyisidir.

**İkinci önemli sonuç:** Model, hiç görmediği bir seraya %0–4 bedelle genelleşiyor. Bu, sistemin takıma özgü alışkanlıkları değil sera fiziğini öğrendiğini gösterir ve pratik taşınabilirlik anlamına gelir.

**Üçüncü sonuç — metodolojik uyarı niteliğinde:** Tek sezonluk sera veri setlerinde (a) örtüşen pencereler etkin örneklem sayısını 30 kat abartır, (b) kronolojik bölme ciddi mevsimsel dağılım kayması yaratır, (c) artık tahminde çıpa seçimi hedefin fiziğine göre yapılmalıdır — yanlış çıpa modeli baseline'ın 4 katı kötüye düşürür. Bu üç tuzak literatürde yeterince vurgulanmamaktadır.

---

# EK — Tekrar üretim

```python
# 0) Kurulum
exec(open("agc_all_in_one.py").read(), globals())
BASE_DIR = Path(".../AutonomousGreenhouseChallenge_edition2")

# 1) Veri hazırlığı → common_core_strict.parquet, common_core_with_grodan_strict.parquet
#    (agc_common_core_pipeline.py)

# 2) Doğrulama — 9 kontrol, 0 hata beklenir
#    (agc_data_verification.py)

# 3) Pencere üretimi
#    (agc_window_generation.py)

# 4) Baseline'lar
#    (agc_baselines.py)

# 5) Derin modeller
MODEL_SIZE = "small"
run(BASE_DIR, target_mode="multi")

# 6) LOTO
run_loto(BASE_DIR)

# Planlanmış:
# 7) Hedef başına ayrı model
run(BASE_DIR, feature_sets=("core",), target_mode="single")
# 8) Temiz ablasyon: MODEL_SIZE="large" + yeni çıpa
```

**Üretilen dosyalar:** `all_forecasting_results_long.csv` (baseline) · `deep_model_results_multi.csv` (derin) · `loto_results.csv` (çapraz doğrulama) · `error_by_step.csv` (hata eğrisi) · `data_verification_report.csv` (doğrulama)
