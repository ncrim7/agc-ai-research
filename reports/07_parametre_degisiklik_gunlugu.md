# Parametre Değişiklik Günlüğü
### Orijinal koddan mevcut sonuçlara: ne değişti, neden değişti, ne etki etti

---

## Üç aşama

Mevcut sonuçlar tek bir değişiklikle elde edilmedi. İki ayrı sıçrama var:

| | **Aşama 0** — Orijinal notebook | **Aşama 1** — Yeniden yapılandırma | **Aşama 2** — Mevcut sonuçlar |
|---|---|---|---|
| Tarih | 28 Temmuz | 30 Temmuz | 30 Temmuz |
| Etiket | — | `model_size = large` | `model_size = small` |
| Veri | Tek takım (Automatoes) | 6 takım havuzlanmış | 6 takım havuzlanmış |
| Sonuç | Tüm hedeflerde baseline'a kayıp | 5-6 hedefte kazanç | **14 hedefte kazanç** |

Sonuç tablosundaki `large` / `small` sütunları Aşama 1 ve Aşama 2'yi gösterir.

---

## Aşama 0 → 1: Veri ve mimari yeniden yapılandırma

| Parametre | Önce | Sonra | Gerekçe |
|---|---|---|---|
| **Eğitim verisi** | Automatoes tek başına, 33.466 satır | 6 takım havuzlanmış, 286.854 satır | Eğitim penceresi 2.762 → 16.482. Tek takımla model öğrenecek kadar örnek görmüyordu. |
| **Sera kimliği** | Yok | `greenhouse_id` kolonu eklendi | Havuzlamada takım ayrımı korunsun |
| **Tahmin hedefi** | Mutlak değer (`y`) | Artık değer (`y − çıpa`) | Model sıfır çıktı verse bile baseline kadar iyi olur; çıta tabana gömülür |
| **Çıpa** | — | Seasonal naive (24 saat öncesi) | Baseline tablosunda seasonal her hedefte en güçlüydü |
| **Model çeşidi** | Yalnızca GRU | GRU + LSTM + TCN | Şartnamede üçü de zorunlu; ayrıca RNN'lerin uzun pencerede zayıflığı test edilecekti |
| **Feature-set** | Tek | Core / Core+Grodan / Core_matched | Grodan katkısının adil ölçümü (aynı pencerelerde) |
| **Pencere tensörü** | Bellekte materialize | İndeksten dilimleme | 23.298 × 288 × 46 ≈ 1,2 GB olurdu, Colab'da patlardı |

---

## Aşama 1 → 2: Mevcut sonuçları üreten değişiklikler

Bu tablodaki **dört değişiklik**, sonuç tablosundaki `large` → `small` farkını yaratan şeydir.

### A. Hedef başına çıpa seçimi ⭐ en büyük etki

| | Önce (v1) | Sonra (v2) |
|---|---|---|
| Tair, Rhair, CO2air, HumDef, Tot_PAR | seasonal | seasonal *(değişmedi)* |
| t_slab1, t_slab2 | seasonal | seasonal *(değişmedi)* |
| **EC_slab1, EC_slab2** | seasonal | **persistence** |
| **WC_slab1, WC_slab2** | seasonal | **persistence** |

**Gerekçe:** Kök bölgesi tuzluluk ve su içeriği günlük döngüsel değil, yavaş sürüklenen büyüklüklerdir. "Dün bu saatte" onlar için yanlış referanstı; model önce bu hatalı çıpayı geri almak zorunda kalıyordu. Baseline tablosu doğru çıpayı zaten söylüyordu: EC_slab 3h'de persistence 0.043, seasonal 0.136.

**Kod:**
```python
ANCHOR_BY_TARGET = {
    "Tair": "seasonal", "Rhair": "seasonal", "CO2air": "seasonal",
    "HumDef": "seasonal", "Tot_PAR": "seasonal",
    "t_slab1": "seasonal", "t_slab2": "seasonal",
    "EC_slab1": "persistence", "EC_slab2": "persistence",
    "WC_slab1": "persistence", "WC_slab2": "persistence",
}
```

### B. Model kapasitesi

| Parametre | Önce | Sonra |
|---|---|---|
| GRU/LSTM gizli birim | 96 | **24** |
| TCN filtre sayısı | 64 | **16** |
| Çıkış katmanı | `Dense(72 × n_hedef)` doğrudan | **Darboğaz** eklendi: `Dense(birim, relu) → Dense(72 × n_hedef)` |
| TCN dropout | 0.1 | 0.2 |
| Genişletme (dilation) | (1,2,4,8,16,32,64) | *(değişmedi)* |

**Parametre sayısı (Core):**

| Model | Önce | Sonra | Azalma |
|---|---|---|---|
| GRU | 75.816 | **14.640** | 5,2× |
| LSTM | 89.064 | **16.224** | 5,5× |
| TCN | 199.208 | **18.088** | 11,0× |

**Gerekçe — etkin örneklem büyüklüğü:** Eğitim penceresi sayısı 16.482 görünüyor ama ardışık pencereler 1 saat kaydırmayla üretildiği için %95,8 örtüşüyorlar. Gerçekten bağımsız pencere sayısı **~552**. TCN'in 199.208 parametresi, bağımsız örnek başına **357 parametre** demekti — bu oranda model ezberler, genellemez. Yeni oran 26–50 arası.

### C. Düzenlileştirme (regularization)

| Parametre | Önce | Sonra |
|---|---|---|
| L2 ağırlık cezası | **yok** | **1e-4** (tüm katmanlarda) |

### D. Eğitim süresi kontrolü

