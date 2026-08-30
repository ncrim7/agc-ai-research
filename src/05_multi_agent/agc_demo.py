"""
AGC — DEMO URETICI
===================
Karar destek katmanini TEK BIR HTML DOSYASINA dokur. Sunucu yok, internet yok,
Colab yok: hoca dosyayi cift tiklayip acar.

DORT EKRAN
-----------
  1 UYARI        anlati + karar tablosu + esik cetveli + celiskiler + susan kurallar
  2 NEDEN        soru-cevap (onceden uretilir; statik dosyada canli LLM olamaz)
  3 YAPILANDIRMA merdiven tablosu + varsayilanin gerekcesi + sekiz kombinasyon
  4 OLCUM        ajan katmani olculeri + kural bazinda isabet + sinirlar

IKI GIRDI MODU — TASARIMIN OMURGASI
------------------------------------
  oracle : gerceklesmis gelecek "tahmin" gibi verilir
           -> "tahmin mukemmel olsaydi karar katmani ne derdi?"  (kurallarin kalitesi)
  model  : trajektori_ozeti.parquet'ten GERCEK model tahminleri
           -> "sistem gercekte ne diyor?"  (uctan uca performans)

Aradaki FARK hatanin kaynagini ayristirir: ayni anda oracle uyari verip model
vermiyorsa kusur TAHMINDEDIR; ikisi de veriyorsa kural islemistir. Demo ikisini
yan yana gosterir -- hangisinin gosterildigi her zaman ekranda yazar.

Model modu, backtest ile AYNI model secimini kullanir (hedef-ufuk basina en dar
terminal arali kli model, dogrulama setinden). Boylece demodaki tahminler
raporlanan metriklerle ayni modellerden gelir.

KULLANIM
--------
    exec(open(BASE_DIR / "agc_demo.py").read(), globals())
    demo_uret(BASE_DIR, ajan=ajan)          # ajan=None -> sablon anlati
"""

from __future__ import annotations

SURUM = "2026-08-24.3"   # en zengin an once + catisma isabet gosterimi

import html
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

_tazele("agc_risk_motoru", "agc_dogrulayici", "agc_karar_kaydi") if "_tazele" in dir() else None

from agc_karar_kaydi import (YAPILANDIRMALAR, karar_kaydi, ozet_metni,
                             AILELER, AILE_OLCUM, aile_of)

HEDEFLER = ["EC_slab1", "EC_slab2", "WC_slab1", "WC_slab2", "t_slab1", "t_slab2",
            "Tair", "Rhair", "HumDef", "CO2air"]
ADIM = {"3h": 36, "6h": 72}

SORULAR = [
    "Bu uyarinin esigi nereden geliyor?",
    "Bu kural ne kadar guvenilir?",
    "Uymazsam ne olur?",
    "Ne kadar degistirmeliyim?",
    "Kis performansi nasil?",
    "Neden baska hedefler hakkinda bir sey soylemiyorsun?",
]


# ---------------------------------------------------------------------------
# GIRDI URETIMI
# ---------------------------------------------------------------------------
def oracle_girdi(d: pd.DataFrame, i: int, sera: str) -> pd.DataFrame:
    """Gerceklesmis pencereyi 'tahmin' gibi verir. UST SINIR: tahmin mukemmel."""
    r = []
    for h in HEDEFLER:
        for uf, k in ADIM.items():
            w = d[h].iloc[i:i + k]
            r.append({"zaman": d.Time.iloc[i], "sera": sera, "hedef": h, "ufuk": uf,
                      "tahmin": float(w.iloc[-1]),
                      "tahmin_min": float(w.min()), "tahmin_max": float(w.max())})
    return pd.DataFrame(r)


def en_iyi_model(tj: pd.DataFrame) -> dict:
    """Hedef-ufuk basina en dar terminal aralikli model -- BACKTEST ILE AYNI OLCUT.

    Demodaki tahminler raporlanan metriklerle ayni modellerden gelmeli; aksi
    halde ekrandaki sayi ile rapordaki sayi farkli sistemleri anlatir.
    """
    v = tj[tj.split == "val"].assign(err=lambda x: x.pred_son - x.true_son)
    g = (v.groupby(["horizon", "target", "model"], observed=True).err
          .apply(lambda s: np.percentile(s, 97.5) - np.percentile(s, 2.5))
          .reset_index(name="w"))
    en = g.sort_values("w").groupby(["horizon", "target"], observed=True).head(1)
    return {(r.target, r.horizon): r.model for r in en.itertuples()}


def model_girdi(tj: pd.DataFrame, sec: dict, zaman, sera: str) -> pd.DataFrame | None:
    """trajektori_ozeti.parquet'ten GERCEK model tahminleri."""
    a = tj[(tj.Time == pd.Timestamp(zaman)) & (tj.greenhouse_id == sera)]
    if a.empty:
        return None
    r = []
    for h in HEDEFLER:
        for uf in ADIM:
            m = sec.get((h, uf))
            s = a[(a.target == h) & (a.horizon == uf) & (a.model == m)]
            if s.empty:
                continue
            s = s.iloc[0]
            r.append({"zaman": pd.Timestamp(zaman), "sera": sera, "hedef": h, "ufuk": uf,
                      "tahmin": float(s.pred_son),
                      "tahmin_min": float(s.pred_min), "tahmin_max": float(s.pred_max)})
    return pd.DataFrame(r) if r else None


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------
def _e(x) -> str:
    return html.escape(str(x), quote=True)


