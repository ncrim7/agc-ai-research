# AGC — Konfigürasyon Referansı ve Ufuk Genişletme Notları

Yeni ufuk (12h / 24h) çalışması için hazırlandı. Sorulan soru: *"Parametrik mi, HORIZON sabit mi?"*

**Kısa cevap: modül düzeyinde sabit, fonksiyon argümanı değil.** Değiştirilebilir ama üç dosyada birden değiştirilmeli ve bazı türetilmiş sabitler elle güncellenmeli.

---

## 1. Sabitlerin tam listesi

### `agc_window_generation.py`
```python
INPUT_STEPS  = 288    # 24 saat (5 dk adımlarla)
OUTPUT_STEPS = 72     # 6 saat
STRIDE       = 12     # 1 saat
TRAIN_FRAC   = 0.70
VAL_FRAC     = 0.15   # test = kalan 0.15
CORE_TARGETS   = ["Tair","Rhair","CO2air","HumDef","Tot_PAR"]
GRODAN_TARGETS = ["EC_slab1","EC_slab2","WC_slab1","WC_slab2","t_slab1","t_slab2"]
```

### `agc_baselines.py`
```python
INPUT_STEPS  = 288
OUTPUT_STEPS = 72
H3_STEPS     = 36     # 3 saat = ilk 36 adım (değerlendirme dilimi)
MA_WINDOW    = 36     # moving average: son 3 saat
TREND_WINDOW = 72     # linear trend: son 6 saatin eğimi
RIDGE_ALPHA  = 10.0
```

### `agc_deep_models.py` (ve `agc_all_in_one.py`)
```python
INPUT_STEPS  = 288
OUTPUT_STEPS = 72
H3_STEPS     = 36

RESIDUAL_MODE = True          # False -> mutlak hedef (hiç çalıştırılmadı)
TARGET_MODE   = "multi"       # "single" -> hedef başına ayrı model
MODEL_SIZE    = "small"

BATCH_SIZE = 64 · EPOCHS = 150 · PATIENCE = 20
LEARNING_RATE = 1e-3 · L2_REG = 1e-4 · SEED = 42

SIZE_PRESETS = {
  "small":  {"rnn_units":24, "tcn_filters":16, "tcn_dilations":(1,2,4,8,16,32,64), "dropout":0.2},
  "medium": {"rnn_units":48, "tcn_filters":32, ...},
  "large":  {"rnn_units":96, "tcn_filters":64, ...},
}
```

### Hedef → çıpa eşlemesi
```python
ANCHOR_BY_TARGET = {
    "Tair":     "seasonal",  "Rhair":    "seasonal",  "CO2air":   "seasonal",
    "HumDef":   "seasonal",  "Tot_PAR":  "seasonal",
    "t_slab1":  "seasonal",  "t_slab2":  "seasonal",
    "EC_slab1": "persistence", "EC_slab2": "persistence",
    "WC_slab1": "persistence", "WC_slab2": "persistence",
}
DEFAULT_ANCHOR = "seasonal"
```

---

## 2. Ufku değiştirirken elden geçmesi gerekenler

`OUTPUT_STEPS`'i değiştirmek **tek başına yetmez.** Aşağıdakiler ufka bağlıdır:

| Sabit | Şu an | Neden ufka bağlı |
|---|---|---|
| `H3_STEPS = 36` | 3h dilimi | 12h/24h için değerlendirme dilimleri yeniden tanımlanmalı (ör. 3h=36, 6h=72, 12h=144, 24h=288) |
| `TREND_WINDOW = 72` | Linear trend son 6 saatin eğimini alır | 24h tahmin için 6 saatlik eğimi 24 saate uzatmak çok agresif; bu baseline ufka göre gözden geçirilmeli |
| `MA_WINDOW = 36` | Son 3 saatin ortalaması | Uzun ufukta muhtemelen daha uzun pencere gerekir |
| `HORIZONS` demeti | `(("3h",36),("6h",72))` | `agc_dogrulamali_cikarim.py`, `agc_adim_bazli.py`, `agc_eksikleri_tamamla.py` içinde tekrarlanır |

**Çıpa mantığı ufuktan bağımsızdır ve olduğu gibi çalışır:**
- `seasonal` → girdi penceresinin ilk `OUTPUT_STEPS` adımı. `OUTPUT_STEPS ≤ INPUT_STEPS` olduğu sürece geçerli. 24h için `OUTPUT_STEPS = 288 = INPUT_STEPS`, yani tam sınırda — girdi penceresinin tamamı çıpa olur. Çalışır ama sınırdadır; `OUTPUT_STEPS > INPUT_STEPS` olursa `build_anchor` kırılır.
- `persistence` → girdinin son değeri, `OUTPUT_STEPS` kez tekrar. Her ufukta çalışır.

---

## 3. Sınır purging mantığı (`generate_windows_for_greenhouse`)

Kritik nokta: pencere **tamamen tek bir bölmenin içinde** kalmalıdır.

```python
last_start = n - (INPUT_STEPS + OUTPUT_STEPS)
for input_start in range(0, last_start + 1, STRIDE):
    output_start = input_start + INPUT_STEPS
    window_end   = output_start + OUTPUT_STEPS      # exclusive

    # 1) input_start hangi bölmede?
    split_name = <lo <= input_start < hi olan bölme>

    # 2) PURGE: pencere o bölmenin dışına taşıyorsa at
    if window_end > hi:
        continue

    # 3) Çıktı aralığında hedef NaN varsa at
    if np.isnan(target_arr[output_start:window_end]).any():
        continue
```

