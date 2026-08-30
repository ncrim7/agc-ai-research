# Karar Destek Katmanı
### AGC 2. Edisyon — Kalibrasyon, Bilgi Tabanı, Risk Motoru ve Geriye Dönük Değerlendirme

**Tarih:** Ağustos 2026 · **Kapsam:** Faz 3 — Decision Intelligence
**İlişki:** *Kısa Vadeli Tahmin*, *Uzun Vadeli Tahmin*, *Altı Kontrol Stratejisi* ve *Sera İşletmesinin Ekonomisi* raporlarının üzerine kurulur. Bu rapor önceki üç raporun bulgularını **çalışan bir sisteme** dönüştürür.

> **Bu belge nasıl okunmalı:** Ana gövde sistemin ne yaptığını, neyi iddia edip neyi etmediğini anlatır. Ekler yöntem ayrıntılarını ve düzeltilen tutarsızlıkları içerir. Bu bir demo değil, **ölçülmüş bir sistemdir** — her iddianın yanında onu destekleyen ölçüm vardır.

---

# ANA GÖVDE

## 1. Neden bu katman?

Önceki raporlar iki soruyu cevapladı: *"Sera durumu gelecekte ne olacak?"* ve *"Bu, paraya nasıl dönüşüyor?"*

Bu rapor üçüncü soruyu cevaplıyor: **tahminlere bakıp yetiştiriciye ne söylemeliyiz — ve o söylediğimize ne kadar güvenebiliriz?**

Cevap dört bileşenden oluşuyor:

1. **Kalibrasyon** — tahmin belirsizliğimiz gerçekten iddia ettiği kadar mı?
2. **Bilgi tabanı (DKB)** — hangi durumda hangi risk, hangi aksiyon?
3. **Risk motoru** — tahmini alıp uyarı üreten çalışan kod
4. **Geriye dönük değerlendirme** — bu uyarılar gerçekten isabetli mi?

Dördü de sırayla inşa edildi ve her biri bir öncekini sınadı.

## 2. Kalibrasyon: sistem ne zaman "bilmiyorum" demeli?

### 2.1 Sorun

Bir risk motoru *"%94 ihtimalle eşiği aşacak"* diyebilmek için tahmin aralıklarının **kalibre** olması gerekir — %95 dediğimiz aralık gerçekten vakaların %95'ini kapsamalı. Bu hiç test edilmemişti.

### 2.2 Yöntem

Aralıklar **doğrulama** setindeki hata yüzdeliklerinden kuruldu (test setinden değil — döngüsel olurdu), sonra **test** setinde ampirik kapsama ölçüldü. Üç kapsama testi:

| Test | Ne ölçer |
|---|---|
| Marjinal | Genel kapsama nominal seviyeye eşit mi |
| Sera bazlı | Her serada ayrı ayrı tutuyor mu |
| **Koşullu** | Uç değerlerde ve günün farklı saatlerinde tutuyor mu |

### 2.3 Bulgu: aralıklar aşırı güvenliydi

Global aralıklar marjinal olarak makuldü ama **uç değerlerde** çöktü:

| | Normal %80 | **Uç %20** |
|---|---|---|
| Ortalama kapsama | 0.93 | **0.855** (nominal 0.95) |

Risk motoru tam olarak uç değerlerde uyarı verir — yani sistem en çok ihtiyaç duyduğu yerde yanıltıcıydı.

### 2.4 Düzeltme denemeleri

**Mondrian conformal prediction** (sera × gündüz/gece katmanlı kalibrasyon) denendi. **Başarısız oldu** — uç değerlerde kapsama 0.855'ten 0.862'ye, marjinal kapsama ise 0.912'den 0.882'ye **düştü**. Sebep: yöntem kalibrasyon ve test verisinin değiştirilebilir (exchangeable) olmasını varsayar; mevsimsel kayma (doğrulama Nisan, test Mayıs) bu varsayımı ihlal ediyor.

**Dürüst şişirme** çalıştı: doğrulama setinin ilk %60'ıyla kalibre edilip son %40'ında uç değerlerde hedef kapsamayı tutturacak bir katsayı **doğrulama içinden** tahmin edildi, teste uygulandı. Test setine hiç bakılmadı.

