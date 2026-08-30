"""
AGC - TRAJEKTORI OZETI CIKARIMI  (v2 — ZAMAN DAMGALI)
======================================================
BACKTEST KUSURUNU DUZELTIR.

SORUN: Backtest'te model TERMINAL degeri tahmin ediyordu (t+6h anindaki
deger), ama gercek-durum PENCERE ICI MAKSIMUM olarak tanimlanmisti.
Uyusmayan karsilastirma.

Kanit (mevcut backtest ciktisi):
    KALITATIF recall   A (terminal<->terminal) 0.689  ->  B 0.425
    SAYISAL   recall   A 0.871                        ->  B 0.787

Recall'daki dusus modelin kotulugunden degil, olcumun tutarsizligindan
geliyordu. SAYISAL daha az etkilendi cunku EC/WC yavas hareket ediyor
(pencere ici max, terminal degere yakin).

COZUM: Modeller zaten 72 adimlik trajektorinin TAMAMINI uretiyor; biz
yalnizca son adimi kaydetmistik. Bu script trajektorinin PENCERE ICI
max/min degerlerini cikarir. Boylece:

    tahmin_max  <-->  gercek_max     (tutarli)
    tahmin_son  <-->  gercek_son     (tutarli)

Her iki tanim da ayri ayri saklanir; backtest ikisini de kullanabilir.


v2'DE NE DEGISTI — 'Time' KOLONU
---------------------------------
Karar destek katmani (agc_karar_kaydi.py) bir ANA dayanir: "2020-05-22 16:00'da
sistem ne dedi". Backtest zaman kolonunu hic kullanmadigi icin eklenmemisti,
ama demo tek bir ani gosteriyor ve o ani bulmak icin zaman lazim.

Zaman kolonu olmadan demo Oile calismak zorunda kalir: gerceklesmis gelecek
"tahmin" diye verilir. Sayilar dogru ama MODEL DEVREDE DEGILDIR.

'Time' TANIMI: tahminin YAPILDIGI capa ani (pencerenin bittigi an degil).
3h tahmini icin Time = T, pencere T .. T+3h. Karar kaydindaki 'zaman' alani
da bu capa anidir; ikisi eslesmelidir.

KENDI KENDINI DOGRULAR: zaman cozumu modeller YUKLENMEDEN once yapilir ve
split sinirlari bilinen tarihlerle karsilastirilir:
    train 2019-12-16 .. 2020-04-10 · val 04-10 .. 05-05 · test 05-05 .. 05-30
Uyusmuyorsa capa tanimi yanlistir ve kosu BASLAMADAN durur (25 dakika
bosa gitmesin diye).

ON KOSUL: agc_all_in_one.py exec edilmis olmali.
SURE: ~25 dakika (val + test, 6 multi + 48 single checkpoint)
CIKTI: trajektori_ozeti.parquet
"""

from __future__ import annotations

SURUM = "2026-08-23.7"   # TCN: build + load_weights (Lambda deserialize cokmesi)

import gc
import os
from pathlib import Path

import numpy as np
import pandas as pd


def _ram_mb() -> float:
    """Surecin kullandigi RAM (MB). psutil yoksa /proc'tan okur."""
    try:
        import psutil
        return psutil.Process(os.getpid()).memory_info().rss / 1e6
    except Exception:                                             # noqa: BLE001
        try:
            with open("/proc/self/status") as f:
                for l in f:
                    if l.startswith("VmRSS:"):
                        return float(l.split()[1]) / 1024
        except Exception:                                         # noqa: BLE001
            pass
        return float("nan")


def _gpu_mb() -> str:
    """GPU bellek kullanimi (guncel/tepe MB). Cokme teshisi icin.

    RAM sabit kalip cekirdek olurse sebep buradadir: TF, ALLOW_GROWTH ile
    aldigi GPU bellegini isletim sistemine GERI VERMEZ. clear_session()
    grafigi temizler ama ayrilmis bellek surecte kalir; 48 model yuklendikten
    sonra agir bir mimari (TCN) siniri asabilir.
    """
    try:
        import tensorflow as tf
        d = tf.config.experimental.get_memory_info("GPU:0")
        return f"{d['current']/1e6:.0f}/{d['peak']/1e6:.0f}"
    except Exception:                                             # noqa: BLE001
        return "-"


_STORE_ONBELLEK: dict = {}


