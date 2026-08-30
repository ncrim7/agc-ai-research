# AGC Projesi — Karar Günlüğü ve Durum

**Son güncelleme:** Ağustos 2026 · **Faz:** Ana rapor teslim edildi, uzun ufuk (12h/24h) çalışması başlıyor

---

## 1. KİLİTLİ KAPSAM

24 saatlik çok değişkenli geçmişten sera durumu tahmini. Altı sera (AGC 2. Edisyon, 16 Ara 2019 – 30 May 2020, 286.854 satır).

| | Değer |
|---|---|
| Girdi | 288 adım (24 saat), tüm sensörler |
| Çıktı | 72 adım (6 saat); 3h = ilk 36 adım |
| Kaydırma | 12 adım (1 saat) |
| Bölme | Sera bazında kronolojik %70/15/15 |
| Core hedefleri | Tair, Rhair, CO2air, HumDef, Tot_PAR |
| Grodan hedefleri | EC_slab1/2, WC_slab1/2, t_slab1/2 |
| Baseline'lar | Persistence, Seasonal Naive, Moving Average, Linear Trend, Ridge |
| Derin modeller | GRU, LSTM, TCN |

**CaseRAG / action-conditioned retrieval fikri terkedildi** — "future work". Semantic Decision Intelligence Platform (LLM+RL ajan, Knowledge Graph, Medallion mimari, DOC-013→022 serisi) de terkedildi; o serideki hiçbir belge aktif bağlama sokulmayacak.

---

## 2. HANGİ DOSYA GEÇERLİ — EN KRİTİK BÖLÜM

Proje sırasında single-target deneyi **iki kez** çalıştırıldı ve iki farklı sonuç seti oluştu. Aralarında %16'ya varan fark var. Yanlış olanı kullanmak raporu geçersiz kılar.

### ✅ GEÇERLİ (checkpoint'ten doğrulanmış)

| Dosya | İçerik |
|---|---|
| `metrikler_tam.csv` | Ridge + tüm derin modeller · MAE, RMSE, R² |
| `pencere_hatalari_v2.parquet` | Ridge + derin · pencere başına hatalar (anlamlılık testi girdisi) |
| `pencere_hatalari.parquet` | 4 analitik baseline + derin (v2'de analitik baseline yok, buradan alınır) |
| `adim_bazli_hatalar.csv` | Adım bazında hata eğrisi |
| `all_forecasting_results_long.csv` | Baseline'lar (analitik 4'ü için kaynak) |
| `loto_results.csv` | LOTO derin modeller |
| `loto_baseline_results.csv` | LOTO baseline'lar |
| `deep_model_results_multi.csv` | Çok hedefli derin (parquet ile tutarlı, 1.98e-05) |

### ❌ KULLANMA

| Dosya | Neden |
|---|---|
| `deep_model_results_single.csv` | **ÖKSÜZ SET.** İkinci koşudan kalma, hiçbir checkpoint'ten yeniden üretilemiyor. `pencere_hatalari_v2.parquet` / `metrikler_tam.csv` ile %16'ya varan fark var. Single-target değerleri buradan DEĞİL, `metrikler_tam.csv`'den alınır. |
| `irrigation_cases_v2_with_resources.parquet` | Join patlaması bug'ı (16.282 → 2.702.812 satır) |

**Doğrulama kanıtı:** `metrikler_tam.csv` ile `pencere_hatalari.parquet` arasında max bağıl fark 5.91e-11. Checkpoint'ler 180/180 eşleşti.

---

## 3. KİLİTLİ MİMARİ KARARLAR — yeniden önerme

| Karar | Detay |
|---|---|
| **Artık (residual) tahmini** | Model mutlak değer değil, çıpadan sapmayı öğrenir. `RESIDUAL_MODE = True` |
| **Hedef başına çıpa** | Tair, Rhair, CO2air, HumDef, Tot_PAR, t_slab1/2 → **seasonal naive**. EC_slab1/2, WC_slab1/2 → **persistence**. Ridge/MA/Trend çıpa DEĞİLDİR. |
| **Model boyutu** | `MODEL_SIZE = "small"`. Doğrulama kaybına göre seçildi (core_grodan/TCN: small 1.1414, large 1.1472). Test setindeki fark model seçiminde KULLANILMADI. |
| **SP kolonları atıldı** | `_vip` tutuldu (+0.99 korelasyon). Token bazlı filtre: `"sp" in c.split("_")` — `endswith("_sp")` yetersizdir, `water_sup_intervals_sp_min` kaçar. |
| **LED NaN → 0** | Off-state ile %94.8–98.2 örtüşme doğrulandı |
| **Slab çapraz onarım** | Yalnızca korelasyon ≥0.7 ise. AICU EC (−0.046), Digilog WC (0.481), TheAutomators EC (0.631) → uygulanmadı |
| **Zaman ekseni** | `.dt.round("5min")` zorunlu; kaynak Excel serileri ~192 ms hata taşıyor |
| **hour_sin / hour_cos / cum_Iglob_today** | **KAPSAM DIŞI.** Kullanıcı kararı, tekrar önerme. |
| **Anlamlılık** | HAC (Newey-West, gecikme 30) + blok bootstrap (blok 60, 2000 tekrar) + Benjamini-Hochberg FDR |

