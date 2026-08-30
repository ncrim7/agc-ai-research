# AGC 2. Edisyon — Ara Rapor
### Sera İkliminde Kısa Vadeli Çok Değişkenli Tahmin: Baseline ve Derin Öğrenme Karşılaştırması

**Tarih:** 30 Temmuz 2026 · **Durum:** Hafta 3/5 · **Kapsam:** Kronolojik bölme deneyleri tamamlandı

---

## 1. Bir cümlede özet

Altı seralık AGC 2. Edisyon verisinde, 24 saatlik geçmişten 3 ve 6 saat sonrasını tahmin ediyoruz. Basit istatistiksel yöntemler (baseline) ile derin öğrenme modellerini aynı koşullarda karşılaştırdık. **Sonuç: hiçbir model ailesi her hedefte üstün değil — doğru model hedef değişkene göre değişiyor.**

---

## 2. Veri seti ve problem

**Veri:** Wageningen Üniversitesi'nin Autonomous Greenhouse Challenge 2. Edisyonu. Altı sera bölmesi, beşi farklı yapay zekâ takımları tarafından, biri (Reference) deneyimli yetiştiriciler tarafından yönetilmiş. 16 Aralık 2019 – 30 Mayıs 2020 arası, 5 dakikalık çözünürlükte 166 gün. Toplam 286.854 satır × 52 kolon.

**Problem:** Geçmiş 24 saatin (288 ölçüm) tüm sensör ve kontrol verisini kullanarak, gelecek 6 saatin (72 ölçüm) sera durumunu tahmin etmek. 3 saatlik tahmin, aynı çıktının ilk yarısı olarak elde ediliyor.

**Hedef değişkenler:**
- *Core (5):* hava sıcaklığı (Tair), bağıl nem (Rhair), CO₂ (CO2air), nem açığı (HumDef), ışık (Tot_PAR)
- *Grodan (6):* kök bölgesi tuzluluk (EC_slab1/2), su içeriği (WC_slab1/2), sıcaklık (t_slab1/2)

**Neden iki ayrı set?** Kök bölgesi sensörleri eklemenin iklim tahminine katkısını ölçmek için.

---

## 3. Veri hazırlığı ve doğrulama

Altı takımın tümüne aynı temizlik hattı uygulandı. Her adımın gerekçesi:

| Adım | Ne yapıldı | Neden |
|---|---|---|
| Kolon seçimi | `_sp` (istenen hedef) kolonları atıldı, `_vip` (gerçekleşen komut) tutuldu | İkisi arasında +0.99 korelasyon var; ikisini birden kullanmak çoklu bağlantı yaratır |
| LED verisi | %46 boş değer 0 ile dolduruldu | Boşluk arıza değil, "lamba kapalı" demek — 6 takımda %94.8–98.2 oranında doğrulandı |
| Kök sensörü onarımı | Slab1↔Slab2 arası çapraz doldurma, **ancak korelasyon ≥0.7 ise** | AICU'da korelasyon −0.046 çıktı (sensör arızalı); körü körüne doldurmak veri uydurmak olurdu |
| Fiziksel sınırlar | İmkânsız değerler maskelendi, satır silinmedi | Reference'ta 8 ihlal bulundu; satır silmek zaman serisinde boşluk yaratır |
| Zaman ekseni | 5 dakikaya yuvarlandı | Kaynak dosyadaki Excel seri numaraları ~192 ms hata taşıyordu |

**Doğrulama:** 9 bağımsız kontrol çalıştırıldı (zaman sürekliliği, şema tutarlılığı, boşluk analizi, sabit kolonlar, mantık dışı değerler, pencere muhasebesi vb.). **Sonuç: 0 hata.**

Öne çıkan iki bulgu:
- Zaman ekseninde **eksik satır yok**; 166 günün tamamı kesintisiz 5 dakikalık ızgarada. Yaz saati geçişi kaynaklı atlama da yok.
- Altı takımda da **aynı 86 saatlik kök sensörü kesintisi** var (26–30 Mayıs). Tesis geneli bir arıza. Bu dönem test setine düştüğü için Grodan deneyinde test penceresi 568'den 470'e iniyor.

---

## 4. Deney tasarımı

**Bölme:** Her sera kendi içinde kronolojik olarak %70 eğitim / %15 doğrulama / %15 test. Rastgele bölme **kullanılmadı** — zaman serisinde gelecekten geçmişe bilgi sızdırır.

**Sızıntı önlemleri:**
- Bir pencere iki bölme sınırını aşıyorsa atılır
- Normalizasyon istatistikleri yalnızca eğitim verisinden hesaplanır
- Çıktı aralığında eksik veri olan pencereler elenir

**Pencere sayıları:**

| Feature-set | eğitim | doğrulama | test | toplam |
|---|---|---|---|---|
| Core | 16.482 | 3.408 | 3.408 | 23.298 |
| Core+Grodan | 16.056 | 3.276 | 2.820 | 22.152 |