Üç nokta:
1. **Bölme ataması `input_start`'a göre yapılır**, `window_end`'e göre değil.
2. **Purge koşulu `window_end > hi`** — sınırı aşan pencere tamamen atılır. Bu, train/val/test arası sızıntıyı engeller.
3. **Hedef NaN filtresi yalnızca çıktı aralığına bakar.** Girdi tarafındaki NaN'ler elenmez; model eğitiminde train-set ortalamasıyla doldurulur.

Bölmeler sera bazında ayrı hesaplanır (`chronological_split_bounds(len(grup))`), pencere sera sınırını aşmaz.

**Ufuk büyüdükçe purge artar:** `window_end > hi` koşulu her bölmenin son `INPUT_STEPS + OUTPUT_STEPS` satırını kullanılamaz kılar.

| Ufuk | Pencere aralığı | Bağımsız örnek (6 sera) | Test penceresi |
|---|---|---|---|
| 6h (mevcut) | 360 | 552 | 568 |
| 12h | 432 | 462 | 562 |
| 24h | 576 | **348** | 550 |

---

## 4. Baseline implementasyonları — dikkat edilecek noktalar

**Seasonal Naive.** Çıktı `t+1 … t+OUTPUT_STEPS`; 24 saat öncesi `t+1-288 … t+OUTPUT_STEPS-288`, yani **girdi penceresinin ilk `OUTPUT_STEPS` adımı**. Ek veri okuma gerekmez:
```python
mevsimsel[i] = win[:OUTPUT_STEPS][:, t_idx]
```
`OUTPUT_STEPS = 288` olduğunda bu `win[:288]` yani tüm girdi penceresi olur — hâlâ doğru ama sınırda.

**Linear Trend.** Son `TREND_WINDOW` adıma en küçük kareler doğrusu uydurup ileri uzatır:
```python
x  = np.arange(TREND_WINDOW); xc = x - x.mean(); d = (xc**2).sum()
y_ort  = trend_dilim.mean(axis=1)
egim   = (xc[None,:,None] * (trend_dilim - y_ort[:,None,:])).sum(axis=1) / d
son    = y_ort + egim * (x[-1] - x.mean())
ileri  = np.arange(1, OUTPUT_STEPS+1)
tahmin = son[:,None,:] + egim[:,None,:] * ileri[None,:,None]
```
**Uzun ufukta bu baseline patlar** — 6 saatlik eğimi 24 saate uzatmak fiziksel olmayan değerler üretir. Mevcut sonuçlarda bile linear trend en kötü yöntemdi (ortalama sıra 10.69/11). 24h'de daha da kötüleşecek; bu beklenen ve raporlanabilir.

**Ridge.** 288×n_feat ham pencere **düzleştirilmez**. Sütun başına 4 özet (mean, std, son değer, eğim) → `4 × n_feat` boyut. `StandardScaler` yalnızca train'e fit edilir. Çok çıktılı Ridge, hedef başına ayrı Ridge ile matematiksel olarak özdeştir (fark 0.000e+00, doğrulandı).

**Persistence / Moving Average.** Skaler değer `OUTPUT_STEPS` kez tekrarlanır; ufuktan bağımsız.

---

## 5. Karar C için gereken veri — çıkarım kodu

Grodan NaN maskesi + zaman damgaları bende yok (yalnızca sonuç dosyaları var). Şu kod üretir:

```python
import pandas as pd, numpy as np
df = pd.read_parquet(BASE_DIR / "common_core_with_grodan_strict.parquet")
GROD = ["EC_slab1","EC_slab2","WC_slab1","WC_slab2","t_slab1","t_slab2"]

satir = []
for gh, g in df.groupby("greenhouse_id", sort=False):
    g = g.sort_values("Time").reset_index(drop=True)
    n = len(g); lo = int(n*0.70) + int(n*0.15)      # test bölmesi başlangıcı
    t = g.iloc[lo:]
    for c in GROD:
        na = t[c].isna()
        if na.any():
            grp = (na != na.shift()).cumsum()
            uzun = na.groupby(grp).sum().max()
            ilk  = t.loc[na, "Time"].min(); son = t.loc[na, "Time"].max()
        else:
            uzun, ilk, son = 0, None, None
        satir.append({"sera": gh, "kolon": c, "test_satir": len(t),
                      "nan_satir": int(na.sum()), "nan_pct": round(100*na.mean(), 2),
                      "en_uzun_blok": int(uzun), "blok_saat": round(uzun*5/60, 1),
                      "ilk_nan": ilk, "son_nan": son})
r = pd.DataFrame(satir)
r.to_csv(BASE_DIR / "grodan_nan_test_bolmesi.csv", index=False)
print(r.to_string(index=False))
```

**Bilinen bulgu:** 26–30 Mayıs arasında altı serada da eşzamanlı ~86 saatlik Grodan kesintisi var (tesis geneli arıza). Bu yüzden Core+Grodan test penceresi 568 yerine 470'tir. Ufuk büyüdükçe bu boşluğun eleyeceği pencere sayısı artar — 24h'de etkisi daha büyük olacaktır.