| Yöntem | Uç değerlerde kapsama |
|---|---|
| Global (düzeltmesiz) | 0.855 |
| Mondrian conformal | 0.862 (başarısız) |
| **Dürüst şişirme** | **0.916** |

Ortalama şişirme katsayısı **1.35×**.

### 2.5 Sonuç: sistem her yerde konuşamaz

| Güven seviyesi | Anlamı | Hedef sayısı |
|---|---|---|
| **SAYISAL** | "%X ihtimalle eşiği aşacak" | 5 |
| **KALİTATİF** | "yükseliş eğiliminde, eşiğe yaklaşıyor" | 15 |
| **KAPSAM_DIŞI** | Değerlendirilmez | 2 |

Yalnızca kök bölgesi (`EC_slab1`, `EC_slab2`, `WC_slab1` 6h) sayısal olasılık iddia edebiliyor. Bu beklenmedik bir sonuçtu: sera iklim kontrolünde en çok konuşulan değişkenler (sıcaklık, nem, CO₂) belirsizlik bütçemizle olasılık üretmeye yetmiyor.

## 3. Bilgi tabanı (DKB): hangi kural, neden var

### 3.1 Yanlış başlangıç ve düzeltme

DKB ilk kurulduğunda *"hangi değişkeni iyi tahmin edebiliyoruz"* sorusundan yola çıkmıştı. Doğrusu *"hangi değişken net kârı etkiliyor"* olmalıydı. `Ekonomi` raporundaki bulgu bunu netleştirdi: kâr farkının %113'ü **lamba süresinden** geliyordu, ama DKB'de hiçbir elektrik/lamba kuralı yoktu. Bölüm 4 bu boşluğu kapatıyor.

### 3.2 Fizyolojik katman: iki eşik türü

**Zarf eşiği (veriden):** her seranın **kendi** normal aralığı (p5–p95). Mutlak eşik yerine bu tercih edildi çünkü mutlak eşik strateji tespit eder, risk değil: `EC > 6` kuralı Digilog'a sürekli alarm verirdi — oysa Digilog en yüksek Brix'i (8.86) alan takımdır, yüksek EC'yi bilerek uygulamıştır.

**Hasar eşiği (literatürden):** gerçek fizyolojik hasar sınırları, stratejiden bağımsız. Veride nadiren aşılıyor (çoğu %0.00) — bu **koruma amaçlı** olmasının işareti, hiçbir zaman tetiklenmemesi beklenir.

### 3.3 Uyarı kriteri: "sürekli sapma"

İlk tasarım "pencere içinde herhangi bir an eşiği geçti mi" (dokunma) idi. Bu, alarm yorgunluğu yarattı (bkz. Bölüm 5.2). Düzeltme: **tahmin edilen pencerenin tamamı** eşik dışında olmalı.

### 3.4 Ekonomik katman: dört deterministik kural

`Economics.pdf` fiyatları ve `ReadMe.pdf` formülleriyle, %0.2–2.2 hatayla doğrulanmış. Tahmin değil, hesap.

| Kural | Ölçtüğü | KRİTİK verebilir mi |
|---|---|---|
| **Birim maliyet** | Toplam değişken €/kg, altı takıma kıyasla | Evet |
| **Tarife verimliliği** | Pik saatteki elektrik **tüketim** payı | Hayır |
| **CO₂ eşik eğilimi** | Kümülatif dozajın sezon sonu projeksiyonu | Hayır |
| **Lamba kullanımı** | Mevsime duyarlı referansla kıyaslanan haftalık kWh | Hayır |

CO₂ ve lambanın hiçbir zaman KRİTİK verememesi bilinçli bir tasarım: bunlar **ekonomik risk**, fizyolojik hasar değil.

> **Düzeltilen hata — birim maliyet metriği.** İlk sürüm ısıtma/kg kullanıyordu. Ekonomi raporunda bunun net kârla korelasyonunun **ρ = −0.09** (öngörü gücü yok) olduğu, doğrusunun toplam değişken €/kg (**ρ = −1.00**) olduğu bulundu. Risk motoru buna göre düzeltildi.

> **Düzeltilen hata — tarife oranı.** İlk deneme pik *saatlerin* zaman oranını ölçüyordu — bu her zaman sabit 16/24 = 0.667'dir (pik aralığı 07:00–23:00 sabit 16 saat). Doğrusu pik saatlerdeki **tüketimin** toplam tüketime oranı. Düzeltme sonrası AICU %89.3'ten %35.5'e değişen, gerçekten ayırt edici bir sinyal verdi.