**Adil karşılaştırma önlemi:** Core ve Core+Grodan farklı test setleri kullandığı için (86 saatlik boşluk yüzünden) doğrudan karşılaştırma geçersiz olurdu. Bu nedenle `core_matched` adında üçüncü bir koşu eklendi: Core öznitelikleri, Grodan pencere alt kümesinde değerlendirildi.

**Karşılaştırılan yöntemler:**

*Baseline (5):* Persistence (son değeri tekrarla) · Seasonal Naive (dün bu saatteki değeri al) · Moving Average (son 3 saatin ortalaması) · Linear Trend (son 6 saatin eğimini uzat) · Ridge Regression (özet istatistiklerden doğrusal tahmin)

*Derin öğrenme (3):* GRU · LSTM · TCN (Temporal Convolutional Network)

---

## 5. İki kritik metodolojik müdahale

Derin modeller ilk denemede baseline'ların **hepsine** kaybetti. Nedenini araştırdık ve iki yapısal sorun bulduk.

### 5.1 Çıpa (anchor) seçimi

Modeller mutlak değer yerine "baseline'a göre fark" tahmin edecek şekilde kuruldu (residual mimari). Bunun avantajı: model sıfır çıktı verse bile baseline kadar iyi olur.

**Hata:** Başlangıçta tüm hedefler *seasonal* çıpaya (dün bu saat) bağlandı. Ama kök bölgesi değişkenleri günlük döngüsel değil, yavaş sürüklenen büyüklükler. "Dün bu saatte" onlar için yanlış referans; model önce bu yanlış çıpayı geri almak zorunda kalıyordu.

**Düzeltme:** Hedef başına çıpa seçimi. Kök tuzluluk ve su içeriği → *persistence*, geri kalanı → *seasonal*.

**Etki (TCN, 3 saat):**

| Hedef | Önce | Sonra | İyileşme |
|---|---|---|---|
| EC_slab1 | 0.153 | **0.055** | %64 |
| EC_slab2 | 0.203 | **0.060** | %70 |
| WC_slab1 | 1.604 | **0.921** | %43 |
| WC_slab2 | 1.742 | **1.034** | %41 |

### 5.2 Model kapasitesi ve etkin örneklem büyüklüğü

Eğitim penceresi sayısı 16.482 görünüyor. **Ancak bu sayı yanıltıcı.** Ardışık pencereler 1 saat kaydırmayla üretildiği için birbirleriyle %95.8 örtüşüyorlar. Gerçekten bağımsız (hiç örtüşmeyen) pencere sayısı yalnızca **~552**.

İlk denemede TCN 199.208 parametre kullanıyordu — bağımsız örnek başına 357 parametre. Bu oranda model genelleme yapmaz, ezberler.

**Düzeltme:** Modeller ~15.000–27.000 parametreye indirildi (örnek başına 26–50), L2 düzenlileştirme eklendi.

**Yan bulgu:** Epoch sınırı 60'tan 150'ye çıkarıldığı hâlde modeller 25–80 epoch'ta kendiliğinden durdu. Yani sorun eğitim süresi değildi — örneklem büyüklüğüydü.

> **Not:** Bu iki müdahale birlikte uygulandı, dolayısıyla etkileri istatistiksel olarak tam ayrıştırılamaz. Ancak kök bölgesi hedeflerinin %40–70 iyileşirken diğerlerinin %5–17 iyileşmesi, farkın büyük kısmının çıpa düzeltmesinden geldiğine güçlü işaret. Temiz ayrıştırma için tek değişkenli bir ablasyon koşusu planlanmıştır.

---

## 6. Sonuçlar

Her hedef için en iyi baseline ile en iyi derin model karşılaştırması (MAE, düşük = iyi):

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

### Core+Grodan — 3 saat
| Hedef | En iyi baseline | MAE | En iyi derin | MAE | Kazanan |
|---|---|---|---|---|---|
| Tair | Seasonal | 1.146 | **TCN** | **0.972** | Derin (−15.2%) |
| WC_slab1 | Persistence | 1.057 | **TCN** | **0.921** | Derin (−12.9%) |
| WC_slab2 | Persistence | 1.151 | **TCN** | **1.034** | Derin (−10.2%) |
| EC_slab1 | **Persistence** | **0.043** | GRU | 0.051 | Baseline |
| CO2air | **Persistence** | **62.175** | LSTM | 62.409 | Baseline |
| t_slab1 | **Ridge** | **0.410** | TCN | 0.650 | Baseline |

### Core+Grodan — 6 saat
| Hedef | En iyi baseline | MAE | En iyi derin | MAE | Kazanan |
|---|---|---|---|---|---|
| Tair | Seasonal | 1.137 | **TCN** | **1.029** | Derin (−9.5%) |
| t_slab1 | Ridge | 0.704 | **TCN** | **0.658** | Derin (−6.5%) |
| WC_slab1 | Seasonal | 1.428 | **TCN** | **1.352** | Derin (−5.3%) |
| t_slab2 | Ridge | 0.688 | **TCN** | **0.659** | Derin (−4.2%) |
| EC_slab1 | **Persistence** | **0.071** | GRU | 0.074 | Baseline |
| CO2air | **Seasonal** | **62.530** | LSTM | 62.862 | Baseline |

