# AGC 2. Edisyon — Proje Karar Günlüğü ve Veri Haritası

**Son güncelleme:** 28 Temmuz 2026 · **Teslim:** 5 hafta kaldı
**Kilitli Kapsam:** Resmi proje spesifikasyonu (`projecct.md`) esas alınıyor — 24 saatlik çok değişkenli geçmişten 3h ve 6h sera durumu tahmini, Core ve Core+Grodan feature-set karşılaştırması, 6 sera. CaseRAG/action-conditioned retrieval fikri "future work".

**Referans doküman:** `projecct.md` (danışman/resmi spesifikasyon) — bu dosyayla birlikte Project Knowledge'a eklenmeli, tekrar özetlenmiyor.

---

## 1. Dosya Haritası (Kaynak vs Deprecated vs Üretilecek)

| Dosya | Durum | Not |
|---|---|---|
| `operational_{team}.parquet` (6 takım) | Ham, birleşik (Weather+Climate+Grodan) | Referans, doğrudan kullanma |
| `operational_{team}_v2.parquet` (6 takım) | Temel v2 (interpolasyon, EC/WC_diff, hour_sin/cos, cum_Iglob) | Tüm 6 takımda mevcut, ama hour_sin/cos/cum_Iglob **common_core_strict'e taşınmayacak** (bkz. Bölüm 2, kullanıcı kararı) |
| `operational_Automatoes_v2_cleaned.parquet` | Derin temizlik SADECE Automatoes'ta yapıldı | ADR-01→05 burada. Diğer 5 takıma UYGULANMADI. |
| `common_core_strict` | Henüz yok, üretilecek | Weather+GreenhouseClimate, VIP-only, 6 takım (tekil+pooled) — Hafta 1 hedefi |
| `common_core_with_grodan_strict` | Henüz yok, üretilecek | common_core_strict + 6 Grodan kolonu — Hafta 1 hedefi |
| `irrigation_cases_v2.parquet` | 6 takım, 16.282 vaka | CaseRAG/sulama tarafı için, şimdilik dokunma |
| `irrigation_cases_v2_with_resources.parquet` | BOZUK (join patlaması, 16.282 satırdan 2.702.812 satıra çıkıyor) | Kullanma |

## 2. Automatoes'ta Alınan Kararlar — 6 Takıma Genelleştirme Planı

| Adım | Automatoes'ta ne yapıldı | 6 takıma genelleştirirken |
|---|---|---|
| VIP/SP çoklu bağlantı | SP kolonları VIP ile dolduruldu, sonra SP silindi | Basitleştir: proxy-fill'i atla, direkt SP'yi sil (VIP zaten dolu) |
| LED NaN (%46) | 0-fill (off-state) | Aynen uygula, her takımda NaN paterni "off" ile örtüşüyor mu hızlı doğrula |
| Slab cross-repair | EC_slab1 ve EC_slab2 arası +0.99 korelasyonla çapraz doldurma | Her takımda korelasyonu ayrı ölç, düşükse (0.7 altı) cross-fill uygulama |
| Fiziksel sınır kontrolü | Tair/CO2air/Rhair/t_heat_sp/pH — Automatoes'ta ihlal yok | Her takım ayrı çalıştırılmalı. Reference'ta bilinen imkansız değerler var (Tair=-1, negatif Rhair/CO2air), mask'le, silme |
| hour_sin / hour_cos / cum_Iglob_today | Takım bazında hesaplandı, bir kere bozuldu (24 Temmuz rollback), sonra geri eklendi (26 Temmuz, doğrulanmamış) | **KAPSAM DIŞI — kullanıcı kararı (29 Temmuz).** Hiç hesaplanmayacak, common_core_strict'e girmeyecek. Not: zaten resmi spesifikasyonda (projecct.md) bu üç kolon istenmiyor, dolayısıyla bu karar "strict" tanımıyla tam uyumlu — mühendislik borcu ve bug geçmişi olan bir özellik tamamen temizleniyor. Trade-off: model, gündüz/gece konumunu açıkça bir saat sinyalinden değil, girdi penceresinin kendi dinamiklerinden (radyasyon şekli vb.) örtük çıkaracak — çok bulutlu günlerde bu ayrımı biraz zorlaştırabilir, ama modeli/pipeline'ı basitleştirme kazancı buna değer. |
| Ardışık NaN blok uzunluğu | Ölçülmedi | Her takım için ayrı ölç, interpolasyon limitini ona göre belirle |