> **Düzeltilen hata — lamba referansı (dördüncü kez aynı desen).** İlk referans tüm sezon ortalamasıydı (yaz dahil), kış haftasıyla karşılaştırılınca **altı takım da** "ÇOK_YÜKSEK" çıktı — ayırt edici olmaktan çıktı. Bu, kalibrasyon analizinde ve maliyet tahmininde de karşılaşılan aynı hata deseniydi: kış dönemini tüm-sezon ortalamasıyla kıyaslamak.

### 3.5 Nihai kural sayısı

| Güven | Kural sayısı |
|---|---|
| SAYISAL | 65 |
| KALİTATİF | 195 |
| KAPSAM_DIŞI | 30 |
| **Toplam** | **290** (266 kullanılabilir) |

## 4. Risk motoru: tahminden uyarıya

### 4.1 İki katman, tek dil kuralı

Motor iki ayrı risk türü üretir ve ikisini asla karıştırmaz:

- **FİZYOLOJİK** — bitki stresi, hasar riski (Bölüm 3.2–3.3)
- **EKONOMİK** — maliyet riski (Bölüm 3.4)

Ve güven seviyesine göre **farklı kesinlikte konuşur**:

> **SAYISAL:** *"EC_slab1 6h içinde eşiği aşacak: tahmin 6.4, %95 aralığı [6.1, 6.7], olasılık %94"*
>
> **KALİTATİF:** *"Tair 3h içinde eşiği aşıyor: tahmin 29.5 [26.8, 32.2] · OLASILIK VERİLEMEZ, yalnızca eğilim"*
>
> **KAPSAM_DIŞI:** (hiçbir şey söylenmez)

### 4.2 Aksiyon önerisi sınırı

Model **nedensel değildir.** Veri setinde "cam açık" ile "sıcak" birlikte görünür çünkü takımlar hava sıcak **olduğu için** camı açtı. Bu yüzden:

| Yapılmaz | Yapılır |
|---|---|
| "Camı %50 açarsan sıcaklık 2°C düşer" (büyüklük iddiası) | "Havalandırmayı artır" + yön + **takım referansı** + "büyüklük tahmin edilemez" uyarısı |

Her aksiyon önerisine bir takım referansı eklenir: *"Digilog en serin rejimi uyguladı ve en yüksek Brix skorunu aldı."* Aksiyonun **yönü** fizikten ve altı takımın gerçek pratiğinden gelir; **büyüklüğü** iddia edilmez.

### 4.3 Alarm yorgunluğu ve çözümü

**Sorun ölçüldü:** "dokunma" kriteriyle (pencerede herhangi bir an eşik dışı) sistem pencerelerin **%91.2'sinde** en az bir uyarı üretiyordu — günde ~22 saat, ortalama 5.3 kural aynı anda tetikli. Kullanılamaz.

**Kök neden:** zarf eşikleri p5/p95 olduğu için her kural tanım gereği zamanın ~%10'unda tetikleniyor. 30 kural × %10 → en az birinin tetiklenme olasılığı ~%90.

**Çözüm:** "sürekli sapma" kriteri — tahmin edilen pencerenin **tamamı** eşik dışında olmalı.

| Kriter | Aktif zaman | Olay oranı | Precision | Recall |
|---|---|---|---|---|
| Dokunma | %91.2 (günde 21.9 saat) | %19.3 | 0.790 | 0.780 |
| **Sürekli sapma** | **%31.4 (günde 7.5 saat)** | **%3.1** | 0.701 | 0.742 |

> **Bu düzeltme koda ilk seferde işlenmemişti.** Backtest'te bulunduktan sonra `agc_risk_motoru.py`'nin `_fizyolojik` metodu hâlâ tek nokta karşılaştırması yapıyordu. Rapor yazılmadan önce bu tutarsızlık fark edildi ve düzeltildi (bkz. Ek D).

## 5. Geriye dönük değerlendirme: sistem gerçekten isabetli mi?

### 5.1 Yöntem — ve bir ölçüm kusurunun düzeltilmesi

