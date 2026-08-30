# AGC Projesi — Karar Günlüğü ve Durum

**Son güncelleme:** Ağustos 2026 · **Faz:** Karar destek katmanı tamamlandı; dört rapor tutarlı (tahmin, strateji, ekonomi, karar katmanı)

---

## 1. KİLİTLİ KAPSAM

24 saatlik çok değişkenli geçmişten sera durumu tahmini. Altı sera (AGC 2. Edisyon, 16 Ara 2019 – 30 May 2020, 286.854 satır).

| | Değer |
|---|---|
| Girdi | 288 adım (24 saat), tüm sensörler |
| Çıktı | 72 adım (6 saat); 3h = ilk 36 adım. **12h/24h için ayrı 288-adım aile** (bkz. Bölüm 8) |
| Kaydırma | 12 adım (1 saat) |
| Bölme | Sera bazında kronolojik %70/15/15 |
| Core hedefleri | Tair, Rhair, CO2air, HumDef, Tot_PAR |
| Grodan hedefleri | EC_slab1/2, WC_slab1/2, t_slab1/2 |
| Baseline'lar | Persistence, Seasonal Naive, Moving Average, Linear Trend, Ridge |
| Derin modeller | GRU, LSTM, TCN |

**CaseRAG / action-conditioned retrieval fikri terkedildi.** Semantic Decision Intelligence Platform (LLM+RL ajan, Knowledge Graph, Medallion mimari, DOC-013→022 serisi) de terkedildi.

**YENİ — Tot_PAR'ın rolü değişti (Bölüm 10).** `ReadMe.pdf` incelemesi sonrası: `Tot_PAR` **deterministik hesaplanabilir** bir değişken (dış PAR × örtü/perde geçirgenlikleri + lamba katkısı). Tahmin hedefi olarak DKB'de `KAPSAM_DISI` — bilinçli karar, kalibrasyon eksikliği değil.

---

## 2. HANGİ DOSYA GEÇERLİ — EN KRİTİK BÖLÜM

### ✅ GEÇERLİ (checkpoint'ten doğrulanmış / formülle doğrulanmış)