def _metin(x) -> str:
    """LLM metnini HTML'e cevirir: ONCE kacis, SONRA kucuk bicimlendirme.

    Model istenmese de markdown uretiyor (olculdu: 112 kalin, 27 madde,
    84 satir sonu). Ham birakilirsa ekranda ** ve - isaretleri gorunur.
    Sira onemli: once html.escape, sonra bicimlendirme -- tersi olursa
    uretilen etiketler de kacirilir ve gorunur hale gelir.
    """
    t = html.escape(str(x), quote=True)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)      # **kalin**
    satirlar, out, liste = t.split("\n"), [], False
    for l in satirlar:
        m = re.match(r"\s*[-*\u2022]\s+(.*)", l)
        if m:
            if not liste:
                out.append("<ul>"); liste = True
            out.append(f"<li>{m.group(1)}</li>")
        else:
            if liste:
                out.append("</ul>"); liste = False
            if l.strip():
                out.append(f"<p>{l}</p>")
    if liste:
        out.append("</ul>")
    return "".join(out) or t


CSS = """
:root{
  /* Palet malzemeden: tas yunu, sera cami, besin cozeltisi.
     Uyari rengi KIRMIZI degil -- bitkide stres sararma olarak gorunur (kloroz). */
  --kagit:#E7EBE8; --yuzey:#FBFCFB; --murekkep:#16211D; --soluk:#68766F;
  --cizgi:#CBD3CE; --olculmus:#2C6B59; --okra:#A8721A; --tugla:#8A3A2B;
  --kok:#2C6B59; --iklim:#3D6382;
  --mono:ui-monospace,"SF Mono","Cascadia Mono","Roboto Mono",Menlo,Consolas,monospace;
  --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;
}
*{box-sizing:border-box}
body{margin:0;background:var(--kagit);color:var(--murekkep);
  font-family:var(--serif);font-size:16px;line-height:1.55;
  -webkit-font-smoothing:antialiased}
.sar{max-width:1080px;margin:0 auto;padding:0 24px 72px}

/* --- baslik + yapilandirma damgasi ------------------------------------- */
header{border-bottom:1px solid var(--cizgi);padding:28px 0 18px;margin-bottom:0}
h1{font-size:23px;font-weight:600;letter-spacing:-.01em;margin:0 0 3px}
.altbaslik{font-family:var(--mono);font-size:11.5px;color:var(--soluk);
  letter-spacing:.06em;text-transform:uppercase}
.damga{margin-top:14px;font-family:var(--mono);font-size:11.5px;color:var(--soluk);
  display:flex;flex-wrap:wrap;gap:0 18px;line-height:1.9}
.damga b{color:var(--murekkep);font-weight:600}

/* --- sekmeler ---------------------------------------------------------- */
nav{display:flex;gap:2px;border-bottom:1px solid var(--cizgi);margin-bottom:26px;
  overflow-x:auto}
nav button{font-family:var(--mono);font-size:12px;letter-spacing:.04em;
  background:none;border:0;border-bottom:2px solid transparent;color:var(--soluk);
  padding:13px 15px;cursor:pointer;white-space:nowrap}
nav button[aria-selected="true"]{color:var(--murekkep);border-bottom-color:var(--olculmus)}
nav button:focus-visible{outline:2px solid var(--olculmus);outline-offset:-2px}
section[hidden]{display:none}

/* --- denetimler -------------------------------------------------------- */
.denetim{display:flex;flex-wrap:wrap;gap:20px;align-items:flex-end;margin-bottom:22px}
.alan{display:flex;flex-direction:column;gap:5px}
.alan label{font-family:var(--mono);font-size:10.5px;letter-spacing:.07em;
  text-transform:uppercase;color:var(--soluk)}
select{font-family:var(--mono);font-size:13px;padding:7px 9px;background:var(--yuzey);
  border:1px solid var(--cizgi);color:var(--murekkep);border-radius:2px}
.ikili{display:flex;border:1px solid var(--cizgi);border-radius:2px;overflow:hidden}
.ikili button{font-family:var(--mono);font-size:12px;padding:7px 13px;background:var(--yuzey);
  border:0;color:var(--soluk);cursor:pointer}
.ikili button[aria-pressed="true"]{background:var(--murekkep);color:var(--yuzey)}

/* --- anlati ------------------------------------------------------------ */
.anlati p,.cevap p{margin:0 0 9px} .anlati p:last-child,.cevap p:last-child{margin-bottom:0}
.anlati ul,.cevap ul{margin:9px 0;padding-left:20px} .anlati li,.cevap li{margin:3px 0}
.anlati strong,.cevap strong{font-weight:600}
.anlati{background:var(--yuzey);border:1px solid var(--cizgi);border-left:3px solid var(--olculmus);
  padding:20px 22px;font-size:16.5px;line-height:1.62;margin-bottom:8px}
.anlati.bos{border-left-color:var(--soluk);color:var(--soluk)}
.rozet{font-family:var(--mono);font-size:10.5px;color:var(--soluk);
  letter-spacing:.05em;margin-bottom:24px}
.rozet span{margin-right:14px}

/* --- IMZA OGE: esik cetveli -------------------------------------------- */
.uyari{background:var(--yuzey);border:1px solid var(--cizgi);padding:14px 16px;margin-bottom:8px}
.uyari.kritik{border-left:3px solid var(--tugla)}
.uyari.orta{border-left:3px solid var(--okra)}
.ust{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:11px}
.ad{font-family:var(--mono);font-size:14px;font-weight:600}
.etiket{font-family:var(--mono);font-size:10px;letter-spacing:.07em;text-transform:uppercase;
  padding:2px 7px;border:1px solid var(--cizgi);color:var(--soluk);border-radius:2px}
.etiket.KOK{border-color:var(--kok);color:var(--kok)}
.etiket.IKLIM{border-color:var(--iklim);color:var(--iklim)}
.isabet{margin-left:auto;font-family:var(--mono);font-size:12px;color:var(--soluk)}
.isabet b{color:var(--olculmus);font-size:14px}

.cetvel{position:relative;height:26px;margin:4px 0 11px}
.cetvel .yol{position:absolute;top:12px;left:0;right:0;height:1px;background:var(--cizgi)}
.cetvel .esik{position:absolute;top:4px;width:1px;height:17px;background:var(--murekkep)}
.cetvel .esik::after{content:attr(data-e);position:absolute;top:-13px;left:50%;
  transform:translateX(-50%);font-family:var(--mono);font-size:9.5px;color:var(--soluk);
  white-space:nowrap}
.cetvel .nokta{position:absolute;top:8px;width:9px;height:9px;border-radius:50%;
  margin-left:-4.5px;border:2px solid var(--yuzey)}
.cetvel .nokta.ust{background:var(--tugla)} .cetvel .nokta.alt{background:var(--okra)}
.cetvel .nokta::after{content:attr(data-t);position:absolute;top:12px;left:50%;
  transform:translateX(-50%);font-family:var(--mono);font-size:10px;
  color:var(--murekkep);white-space:nowrap}
.satirlar{font-size:14.5px;line-height:1.5}
.satirlar div{margin-top:3px}
.k{font-family:var(--mono);font-size:10px;letter-spacing:.07em;text-transform:uppercase;
  color:var(--soluk);margin-right:7px}

/* --- celiski ----------------------------------------------------------- */
.celiski{background:#FAF3E4;border:1px solid #E2D0A8;border-left:3px solid var(--okra);
  padding:14px 16px;margin-bottom:8px}
.celiski h4{margin:0 0 7px;font-family:var(--mono);font-size:11.5px;letter-spacing:.06em;
  text-transform:uppercase;color:var(--okra)}
.celiski .yon{font-family:var(--mono);font-size:13px;margin:3px 0}
.celiski .karar{margin-top:8px;font-size:14.5px}

/* --- tablo ------------------------------------------------------------- */
table{width:100%;border-collapse:collapse;font-family:var(--mono);font-size:12.5px;
  background:var(--yuzey);margin-bottom:10px}
th,td{padding:8px 11px;text-align:left;border-bottom:1px solid var(--cizgi)}
th{font-size:10px;letter-spacing:.07em;text-transform:uppercase;color:var(--soluk);
  font-weight:600;background:#F3F5F3}
td.n{text-align:right;font-variant-numeric:tabular-nums}
tr.vurgu td{background:#EEF4F1;font-weight:600}

h2{font-size:15px;font-weight:600;margin:34px 0 12px;letter-spacing:-.005em}
h2:first-child{margin-top:0}
.not{font-size:14.5px;color:var(--soluk);margin:9px 0 20px;max-width:66ch}
.sinir{font-family:var(--mono);font-size:12px;color:var(--soluk);
  border-left:2px solid var(--cizgi);padding:5px 0 5px 13px;margin:5px 0}

/* --- soru-cevap -------------------------------------------------------- */
details{background:var(--yuzey);border:1px solid var(--cizgi);margin-bottom:6px}
summary{padding:13px 16px;cursor:pointer;font-size:15px;font-weight:600;list-style:none}
summary::-webkit-details-marker{display:none}
summary::before{content:"→";color:var(--olculmus);margin-right:11px;
  display:inline-block;transition:transform .15s}
details[open] summary::before{transform:rotate(90deg)}
summary:focus-visible{outline:2px solid var(--olculmus);outline-offset:-2px}
.cevap{padding:0 16px 15px 40px;font-size:15.5px;line-height:1.6}
.cevap .rozet{margin:11px 0 0}

.mini{font-family:var(--mono);font-size:11px;color:var(--soluk)}
@media (max-width:640px){.sar{padding:0 15px 48px} .isabet{margin-left:0;width:100%}}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
"""