İlk backtest, modelin **terminal** tahminini (t+6h anındaki değer) gerçek-durumun **pencere içi maksimumuyla** karşılaştırıyordu — tutarsız bir kıyas. Recall'ı yapay olarak düşürüyordu (KALİTATİF kurallarda 0.689 → 0.425).

Düzeltme: modeller zaten 72 adımlık trajektorinin tamamını üretiyor. `pred_max` ↔ `true_max` (elmayla elma) karşılaştırması yapıldı.

| Karşılaştırma | Recall |
|---|---|
| Terminal ↔ Terminal | 0.740 |
| Terminal ↔ Pencere (tutarsız) | 0.500 |
| **Pencere ↔ Pencere (referans)** | **0.829** |

### 5.2 Nihai performans

**32.842 pencere, test dönemi (Mayıs):**

| | Gerçekten oldu | Olmadı |
|---|---|---|
| **Uyarı verdi** | 12.056 | 2.647 |
| **Uyarı vermedi** | 2.487 | 126.630 |

**Precision 0.820 · Recall 0.829 · F1 0.824**. Temel olay oranı %13.9 → precision **5.9 kat** rastgeleden iyi.

En güçlü kural `EC_slab1 3h`: precision 0.808, **recall 0.981** — neredeyse hiçbir olayı kaçırmıyor.

### 5.3 Susma kararı fazla temkinliydi — düzeltildi

İlk backtest'te kapsam dışı bırakılan `CO2air`, `HumDef`, `Rhair(6h)` için *"uyarsaydık ne olurdu"* testi yapıldı:

| Hedef | Uyarsaydık precision |
|---|---|
| CO2air | 0.766–0.774 |
| HumDef | 0.735–0.749 |
| Rhair (6h) | 0.688 |

Değerlendirilen hedeflerin ortalamasından (0.822) çok kötü değil. Bu beş hedef `KALİTATİF`'e yükseltildi (Bölüm 3.5, Ek C). **Yalnızca `Tot_PAR` gerçekten başarısız** (precision 0.33–0.37) — kapsam dışında kaldı.

### 5.4 Modelin şekil doğruluğu

Tahmin edilen trajektorinin pencere-içi salınımı, gerçeğin salınımına ne kadar yakın?

| Hedef | Oran (tahmin/gerçek genlik) |
|---|---|
| EC_slab1 | 0.61 (düzleştiriyor) |
| WC_slab | 0.90–0.96 |
| Tair, CO2air, Rhair, t_slab | 1.00–1.05 (doğru) |

EC_slab'de model tepe noktalarının yalnızca %61'ini üretiyor — ama bu **tespit performansını bozmuyor** (recall 0.98), çünkü EC yavaş sürüklenir ve eşiği geçtiğinde uzun süre üstünde kalır.

## 6. Sonuç

**Sistem ölçülmüş bir karar destek katmanıdır, demo değildir.** Her iddianın bir dayanağı var:

| İddia türü | Dayanak |
|---|---|
| "%94 ihtimalle eşiği aşacak" | Kalibrasyon ölçümü (5 hedef-ufuk) |
| "Yükseliş eğiliminde" | Yön güvenilir, büyüklük değil (15 hedef-ufuk) |
| (Sessizlik) | Belirsizlik çok yüksek (2 hedef-ufuk) |
| "Bu aksiyon şu kadar eder" | Economics.pdf + ReadMe.pdf, %0.2–2.2 hatayla doğrulanmış |
| "X takımı böyle yaptı" | Altı gerçek strateji, ölçülmüş sonuç |
| Genel isabet | Precision 0.82, recall 0.83, backtest üzerinde ölçüldü |

**En büyük ders:** sistem tasarlanırken bulunan düzeltmelerin bazıları **koda hiç işlenmemişti** (Bölüm 3.4, 4.3). Bu rapor yazılmadan önce ikisi de bulunup düzeltildi. Ders: bir bulguyu belgelemek, onu uygulamakla aynı şey değildir — ikisi ayrı ayrı doğrulanmalı.

---
---

# EKLER

## Ek A — Kalibrasyon yöntemi ayrıntıları