Hafta 1'in gerçek işi: yukarıdaki tabloyu tek parametrik bir fonksiyona/script'e dökup 6 takıma da (Reference dahil) koşturmak, çıktı olarak common_core_strict ve common_core_with_grodan_strict'i hem tekil hem pooled üretmek. Takıma özel doğrulama adımları (LED, slab korelasyonu, fiziksel sınır, NaN blok uzunluğu) zaten bu "6 takımı tek tek analiz et" aşamasının doğal parçası — ayrı bir iş kalemi değil, aynı geçişte yapılacak.

## 3. Açık Maddeler — TÜMÜ KAPANDI (29 Temmuz, 2. çalıştırma)

1. ✅ En uzun ardışık NaN bloğu: 6/6 takımda `EC_slab1` için birebir aynı **1037 satır (~3.6 gün)** — tesis genelinde ortak bir Grodan sensör kesintisi olarak kabul edildi, kabul edilmiş bilinen veri boşluğu (raporda belirtilecek, tam tarih aralığı opsiyonel/nice-to-have, engelleyici değil).
2. ✅ Fiziksel sınır kontrolü: Reference'ta Tair(1), CO2air(2), Rhair(3), HumDef(2) ihlali — maskelendi, sayılar küçük.
3. ✅ Slab korelasyonu: AICU EC_slab1↔2 = -0.046, Digilog WC_slab1↔2 = 0.481, TheAutomators EC_slab1↔2 = 0.631 — üçü eşik altı, cross-fill doğru şekilde atlandı. Diğerleri ≥0.86, uygulandı.
4. ✅ LED off-state doğrulaması: %94.8-98.2, kabul edilebilir.
5. ✅ **ÇÖZÜLDÜ** — AICU'nun `remaining_nan_total` anomalisi (51.641) ayrı bir sorun değilmiş, madde 3b'deki `water_sup_intervals_sp_min` bug'ının AICU'da (SP kanalları zaten %86-99 boş olduğu için) daha görünür şekilde ortaya çıkmasıymış. Düzeltme sonrası 6 takım da tutarlı aralıkta: 12.918-12.930.
6. ✅ 5/6 → 6/6 düzeltildi, madde 1 ile birleşti.

## 3c. Hafta 1 — Pencere Üretimi (29 Temmuz)

`agc_window_generation.py`: 288 adım (24h) girdi, 72 adım (6h) çıktı, stride=12, sera-bazlı kronolojik %70/15/15 split + sınır-purge + hedef-NaN filtresi. Pencereler materialize edilmiyor, sadece indeks (input_start/output_start/split) üretiliyor — gerçek array çıkarma Hafta 3'e (model eğitimi) bırakıldı.

**Varsayım (doğrulanmadı, kullanıcı onayı bekliyor):** Core+Grodan deneyinde hedef seti = 5 Core + 6 Grodan hedefinin BİRLEŞİMİ (11 hedef, hepsi çıktı olarak isteniyor). Bu yanlışsa (örn. Grodan sadece girdi olarak ekleniyor, Core hedefleri aynı kalıyor) söyle, tek satırlık değişiklik.

**Hafta 1 durumu: TAMAMLANMADI.** Temizlik ve pencere kodu yazıldı, ama veri doğrulaması (Bölüm 3d) gerçek veride henüz koşturulmadı. Doğrulama geçmeden baseline/model aşamasına geçilmeyecek.

## 3d. Veri Doğrulama Kapısı — `agc_data_verification.py` (29 Temmuz)

Modele geçmeden önce zorunlu 9 kontrol. FAIL varsa sonraki aşamaya geçilmez.