JS = """
const D = window.DEMO;
function sekme(ad){
  document.querySelectorAll('nav button').forEach(b=>
    b.setAttribute('aria-selected', String(b.dataset.s===ad)));
  document.querySelectorAll('main section').forEach(s=> s.hidden = s.id!==ad);
}
let anIx = 0, mod = 'oracle';
function ciz(){
  const an = D.anlar[anIx], v = an[mod];
  const kutu = document.getElementById('uyari-govde');
  if(!v){ kutu.innerHTML = '<div class="anlati bos">Bu an icin '+mod+
    ' modunda kayit yok.</div>'; return; }
  let h = '';
  h += '<div class="anlati'+(v.uyarilar.length?'':' bos')+'">'+v.anlati+'</div>';
  h += '<div class="rozet"><span>kaynak: '+v.kaynak+'</span><span>model: '+v.model+
       '</span><span>sayi denetimi: '+v.denetim+'</span><span>deneme: '+v.deneme+'</span></div>';
  for(const c of v.catismalar){
    h += '<div class="celiski"><h4>zit aksiyon · '+c.aktuator+'</h4>'+
         '<div class="yon">artir → '+c.artir+'</div>'+
         '<div class="yon">azalt → '+c.azalt+'</div>'+
         '<div class="karar">'+c.karar+'</div></div>';
  }
  for(const u of v.uyarilar){
    h += '<div class="uyari '+u.seviye.toLowerCase()+'">'+
      '<div class="ust"><span class="ad">'+u.ad+'</span>'+
      '<span class="etiket '+u.aile+'">'+u.aile+'</span>'+
      '<span class="etiket">'+u.seviye+'</span>'+
      '<span class="etiket">'+u.kriter+'</span>'+
      (u.isabet!=null?'<span class="isabet">olculmus isabet <b>%'+u.isabet+
        '</b> · alt sinir %'+u.alt+' · '+u.olay+' olay</span>':'')+'</div>'+
      '<div class="cetvel"><div class="yol"></div>'+
      '<div class="esik" style="left:'+u.px_esik+'%" data-e="esik '+u.esik+'"></div>'+
      '<div class="nokta '+u.yon+'" style="left:'+u.px_tahmin+'%" data-t="tahmin '+
        u.tahmin+'"></div></div>'+
      '<div class="satirlar"><div><span class="k">yap</span>'+u.aksiyon+'</div>'+
      '<div><span class="k">dikkat</span>'+u.kisit+'</div>'+
      (u.referans?'<div><span class="k">baska takim</span>'+u.referans+'</div>':'')+
      '</div></div>';
  }
  if(v.susan.length)
    h += '<h2>Bilincli susan kurallar</h2><div class="not">'+v.susan.join(' · ')+'</div>';
  kutu.innerHTML = h;
  document.getElementById('an-ozet').textContent = v.ozet;
}
document.addEventListener('DOMContentLoaded',()=>{
  document.querySelectorAll('nav button').forEach(b=>
    b.onclick=()=>sekme(b.dataset.s));
  const sec=document.getElementById('an-sec');
  sec.onchange=()=>{anIx=+sec.value; ciz();};
  document.querySelectorAll('.ikili button').forEach(b=>
    b.onclick=()=>{mod=b.dataset.m;
      document.querySelectorAll('.ikili button').forEach(x=>
        x.setAttribute('aria-pressed',String(x.dataset.m===mod)));
      ciz();});
  ciz();
});
"""