| Dosya | İçerik |
|---|---|
| `metrikler_tam.csv` | Ridge + tüm derin modeller · MAE, RMSE, R² |
| `pencere_hatalari_v2.parquet` | Ridge + derin · pencere başına hatalar |
| `pencere_hatalari.parquet` | 4 analitik baseline + derin |
| `adim_bazli_hatalar.csv` | Adım bazında hata eğrisi |
| `all_forecasting_results_long.csv` | Baseline'lar (analitik 4'ü için kaynak) |
| `loto_results.csv` / `loto_baseline_results.csv` | LOTO derin / baseline |
| `deep_model_results_multi.csv` | Çok hedefli derin |
| `trajektori_ozeti.parquet` | **YENİ.** Pencere içi max/min/son — backtest'in referans karşılaştırması bunu kullanır |
| `kalibrasyon_ham.parquet` | **YENİ.** Doğrulama+test tahmin/gerçek çiftleri, kalibrasyon analizi girdisi |
| `maliyet_serisi.parquet` | **YENİ.** 5 dakikalık maliyet serisi, resmi Resources.csv ile %0.2–2.2 hatayla doğrulandı |
| `strateji_sonuc_tablosu.csv` | **YENİ.** Altı takım kaynak/üretim/kalite (fiziksel birimler — **euro'ya çevrilmeden yorumlanmamalı**, bkz. Bölüm 9) |
| `ec_brix_regresyon.csv` / `ekonomik_zemin.csv` | **YENİ.** EC→Brix denendi, **ölçülemedi** (bkz. Bölüm 4) |
| `decision_knowledge_base_v3.csv` | **YENİ, GÜNCEL DKB.** v1/v2 değil bu kullanılmalı — backtest kanıtıyla düzeltilmiş güven seviyeleri |
| `dkb_zarf.csv` | Sera bazlı normal çalışma zarfları (p1/p5/p50/p95/p99) |
| `dkb_ekonomik_ek.csv` | **YENİ.** Dört ekonomik kural örnek çıktısı |
| `backtest_v2_detay.csv` | **YENİ, NİHAİ backtest.** Precision 0.820, recall 0.829 (C_pen_pen modu referans alınmalı) |

### ❌ KULLANMA

| Dosya | Neden |
|---|---|
| `deep_model_results_single.csv` | Öksüz set — `metrikler_tam.csv` kullanılır |
| `irrigation_cases_v2_with_resources.parquet` | Join patlaması bug'ı |
| **`decision_knowledge_base.csv` (v1, ekonomik-öncesi)** | **YENİ.** `CO2air`, `HumDef`, `Rhair(6h)` yanlışlıkla `KAPSAM_DISI` — backtest kanıtı `KALİTATİF` olması gerektiğini gösterdi. `decision_knowledge_base_v3.csv` kullanılmalı. |
| `backtest_ozet.csv` / `backtest_detay.csv` (v1, "A_terminal"/"B_ter_pen" modları) | **YENİ.** Terminal-pencere karşılaştırması tutarsız (elmayla armut); `backtest_v2_detay.csv`'deki `C_pen_pen` modu referans alınmalı |
| `hava_oracle_sonuclari.csv` / `hava_oracle_cok_tohum.csv` | **YENİ.** Deney sonuçsuz kaldı — mimariye özgü artefaktlar (GRU'nun sıfır-dolgu girdisiyle başa çıkamaması) gerçek etkiyi maskeledi. "Hava tahmini işe yaramıyor" DENEMEZ, "ölçülemedi" denir. |
| `maliyet_v3_politika_kis.csv` (politika ucuzluk siralaması) | Tahmin edilen sütun modelin politika ayırt edemediğini gösteriyor (ρ=+0.09); yalnızca **gerçek** kış maliyeti net kârla güçlü ilişkili (ρ=−0.94), tahmin değil |

**Doğrulama kanıtları:** `metrikler_tam.csv` ↔ `pencere_hatalari.parquet` max fark 5.91e-11 · `maliyet_serisi.parquet` ↔ `Resources.csv` ısı %0.2, elektrik %2.2, CO₂ %1.2 hata.

---

## 3. KİLİTLİ MİMARİ KARARLAR — yeniden önerme

| Karar | Detay |
|---|---|
| **Artık (residual) tahmini** | Model çıpadan sapmayı öğrenir. `RESIDUAL_MODE = True` |
| **Hedef başına çıpa** | Tair, Rhair, CO2air, HumDef, Tot_PAR, t_slab1/2 → seasonal naive. EC/WC_slab → persistence |
| **Model boyutu** | `MODEL_SIZE = "small"` — doğrulama kaybına göre, test setindeki fark seçimde KULLANILMADI |
| **SP kolonları atıldı** | Token bazlı filtre: `"sp" in c.split("_")` |
| **LED NaN → 0** | Off-state, %94.8–98.2 örtüşme |
| **Slab çapraz onarım** | Yalnızca korelasyon ≥0.7 |
| **Zaman ekseni** | `.dt.round("5min")` zorunlu |
| **hour_sin / hour_cos / cum_Iglob_today** | KAPSAM DIŞI. Maliyet tahmininde de `pik_pay` (doğrudan ekonomik büyüklük) kullanıldı, döngüsel kodlama değil |
| **Anlamlılık** | HAC (gecikme 30) + blok bootstrap (60, 2000) + BH-FDR |
| **YENİ — CO₂ birimi** | `ReadMe.pdf`'de `co2_dos` için "kg/ha hour" yazıyor — **YANLIŞ**. Ampirik doğrulama katsayının tam **10000** olduğunu gösterdi; gerçek birim kg/m²/saat. Resmi dokümantasyon hatası, düzeltilmiş kullanılmalı. |
| **YENİ — Risk kriteri: "sürekli sapma"** | Uyarı kriteri "pencerede herhangi bir an eşik dışı" (dokunma) DEĞİL, "pencerenin tamamı eşik dışı". Dokunma kriteri alarm oranını günde 21.9 saate çıkarıyordu; sürekli sapma 7.5 saate indirdi. |

---

## 4. TEST EDİLİP REDDEDİLEN / ÖLÇÜLEMEYEN HİPOTEZLER — tekrar önerme

**Kapasite küçültme.** Reddedildi. Genel etki +0.6% (zararlı). İyileşme çıpadan (−42.1%).

**Automatoes'un ayırt edici stratejisi.** Reddedildi. Uzaklığı altı takımın en düşüğü (0.783). Gerçek mekanizma: kök bölgesi oynaklığı (ρ=+0.83), genelleme değil içsel tahmin edilebilirlik (kronolojik↔LOTO ρ=+1.00).

**Drenaj oranı ↔ EC tahmin edilebilirliği.** Reddedildi, ters yönde (ρ=−0.31).

**YENİ — EC → Brix ilişkisi.** **Ölçülemedi.** Takım-içi korelasyon ρ=−0.007, p=0.964. Tasarımın tespit edebileceği minimum etki 0.445 Brix/(dS/m); literatürdeki tipik etki ~0.40 — sınırın altında. Ayrıca bizim EC aralığımız (4.2–7.3) literatürün test ettiği aralıktan (2.5–5.0) yüksek. **PAR → Brix ölçüldü** (t=+4.81, zaman kontrolünden sonra da sağlam) ama **lambaya nedensel olarak genellenemez** — Digilog en çok elektrik harcayan takım olmasına rağmen ortalama PAR katkısı düşük çıktı; ölçülen ilişkinin çoğu güneşten geliyor.

**YENİ — Hava kâhini deneyi (gelecek havayı bilmenin değeri).** **Ölçülemedi**, iki turda da. Tek koşulu ilk deneyde iki mimari zıt yön gösterdi (korelasyon −0.58). Beş tohumlu tekrarda da (eşleştirilmiş fark analizi) mimariler arası korelasyon −0.08 çıktı — GRU'nun sıfır-dolgulu girdiyle dejenere bir çözüme kilitlenmesi (temel model varyansı ~0) gerçek etkiyi maskeledi. **Üçüncü deneme yapılmadı** (kullanıcı kararı — zaman kısıtı, ana hedef zaten netti). Sonuç: "hava tahmini işe yaramıyor" DEĞİL, "3-6 saat ufkunda bu tasarımla ölçülemedi".

**YENİ — Maliyet tahmininde artık mimarisi.** **Başarısız — temiz negatif sonuç.** Çıpa (seasonal naive: "dün aynı saatteki 6 saat") beş kayan-başlangıç katmanının **hepsinde** kazandı (MAE 0.370 vs artık 0.604-0.637). Hava eklemek %63-72 kötüleştirdi. Açıklama: hava günden güne otokorelasyonlu, politika kararlı; "dün ne harcadın" zaten ikisini birden kodluyor. **Hava kâhini deneyiyle tutarlı** — iki bağımsız deney aynı yapısal gerçeği gösteriyor: kısa ufukta ek hava bilgisi katkı sağlamıyor.

---

## 5. TEKRARLAYAN HATA DESENİ — dikkat, beşinci kez olmasın

**"Mevsimsel referans karıştırma"** bu projede **dört kez** ayrı ayrı ortaya çıktı:

1. **Kalibrasyon:** doğrulama Nisan, test Mayıs — tüm-dönem yüzdeliğiyle aralık kurulunca uç değerlerde kapsama 0.855'e düştü
2. **Maliyet tahmini v1:** tek kronolojik bölme — test %1.7 (Mayıs, günlük 1.13 cent), eğitim %90.2 (kış, günlük 15.16 cent) → R²=−161
3. **DKB ekonomik ek, ilk deneme:** sezon-sonu demo noktası seçildi — altı sera aynı takvim gününde, lambalar kapalı → tüm kurallar sabit/sıfır çıktı
4. **Lamba kuralı referansı:** tüm-sezon ortalaması (11.4 kWh/hafta, yaz dahil) kış haftasıyla kıyaslanınca altı takım da "ÇOK_YÜKSEK" çıktı

**Genel ders:** Bu veri setinde kış ve yaz maliyet/davranış açısından bambaşka rejimler. **Herhangi bir yeni analiz "tüm sezon ortalaması" veya "sezon sonu" gibi tek bir referans noktası kullanmadan önce, o referansın karşılaştırılacağı dönemle aynı mevsimden geldiğini doğrulamalı.**

**5. tekrar — DKB v3'ün zarf eşikleri.** `agc_decision_kb.py`'deki `zarf_hesapla` yalnızca gündüz/gece ayrımı yapıyor, **mevsim ayrımı yok**. Yeni sohbette (Faz 6 raporu, Bölüm 5.3) bu ölçüldü: tüm-sezon yüzdelikleriyle kurulan eşiklerde kuralların %3'ü tasarım oranında, %45'i hiç, %32'si tasarım oranının 4 katından fazla tetiklendi — mevsim içi yüzdeliklere geçilince dengesizlik medyanı **153.6×'ten 1.5×'e** indi. `decision_knowledge_base_v3.csv`'deki zarf eşikleri bu yüzden **gözden geçirilmeli**; mevsim-içi (kış/ilkbahar ayrı) p5/p95 ile yeniden hesaplanmalı. Bu, listedeki dördüncü örneğin farkına varılmasından *sonra bile* aynı hataya beşinci kez düşüldüğünü gösteriyor — kontrol listesi tek başına yeterli değil, her yeni referans hesabında açıkça sorulmalı.

---

## 6. ANA SONUÇLAR (nihai tahmin raporu, 3h/6h)

**32 hedef–ufuk kombinasyonu, tamamı test edildi:** Derin öğrenme anlamlı üstün 11 · Baseline anlamlı üstün 8 · Fark yok 13.

**Hedefe özgü strateji:** Sıcaklık/kök suyu → TCN · CO₂/ışık → Seasonal Naive · Kök tuzluluğu → Persistence · Nem/slab sıcaklığı → Ridge.

> **YENİ — Kısmen değişti (12h/24h, Bölüm 8):** "TCN her koşulda en iyisidir" iddiası yalnızca **kısa ufukta** (3-6h) doğru. 24 saatte GRU öne geçiyor (16 hedefte GRU 7, TCN 5, LSTM 4). Sebep: TCN'in avantajı pencerenin başındaki bilgiyi görebilmesiydi; 24 saatlik çıktıda o bilgi zaten çıpanın içinde, avantaj tükeniyor.

**Metodolojik bulgular:** Etkin örneklem 552 · Mevsimsel kayma (ışık 2.05×, nem açığı 1.46×) · Naif test 10 yanlış pozitif · LOTO bedeli %2.3–4.6.

---

## 7. TESLİM EDİLENLER — dört rapor, tutarlı

| Rapor | Sayfa | Durum |
|---|---|---|
| `AGC_Nihai_Rapor` (3h/6h) | 27 | Kilitli |
| `Uzun_Vadeli_Tahmin_12h_24h` | — | Ayrı sohbette üretildi (bkz. Bölüm 8) |
| `AGC_Strateji_Sonuc_Raporu` **Sürüm 2** | 9 | Ekonomik düzeltmelerle güncellendi |
| `AGC_Ekonomi_Raporu` | 7 | Net kâr, maliyet ayrıştırma, aydınlatma ekonomisi |
| `AGC_Karar_Katmani_Raporu` | 8 | Kalibrasyon, DKB, risk motoru, backtest |

**Tüm raporlar birbirine çapraz referans veriyor ve tutarlı.** Ana tahmin raporu (3h/6h) kilitli; TCN iddiası düzeltilmedi (bkz. Bölüm 11, bekleyen iş).

---

## 8. TAMAMLANDI — uzun ufuk (12h / 24h)

Ayrı bir sohbette yürütüldü, 288-adım çıktılı ayrı model ailesiyle (72-adım aile korunarak). Rapor: `Uzun_Vadeli_Tahmin_12h_24h.docx`.

**Doğrulanan iddialar:** LOTO transfer bedeli 24h'de kök bölgesinde %10-27 (3h/6h'deki %2-5'ten farklı, doğru — farklı ufuk). EC_slab 6h'de 288-adım aile 72-adım aileden daha iyi (0.0656 vs 0.076) — uzun ufka zorlanan model yavaş sürüklenme dinamiğini öğrenmiş, bu kısa ufukta da işe yaramış.

**Düzeltilmiş iddia:** "TCN her koşulda en iyi" → 24h'de GRU öne geçiyor.

**Bölüm 3.3'ün ilkesi:** "Kazanç, referansın bıraktığı boşlukla orantılı" — başka veri setlerine taşınabilir bir kural.

**YENİ — Ek B.3'te bulunan gerçek sayısal hata (kilitli Nihai Rapor'un kendisinde).** 12h/24h sohbetinde, `agc_anlamlilik.py`'nin birleşik çerçeve (Ridge dahil, 11 model) ile yeniden çalıştırılması hem §4.4 tablosunu (13 fark yok · 11 derin · 8 baseline) hem de Ridge'in tek tek katsayılarını (Rhair 4.6537, HumDef 1.2774, vb.) rapordakiyle **birebir doğruladı** — §4.4 sağlam. Ama Ek B.3'ün istatistik tablosunda gerçek bir hata bulundu:

| Satır | Raporda yazan | Ölçümle doğrulanan |
|---|---|---|
| Naif Diebold-Mariano | 26 / 32 | **29 / 32** |
| HAC + blok bootstrap + FDR | 16 / 32 | **19 / 32** |
| "10 fark yanlışlıkla gerçek sayılacaktı" | 10 | 10 ✓ (29−19=10, 26−16=10 de aynı farkı verdiği için hata ilk bakışta fark edilmemiş) |

Muhtemel sebep: erken bir koşudan (26/16) kopyalanıp güncellenmemiş. **Nihai Rapor kilitli olduğu için ana metne dokunulmadı**; bu, GitHub'a aktarılırken bir erratum notu olarak taşınmalı.

**YENİ — Reproducibility notu.** §4.4'ü üreten "birleştirme" (iki ayrı parquet dosyasının — analitik baseline'lar ve Ridge — tek çerçevede birleştirilmesi) hiçbir script'te ayrı bir adım olarak yok. `agc_anlamlilik.py`'yi varsayılan haliyle (tek dosya) çalıştıran biri rapordan **farklı** bir sonuç (17 derin/3 baseline/12 fark yok) alır. Sonuç yanlış değil — girdi eksik. GitHub'a taşınırken bu açıkça belgelenmeli, aksi halde script'i çalıştıran biri raporla uyuşmayan bir çıktı alıp güvenilirlik sorgulayabilir.