| # | Kontrol | Neden |
|---|---|---|
| 1 | **Zaman ekseni sürekliliği** | Pencere üretimi KONUMSAL indeksleme yapıyor (`input_start + 288`). Bu, satırların kesintisiz 5dk aralıklarla dizildiğini varsayıyor. 29 Mart 2020 yaz saati geçişi + 30 Mart'ta ~75dk kesinti biliniyor. Atlama varsa bazı "24 saatlik" pencereler sessizce 25 saat kapsar — model bunu söylemez, sessizce yanlış öğrenir. **En kritik kontrol.** |
| 2 | Duplike timestamp | Merge doğruluğu |
| 3 | **Şema tutarlılığı** | `pd.concat` farklı kolon setlerini sessizce NaN ile doldurur. Bir takımda tamamen NaN kolon = pooling hatası işareti |
| 4 | Per-kolon NaN dökümü | `remaining_nan_total` toplamı yeterli değil — hangi kolonda, hedefte mi girdide mi |
| 5 | Sabit / neredeyse sabit kolonlar | O takımda hiç çalışmamış sensör göstergesi, ölü feature |
| 6 | Tüm kolonlarda mantık dışı değer | Önceki fiziksel sınır kontrolü sadece 11 kolonu tarıyordu, ~46 kolonun geri kalanı taranmadı |
| 7 | 1037 satırlık boşluğun tarih aralığı + hangi split'e düştüğü | Test split'ine düşerse değerlendirme etkilenir |
| 8 | Takımlar arası hedef dağılımı | Pooling'de takım confound'unun büyüklüğü |
| 9 | Pencere kaybı muhasebesi | Kaç pencere üretildi, kaçı neden atıldı (sınır purge vs hedef NaN) |

**Doğrulama sırasında bulunan ve düzeltilen 2. bug:** `excel_serial_to_datetime()` kayan nokta hassasiyeti kaybediyordu — adımlar `00:04:59.999999721` gibi çıkıyordu. Bu hem kontrol 1'i anlamsız kılıyor hem de `Time` üzerinden yapılan Weather merge'ini kırılgan hale getiriyordu (jitter farklı olsa sessizce NaN üretebilirdi). Düzeltme: `.dt.round("s")` — mikro-saniyelik gürültüyü siler, gerçek boşlukları (DST, kesinti) korur. Bu düzeltme nedeniyle **pipeline yeniden çalıştırılmalı**, parquet dosyaları yenilenmeli.

## 3b. Bulunan ve Düzeltilen Kod Hatası (29 Temmuz)

`sp_cols = [c for c in df.columns if c.endswith("_sp")]` filtresi `water_sup_intervals_sp_min` kolonunu KAÇIRIYORDU (isim `_sp` ile bitmiyor, `_min` ile bitiyor — `_sp` ortada geçiyor). Bu, Reference'ta sahte bir "39.308 satırlık dev boşluk" gibi görünüp gerçek bir veri sorunuymuş gibi yanlış yorumlanabilirdi; ayrıca AICU'nun `remaining_nan_total` anomalisinin (51.641) de gerçek nedeniydi. Düzeltme: token-bazlı eşleşme (`"sp" in c.split("_")`) — `water_sup` ve `water_sup_intervals_vip_min` yanlışlıkla yakalanmadan, `water_sup_intervals_sp_min` doğru şekilde silindi. Sentetik veriyle doğrulandı, gerçek veriyle teyit edildi (6 takım da 12.918-12.930 aralığına düştü), script güncellendi.

## 3e. HAFTA 1 KAPANDI — Doğrulama 0 FAIL (29 Temmuz)

Tüm kontroller geçti. Kalan WARN'ların hepsi incelendi, **hiçbiri veri sorunu değil**:

| WARN | Gerçek açıklama |
|---|---|
| `int_*_vip` on binlerce "ihlal" | LED yoğunluğu (µmol/m²/s), yüzde değil. Sınır yanlıştı, (0,1000) yapıldı. Yan bulgu: takımlar farklı spektrum kullanmış (Automatoes far-red'i kısmış, TheAutomators mavi'yi) — makalede kontrol politikası farkı olarak kullanılabilir. |
| Digilog `t_grow_min_vip` 1250× tam 80.0 | Büyütme borusu min sıcaklık setpoint'i; 80°C Hollanda seralarında normal. Sınır (0,90) yapıldı. Digilog ~104 saat yüksek boru sıcaklığı kullanmış. |
| Reference `Tair` min 0.5, `Rhair` min 7.7 | Toplam **11 satır** (%0.02), Ocak sonu gece saatleri, tutarlı Rhair ile. Hepsi train split'inde. Maskelenmedi, raporda dipnot. |
| 86 saatlik EC_slab boşluğu | 26-30 Mayıs, 6 takımda da aynı, tamamı test split'inde. Tesis geneli Grodan kesintisi. Grodan test penceresi 568→470 (%17 kayıp), kabul edildi. |
| Sabit kolonlar | AICU (`t_grow_min_vip`,`t_rail_min_vip`), IUACAAS (`t_rail_min_vip`), Reference (`dx_vip`,`scr_blck_vip`). Ridge'de sorun çıkarmıyor (sklearn `scale_=1.0`). Ama **takım parmak izi** — pooled modelde confound riski, hata analizinde hatırla. |

**Pencere sayıları (nihai):**

| Feature-set | train/sera | val/sera | test/sera | toplam (6 sera) |
|---|---|---|---|---|
| Core | 2.747 | 568 | 568 | **23.298** |
| Core+Grodan | 2.676 | 546 | 470 | **22.152** |

## 3f. Hafta 2 — Baseline'lar (`agc_baselines.py`)

5 baseline: `persistence`, `seasonal_naive`, `moving_average` (son 3h), `linear_trend` (son 6h eğim ekstrapolasyonu), `ridge`. 2 feature-set × 2 değerlendirme (pooled / per_greenhouse) × 2 ufuk (3h/6h).

**Alınan kararlar:**
- **Girdi NaN stratejisi:** train split'inin sera-bazlı sütun ortalamasıyla doldurma (val/test'ten sızıntı yok). Hedef tarafta NaN yok, pencere üretiminde elendi. Alternatif (`is_missing` maske kanalı) denenmedi — NaN oranı düşük olduğu için gerekli görülmedi.
- **Ridge girdisi:** 288×46 ham pencere düzleştirilmiyor. Sütun başına 4 özet (mean/std/son değer/eğim) → 4×n_feature boyut. `alpha=10.0`.
- **Bellek:** pencere tensörü hiç materialize edilmiyor (23k×288×46 ≈ 1.2 GB olurdu); sera başına ham dizi (~9 MB) tutulup pencere indekslerinden dilim alınıyor.
- **Seasonal naive:** çıktı t+1..t+72'nin 24 saat öncesi = girdi penceresinin ilk 72 adımı. Ek veri okuma yok.

**Doğrulama:** her baseline elle hesaplanmış beklenen değerlere karşı test edildi (9 assert) — `extract_window_data` 6/6, `linear_trend` bilinen eğimde tam ekstrapolasyon, `compute_metrics` mükemmel tahminde MAE=0/R²=1.

**Çıktılar:** `all_forecasting_results_long.csv`, `error_by_step.csv`

## 4. Bilinen Bulgular (makalede kullanılabilir)

- Sulama eylem büyüklüğü (delta_interval) ile 3-6h EC/WC sonucu korelasyonu: -0.03 ile 0.16 arası (kök bölgesi ataleti kanıtı).
- Takım kimliği kontrol politikasını güçlü belirliyor ("The Automators" mikro-reaktif ~4200 eylem, "Automatoes"/"Digilog" makro-proaktif) — pooled modelde confound riski olarak hatırla.
- Reference takımında fiziksel olarak imkansız değerler mevcut (Tair=-1, negatif Rhair/CO2air) — 6 takım havuzlanınca bu kontrol zorunlu.

## 5. Önerilen 5 Haftalık MVP Triajı — ONAY BEKLİYOR (henüz karar verilmedi)