def _cetvel_konum(esik: float, tahmin: float, olcek: float) -> tuple:
    """Esik %50'de sabit; tahmin sapmasi ORTAK olcege gore yerlestirilir.

    Ortak olcek = o andaki en buyuk sapma. Boylece ayni ekrandaki uyarilarin
    sapma buyuklukleri BIRBIRIYLE karsilastirilabilir olur. Mutlak bir eksen
    iddia edilmez -- sayilar zaten yazili.
    """
    if not olcek:
        return 50.0, 50.0
    d = (tahmin - esik) / olcek
    return 50.0, float(np.clip(50 + d * 38, 3, 97))


def _uyari_gorunum(kayit: dict) -> list:
    """Cetvel, terminal tahmini DEGIL, KARARI VEREN degeri gosterir.

    'dokunma' kriterinde yuksek yonlu bir uyari pencere MAKSIMUMUNA bakar;
    terminal tahmin esigin altinda kalabilir. Terminal degeri gostermek
    "esik 958 · tahmin 880 · esigi asiyor" gibi anlamsiz satirlar uretiyordu.
    """
    u = kayit["uyarilar"]

    def kd(x):
        return x.get("karar_degeri") if x.get("karar_degeri") is not None else x["tahmin"]

    olcek = max((abs(kd(x) - x["esik"]) for x in u
                 if x["esik"] is not None and kd(x) is not None), default=0.0)
    out = []
    for x in u:
        pe, pt = _cetvel_konum(x["esik"] or 0, kd(x) or 0, olcek)
        yukari = (x.get("karar_yonu") == "yuksek")
        out.append({
            "ad": f"{x['hedef']} · {x['ufuk']}", "aile": x.get("aile", "-"),
            "seviye": x["seviye"], "kriter": x.get("kriter", "-"),
            "esik": x["esik"], "tahmin": kd(x), "terminal": x["tahmin"],
            "karar_yonu": x.get("karar_yonu", ""),
            "px_esik": pe, "px_tahmin": pt, "yon": "ust" if yukari else "alt",
            "isabet": None if x["olculmus_isabet"] is None
                      else round(x["olculmus_isabet"] * 100),
            "alt": None if x["olculmus_isabet_alt_sinir"] is None
                   else round(x["olculmus_isabet_alt_sinir"] * 100),
            "olay": x.get("olcum_olay_sayisi"),
            "aksiyon": _e(x["aksiyon"]), "kisit": _e(x["kisit"]),
            "referans": _e(x["referans"]) if x["referans"] else "",
        })
    return out