def _store_yukle(base_dir: Path, fs_name: str):
    """load_arrays ONBELLEKLI.

    Eski surumde cikar() her cagrida load_arrays yapiyordu: 6 sera x
    (47809, 50) float32 = 57 MB, 72 kez. Onbellek bunu bir kereye indirir.
    """
    if fs_name not in _STORE_ONBELLEK:
        _STORE_ONBELLEK[fs_name] = globals()["load_arrays"](base_dir, fs_name)
    return _STORE_ONBELLEK[fs_name]


# Bu modeller load_model YERINE build + load_weights ile yuklenir.
#
# NEDEN: build_tcn icinde bir Lambda katmani var --
#     x = layers.Lambda(lambda t: t[:, -1, :])(x)
# Lambda, Python fonksiyonunu BYTECODE olarak saklar. Model baska bir Python
# surumunde egitildiyse Keras o bytecode'u cozerken yorumlayiciyi COKERTIR.
# GRU/LSTM'de Lambda yok, o yuzden onlar sorunsuz yukleniyor.
#
# DIKKAT: bu bir Python ISTISNASI degil, SEGFAULT. try/except YAKALAYAMAZ --
# surec oluyor. Bu yuzden TCN icin load_model DENENMEZ bile; dogrudan
# mimari koddan kurulur ve yalnizca agirlik tensorleri dosyadan okunur.
# Agirliklar ayni oldugu icin tahminler de AYNIDIR; yeniden egitim gerekmez.
AGIRLIK_ILE = ("tcn",)


def _model_yukle(ck, model_name: str, store, targets):
    """Checkpoint'i yukler. AGIRLIK_ILE listesindekiler icin mimari KODDAN kurulur."""
    from tensorflow import keras
    g = globals()
    if model_name not in AGIRLIK_ILE:
        return keras.models.load_model(ck, safe_mode=False, compile=False), "load_model"

    for ad in ("BUILDERS", "SIZE_PRESETS", "MODEL_SIZE"):
        if ad not in g:
            raise RuntimeError(f"'{ad}' bulunamadi -- once agc_all_in_one.py'yi exec edin.")
    cfg = g["SIZE_PRESETS"][g["MODEL_SIZE"]]
    n_feat = int(next(iter(store.values()))["feats"].shape[1])
    n_tgt = len(targets)
    model = g["BUILDERS"][model_name](n_feat, n_tgt, cfg)
    model.load_weights(str(ck))          # yalnizca tensorler; mimari tarifi OKUNMAZ
    return model, f"build+load_weights (n_feat={n_feat}, n_tgt={n_tgt})"


def _temizle():
    """Keras oturumunu ve cop toplayiciyi calistir.

    Eski surumde load_model dongude 72 kez cagriliyordu ve TF grafigi hic
    temizlenmiyordu. Cekirdek olumunun en olasi sebeplerinden biri budur.
    """
    try:
        from tensorflow import keras
        keras.backend.clear_session()
    except Exception:                                             # noqa: BLE001
        pass
    gc.collect()

ADIM = {"3h": 36, "6h": 72}



def _kontrol():
    eksik = [k for k in ["load_arrays", "collect_starts", "compute_norm_stats",
                         "WindowSequence", "get_raw_eval_data", "ANCHOR_BY_TARGET",
                         "DEFAULT_ANCHOR", "RESIDUAL_MODE", "BATCH_SIZE",
                         "MODEL_SIZE", "FEATURE_SETS"] if k not in globals()]
    if eksik:
        raise RuntimeError("Once agc_all_in_one.py'yi exec edin. Eksik: " + ", ".join(eksik))