---

## 4. TEST EDİLİP REDDEDİLEN HİPOTEZLER — tekrar önerme

**Kapasite küçültme.** Etkin örneklem analizi (552 bağımsız pencere, örnek başına 357 parametre) modeli küçültmeyi öngördü. Kontrollü ablasyon bunu **desteklemedi**: genel etki +0.6% (yani zararlı), TCN'de +4.5%. İyileşmenin tamamına yakını çıpa seçiminden geliyor (−42.1%); yan değişiklikler (L2, patience, darboğazlı çıktı kafası) −2.7%.

> Küçük model, doğrulama kaybı iki kapasiteyi ayırt etmediği için korundu — performans üstünlüğü nedeniyle değil.

---

**Automatoes'un ayırt edici stratejisi.** LOTO'da Automatoes'un en zor genellenen sera olmasının, en ayırt edici kontrol politikasına sahip olmasından kaynaklandığı düşünüldü. `Resources.csv` (996 gözlem) ile leave-one-out centroid mesafesi hesaplandı, hipotez **reddedildi**: Automatoes'un uzaklığı altı takımın **en düşüğüdür** (0.783); sulama boyutunda 5/6, iklim boyutunda 5/6 sıradadır. Kaynak kullanım profili en *ortalama* olan takım odur.

> **Gerçek mekanizma:** Zorluk genellemeden değil, içsel tahmin edilebilirlikten geliyor. Kronolojik test ile LOTO zorluk sıralaması birebir aynı (Spearman ρ = **+1.00**) — yani model o serayı görse de görmese de zorlanıyor. Açıklayıcı değişken kök bölgesi oynaklığı: persistence hatası ile tahmin zorluğu arasında kök bölgesinde ρ = **+0.83**, hava hedeflerinde ρ = −0.37. Automatoes hem en oynak kök bölgesine (1.296) hem en zor kök bölgesi tahminine (1.362) sahip.
>
> Testin sınırı: günlük toplamlar kullanıldı; aynı su miktarının farklı zamanlamayla verilmesi bu ölçümde görünmez. 5 dakikalık `water_sup` verisiyle zamanlama imzası ayrıca incelenebilir.

**Drenaj oranı ↔ EC tahmin edilebilirliği.** "Yüksek drenaj = aktif EC yönetimi = daha zor EC tahmini" iddiası test edildi, **ters yönde çıktı** (ρ = −0.31, n=6). Desteklenmedi.

---

## 5. HENÜZ TEST EDİLMEMİŞ — bilinen boşluk

**Artık tahmini vs doğrudan tahmin.** `RESIDUAL_MODE = False` hiç çalıştırılmadı. "Doğrudan tahmin kötüydü" gözlemi temmuz sonundaki eski kurulumdan geliyor (tek takım, farklı mimari, farklı veri hattı) — karşılaştırılabilir değil. Kontrollü ablasyon için 6 koşu (~30 dk) gerekir.

---

## 6. ANA SONUÇLAR (nihai rapor)

**32 hedef–ufuk kombinasyonu, tamamı istatistiksel olarak test edildi:**

| | Sayı |
|---|---|
| Derin öğrenme anlamlı üstün | 11 |
| Baseline anlamlı üstün | 8 |
| Anlamlı fark yok | 13 |

**En iyi yaklaşım dağılımı:** hedef başına derin 16 · baseline 12 · çok hedefli derin 4

**Hedefe özgü strateji:**

| Değişken | Kazanan |
|---|---|
| Sıcaklık, kök suyu | TCN |
| CO₂, ışık | Seasonal Naive |
| Kök tuzluluğu (EC) | Persistence |
| Nem, slab sıcaklığı | Ridge |

**Metodolojik bulgular:**
- Etkin örneklem 552 (raporlanan 16.482 değil) — %95.8 pencere örtüşmesi
- Mevsimsel kayma: test döneminde ışık 2.05 kat, nem açığı 1.46 kat yüksek
- Naif anlamlılık testi 10 yanlış pozitif üretiyor; HAC varyansı 7–8.8 kat büyütüyor
- LOTO genelleme bedeli %2.3–4.6; en zor genellenen sera Automatoes (1.307), zorluk kök bölgesinde yoğunlaşıyor (1.458 vs hava 1.126)