def _catisma_gorunum(kayit: dict) -> list:
    out = []
    for c in kayit.get("catismalar", []):
        out.append({
            "aktuator": c["aktuator"],
            "artir": ", ".join(
                f"{x['hedef']} {x['ufuk']}"
                + (f" (%{round(x['isabet']*100)})" if x.get("isabet") else "")
                for x in c["artir_yonu"]),
            "azalt": ", ".join(
                f"{x['hedef']} {x['ufuk']}"
                + (f" (%{round(x['isabet']*100)})" if x.get("isabet") else "")
                for x in c["azalt_yonu"]),
            "karar": (f"Oncelikli: <b>{c['oncelikli']['hedef']} {c['oncelikli']['ufuk']}</b> — "
                      f"{_e(c['gerekce'])}") if c["cozuldu"]
                     else f"<b>Sistem oncelik veremiyor.</b> {_e(c['gerekce'])}",
        })
    return out


# ---------------------------------------------------------------------------
def _tablo(df: pd.DataFrame, sayisal=(), vurgu=None) -> str:
    b = ["<table><thead><tr>"] + [f"<th>{_e(c)}</th>" for c in df.columns] + ["</tr></thead><tbody>"]
    for _, r in df.iterrows():
        cls = ' class="vurgu"' if vurgu and vurgu(r) else ""
        b.append(f"<tr{cls}>")
        for c in df.columns:
            k = ' class="n"' if c in sayisal else ""
            v = r[c]
            b.append(f"<td{k}>{'' if pd.isna(v) else _e(v)}</td>")
        b.append("</tr>")
    return "".join(b + ["</tbody></table>"])


GEREKLI = {
    "operational_v2_combined.csv": ("Time", "greenhouse_id"),
    "decision_knowledge_base_v5.csv": ("hedef", "ufuk", "sera", "mevsim", "esik"),
    "dkb_zarf.csv": ("hedef", "sera", "donem"),
}
ISTEGE_BAGLI = {
    "kural_guvenilirlik.csv": ("hedef", "ufuk", "aile", "kriter", "precision"),
    "backtest_v3_merdiven.csv": ("adim", "precision", "recall"),
    "trajektori_ozeti.parquet": ("Time", "greenhouse_id", "target", "horizon", "model"),
}


def on_kontrol(base_dir) -> dict:
    """Dosya ve KOLON denetimi -- LLM cagrilarindan ONCE.

    GERCEK VAKA: demo 84 LLM cagrisini yaptiktan SONRA, ekran 4'te
    kural_guvenilirlik.csv'de 'aile' kolonu olmadigi icin coktu. Para
    harcandi, is kayboldu. Girdi denetimi en basta olmali.

    Zorunlu dosyada eksik varsa DURDURUR. Istege bagli dosyada eksik varsa
    o ekran/mod devre disi kalir ve sebebi ekranda yazar.
    """
    base_dir = Path(base_dir)
    hata, uyari = [], []
    for ad, kol in GEREKLI.items():
        y = base_dir / ad
        if not y.exists():
            hata.append(f"{ad} YOK"); continue
        var = list(pd.read_csv(y, nrows=0).columns)
        eks = [c for c in kol if c not in var]
        if eks:
            hata.append(f"{ad}: eksik kolon {eks} (var olanlar: {var[:8]})")
    for ad, kol in ISTEGE_BAGLI.items():
        y = base_dir / ad
        if not y.exists():
            uyari.append(f"{ad} yok"); continue
        var = list((pd.read_parquet(y).head(0) if y.suffix == ".parquet"
                    else pd.read_csv(y, nrows=0)).columns)
        eks = [c for c in kol if c not in var]
        if eks:
            uyari.append(f"{ad}: eksik kolon {eks} -> ilgili bolum devre disi")
    if hata:
        raise RuntimeError("ON KONTROL BASARISIZ (LLM cagrisi YAPILMADI):\n  - "
                           + "\n  - ".join(hata))
    for u in uyari:
        print(f"  [on kontrol] {u}")
    return {"uyari": uyari}


