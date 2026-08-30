# AGC Karar Destek Sistemi

**Sera İklimi ve Kök Bölgesi Tahmini → Ekonomik Analiz → Açıklanabilir Karar Destek Katmanı**

Bu depo, [Autonomous Greenhouse Challenge (AGC), 2. Edisyon](https://data.4tu.nl/articles/_/12764777/2) veri seti üzerine kurulmuş uçtan uca bir karar destek sisteminin tüm kodunu, raporlarını ve bulgularını içerir. Sistem beş aşamada gelişti: kısa ve uzun vadeli iklim tahmini → altı takımın strateji-sonuç analizi → ekonomik modelleme → kalibre edilmiş bir risk/karar katmanı → bu katmanı doğal dilde açıklayan bir yapay zekâ bileşeni.

## Neden bu proje ilginç

Bu sadece bir tahmin modeli değil. Her aşama, bir önceki aşamanın **ölçülmüş** bir kusurunu düzeltti:

| Aşama | Bulgu |
|---|---|
| Tahmin | Hiçbir model ailesi (basit yöntem/derin öğrenme) her hedefte üstün değil — doğru yöntem hedefe göre değişiyor |
| Strateji | Kaynakları fiziksel birimlerle karşılaştırmak yanıltıcıydı; euro'ya çevirince sonuç tersine döndü |
| Ekonomi | Bir kod hatası (`iterrows()` tip bozulması) net kâr sıralamasını değiştiriyordu; düzeltilince gerçek yarışma sonucuyla birebir örtüştü |
| Karar katmanı | Yanlış uyarı kriteri, iklim değişkenlerinde kesinliği %29'a düşürüyordu; kriter değişken ailesine göre ayrıştırılınca %70'e çıktı |
| Çok-ajanlı mimari | Yol haritası dört ayrı ajan öngörüyordu; üç aday çatışma senaryosu ölçüldü, hiçbiri ekonomik/istatistiksel eşiği geçmedi — mimari tek açıklayıcı ajana indirgendi |

Aynı hata deseni (bir referans değerini yanlış bir dönemle karşılaştırmak — "mevsimsel karıştırma") projede **dört ayrı yerde** bulunup düzeltildi. Bu depo o sürecin tamamını, düzeltmeler dahil, saklıyor.

## Sonuçlar — bir bakışta

<table>
<tr>
<td width="50%">

**Karar destek sisteminin nihai performansı** (geriye dönük test, Mayıs dönemi):

Precision **0.820** · Recall **0.829** · F1 **0.824**
Temel olay oranından **5.9 kat** daha isabetli.

</td>
<td width="50%">

![Nihai performans](figures/gorsel6_nihai_ozet.png)

</td>
</tr>
</table>

| | | |
|---|---|---|
| ![Sulama vakaları](figures/gorsel1_sulama_vaka.png) | ![Model karşılaştırması](figures/gorsel2_en_dusuk_hata.png) | ![İstatistiksel anlamlılık](figures/gorsel3_istatistik_anlamlilik.png) |
| ![Maliyet doğrulama](figures/gorsel4_maliyet_dogrulama.png) | ![Kriter hizalama](figures/gorsel5_kriter_hizalama.png) | |

## Proje yapısı

```
reports/                     Tüm raporlar (kronolojik sırayla numaralı)
  01_nihai_rapor_3h_6h.md    Kısa vadeli tahmin — KİLİTLİ, sayıları değiştirilmedi
  02_strateji_sonuc_raporu.md   Sürüm 2 (euro cinsinden düzeltilmiş)
  03_ekonomi_raporu.md
  04_karar_katmani_raporu.md
  05_karar_gunlugu.md        Projenin tam kronolojik karar kaydı — en detaylı belge
  06_konfigurasyon_referansi.md
  07_parametre_degisiklik_gunlugu.md
  08_uzun_vadeli_tahmin_12h_24h.md
  09_faz6_multi_agent_raporu.md   Çok-ajanlı mimarinin ölçülüp reddedildiği, tek-ajan
                              mimarisinin kurulduğu son faz
  archive/                   Süperseded belgeler (tarihsel referans için tutuluyor)

src/
  01_forecasting/            Veri hattı, pencere üretimi, baseline'lar, derin modeller,
                              LOTO çapraz doğrulama, istatistiksel anlamlılık testi
  02_strategy/                Altı takımın strateji-sonuç karşılaştırması
  03_economics/               Maliyet serisi inşası, net kâr hesabı, maliyet tahmini denemeleri
  04_decision_layer/          Kalibrasyon, karar bilgi tabanı (DKB), risk motoru — İLK SÜRÜM
  05_multi_agent/             Faz 6 — GÜNCEL risk motoru + açıklayıcı ajan + sayı denetleyici

data/
  decision_knowledge_base_v3.csv   İlk DKB (mevsim ayrımı yok — bkz. Bilinen Sorunlar)
  decision_knowledge_base_v5.csv   GÜNCEL DKB (818 satır, mevsim-içi eşikler)
  kural_guvenilirlik.csv           20 kuralın ölçülmüş isabeti

figures/                      Rapor görselleri
```

### ⚠️ `agc_risk_motoru.py` ve `agc_trajektori_ozeti.py` iki yerde var

Bu iki dosya hem `04_decision_layer/` (ilk kurulan sürüm) hem `05_multi_agent/` (Faz 6'da düzeltilmiş, güncel sürüm) klasöründe bulunuyor. **Üretim/referans amaçlı kullanım için her zaman `05_multi_agent/` altındaki sürüm esas alınmalıdır** — `decision_knowledge_base_v5.csv` ile birlikte çalışacak şekilde güncellenmiş, "sürekli sapma / dokunma" kriter ayrımını değişken ailesine göre doğru uyguluyor. `04_decision_layer/` altındaki sürümler yalnızca projenin nasıl evrildiğini göstermek için tutuluyor.

## Veriye erişim

Ham veri seti bu depoda **yok** (boyut nedeniyle). Kaynak:

> Hemming, S.; de Zwart, F.; Elings, A.; Petropoulou, A.; Righini, I. (2020). **Autonomous Greenhouse Challenge, Second Edition (2019)**. Version 2. 4TU.ResearchData. [doi:10.4121/uuid:88d22c60-21b3-4ea8-90db-20249a5be2a7](https://doi.org/10.4121/uuid:88d22c60-21b3-4ea8-90db-20249a5be2a7)
>
> Lisans: **CC0** (kamu malı — atıf zorunlu değil, ama akademik nezaket olarak önerilir)

## Bilinen sorunlar ve şeffaflık notları

Bu proje "hiçbir şeyi gizlememe" ilkesiyle yürütüldü. Bulunan ve **henüz düzeltilmemiş** sorunlar:

**1. `01_nihai_rapor_3h_6h.md` Ek B.3'te sayısal hata (rapor kilitli, ana metne dokunulmadı):**

| Satır | Raporda yazan | Doğrulanan |
|---|---|---|
| Naif Diebold-Mariano | 26 / 32 | **29 / 32** |
| HAC + blok bootstrap + FDR | 16 / 32 | **19 / 32** |

Anlatı doğru kalmış (her iki çiftin farkı da 10), ama mutlak sayılar erken bir koşudan kopyalanıp güncellenmemiş. §4.4'ün kendisi (13 fark yok / 11 derin / 8 baseline) bağımsız olarak yeniden doğrulandı ve doğru.

**2. Reproducibility notu:** `01_forecasting/agc_anlamlilik.py`'yi varsayılan girdiyle (tek dosya) çalıştırmak, raporun §4.4 sonucundan **farklı** bir çıktı (17 derin / 3 baseline / 12 fark yok) üretir. Sebep: rapor, iki ayrı sonuç dosyasının (analitik baseline'lar + Ridge) birleştirilmesiyle üretildi; bu birleştirme adımı ayrı bir script olarak kayıtlı değil. Script'i çalıştırıp rapordan farklı bir sayı alırsanız, bu bir hata değil — eksik bir girdi adımıdır.

**3. `data/decision_knowledge_base_v3.csv`'nin zarf eşikleri mevsim ayrımı yapmıyor.** Bu, `decision_knowledge_base_v5.csv`'de düzeltildi (mevsimsel dengesizlik 153.6× → 1.5×). `v3` yalnızca tarihsel referans için tutuluyor, kullanılmamalı.

Detaylı kayıt için `reports/05_karar_gunlugu.md` — projenin tüm kararları, bulunan hatalar ve düzeltmeleri kronolojik olarak burada.

## Nasıl çalıştırılır

```bash
pip install -r requirements.txt
```

Script'ler ham veriyi `common_core_with_grodan_strict.parquet` gibi ara işlenmiş dosyalardan okuyor (repo'da yok, veri kaynağından türetilmeli). Her script'in başındaki `BASE_DIR` değişkeni kendi ortamınıza göre ayarlanmalı — script'ler orijinal olarak Google Colab (`/content/drive/MyDrive/...`) ve bir yerel Windows/Anaconda ortamında geliştirildi.

## Lisans

Kod: MIT. Veri seti: yukarıda belirtildiği gibi CC0 (Wageningen University & Research).

---

*Bu proje 20 Temmuz – 28 Ağustos 2026 tarihleri arasında 30 iş günlük bir çalışmanın ürünüdür.*