---

## 9. TAMAMLANDI — strateji-sonuç analizi (Sürüm 2)

### 9.1 Sürüm 1'in hatası ve düzeltmesi

İlk sürüm kaynakları **fiziksel birimlerle** (MJ ısı, kWh elektrik) karşılaştırdı, ısıtma farkını (2.7 kat) ana bulgu olarak sundu. **Yanlıştı.**

`Economics.pdf` ve `ReadMe.pdf` okunduktan sonra (Bölüm 10) euro'ya çevrildi:

| Metrik | Net kârla Spearman ρ |
|---|---|
| Isıtma / kg | **−0.09** (öngörü gücü yok) |
| **Euro / kg** | **−1.00** (mükemmel sıralama) |

Gerçek birim maliyet farkı **1.24 kat**, kaynağı **elektrik** (toplam değişken maliyetin %79-90'ı), ısıtma değil (%6-18'i).

### 9.2 İki veri onarımı (hâlâ geçerli)

Reference/Production: yıl yazım hatası (+365 gün). Reference/TomQuality: ayraç hatası (sekme+virgül karışımı, kolon kayması) — tarih hatası DEĞİL, yapısal hata.

### 9.3 Doğrulanan ilişkiler (değişmedi)

Yavaş olgunlaşma→yüksek briks (ρ=+0.71) · Sıcak sera→hızlı salkım (−0.66) · Sıcak sera→düşük briks (−0.54). Bunlar literatürle bağımsız doğrulama sağlıyor.