| Parametre | Önce | Sonra |
|---|---|---|
| `EPOCHS` (üst sınır) | 60 | **150** |
| `PATIENCE` (erken durdurma) | 8 | **20** |

**Gerekçe:** Danışman geri bildirimi "modelin 100-150 epoch'a kadar ilerlemesi lazım" yönündeydi. Sınır yükseltildi. **Gözlem: modeller yine 25–80 epoch'ta kendiliğinden durdu.** Bu, eğitim süresinin darboğaz olmadığının doğrudan kanıtıdır — model 150 epoch koşabilirdi, doğrulama hatası iyileşmediği için durdu.

---

## Değişmeyen parametreler

Karşılaştırmanın geçerli olması için bunlar sabit tutuldu:

| Parametre | Değer |
|---|---|
| Girdi penceresi | 288 adım (24 saat) |
| Çıktı penceresi | 72 adım (6 saat); 3h = ilk 36 adım |
| Kaydırma (stride) | 12 adım (1 saat) |
| Bölme | Kronolojik %70 / %15 / %15, sera bazında |
| Optimizasyon | Adam, `learning_rate = 1e-3` |
| Kayıp fonksiyonu | MSE (normalize edilmiş artık üzerinde) |
| Batch boyutu | 64 |
| LR azaltma | `ReduceLROnPlateau(factor=0.5, patience=4, min_lr=1e-5)` |
| Rastgelelik tohumu | 42 |
| TCN çekirdek boyutu | 3 |
| TCN alıcı alanı | 509 adım (girdi penceresinin tamamını kapsar) |
| Normalizasyon | Yalnızca eğitim bölmesinden hesaplanır |
| Eksik veri | Eğitim bölmesi sütun ortalamasıyla doldurulur (girdi tarafı) |

---

## Ölçülen etki (TCN, 3 saat, `large` → `small`)

### Core feature-set
| Hedef | large | small | Değişim |
|---|---|---|---|
| CO2air | 72.169 | 59.916 | **−17,0%** |
| Tot_PAR | 82.311 | 78.919 | −4,1% |
| HumDef | 1.365 | 1.345 | −1,5% |
| Rhair | 5.108 | 5.066 | −0,8% |
| Tair | 1.054 | 1.154 | *+9,5% (kötüleşti)* |

### Core+Grodan feature-set
| Hedef | large | small | Değişim |
|---|---|---|---|
| **EC_slab2** | 0.203 | 0.060 | **−70,4%** |
| **EC_slab1** | 0.153 | 0.055 | **−64,1%** |
| **WC_slab1** | 1.604 | 0.921 | **−42,6%** |
| **WC_slab2** | 1.742 | 1.034 | **−40,6%** |
| CO2air | 73.385 | 63.132 | −14,0% |
| Tair | 1.050 | 0.972 | −7,4% |
| t_slab2 | 0.675 | 0.650 | −3,7% |
| t_slab1 | 0.669 | 0.650 | −2,8% |
| HumDef | 1.340 | 1.316 | −1,8% |
| Rhair | 4.983 | 5.069 | *+1,7% (kötüleşti)* |
| Tot_PAR | 84.510 | 88.038 | *+4,2% (kötüleşti)* |

**Okuma:** İyileşme tekdüze değil. 16 hedef-feature kombinasyonunun 13'ünde iyileşme, 3'ünde kötüleşme var. Kök bölgesi hedeflerindeki %40–70'lik sıçrama, diğerlerindeki %1–17'lik değişimden nitel olarak farklı.

---

## Dürüst kısıtlama: değişiklikler ayrıştırılamıyor

Yukarıdaki **dört değişiklik (A, B, C, D) aynı anda uygulandı.** Dolayısıyla hangi iyileşmenin hangisinden geldiği istatistiksel olarak kanıtlanmış değildir.

**Elimizdeki dolaylı kanıt:** Kök bölgesi hedefleri (%40–70) diğerlerinden (%1–17) çok daha fazla iyileşti. Kapasite düşürme tüm hedefleri benzer oranda etkilerdi; bu asimetri, kök hedeflerindeki kazancın büyük ölçüde **çıpa değişikliğinden (A)** geldiğine güçlü işarettir.

**Temiz ayrıştırma için gereken deney (~30 dakika, 6 koşu):**

```python
MODEL_SIZE = "large"        # kapasiteyi ESKİ haline al
# ANCHOR_BY_TARGET aynı kalsın (yeni çıpa)
run(BASE_DIR, target_mode="multi")
```

Bu koşu, kapasiteyi sabit tutup yalnızca çıpayı değiştirmiş olur ve A ile B'nin katkısını ayırır. Rapordaki iddiayı tartışmasız hale getirir.

---

## Tekrar üretim

Her aşama tek satırla üretilebilir. Sonuç dosyasındaki `model_size` ve `anchor_scheme` sütunları hangi konfigürasyondan geldiğini kaydeder.

```python
# Aşama 1 (large)
MODEL_SIZE = "large"
run(BASE_DIR, target_mode="multi")

# Aşama 2 (small) — mevcut sonuçlar
MODEL_SIZE = "small"
run(BASE_DIR, target_mode="multi")

# Kapasite ablasyonu — ara nokta
MODEL_SIZE = "medium"
run(BASE_DIR, target_mode="multi")
```

**Not:** Sonuç dosyası aynı olduğu için tamamlanmış koşular otomatik atlanır. Konfigürasyon parmak izi (`model_size`) model etiketine gömülüdür — ayar değiştiğinde koşu yeniden yapılır, eski sonuç sessizce kullanılmaz.