Resmi spesifikasyonun tamamı (2 feature-set x 3 model x 13 split-konfigürasyonu = 78 eğitim koşusu) 5 haftada solo gerçekçi değil. Önerilen kesinti (henüz kullanıcı onayı yok):

| Boyut | Doküman istiyor | Önerilen MVP |
|---|---|---|
| Feature-set | Core + Core+Grodan | İkisi de kalıyor |
| Ufuk | 3h + 6h ayrı ayrı | Tek eğitim (72 adım çıktı), 36. adımda kesip 3h elde et |
| Modeller | GRU+LSTM+TCN zorunlu | GRU+LSTM öncelik, TCN zaman kalırsa |
| Transformer | Opsiyonel | Kapsam dışı |
| Değerlendirme | Per-greenhouse + Pooled + Tam LOGO (6 fold) | Pooled = ana deney; per-greenhouse sadece Core; LOGO 2-3 fold (kısmi, raporda belirtilerek) |
| Baseline'lar | Persistence, Seasonal, MA/Trend, Ridge | Hepsi kalıyor (ucuz) |

Ridge implementasyon notu: 288x57 ham pencereyi flatten etme (overfit riski). 24h pencerenin özet istatistiklerini (mean/std/son değer/eğim, yaklaşık 228 boyut) kullan.

## 5b. Project Knowledge Küratörlüğü (29 Temmuz)

Drive'daki `01_Project_Knowledge` klasöründe iki ayrı, çelişen vizyon tespit edildi:
1. **Aktif kapsam:** Bu doküman + `projecct.md` (GRU/LSTM/TCN forecasting).
2. **"AGC Semantic Decision Intelligence Platform"** — LLM+RL ajan, Knowledge Graph, Medallion mimari, State-Action-Reward döngüsü. DOC-013→DOC-022 numaralı sistemli bir seri (`Decision_Flow_Diagram.md`, `Feature_Registry.md`, `Product_Requirements_Document.md`, `Canonical_Dataset_Blueprint.md`, `Semantic_Layer_Architecture.md`, `State_Action_Reward_Schema.md`, `Glossary.md`, `Domain_Ontology.md` vb.).

**Karar (kullanıcı, 29 Temmuz):** Semantic Platform vizyonu şimdilik tamamen terkedildi. Bu serideki hiçbir dosya Project Knowledge'a yüklenmeyecek — Drive'da tarihsel kayıt olarak kalabilir ama aktif bağlama sokulmayacak.

**İncelenip Project Knowledge'a alınanlar:**
- `Dataset_Health_Report.md` — EKLENDİ. Ham veri tanı raporu, düşük risk, kapsamla çelişmiyor. Not: GreenhouseClimate.csv'de 6 takımda da neredeyse tüm sayısal kolonlar object/mixed dtype (force_numeric() adımını doğruluyor, plan değişmedi). Reference'ın TomQuality.csv'sinde 2 duplicate timestamp var — TomQuality şu an kapsamda kullanılmıyor, bilgi amaçlı not düşüldü.
- `Decision_Flow_Diagram.md`, `Feature_Registry.md`, `Product_Requirements_Document.md`, `Canonical_Dataset_Blueprint.md` — EKLENMEDİ (Semantic Platform serisinin parçası).

## 6. Sonraki 5 Hafta (MVP triajı onaylanırsa)

| Hafta | İş |
|---|---|
| 1 | 6 takıma genelleştirilmiş temizlik pipeline'ı (bkz. Bölüm 2) -> common_core_strict + _grodan üretimi. feature_inventory tamamlama. Pencere üretimi (72 adım, stride=12) |
| 2 | 4 baseline (pooled + per-greenhouse, iki feature-set). all_forecasting_results_long.csv altyapısı |
| 3 | GRU+LSTM pooled (Core+Grodan, 4 koşu). GRU per-greenhouse (Core, 6 koşu) |
| 4 | Kısmi LOGO (2-3 fold). TCN (zaman varsa). Hata analizi. 8 grafik |
| 5 | Rapor (12 bölüm), tablolar, tampon |