### 9.4 Mekanizma — elektrik çözüldü, ısıtma açık

Kış maliyet farkının kaynağı: elektrik %112, ısıtma −%12. Elektrik farkının kaynağı: **lamba süresi** %113 (yoğunluk herkeste aynı, ~%99.9), tarife zamanlaması −%13. Isıtma farkının mekanizması **hâlâ bulunamadı** (havalandırma ρ=+0.43, sıcaklık entegrasyonu ρ=−0.20 — ikisi de zayıf).

---

## 10. TAMAMLANDI — resmi dokümantasyon incelendi

`ReadMe.pdf` ve `Economics.pdf` okundu. Bu, projenin ekonomik zeminini kurdu.

**Elde edilen deterministik formüller:**
```
Isı akısı = (t_rail − t_air)·2.1 + (t_grow − t_air)·0.62   [W/m²]
Elektrik  = HPS 81 W/m² + LED (mavi 7.27, kırmızı 25.3, uzak-kırmızı 6.23, beyaz 22.72)
Tot_PAR   = dış PAR × örtü(0.5) × perde geçirgenlikleri + lamba PAR'i
```

**Resmi fiyatlar:** Isı 0.0083 €/MJ · Elektrik 0.08€/kWh (07-23) / 0.04€/kWh dışı · CO₂ 0.08€/kg ilk 12kg/m², sonra 0.20€/kg · Brix 0.35€/kg (sezon boyunca sabit) · B sınıfı yarım fiyat.