# ---------------------------------------------------------------------------
# ZAMAN COZUMU
# ---------------------------------------------------------------------------
def yapi_incele(base_dir: Path, fs_name: str = "core_grodan", split: str = "test"):
    """TESHIS: store ve start yapisini basar.

    Zaman cozumu asagidaki fonksiyonda birkac olasi yapiyi deniyor. Hicbiri
    tutmazsa BU fonksiyonun ciktisini paylasin; cozumu ona gore yazariz.
    Modelleri yuklemez, saniyeler surer.
    """
    g = globals()
    store, target_idx, targets, fcols = g["load_arrays"](base_dir, fs_name)
    st = g["collect_starts"](store, split)
    print("=" * 74)
    print(f"YAPI INCELEMESI · fs={fs_name} · split={split}")
    print("=" * 74)
    print(f"store tipi   : {type(store)}")
    if isinstance(store, dict):
        print(f"store anahtarlari ({len(store)}): {list(store)[:8]}")
        ilk = store[list(store)[0]]
        print(f"ilk deger tipi: {type(ilk)}")
        if isinstance(ilk, dict):
            print(f"  ic anahtarlar: {list(ilk)}")
            for k, v in ilk.items():
                bilgi = getattr(v, "shape", None) or (len(v) if hasattr(v, "__len__") else "-")
                print(f"    {k:<16} {type(v).__name__:<12} {bilgi}")
    else:
        for a in ("keys", "_fields", "__dict__"):
            if hasattr(store, a):
                print(f"store.{a}: {getattr(store, a)}")
                break
    print()
    print(f"st tipi      : {type(st)} · uzunluk {len(st)}")
    print(f"st[:3]       : {st[:3]}")
    if len(st) and hasattr(st[0], "__len__") and not isinstance(st[0], (str, bytes)):
        print(f"st[0] ogeleri: {[type(x).__name__ for x in st[0]]}")
    print()
    print("targets:", targets)
    print("=" * 74)
    return store, st


def _sera_zaman_ekseni(base_dir: Path, seralar) -> dict:
    """Her sera icin 5dk'ya yuvarlanmis zaman ekseni (feats dizisiyle ayni sirada)."""
    yol = Path(base_dir) / "operational_v2_combined.csv"
    if not yol.exists():
        raise RuntimeError(f"{yol} bulunamadi -- capa zamani cozulemez.")
    ham = pd.read_csv(yol, usecols=["Time", "greenhouse_id"], parse_dates=["Time"])
    ham["Time"] = ham.Time.dt.round("5min")
    eksen = {g: d.sort_values("Time").Time.reset_index(drop=True)
             for g, d in ham.groupby("greenhouse_id")}
    eksik = [s for s in seralar if s not in eksen]
    if eksik:
        raise RuntimeError(f"operational dosyasinda su seralar yok: {eksik}")
    return eksen


def capa_zamanlari(base_dir: Path, store, st, gh_ids, split=None,
                   capa_kolonu: str = "output_start", kaydirma: int = 0):
    """Her pencere icin CAPA zamani = tahminin BASLADIGI an.

    NEDEN 'output_start': store[sera]['windows'] uc sutun tasiyor --
        input_start   : 24 saatlik gecmis penceresinin basi
        output_start  : tahminin BASLADIGI an   <-- KARAR ANI budur
        window_end    : tahmin penceresinin sonu
    Ornek satir: 108 -> 396 -> 468 (fark sabit 288 adim = 24 saat).

    'st' listesi input_start tasir. Ilk surumde capa olarak o kullanildi ve
    zamanlar 24 saat GERIDE cikti. Kaydirma hesabi yapmak yerine 'windows'
    tablosundan dogrudan output_start okunur -- tahmin yurutulmez.

    Dogrulama: cozulen her pencerenin 'windows' tablosundaki split etiketi
    istenen split ile ESLESMELIDIR. Eslesmezse indeksleme kaymis demektir.
    """
    seralar = sorted({gh_ids[w] for w in range(len(st))})
    eksen = _sera_zaman_ekseni(base_dir, seralar)

    # (sera, input_start) -> (capa_indeksi, split)  esleme tablosu
    harita = {}
    for sera, veri in store.items():
        w = veri.get("windows") if isinstance(veri, dict) else None
        if w is None or capa_kolonu not in getattr(w, "columns", []):
            raise RuntimeError(
                f"store['{sera}']['windows'] icinde '{capa_kolonu}' kolonu yok. "
                f"Bulunanlar: {list(getattr(w, 'columns', []))}")
        for r in w.itertuples():
            harita[(sera, int(r.input_start))] = (int(getattr(r, capa_kolonu)),
                                                  getattr(r, "split", None))

    zaman, split_etiketi, kayip = [], [], 0
    for i, s in enumerate(st):
        sera, ix = (s[0], int(s[-1])) if isinstance(s, (tuple, list)) else (gh_ids[i], int(s))
        anahtar = harita.get((sera, ix))
        if anahtar is None:
            kayip += 1
            continue
        capa, sp = anahtar
        z = eksen[sera]
        j = capa + kaydirma
        if not (0 <= j < len(z)):
            kayip += 1
            continue
        zaman.append(z.iloc[j]); split_etiketi.append(sp)

    if kayip:
        raise RuntimeError(f"{kayip}/{len(st)} pencere icin capa cozulemedi -- "
                           f"'windows' tablosu ile st listesi uyusmuyor.")
    if split is not None:
        yanlis = sum(1 for x in split_etiketi if x is not None and x != split)
        if yanlis:
            raise RuntimeError(f"{yanlis}/{len(st)} pencerenin split etiketi "
                               f"'{split}' degil -- indeksleme kaymis.")
    return pd.to_datetime(pd.Series(zaman)), f"windows.{capa_kolonu}"