---

## 7. TESLİM EDİLENLER

`AGC_Nihai_Rapor.md` / `.docx` / `.pdf` (27 sayfa, ana gövde + 7 ek) · 12 şekil (`figurler/`) · 12 script

**Rapor kilitlidir.** Yeni çalışmalar mevcut 3h/6h sayılarını değiştirmemelidir.

---

## 8. AKTİF FAZ — uzun ufuk (12h / 24h)

**Amaç:** Modelin ne kadar ileriyi görebildiğini ölçmek.

**Tasarım kararı:** Mevcut 72 adımlık modeller 3h/6h için KORUNUR. 12h/24h için **ayrı bir model ailesi** (288 adım çıktı) eğitilir. Sebep: tek bir modeli 288 adım çıktıya zorlamak kısa ufuktaki doğruluğu düşürür ve raporun mevcut sayılarını geçersiz kılar.

**Maliyet:**

| Ufuk | Çıktı adım | Pencere aralığı | Bağımsız örnek (6 sera) | Test penceresi |
|---|---|---|---|---|
| 3h/6h (mevcut) | 72 | 360 | 552 | 568 |
| 12h | 144 | 432 | 462 | 562 |
| 24h | 288 | 576 | **348** | 550 |

24h'de etkin örneklem %37 azalır.

**Beklenti (test edilecek):** Seasonal naive'in hatası ufka göre neredeyse hiç artmıyor (Tair 3h 1.182 → 6h 1.193). 24 saatte tam bir günlük döngü tamamlandığı için hâlâ güçlü olması muhtemel. Derin modelin onu geçmesi 6 saattekinden zor olabilir. Negatif sonuç da raporlanabilir bir bulgudur.

**Sonraki adaylar (öncelik sırasıyla):** artık-vs-doğrudan ablasyonu · CropParameters entegrasyonu (haftalık, 23 ölçüm — kazanç düşük, sızıntı riski var, ileriye dönük doldurma YAPILMAZ)


---

## 9. KULLANILMAYAN VERİ SETLERİ — envanter ve karar

Sekiz dosya türünün üçü kullanıldı (GreenhouseClimate, GrodanSens, Weather). Kalan beşi incelendi:

| Dosya | Satır/takım | Toplam | Kritik kolonlar | Karar |
|---|---|---|---|---|
| **Resources** | 166 | 996 | `Irr`, `Drain`, `Heat_cons`, `CO2_cons`, `ElecHigh/Low` | ✅ Strateji parmak izi analizinde kullanıldı |
| Production | 23-24 | ~140 | `ProdA/B`, `Truss development time` (40.3-53.3 gün) | ⏸ Betimsel analiz için aday |
| CropParameters | 23 | 138 | `Stem_elong`, `Stem_thick`, `Cum_trusses` (`plant_dens` sabit 1.8 — işe yaramaz) | ❌ Modelleme için örneklem yetersiz |
| LabAnalysis | 10 | 60 | 19 besin iyonu × (sulama + drenaj) | ❌ Yalnızca betimsel |
| TomQuality | 8 | 48 | `Flavour`, `TSS`, `Acid`, `Bite` | ❌ Yalnızca betimsel |

### Bulunan veri kalitesi sorunları — kullanmadan önce düzeltilmeli

1. **Reference / Production:** ilk tarih `2019-02-14`, diğer beş takımda `2020-02-19`. Excel serisi farkı tam **365 gün** — veri giriş hatası.
2. **Reference / TomQuality:** tarihler `1900-03-11` – `1900-03-19` çıkıyor (seri numaraları 70-78, Excel serisi değil). Ayrıca 8 yerine **7 kolon** — bir sütun eksik.
3. **IUACAAS / Resources:** `Unnamed: 7`-`Unnamed: 11` kolonları (%0 dolu, CSV'de fazladan virgül). Zararsız, okurken düşürülür.

### Sonraki adaylar

| Öncelik | İş | Süre | Gerekçe |
|---|---|---|---|
| 1 | **12h / 24h uzun ufuk** | ~1 saat | Aktif faz, Bölüm 8 |
| 2 | Artık-vs-doğrudan ablasyonu | ~30 dk | Bölüm 5'teki boşluk |
| 3 | Betimsel strateji-sonuç tablosu (Resources + Production + TomQuality) | ~yarım gün | Yarışmanın asıl hedefine (net kâr) bağlanır |
| ✗ | Üretim tahmini, CropParameters girdi olarak | — | 138 örnek — projenin etkin örneklem duruşuyla çelişir |