def demo_uret(base_dir, anlar=None, yapilandirma=None, ajan=None,
              cikti: str = "agc_demo.html", sorular=None) -> Path:
    """Dort ekranli tek-dosya demo uretir.

    anlar : [(sera, "2020-05-22 16:00"), ...] · None -> otomatik secim
    ajan  : AciklayiciAjan · None -> sablon anlati (LLM'siz de calisir)
    """
    base_dir = Path(base_dir)
    kontrol = on_kontrol(base_dir)          # LLM cagrisindan ONCE
    y = yapilandirma or YAPILANDIRMALAR["demo"]
    sorular = sorular or SORULAR

    ham = pd.read_csv(base_dir / "operational_v2_combined.csv", parse_dates=["Time"])
    ham["Time"] = ham.Time.dt.round("5min")
    seralar = sorted(ham.greenhouse_id.unique())

    # --- model modu icin trajektori ---------------------------------------
    tj, sec, model_notu = None, {}, ""
    ty = base_dir / "trajektori_ozeti.parquet"
    if ty.exists():
        tj = pd.read_parquet(ty)
        if "Time" in tj.columns:
            tj["Time"] = pd.to_datetime(tj.Time)
            sec = en_iyi_model(tj)
            model_notu = (f"{tj.model.nunique()} model · hedef-ufuk basina en dar "
                          f"terminal aralikli olan secildi (backtest ile ayni olcut)")
        else:
            tj = None
            model_notu = "trajektori dosyasinda Time kolonu yok -> model modu kapali"
    else:
        model_notu = "trajektori_ozeti.parquet yok -> model modu kapali"

    if anlar is None:
        # Otomatik secim ZENGIN anlari tercih eder. Puanlama sirasi:
        #   +200 trajektori dosyasinda VAR (yoksa model modu gosterilemez)
        #   +100 iki aile birden temsil ediliyor
        #   + 50 her zit aksiyon catismasi
        #   +  n uyari sayisi
        # Ilk uyariyi alan naif secim gece yarisi tek-iklim anlari getiriyordu;
        # ayrica AICU icin trajektoride olmayan bir an secildi ve o serada
        # model modu hic gosterilemedi.
        tj_anlar = (set(zip(tj.Time.astype(str), tj.greenhouse_id))
                    if tj is not None else set())
        anlar = []
        for s in seralar:
            d = ham[ham.greenhouse_id == s].sort_values("Time").reset_index(drop=True)
            adaylar = []
            for i in [int(x) for x in d.index[(d.Time >= "2020-05-06") &
                                              (d.Time <= "2020-05-26")][::288]][:20]:
                k = karar_kaydi(base_dir, oracle_girdi(d, i, s), y)
                n = k["ozet"]["uyari"]
                if not n:
                    continue
                z = str(d.Time.iloc[i])
                aileler = {a for a, o in k["aile_ozet"].items() if o["uyari"]}
                puan = (((z, s) in tj_anlar) * 200 + (len(aileler) >= 2) * 100
                        + k["ozet"]["catisma"] * 50 + n)
                adaylar.append((puan, z))
            if adaylar:
                anlar.append((max(adaylar)[0], s, max(adaylar)[1]))
        # EN ZENGIN AN ONCE. Anlar sera adina gore siralandiginda demo en zayif
        # ornekle aciliyordu (AICU: 2 uyari, ayni hedefin iki ufku, ayni aksiyon,
        # cetvelde iki ozdes cubuk). Demo en guclu orneginle acilmali.
        anlar = [(s, z) for _, s, z in sorted(anlar, reverse=True)]
    print(f"{len(anlar)} an · yapilandirma '{y.ad}' · {model_notu}")

    veri = {"anlar": []}
    for sera, zaman in anlar:
        d = ham[ham.greenhouse_id == sera].sort_values("Time").reset_index(drop=True)
        ix = d.index[d.Time == pd.Timestamp(zaman)]
        if not len(ix):
            print(f"  ATLANDI {sera} {zaman}: zaman ekseninde yok")
            continue
        girdiler = {"oracle": oracle_girdi(d, int(ix[0]), sera)}
        if tj is not None:
            g = model_girdi(tj, sec, zaman, sera)
            if g is not None:
                girdiler["model"] = g

        an = {"etiket": f"{sera} · {zaman[:16]}"}
        for mod, g in girdiler.items():
            k = karar_kaydi(base_dir, g, y)
            if ajan is not None:
                c = ajan.anlat(k)
                metin, kaynak, model, deneme = c.metin, c.kaynak, c.model, c.deneme
                denetim = f"{c.denetim.dogrulanan}/{c.denetim.toplam_sayi}"
                sorucevap = []
                for s in sorular:
                    cc = ajan.sor(k, s)
                    sorucevap.append({"s": s, "c": _metin(cc.metin),
                                      "d": f"{cc.denetim.dogrulanan}/{cc.denetim.toplam_sayi}",
                                      "m": cc.model or "-", "kaynak": cc.kaynak})
            else:
                from agc_aciklayici_ajan import sablon_anlati, sablon_cevap
                from agc_dogrulayici import denetle
                metin = sablon_anlati(k); dn = denetle(metin, k)
                kaynak, model, deneme = "sablon", "-", 1
                denetim = f"{dn.dogrulanan}/{dn.toplam_sayi}"
                sorucevap = [{"s": s, "c": _metin(sablon_cevap(k, s)),
                              "d": "-", "m": "-", "kaynak": "sablon"} for s in sorular]
            ao = {a: o["uyari"] for a, o in k["aile_ozet"].items() if o["uyari"]}
            an[mod] = {
                "anlati": _metin(metin), "kaynak": kaynak, "model": model or "-",
                "denetim": denetim, "deneme": deneme,
                "uyarilar": _uyari_gorunum(k), "catismalar": _catisma_gorunum(k),
                "susan": [f"{x['hedef']} {x['ufuk']}" for x in k["susan_kurallar"]],
                "sorucevap": sorucevap,
                "ozet": (f"{k['ozet']['uyari']} uyari · " +
                         " · ".join(f"{a} {n}" for a, n in ao.items()) +
                         (f" · {k['ozet']['catisma']} zit aksiyon"
                          if k["ozet"]["catisma"] else "")) or "uyari yok",
            }
        veri["anlar"].append(an)
        print(f"  {an['etiket']:<34} {' + '.join(girdiler)}")

    # --- ekran 3: merdiven --------------------------------------------------
    my = base_dir / "backtest_v3_merdiven.csv"
    if my.exists():
        mdf = pd.read_csv(my)
        merdiven = _tablo(mdf, sayisal=tuple(c for c in
                          ("TP", "FP", "FN", "precision", "recall", "F1",
                           "temel_olay", "kural") if c in mdf.columns),
                          vurgu=lambda r: str(r.get("adim", "")).startswith("3"))
    else:
        merdiven = '<p class="not">backtest_v3_merdiven.csv bulunamadi.</p>' 

    # --- ekran 4: kural guvenilirligi --------------------------------------
    gy = base_dir / "kural_guvenilirlik.csv"
    if gy.exists():
        g = pd.read_csv(gy)
        # Var olan kolonlara gore sirala; eksik kolonda COKME.
        sirala = [c for c in ("aile", "precision") if c in g.columns]
        if sirala:
            g = g.sort_values(sirala, ascending=[c != "precision" for c in sirala])
        guv = _tablo(g, sayisal=tuple(c for c in
                     ("olay", "TP", "FP", "FN", "precision", "prec_alt_sinir", "recall")
                     if c in g.columns))
        if "aile" not in g.columns:
            guv += ('<p class="not">Bu tablo ESKI surumdur (aile/kriter kolonu yok). '
                    'Guncel kural_guvenilirlik.csv ile yeniden uretin.</p>')
    else:
        guv = '<p class="not">kural_guvenilirlik.csv bulunamadi.</p>' 

    aile_tab = _tablo(pd.DataFrame([
        {"aile": a, "kriter": o["kriter"], "kural": o.get("kural"),
         "precision": o["precision"], "recall": o["recall"],
         "isabet medyani": o.get("isabet_medyani")} for a, o in AILE_OLCUM.items()]),
        sayisal=("kural", "precision", "recall", "isabet medyani"))

    ilk = veri["anlar"][0] if veri["anlar"] else {}
    sec_html = "".join(f'<option value="{i}">{_e(a["etiket"])}</option>'
                       for i, a in enumerate(veri["anlar"]))
    sc = (ilk.get("oracle") or {}).get("sorucevap", [])
    sc_html = "".join(
        f'<details><summary>{_e(q["s"])}</summary><div class="cevap">{q["c"]}'
        f'<div class="rozet"><span>sayi denetimi: {q["d"]}</span>'
        f'<span>model: {_e(q["m"])}</span><span>kaynak: {_e(q["kaynak"])}</span></div>'
        f'</div></details>' for q in sc)

    kr = y.kriter
    kr_txt = ("hedef bazli — " + ", ".join(
        f"{a.lower()}: {AILE_OLCUM[a]['kriter']}" for a in AILELER)) if isinstance(kr, dict) else kr

    HTML = f"""<!DOCTYPE html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AGC · Karar Destek Katmani</title><style>{CSS}</style></head><body>
<div class="sar">
<header>
  <h1>Sera karar destek katmani</h1>
  <div class="altbaslik">Autonomous Greenhouse Challenge · 2. surum verisi · Mayis 2020 test penceresi</div>
  <div class="damga">
    <span>yapilandirma <b>{_e(y.ad)}</b></span>
    <span>kural tabani <b>{_e(y.dkb_dosya)}</b></span>
    <span>esik donemi <b>{_e(y.mevsim_modu)}</b></span>
    <span>kriter <b>{_e(kr_txt)}</b></span>
    <span>{_e(model_notu)}</span>
  </div>
</header>
<nav role="tablist">
  <button data-s="uyari" aria-selected="true">1 · UYARI</button>
  <button data-s="neden" aria-selected="false">2 · NEDEN</button>
  <button data-s="yapilandirma" aria-selected="false">3 · YAPILANDIRMA</button>
  <button data-s="olcum" aria-selected="false">4 · OLCUM</button>
</nav>
<main>

<section id="uyari">
  <div class="denetim">
    <div class="alan"><label for="an-sec">an</label>
      <select id="an-sec">{sec_html}</select></div>
    <div class="alan"><label>girdi</label>
      <div class="ikili">
        <button data-m="oracle" aria-pressed="true">oracle</button>
        <button data-m="model" aria-pressed="false">model</button>
      </div></div>
    <div class="alan"><label>ozet</label>
      <div class="mini" id="an-ozet" style="padding-bottom:8px"></div></div>
  </div>
  <div class="not"><b>oracle</b> gerceklesmis gelecegi tahmin gibi verir — tahmin mukemmel
  olsaydi karar katmani ne derdi. <b>model</b> gercek tahminleri kullanir. Ikisi ayni anda
  farkli seyler soyluyorsa kusur tahmindedir, kuralda degil.</div>
  <div class="sinir">Bu ekrandaki anlar <b>oracle zenginligine gore secildi</b> (iki aile +
  celiski onceligi). Dolayisiyla burada gorunen oracle/model farki yansiz bir performans
  olcumu <b>degildir</b>; ornekler bilerek yogun anlardan alinmistir. Yansiz sayilar
  <b>Olcum</b> ekranindadir ve tum test penceresi uzerinden hesaplanmistir.</div>
  <div id="uyari-govde"></div>
</section>

<section id="neden" hidden>
  <h2>Sorular yalnizca karar kaydindan cevaplanir</h2>
  <div class="not">Ajan hesap yapmaz, sayi uretmez. Cevap kayitta yoksa "kayitta yok" der —
  bu bir kusur degil, tasarimdir. Asagidaki cevaplar ilk an icin onceden uretildi;
  tek dosyalik demoda canli LLM cagrisi yapilamaz.</div>
  {sc_html or '<p class="not">Soru-cevap uretilmedi.</p>'}
</section>

<section id="yapilandirma" hidden>
  <h2>Dort yapilandirma, dort sonuc</h2>
  <div class="not">Her satir bir oncekinden <b>tek bir degisiklikle</b> ayrilir; boylece farkin
  kaynagi tartismasizdir. Adim 0 yayimlanan yapilandirmadir.</div>
  {merdiven}
  <h2>Varsayilan neden bu</h2>
  <div class="not">{_e(y.gerekce)}</div>
  {aile_tab}
  <div class="not">Bu iki satir <b>birlestirilmez</b>. Farkli olay tanimlarini tek paydada
  toplamak elma ile armudu ortalamaktir.</div>
  <h2>Diger ayarlar kaybolmadi</h2>
  <div class="not">Esik donemi (tum sezon / mevsimsel), kriter (dokunma / surekli sapma) ve
  hedef susturma bagimsiz parametrelerdir; sekiz kombinasyonun hepsi calisir. Secim
  denemeye acik ve her ciktiya damgalanir.</div>
</section>

<section id="olcum" hidden>
  <h2>Kural bazinda olculmus isabet</h2>
  <div class="not">Mayis test penceresi, tutulmus veri. Her uyarinin yaninda gosterilen
  yuzde buradan gelir. <b>Alt sinir</b> Wilson %95 alt siniridir — az olayli kurallarda
  durust kalmak icin.</div>
  {guv}
  <h2>Aciklayici katmanin kendi olcumu</h2>
  <div class="not">30 an, 6 sera. Duzeltme <b>oncesi</b> rakamlar — kabul edilen metnin
  sadakati tanim geregi %100'dur ve model kalitesini olcmez.</div>
  <table><thead><tr><th>olcu</th><th>sonuc</th><th>ne anlama geliyor</th></tr></thead><tbody>
  <tr><td>ilk denemede tam gecen</td><td class="n">%97</td><td>duzeltmesiz kabul edilen anlati orani</td></tr>
  <tr class="vurgu"><td>uyarili anlarda sayisal sadakat</td><td class="n">96/96</td><td>uydurulan sayi YOK</td></tr>
  <tr><td>sablona dusme</td><td class="n">%0</td><td>LLM her seferinde denetimden gecti</td></tr>
  <tr><td>ortalama deneme</td><td class="n">1.03</td><td>duzeltme dongusu nadiren devreye girdi</td></tr>
  <tr><td>pahali modele yukselme</td><td class="n">%0</td><td>ucuz model yetti</td></tr>
  </tbody></table>
  <h2>Bu olcum neyi GOSTERMEZ</h2>
  <div class="sinir">Sayisal sadakat, cumlenin ANLAMININ dogru oldugunu gostermez. Elle
  incelenen 8 vakada 5'i temiz cikti; 3'unde zit aksiyonlar tek yonmus gibi sunulmustu —
  bu bulgu uzerine karar kaydina zit aksiyon tespiti eklendi.</div>
  <div class="sinir">Kis performansi olculmedi. Kronolojik bolme test setini tamamen
  Mayis'a birakiyor; kis ancak yeniden egitimle olculebilir. Ekonomi raporu yarismayi
  KIS maliyetinin belirledigini soyluyor.</div>
  <div class="sinir">Model nedensel degildir. Aksiyonun YONU bilinir, BUYUKLUGU tahmin
  edilemez. Sistem "sulamayi ne kadar artir" sorusuna cevap VERMEZ.</div>
  <div class="sinir">Zarf esikleri seranin kendi normal araligidir, mutlak literatur
  siniri degil. Hasar esikleri taslak durumdadir.</div>
</section>

</main></div>
<script>window.DEMO={json.dumps(veri, ensure_ascii=False)};</script>
<script>{JS}</script>
</body></html>"""

    yol = base_dir / cikti
    yol.write_text(HTML, encoding="utf-8")
    print(f"\nYazildi: {yol}  ({len(HTML)/1024:.0f} KB)")
    return yol