def _sinir_dogrula(zamanlar: pd.Series, split: str, kaynak: str, n_pencere: int) -> bool:
    """ICSEL tutarlilik kontrolu.

    Ilk surumde SABIT tarihlerle karsilastiriliyordu ve yanlis alarm verdi:
    pencere capalar veri sonuna kadar gidemez (her pencere 288 adim gecmis +
    72 adim gelecek ister, ayrica bosluklu bolgeler atlanir). Sabit tarih
    beklentisi bu yuzden yanlisti -- capa tanimi degil.

    Artik kontrol edilen: (a) her pencereye bir zaman dustu mu, (b) zamanlar
    artan mi, (c) 5dk izgarasina oturuyor mu. Tarih araligi bilgi olarak basilir.
    """
    a, b = zamanlar.min(), zamanlar.max()
    print(f"  [zaman] {split:<5} kaynak={kaynak:<22} {a:%Y-%m-%d %H:%M} .. "
          f"{b:%Y-%m-%d %H:%M}  ({zamanlar.nunique()} tekil capa / {len(zamanlar)} pencere)")
    ok = True
    if len(zamanlar) != n_pencere:
        print(f"  [zaman] !! {len(zamanlar)} zaman / {n_pencere} pencere -- uyusmuyor")
        ok = False
    izgara = (zamanlar.dt.minute % 5 == 0) & (zamanlar.dt.second == 0)
    if not izgara.all():
        print(f"  [zaman] !! {int((~izgara).sum())} zaman 5dk izgarasinda degil")
        ok = False
    return ok


# ---------------------------------------------------------------------------
def cikar(base_dir: Path, fs_name: str, model_name: str, split: str,
          only_target=None, zamanlar=None):
    """Bir checkpoint icin: her pencere x ufuk x hedef -> tahmin ve gercek
    degerlerin pencere ici max / min / son degerleri."""
    from tensorflow import keras
    g = globals()
    store, target_idx, targets, fcols = _store_yukle(base_dir, fs_name)
    if only_target is not None:
        if only_target not in targets:
            return None
        target_idx = [fcols.index(only_target)]; targets = [only_target]

    suffix = ("resid" if g["RESIDUAL_MODE"] else "abs") + ("_single" if only_target else "")
    mt = f"{model_name}_{suffix}_{g['MODEL_SIZE']}"
    tag = f"{fs_name}_{mt}" + (f"_{only_target}" if only_target else "")
    ck = base_dir / "checkpoints" / f"{tag}.keras"
    if not ck.exists():
        return None

    anchor = [g["ANCHOR_BY_TARGET"].get(t, g["DEFAULT_ANCHOR"]) for t in targets]
    tr = g["collect_starts"](store, "train")
    st = g["collect_starts"](store, split)
    if not st:
        return None
    stats = g["compute_norm_stats"](store, tr, target_idx, anchor)

    model, yukleme_yolu = _model_yukle(ck, model_name, store, targets)
    if model_name in AGIRLIK_ILE:
        print(f"      [{model_name}] {yukleme_yolu} · {model.count_params():,} parametre",
              flush=True)
    seq = g["WindowSequence"](store, st, target_idx, stats, g["BATCH_SIZE"], anchor)
    P = model.predict(seq, verbose=0) * stats["tgt_std"] + stats["tgt_mean"]
    Y, cipa, gh_ids = g["get_raw_eval_data"](store, st, target_idx, anchor)
    if g["RESIDUAL_MODE"]:
        P = P + cipa                       # (n_win, 72, n_tgt)

    # v2: pencere basina capa zamani (onceden cozulmus olarak gelir)
    zs = zamanlar.get(split) if isinstance(zamanlar, dict) else None
    if zs is not None and len(zs) != Y.shape[0]:
        raise RuntimeError(f"zaman dizisi ({len(zs)}) pencere sayisiyla "
                           f"({Y.shape[0]}) uyusmuyor · {fs_name}/{mt}/{split}")

    # VEKTOREL kurulum. Eski surum satir satir dict uretiyordu:
    # 1.49M dict x ~1.2 KB = ~1.8 GB gecici zirve. Ayni sonucu numpy ile
    # uretmek hem hizli hem hafif. Hesap BIREBIR aynidir:
    #   Pd[w,:,j].max()  ==  Pd[:,:,j].max(axis=1)[w]
    n_win = Y.shape[0]
    gh = pd.Categorical(np.asarray(gh_ids))
    ix = np.arange(n_win, dtype=np.int32)
    parcalar = []
    for ad, adim in ADIM.items():
        Pd, Yd = P[:, :adim, :], Y[:, :adim, :]
        for j, t in enumerate(targets):
            df = pd.DataFrame({
                "window_ix": ix,
                "greenhouse_id": gh,
                "pred_max": Pd[:, :, j].max(axis=1).astype(np.float32),
                "pred_min": Pd[:, :, j].min(axis=1).astype(np.float32),
                "pred_son": Pd[:, -1, j].astype(np.float32),
                "true_max": Yd[:, :, j].max(axis=1).astype(np.float32),
                "true_min": Yd[:, :, j].min(axis=1).astype(np.float32),
                "true_son": Yd[:, -1, j].astype(np.float32),
            })
            if zs is not None:
                df["Time"] = zs.to_numpy()          # v2: capa ani
            # tekrar eden dizeler KATEGORIK -- bellek icin
            df["feature_set"] = pd.Categorical([fs_name] * n_win)
            df["model"] = pd.Categorical([mt] * n_win)
            df["split"] = pd.Categorical([split] * n_win)
            df["horizon"] = pd.Categorical([ad] * n_win)
            df["target"] = pd.Categorical([t] * n_win)
            parcalar.append(df)
    del P, Y, cipa, Pd, Yd, model, seq
    _temizle()
    return pd.concat(parcalar, ignore_index=True)