**Bulunan dokümantasyon hatası:** CO₂ birimi (bkz. Bölüm 3).

---

## 11. TAMAMLANDI — Ekonomi Raporu

### 11.1 Net kâr hesabı ve `iterrows()` bug'ı

İlk hesap `iterrows()` kullanıyordu, tip bozulmasına yol açtı. Digilog'un geliri 29.21 yerine gerçekte **34.42 €/m²**. Düzeltme sonrası sıralama **gerçek yarışma sonucuyla eşleşti**: Automatoes 8.15 €/m² net kâr ile birinci (birim maliyeti 1.294 €/kg, altı takımın en düşüğü), ikinciden %25 önde. Bu, düzeltmenin bağımsız doğrulamasıdır.

### 11.2 Yarışmayı kış maliyeti belirledi

Kış dönemi maliyeti ↔ net kâr: **ρ=−0.94**. Nicelik: 6 saatte 0.89 cent fark × 664 pencere = 5.93 €/m² ≈ gerçek kâr farkı 5.55 €/m² (**%107 açıklama**).

### 11.3 Aydınlatma ekonomisi — maliyet kesin, fayda belirsiz

| İlişki | Etki (1000 saat) | R² |
|---|---|---|
| Lamba → elektrik maliyeti | +6.98 €/m² | **0.86** |
| Lamba → üretim değeri | +3.09 €/m² | 0.36 (sıfırı içeriyor) |
| Lamba → Brix değeri | +2.23 €/m² | 0.39 (sıfırı içeriyor) |
| **Net** | **−1.67 €/m²** | |

Nokta tahmini negatif ama n=6 ile fayda tarafı istatistiksel olarak kurulamıyor. **Nedensel iddia yok.**

### 11.4 Tarife zamanlaması — risksiz kaldıraç

Elektrik pik saatte (07-23) 2 kat pahalı. Altı sera toplamı **2.18 €/m²** kaçırılmış tasarruf, saf yeniden fiyatlama (aynı kWh, farklı saat).

---

## 12. TAMAMLANDI — Karar Destek Katmanı

### 12.1 Kalibrasyon