Aralıklar %95 nominal seviyede, doğrulama setinin yüzdelikleriyle kuruldu. Dürüst şişirme prosedürü: doğrulama setinin ilk %60'ı ile ham aralık hesaplanır; son %40'ında, uç değerlerde (medyan sapmasının üst %20'si) hedef kapsamayı tutturacak minimum şişirme katsayısı bulunur; bu katsayı **teste hiç bakılmadan** uygulanır.

## Ek B — DKB kural yapısı

Her kural: `Hedef → Sera → Eşik türü (ZARF/HASAR) → Eşik → Yön → Risk açıklaması → Aksiyon ailesi → Maliyet kalemi → Kısıt → Güven seviyesi → Takım referansı → Kaynak`.

Zarf eşikleri sera × hedef × dönem (tümü/gündüz/gece) bazında p5/p95 yüzdelikleridir. Hasar eşikleri literatürden alınmış **taslak** değerlerdir ve akademik kaynak gösterilerek teyit edilmelidir.

## Ek C — Değiştirilen dosya: `decision_knowledge_base_v3.csv`

Orijinal DKB'den farkı: `CO2air` (3h, 6h), `HumDef` (3h, 6h), `Rhair` (6h) hedeflerinin güven seviyesi `KAPSAM_DISI`'dan `KALİTATİF`'e yükseltildi. Gerekçe her satırda `guven_gerekce` alanında backtest precision değeriyle birlikte kayıtlıdır. `Tot_PAR` kasıtlı olarak değiştirilmedi: hem gerçekten düşük performans (precision 0.33–0.37) hem de deterministik hesaplanabilir olması (sürücü öznitelik, tahmin hedefi değil) nedeniyle.

## Ek D — Rapor yazılmadan önce bulunan ve düzeltilen iki tutarsızlık

**D.1 · DKB güncellemesi koda işlenmemişti.** Bölüm 5.3'teki bulgu (susma kararının fazla temkinli olması) ilk bulunduğunda yalnızca konuşmada kaydedilmiş, `decision_knowledge_base.csv` dosyasına yansıtılmamıştı. Bu rapor yazılmadan hemen önce fark edildi ve `decision_knowledge_base_v3.csv` olarak düzeltildi.

**D.2 · Risk motoru, kendi çözdüğü alarm yorgunluğu sorununu kullanmıyordu.** Bölüm 4.3'teki "sürekli sapma" kriteri yalnızca backtest script'inde (`agc_backtest_v2.py`) mevcuttu; üretim risk motorunda (`agc_risk_motoru.py`) hâlâ tek nokta karşılaştırması kullanılıyordu. Düzeltme: `_fizyolojik` metodu artık pencere bilgisi (`tahmin_min`/`tahmin_max`) varsa sürekli sapma kriterini uygular; yoksa eski davranışa geriler ama bunu mesaj içinde `[DOKUNMA — tek nokta, daha az güvenilir]` olarak açıkça işaretler, sessizce geçmez.

Sekiz testle doğrulandı; en belirleyici test: aynı "son değer" tahmini, pencerenin geçmişine (geçici sıçrama mı, sürekli sapma mı) bağlı olarak bir durumda 0 uyarı, diğerinde 1 uyarı üretiyor.

## Ek E — Bilinen sınırlamalar

**E.1 · Nedensellik yok.** Tüm aksiyon önerileri korelasyonel gözleme dayanır. Takımlar rastgele politika uygulamadı.

**E.2 · Örneklem altı takım.** Ekonomik referanslar (birim maliyet, tarife payı, lamba kullanımı) n=6 üzerindendir.

**E.3 · Hasar eşikleri taslak.** Literatürden alınan fizyolojik hasar sınırları akademik kaynakla teyit edilmemiştir.

**E.4 · Geriye dönük değerlendirme yalnızca 3h/6h ufkunu kapsar.** 12h/24h model ailesi için kalibrasyon hiç yapılmadı; bu ufuklarda karar katmanı henüz mevcut değildir.

**E.5 · Test dönemi ekonomik olarak küçük.** Backtest Mayıs ayında yapıldı — sezon maliyetinin yalnızca %1.7'si (bkz. Ekonomi raporu Ek C). Kış döneminde performansın farklı çıkma ihtimali test edilmemiştir.

**E.6 · Ekonomik kuralların fayda tarafı belirsiz.** Lamba kullanımı kuralının maliyet tarafı kesindir (R²=0.86); üretim/Brix faydası bu örneklemle istatistiksel olarak kurulamamıştır (bkz. Ekonomi raporu Bölüm 5).