def run(base_dir: Path, feature_sets=("core_grodan",), models=("gru", "lstm", "tcn"),
        single_target=True, splitler=("val", "test"),
        capa_kolonu: str = "output_start", capa_kaydirma: int = 0,
        zaman_zorunlu: bool = True, sinirla: int | None = None,
        devam: bool = True, parca_dizin=None):
    """capa_kolonu   : 'windows' tablosunda capa olarak kullanilacak sutun.
                      VARSAYILAN 'output_start' = tahminin BASLADIGI an = karar ani.
                      ('input_start' 24 saat once, gecmis penceresinin basidir.)
    capa_kaydirma   : gerekirse ek kaydirma (1 adim = 5 dk); normalde 0
    parca_dizin     : None -> <base_dir>/_trajektori_parca (Drive, kalici).
                      "/content/_trajektori_parca" daha hizli ama cekirdek
                      yeniden baslatilinca silinir.
    devam           : True (varsayilan) ise tamamlanmis parcalar ATLANIR --
                      cokme sonrasi kaldigi yerden devam eder.
    sinirla         : yalnizca ilk N adimi kos (cokme teshisi icin).
                      sinirla=2 ile once kucuk bir kosu deneyin.
    zaman_zorunlu   : True ise zaman cozulemezse KOSU BASLAMAZ (varsayilan).
                      False yaparsan eski davranis (Time kolonsuz) uretilir --
                      demo o dosyayla MODEL MODUNDA calisamaz."""
    _kontrol()
    g = globals()

    # --- ZAMAN COZUMU: modeller yuklenmeden ONCE, hizli, dogrulanabilir ----
    print("=" * 78)
    print(f"ZAMAN COZUMU (capa={capa_kolonu}, kaydirma={capa_kaydirma})")
    print("=" * 78)
    zamanlar, tum_tamam = {}, True
    fs0 = feature_sets[0]
    store0, target_idx0, targets0, _ = g["load_arrays"](base_dir, fs0)
    for sp in splitler:
        st = g["collect_starts"](store0, sp)
        if not st:
            continue
        _, _, gh_ids = g["get_raw_eval_data"](store0, st, target_idx0,
                                              [g["ANCHOR_BY_TARGET"].get(t, g["DEFAULT_ANCHOR"])
                                               for t in targets0])
        try:
            z, kaynak = capa_zamanlari(base_dir, store0, st, gh_ids, split=sp,
                                       capa_kolonu=capa_kolonu, kaydirma=capa_kaydirma)
        except RuntimeError as e:
            if zaman_zorunlu:
                raise
            print(f"  [zaman] {sp}: COZULEMEDI -> {e}")
            tum_tamam = False
            continue
        zamanlar[sp] = z.reset_index(drop=True)
        tum_tamam &= _sinir_dogrula(zamanlar[sp], sp, kaynak, len(st))

    if not tum_tamam and zaman_zorunlu:
        raise RuntimeError(
            "Zaman cozumu icsel tutarlilik kontrolunden gecemedi. Kosu BASLATILMADI. "
            "yapi_incele(BASE_DIR) ciktisini paylasin, ya da zaman_zorunlu=False ile "
            "eski davranisa donun (demo model modunda calismaz).")
    print()

    # Parcalar DISKE yazilir, bellekte BIRIKMEZ.
    # Eski surum 72 DataFrame'i ayni anda tutuyordu; cekirdek olumunun ikinci
    # olasi sebebi buydu. Simdi her checkpoint kendi parquet parcasina yazilir
    # ve en sonda birlestirilir -- bellek tek checkpoint'le sinirli kalir.
    # DEVAM ETME: parcalar SILINMEZ. Kosu coktugunde 48 adimlik is bosa
    # gitmesin diye tamamlanan adimlar atlanir. Sifirdan baslamak icin
    # devam=False verin.
    # Parca dizini VARSAYILAN olarak base_dir icinde (Drive). Drive yazimi
    # yavas ve zaman zaman kirilgan; yerel diske almak icin
    # parca_dizin="/content/_trajektori_parca" verin -- ama cekirdek yeniden
    # baslatilinca yerel disk SILINIR, devam etme ozelligi kaybolur.
    parca_dizin = Path(parca_dizin) if parca_dizin else Path(base_dir) / "_trajektori_parca"
    parca_dizin.mkdir(parents=True, exist_ok=True)
    if not devam:
        for eski in parca_dizin.glob("*.parquet"):
            eski.unlink()
        print("  [devam=False] onceki parcalar silindi")

    yazilan, n_satir, adim_no = [], 0, 0
    plan = [(fs, m, tgt, sp)
            for fs in feature_sets
            for m in models
            for tgt in [None] + (list(g["FEATURE_SETS"][fs][2]) if single_target else [])
            for sp in splitler]
    if sinirla:
        plan = plan[:sinirla]
        print(f"  [sinirla] yalnizca ilk {sinirla} adim kosulacak (deneme modu)\n")

    print(f"  baslangic RAM: {_ram_mb():.0f} MB · GPU {_gpu_mb()} MB · {len(plan)} adim")
    hazir = sorted(parca_dizin.glob("*.parquet"))
    if hazir:
        print(f"  [devam] {len(hazir)} parca zaten var, o adimlar atlanacak")
    print()
    for fs, m, tgt, sp in plan:
        adim_no += 1
        # NOT: dosya adi ICERIKTEN uretilir; farkli 'models' argumanlariyla
        # kosuldugunda parcalar birbirine karismaz.
        yol = parca_dizin / _parca_adi(fs, m, tgt, sp)
        if yol.exists():                       # DEVAM: bu adim zaten tamam
            n_satir += len(pd.read_parquet(yol, columns=["window_ix"]))
            yazilan.append(yol)
            continue
        print(f"  [{adim_no:3d}/{len(plan)}] {fs}/{m}/{tgt or 'ALL':10s}/{sp:4s} "
              f"basliyor...", flush=True)
        d = cikar(base_dir, fs, m, sp, tgt, zamanlar)
        if d is None:
            print(f"  [{adim_no:3d}/{len(plan)}] {fs}/{m}/{tgt or 'ALL':10s}/{sp:4s} "
                  f"checkpoint yok, atlandi")
            continue
        d.to_parquet(yol, index=False)
        n_satir += len(d)
        yazilan.append(yol)
        del d
        _temizle()
        print(f"  [{adim_no:3d}/{len(plan)}] {fs}/{m}/{tgt or 'ALL':10s}/{sp:4s} "
              f"tamam · {n_satir:,} satir · RAM {_ram_mb():.0f} MB · GPU {_gpu_mb()} MB",
              flush=True)

    if not yazilan:
        print("Hicbir checkpoint bulunamadi."); return None
    print(f"\n  parcalar birlestiriliyor ({len(yazilan)} dosya, {n_satir:,} satir)...")
    d = pd.concat([pd.read_parquet(y) for y in yazilan], ignore_index=True)

    # KATEGORIK -> DUZ METIN. Kategorik dtype kosu SIRASINDA bellek kazandirir,
    # ama diske yazilirsa asagi akista kirilma yaratir:
    # agc_backtest_v3.sigma_hesapla() groupby yapiyor ve kategorik sutunlarda
    # pandas varsayilan olarak TUM kategori carpimini uretir (observed=False).
    # Bos gruplar olusur ve np.percentile(bos_seri) hata verir.
    # Cikti semasini eski surumle BIREBIR ayni tutmak icin geri cevriliyor.
    for c in ("feature_set", "model", "split", "horizon", "target", "greenhouse_id"):
        if c in d.columns and str(d[c].dtype) == "category":
            d[c] = d[c].astype(str)
    d.to_parquet(base_dir / "trajektori_ozeti.parquet", index=False)
    # Parcalar SILINMEZ: sonradan eksik modeller eklenip yeniden
    # birlestirilebilsin diye. Temizlemek icin dizini elle silin.
    print(f"  birlestirme tamam · RAM {_ram_mb():.0f} MB · "
          f"parcalar korundu ({parca_dizin})")

    print("\n" + "=" * 78)
    print("TRAJEKTORI OZETI")
    print("=" * 78)
    print(f"  {len(d):,} satir · {d.model.nunique()} model · {d.target.nunique()} hedef")
    if "Time" in d.columns:
        print(f"  ZAMAN KOLONU VAR · {d.Time.nunique()} tekil capa ani")
        print(d.groupby("split", observed=True).Time.agg(["min", "max", "nunique"]).to_string())
    else:
        print("  !! ZAMAN KOLONU YOK — demo MODEL MODUNDA calisamaz")

    # --- Dogrulama: terminal degerler kalibrasyon dosyasiyla eslesiyor mu? ---
    kp = base_dir / "kalibrasyon_ham.parquet"
    if kp.exists():
        k = pd.read_parquet(kp)
        a = d.groupby(["model", "split", "horizon", "target"], observed=True).pred_son.mean()
        b = k.groupby(["model", "split", "horizon", "target"], observed=True).y_pred.mean()
        o = a.index.intersection(b.index)
        if len(o):
            f = (a.loc[o] - b.loc[o]).abs() / b.loc[o].abs().clip(lower=1e-9)
            print(f"\n  Kalibrasyon dosyasiyla tutarlilik: {len(o)} ortak, "
                  f"max bagil fark {f.max():.2e}")
            print(f"  {'TUTARLI — ayni modeller' if f.max() < 1e-3 else 'FARKLI — INCELE'}")

    # --- Terminal ile pencere-ici tahmin ne kadar farkli? ---
    t = d[d.split == "test"].copy()
    t["fark_max"] = (t.pred_max - t.pred_son).abs()
    t["fark_true"] = (t.true_max - t.true_son).abs()
    ozet = t.groupby(["horizon", "target"], observed=True).agg(
        tahmin_farki=("fark_max", "mean"), gercek_farki=("fark_true", "mean"))
    ozet["oran"] = (ozet.tahmin_farki / ozet.gercek_farki.replace(0, np.nan)).round(2)
    print("\n" + "=" * 78)
    print("PENCERE ICI MAX ile TERMINAL arasindaki fark")
    print("  oran ~1.0 -> model trajektori sekillerini dogru yakaliyor")
    print("  oran <1.0 -> model uc noktalari yeterince tahmin edemiyor (duzlestirme)")
    print("=" * 78)
    print(ozet.round(3).sort_values("oran").to_string())

    print(f"\nKaydedildi: trajektori_ozeti.parquet")
    return d