**Genel tablo:** 32 hedef-ufuk kombinasyonunun **14'ünde derin öğrenme**, 18'inde baseline üstün.

---

## 7. Yorum

**TCN, derin modeller arasında açık ara en iyisi.** Sebebi mimari: TCN genişletilmiş (dilated) evrişim kullanıyor ve alıcı alanı 509 adım — 288 adımlık girdi penceresinin tamamını görüyor. GRU ve LSTM ise diziyi sırayla işlediği için pencerenin başındaki bilgiyi tutmakta zorlanıyor. Seasonal naive'in kullandığı "dün bu saatteki değer" tam da pencerenin başında duruyor.

**Sıcaklık ve nem derin modellere uygun.** Bu değişkenler dış hava, radyasyon, havalandırma ve ısıtma arasındaki doğrusal olmayan etkileşimlerden doğuyor — modelin yakalayabileceği yapı var.

**CO₂ ve ışıkta basit yöntemler yeterli.** Her ikisi de güçlü ve düzenli günlük döngüye sahip. CO₂ ayrıca yüksek oranda deterministik bir kontrol politikasıyla sürülüyor. "Dün bu saatte ne vardı" bu değişkenler için neredeyse optimal.

**Kök bölgesinde ikili tablo.** Tuzluluk (EC) o kadar yavaş değişiyor ki "hiçbir şey değişmeyecek" demek en iyi tahmin — bu, sulama eylemi ile 3–6 saatlik EC sonucu arasındaki korelasyonun −0.03 ile 0.16 arasında çıkmasıyla da tutarlı. Buna karşılık su içeriği (WC) ve slab sıcaklığı iklimle daha güçlü bağlı ve derin modeller burada kazanıyor.

**Grodan sensörlerinin katkısı sınırlı ama fiziksel olarak anlamlı.** Eşleştirilmiş pencerelerde karşılaştırıldığında nem tarafında (HumDef, Rhair) tutarlı %3–8 iyileşme sağlıyor — slab su içeriği terlemeyi, terleme de nemi etkilediği için beklenen bir sonuç. Sıcaklıkta ise katkı sağlamıyor.

---

## 8. Dürüst sınırlamalar

1. **Mevsimsel dağılım kayması.** Eğitim kışı (Aralık–Nisan), test ilkbaharı (Mayıs) kapsıyor. Bu dönemde ışık **2.05 kat**, nem açığı **1.46 kat** artıyor. Model kolay bir dönemde öğrenip zor bir dönemde sınava giriyor. Doğrulama hatası daha ilk epoch'ta eğitim hatasının 2.2 katı — bu aşırı öğrenme değil, dağılım farkı.
2. **Tek sezon, tek tesis, tek çeşit.** Sonuçlar başka ürün veya iklim bölgesine doğrudan genellenemez.
3. **Örtüşen pencereler.** Raporlanan pencere sayıları bağımsız örnek sayısı değil; güven aralıkları olduğundan dar görünür.
4. **İstatistiksel anlamlılık testi henüz yapılmadı.** %2'lik farkların gürültü olup olmadığı test edilmeli.
5. **Takım kimliği karıştırıcı değişken.** Altı takımın kontrol politikaları farklı; havuzlanmış model "ortalama politika" öğreniyor.

---

## 9. Devam eden ve planlanan çalışmalar

| Çalışma | Amaç | Durum |
|---|---|---|
| Leave-One-Team-Out CV | Modelin görülmemiş bir kontrol politikasına genellenebilirliği | Kod hazır, koşulacak |
| Ortak-hava sızıntı kontrolü | Altı sera aynı hava verisini paylaşıyor; klasik LOTO'nun iyimserliğini ölçmek | LOTO ile birlikte |
| Hedef bazlı ayrı modeller | "Hedefe özgü strateji" iddiasının doğrudan kanıtı | Kod hazır, 48 koşu |
| Kapasite ablasyonu (small/medium/large) | Kapasite–genelleme ilişkisini tek değişkenli göstermek | Kısmen yapıldı |
| İstatistiksel anlamlılık | Farkların gürültü olmadığını göstermek | Planlandı |

---

## 10. Ana çıkarım

Bu çalışmanın en savunulabilir sonucu bir model sıralaması değil, bir **metodolojik gözlem**dir:

> Sera iklim tahmininde tek bir "en iyi model" yoktur. Doğru yöntem, hedef değişkenin fiziksel dinamiğine bağlıdır. Güçlü günlük döngüye sahip değişkenlerde (CO₂, ışık) basit mevsimsel yöntemler; doğrusal olmayan etkileşimlerle sürülen değişkenlerde (sıcaklık, nem) genişletilmiş evrişimli derin modeller; çok yavaş değişen değişkenlerde (kök tuzluluğu) persistence üstündür.

Bu sonuç, uygulamada **hedefe özgü hibrit tahmin stratejisini** destekler ve bilimsel raporlamada tek bir modelin üstünlüğünü iddia etmekten daha sağlam bir zemin sunar.