Global aralıklar uç değerlerde aşırı güvenliydi (kapsama 0.855, nominal 0.95). Mondrian conformal **başarısız oldu** (mevsimsel kayma exchangeability'yi bozuyor — kapsama 0.862'ye çıktı ama marjinal 0.882'ye düştü). **Dürüst şişirme** (doğrulama içinden tahmin edilen katsayı, teste bakılmadan) uç kapsamayı 0.916'ya çıkardı.

**Nihai güven dağılımı (`decision_knowledge_base_v3.csv`):** SAYISAL 5 (yalnızca EC_slab, WC_slab 6h) · KALİTATİF 15 · KAPSAM_DISI 2 (Rhair/CO2air/HumDef artık KALİTATİF; yalnızca Tot_PAR — deterministik hesaplanabilir — ve bir diğeri kapsam dışı kaldı).

### 12.2 DKB — iki eşik türü, dört ekonomik kural

Zarf eşiği (veriden, sera-özgü p5/p95) + hasar eşiği (literatürden, taslak). Dört deterministik ekonomik kural: birim maliyet (€/kg), tarife verimliliği (tüketim ağırlıklı pik payı — zaman oranı DEĞİL, o sabit 16/24), CO₂ eşik eğilimi (projeksiyon, aşım değil), lamba kullanımı (mevsime duyarlı referans).

**Düzeltilen hatalar bu katmanda:**
- Birim maliyet metriği: ısıtma/kg → euro/kg (Bölüm 9.1)
- Tarife oranı: zaman payı (sabit 0.667) → tüketim payı (gerçekten ayırt edici)
- Lamba referansı: tüm-sezon → mevsime duyarlı (Bölüm 5, 4. tekrar)

### 12.3 Risk motoru

İki katman (FİZYOLOJİK, EKONOMİK), güven seviyesine göre farklı dil (SAYISAL: olasılık · KALİTATİF: yön · KAPSAM_DIŞI: sessizlik). Aksiyon önerisi nedensel değil — yön + takım referansı + "büyüklük tahmin edilemez" uyarısı.

### 12.4 Backtest — nihai performans

Terminal-pencere tutarsızlığı düzeltildi (referans: `C_pen_pen`, pencere↔pencere).

**Precision 0.820 · Recall 0.829 · F1 0.824.** Temel olay oranı %13.9 → 5.9 kat rastgeleden iyi. En güçlü kural EC_slab1 3h (recall 0.981).

**Alarm yorgunluğu:** "dokunma" kriteriyle günde 21.9 saat aktif → "sürekli sapma" ile 7.5 saat.

**Susma fazla temkinliydi:** CO2air/HumDef/Rhair(6h) uyarsaydı precision 0.688–0.774 çıkardı — DKB v3'te düzeltildi.

### 12.5 Rapor yazılmadan önce bulunan iki tutarsızlık (Ek D, Karar Katmanı raporu)

1. DKB'nin "susma fazla temkinliydi" düzeltmesi CSV'ye hiç işlenmemişti — `decision_knowledge_base_v3.csv` ile düzeltildi
2. Risk motoru "sürekli sapma" kriterini hiç kullanmıyordu (hâlâ tek nokta karşılaştırması) — `agc_risk_motoru.py` güncellendi, sekiz testle doğrulandı

**Ders:** Bir bulguyu belgelemek onu uygulamakla aynı şey değil — ikisi ayrı doğrulanmalı.

---

## 13. FAZ 6 — Multi-Agent katmanı (başlandı, mimari netleşiyor)

### 13.1 Neden bu bölüm var

Projenin ilk yol haritasında şöyle deniyordu: *"önce karar mantığını tanımlayacak, sonra bunu Multi-Agent mimarisine dönüştürerek açıklanabilir öneriler üreten bir sistem haline getireceğiz."* Karar katmanı (Bölüm 12) bu ilk kısmı karşılıyor — çalışan, ölçülmüş bir çekirdek var. İkinci kısım (ajan mimarisi) hiç başlanmadı. Bu bölüm, o işe başlamadan önceki tartışmayı ve bulunan somut kanıtı kayda geçiriyor.

**Karar: bu iş yeni bir sohbette yapılacak.** Gerekçe: bu oturum çok uzadı ve gözlemlenebilir bir bedeli oldu (Bölüm 5'teki dört tekrarlı hata, Bölüm 12.5'teki "bulguyu koda işlememe" hatası). Yeni sohbet, bu belgeyi ve Karar Katmanı raporunu Project Knowledge'a alarak temiz başlamalı.

### 13.2 Ajan mimarisinin gerçek gerekçesi — ne zaman değer katar

Yol haritasındaki dört ajan (izleme / risk / öneri / açıklama), **mevcut `RiskMotoru`'nun zaten tek başına yaptığı işleri** parçalara ayırıyor. Bunu ajanlara bölmek, aşağıdaki tablodaki kazançlardan en az biri sağlanmadıkça **yalnızca karmaşıklık ekler, değer katmaz**:

| Potansiyel kazanç | Bizde mevcut mu |
|---|---|
| Doğal dil açıklama üretimi (LLM) | ✅ Şu an mesajlar şablon metin; LLM burada gerçek katkı sağlar |
| **Çelişen sinyalleri müzakere / önceliklendirme** | ✅ **Kanıtlandı — bkz. 13.3** |
| Kullanıcının "neden bu uyarı?" sorusuna cevap | ✅ Şu an yok |
| Dinamik araç seçimi | ❌ Araç kümesi sabit (DKB, risk motoru, maliyet serisi) |
| Paralel yürütme ihtiyacı | ❌ Hesap zaten milisaniyeler mertebesinde |

### 13.3 Bulunan gerçek çatışma — spekülasyon değil, DKB'nin kendi kural setinde mevcut

İlk düşünülen örnek (ısıtma önerisi ile elektrik tarifesi arasında çatışma) **test edildiğinde sahte çıktı**: ısı fiyatı saatten bağımsız sabittir (0.0083 €/MJ); pik/pik-dışı ayrımı yalnızca elektriğe uygulanır. Bu örnek rapora konulmadı.

**Gerçek çatışma CO₂ dozajında bulundu**, `decision_knowledge_base_v3.csv`'nin kendi kural çiftinde:

| Katman | Kural | Yön |
|---|---|---|
| FİZYOLOJİK (`CO2air`, KALİTATİF) | CO₂air düşükse | **"CO2 dozajını artır"** |
| EKONOMİK (`co2_esik_egilimi`) | Kümülatif 12 kg/m² eşiğine yaklaşıyorsa | **"CO2 dozaj hızını gözden geçir"** (örtük: azalt) |

Bu senaryo hipotetik değil — `TheAutomators` **gerçekten** sezon sonunda kümülatif CO₂'yi eşiğin üstüne (12.50 kg/m²) taşıdı (bkz. Ekonomi raporu). Aynı takım, sezon ortasında CO₂air fizyolojik olarak düşük çıktığı bir anda, iki katmandan **zıt yönde** öneri alırdı.

**Motorun şu anki davranışı:** ikisini de aynı raporda yan yana basıyor, öncelik sırası koymuyor. Kullanıcı hangisini dinleyeceğine kendi karar vermek zorunda kalıyor.

**Aranıp bulunamayan (henüz veri yok):** havalandırma ile ısıtma arasındaki seçimde de potansiyel bir çatışma var (`HumDef` düşükse aksiyon havuzu ikisini de öneriyor) ama bunu çözecek somut veri (havalandırmanın CO₂/enerji maliyeti karşılığı) elimizde yok. Bu, ajan mimarisi kurulmadan önce doldurulması gereken bir veri boşluğu olarak not edilmelidir.

### 13.4 Açık soru — çözülmedi, kullanıcı henüz cevap vermedi

**Çıktı kime gidecek?** Üç olası hedef kitle, üç farklı minimal mimari gerektirir:

| Hedef kitle | Mimari eğilimi |
|---|---|
| Yetiştirici (nihai kullanıcı) | Doğal dil, tek birleştirilmiş öneri, gerekçeli |
| Otomasyon sistemi | Yapılandırılmış karar (JSON/API), açıklama ikincil |
| Hoca/patron (akademik demo) | Ajanların "düşünme" süreci görünür olmalı, adım adım izlenebilir |

Bu seçim yapılmadan mimari taslağı çizmek erken olur — üçü de farklı ajan sayısı, farklı iletişim protokolü, farklı çıktı formatı gerektirir.

### 13.5 Sonraki oturum için başlangıç noktası

1. Yukarıdaki hedef kitle sorusunu cevapla
2. `co2_esik_egilimi` ↔ `CO2air` çatışmasını ilk somut test senaryosu olarak kullan — gerçek veriye dayanıyor, hipotetik değil
3. Havalandırma-ısıtma çatışmasını çözecek veri boşluğunu doldurmayı değerlendir (ya da bilinçli olarak kapsam dışı bırak)
4. Ajan sayısını yol haritasındaki dörtten değil, 13.2'deki gerekçe tablosundan türet — her ajanın var olma sebebi somut bir kazanca bağlanmalı

### 13.6 Yeni sohbette ölçülen ilerleme (`AGC_Faz6_Teknik_Rapor.pdf`)

Yeni sohbet 13.5'teki plana göre ilerledi ve üç somut sonuç üretti — 13.3'teki CO₂ senaryomu **ölçüp reddetti**, kendi kararını **gerçek veriyle** doğruladı.

**a) Çok-ajanlı gerekçe test edildi ve çürütüldü.** Üç aday çatışma (sulama, havalandırma, CO₂) ayrı ayrı ölçüldü:

| Aday çatışma | Ölçüm | Sonuç |
|---|---|---|
| Sulama aktüatörü | Sezon boyunca 0 eşzamanlı adım | Yapısal olarak imkansız (EC/WC ters kuplajlı) |
| Havalandırma | 133 adım, 11 saat/sezon | Var ama hepsi acil-olmayan seviyede |
| **CO₂ dozajı (13.3'teki önerim)** | 42 adım, **0.0003 €/m²** | Ölçüm eşiğinin altında; düşük CO₂ anlarının çoğunda havalandırma zaten açık |

**Sonuç: tek açıklayıcı ajan + üç satırlık deterministik öncelik kuralı**, dört-ajanlı müzakere protokolü yerine. Bulunan gerçek çatışma kaynağı CO₂ değil, **aynı aktüatörü zıt yönde süren uyarılar** çıktı (8 karar anında 50 çatışma, elle inceleme).

**b) Benim "sürekli sapma her yerde iyi" iddiam eksikti.** Karar Katmanı raporum (Bölüm 4.3, 5.2) tek bir kriteri genel önermişti. Yeni ölçüm kriter × değişken ailesini ayrıştırdı:

| | Sürekli sapma | Dokunma |
|---|---|---|
| Kök bölgesi | 0.722 | **0.802** (seçildi) |
| İklim | **0.291** (neredeyse işe yaramaz) | **0.698** (seçildi) |