def _parca_adi(fs: str, model: str, tgt, split: str) -> str:
    """Parca dosya adi ICERIKTEN uretilir, sira numarasindan DEGIL.

    ILK SURUMDEKI HATA: parcalar p001, p002... diye numaralaniyordu ve numara
    'plan' icindeki KONUMA baglilydi. models=("tcn",) ile kosuldugunda p001
    artik tcn/ALL/val demek oluyor, oysa diskteki p001 gru/ALL/val idi ->
    devam etme mantigi YANLIS parcayi eslestirir, sessizce hatali veri uretir.
    Icerik tabanli ad bu sinifi imkansiz kilar.
    """
    return f"{fs}__{model}__{tgt or 'ALL'}__{split}.parquet"


def parca_durumu(base_dir):
    """Hangi parcalar hazir, hangileri eksik? Hicbir sey yuklemez."""
    d = Path(base_dir) / "_trajektori_parca"
    yollar = sorted(d.glob("*.parquet")) if d.exists() else []
    print(f"{d}\n  {len(yollar)} parca")
    if not yollar:
        print("  (bos -- kosu hic tamamlanmamis ya da parcalar silinmis)")
        return []
    from collections import Counter
    say = Counter(y.name.split("__")[1] for y in yollar if "__" in y.name)
    for m, n in sorted(say.items()):
        print(f"    {m:<24} {n} parca")
    eski = [y.name for y in yollar if "__" not in y.name]
    if eski:
        print(f"  !! {len(eski)} parca ESKI adlandirmada (p###) -- "
              f"hangi modele ait oldugu isimden anlasilmiyor, icerikten cozulecek")
    return yollar


def parca_adlarini_duzelt(base_dir):
    """Eski p###.parquet parcalarini ICERIGINE gore yeniden adlandirir."""
    d = Path(base_dir) / "_trajektori_parca"
    n = 0
    for y in sorted(d.glob("p*.parquet")):
        if "__" in y.name:
            continue
        t = pd.read_parquet(y, columns=["feature_set", "model", "target", "split"]).head(1)
        if t.empty:
            continue
        r = t.iloc[0]
        hedefler = pd.read_parquet(y, columns=["target"]).target.nunique()
        tgt = "ALL" if hedefler > 1 else str(r.target)
        yeni = d / _parca_adi(str(r.feature_set), str(r.model), tgt, str(r.split))
        y.rename(yeni); n += 1
        print(f"  {y.name} -> {yeni.name}")
    print(f"{n} parca yeniden adlandirildi")
    return n


def birlestir(base_dir, cikti: str = "trajektori_ozeti.parquet", parca_dizin=None):
    """Diskteki parcalari MODEL YUKLEMEDEN birlestirir.

    Kosu coktugunde tamamlanmis adimlar '_trajektori_parca' icinde durur.
    Bu fonksiyon onlari birlestirip kullanilabilir bir dosya uretir --
    eksik modeller olsa bile. Backtest zaten her hedef-ufuk icin EN IYI
    modeli seciyor; eksik model hic secilmiyorsa sonuc degismez.
    """
    base_dir = Path(base_dir)
    parca_dizin = Path(parca_dizin) if parca_dizin else base_dir / "_trajektori_parca"
    yollar = sorted(parca_dizin.glob("*.parquet"))
    if not yollar:
        raise FileNotFoundError(f"{parca_dizin} icinde parca yok.")
    print(f"{len(yollar)} parca birlestiriliyor...")
    d = pd.concat([pd.read_parquet(y) for y in yollar], ignore_index=True)
    for c in ("feature_set", "model", "split", "horizon", "target", "greenhouse_id"):
        if c in d.columns and str(d[c].dtype) == "category":
            d[c] = d[c].astype(str)
    yol = base_dir / cikti
    d.to_parquet(yol, index=False)
    print(f"  {len(d):,} satir · {d.model.nunique()} model · {d.target.nunique()} hedef")
    print(f"  modeller: {sorted(d.model.unique())}")
    if "Time" in d.columns:
        print(f"  ZAMAN KOLONU VAR · {d.Time.nunique()} tekil capa")
        print(d.groupby("split", observed=True).Time.agg(["min", "max", "nunique"]).to_string())
    eksik = {(t, h) for t in d.target.unique() for h in d.horizon.unique()} - \
            set(map(tuple, d[["target", "horizon"]].drop_duplicates().to_numpy()))
    if eksik:
        print(f"  !! eksik hedef-ufuk: {sorted(eksik)}")
    print(f"\nKaydedildi: {yol}")
    return d


def _not_defteri_mi() -> bool:
    import sys
    return ("ipykernel" in sys.modules) or ("google.colab" in sys.modules)


if __name__ == "__main__" and not _not_defteri_mi():
    BASE_DIR = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")
    run(BASE_DIR)