İklimde sürekli sapma kriteri precision'ı 0.291'e düşürüyor — hızlı salınan değişkenlerde "pencerenin tamamı eşik dışı" nadiren gerçekleşiyor. Doğru çerçeve: kriter tek bir evrensel seçim değil, her değişken ailesi için ayrı optimize edilmeli.

**c) Benim DKB v3'ün zarf eşikleri muhtemelen mevsimsel karıştırma hatası taşıyor (bkz. Bölüm 5, 5. tekrar).** Bu, bulunduktan sonra bile yapılan bir hata — kontrol listesine yazmak tek başına yetmiyor.

**d) Yeni katkılar, benim metodolojimde olmayan:** Oracle/Model girdi modu ayrımı (hata kaynağını tahmin/kural olarak ayrıştırıyor); mimari × değişken salınım yakalama karşılaştırması (TCN kök bölgesinde GRU/LSTM'den belirgin daha başarılı); yapılandırma merdiveni (4 basamak, her biri tek değişiklikle ayrılıyor — ham precision düşerken şansa-göre-kazancın 5.9×'ten 30.3×'e çıktığını gösteriyor, çünkü sürekli sapma kriteri olayları 6 kat seyrekleştirip her birinin bilgi değerini artırıyor).

**e) Üç katmanlı mimari netleşti:** Katman 1 (deterministik çekirdek, karar burada verilir) → Katman 2 (tek açıklayıcı ajan, hesap yapmaz) → Katman 3 (sayı denetleyicisi, LLM değil kod, metindeki her sayıyı kayıtta arar). Denetim başarısızsa metin reddedilip eksikler ajana bildiriliyor; LLM tamamen devre dışı kalsa bile sistem şablon anlatıyla çalışmaya devam ediyor — karar yolu LLM'den etkilenmiyor.

---

## 14. BEKLEYEN İŞLER (güncellenmiş)

| Öncelik | İş | Not |
|---|---|---|
| **Orta-Yüksek** | **Multi-Agent katmanı** | **Bölüm 13 — aktif, üç katmanlı mimari netleşti (13.6); hedef kitle sorusu (13.4) hâlâ açık** |
| **Orta** | **DKB v3 zarf eşiklerini mevsim-içi olarak yeniden hesapla** | Bölüm 5 (5. tekrar) — Faz 6 raporuyla tespit edildi, henüz düzeltilmedi |
| Düşük | Ana rapordaki "TCN her koşulda en iyi" iddiasını düzelt | 12h/24h bulgusuyla çelişiyor, henüz düzeltilmedi |
| Düşük | Artık-vs-doğrudan tahmin ablasyonu | Hâlâ hiç çalıştırılmadı (Bölüm 4) |
| Düşük | 12h/24h ufuklarına karar katmanı genişletmesi | Ertelendi — bkz. not aşağıda |
| Çok düşük | Hasar eşiklerinin literatür kaynaklandırması | Şu an taslak değerler |
| Terkedildi | CropParameters modelleme | 138 örnek, etkin örneklem duruşuyla çelişir |
| Terkedildi | Hava kâhini üçüncü deneme | Kullanıcı kararı — ana hedef zaten netti |

> **12h/24h genişletmesi hakkında not:** Süre tahmini yapıldı (~4-6 saat dağınık iş + ~1-1.5 saat Colab bekleme, ardışık adımlar). İki yeni risk belirlendi ama ölçülmedi: (1) 24h'de bağımsız örneklem 348'e düşüyor, kalibrasyonun "dürüst şişirme" katsayı tahmini daha gürültülü olabilir; (2) "sürekli sapma" kriteri 288 adımlık pencerede (3h/6h'deki 72 adımın 4 katı) aşırı katı olabilir, kural neredeyse hiç tetiklenmeyebilir. Kullanıcı bu işi bilinçli olarak Multi-Agent katmanının arkasına erteledi.
