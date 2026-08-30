"""
AGC 2. Edisyon - VERI DOGRULAMA (model egitiminden ONCE zorunlu)
==================================================================
9 kontrol. Her biri PASS / WARN / FAIL doner.
FAIL varsa sonraki asamaya (baseline, model) GECILMEZ.

En kritik kontrol #1: zaman ekseni surekliligi.
agc_window_generation.py KONUMSAL indeksleme yapiyor (input_start + 288).
Bu, satirlarin kesintisiz 5dk araliklarla dizildigini VARSAYIYOR.
Yaz saati gecisi (29 Mart 2020) veya eksik satir varsa, bazi "24 saatlik"
pencereler sessizce 25 saat kapsar. Bu kontrol o varsayimi test eder.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

EXPECTED_STEP = pd.Timedelta(minutes=5)
CORE_TARGETS = ["Tair", "Rhair", "CO2air", "HumDef", "Tot_PAR"]
GRODAN_TARGETS = ["EC_slab1", "EC_slab2", "WC_slab1", "WC_slab2", "t_slab1", "t_slab2"]

# Kontrol 6 icin: TUM kolonlar icin genis mantik siniri (sadece 11 hedef degil).
# Amac kesin dogruluk degil, "bu deger fiziksel olarak mumkun mu" taramasi.
SANITY_RANGES: dict[str, tuple[float, float]] = {
    "Tair": (0, 50), "Rhair": (0, 100), "CO2air": (0, 3000), "HumDef": (0, 30),
    "Tot_PAR": (0, 3000), "PARout": (0, 3000), "Iglob": (0, 1500),
    "Tout": (-25, 45), "Rhout": (0, 100), "Windsp": (0, 50), "Winddir": (0, 360),
    "Rain": (0, 1), "AbsHumOut": (0, 40),
    "EC_slab1": (0, 15), "EC_slab2": (0, 15),
    "WC_slab1": (0, 100), "WC_slab2": (0, 100),
    "t_slab1": (0, 50), "t_slab2": (0, 50),
    "EC_drain_PC": (0, 20), "pH_drain_PC": (0, 14),
    "VentLee": (0, 100), "Ventwind": (0, 100), "window_pos_lee_vip": (0, 100),
    "EnScr": (0, 100), "BlackScr": (0, 100), "scr_enrg_vip": (0, 100), "scr_blck_vip": (0, 100),
    "PipeLow": (0, 100), "PipeGrow": (0, 100),
    "AssimLight": (0, 100), "assim_vip": (0, 100),
    "co2_dos": (0, 500), "co2_vip": (0, 3000),
    "t_heat_vip": (0, 40), "t_ventlee_vip": (0, 50), "t_ventwind_vip": (0, 50),
    "t_rail_min_vip": (0, 90), "t_grow_min_vip": (0, 90),   # boru sicakligi setpoint'i, 80C normal
    "water_sup": (0, 10000), "Cum_irr": (0, 20000),
    "water_sup_intervals_vip_min": (0, 3000),
    "dx_vip": (0, 30),
    "Tot_PAR_Lamps": (0, 3000),
    # int_* = LED yogunlugu (umol/m2/s), YUZDE DEGIL - 100 ustu tamamen normal
    "int_blue_vip": (0, 1000), "int_red_vip": (0, 1000),
    "int_white_vip": (0, 1000), "int_farred_vip": (0, 1000),
    "Pyrgeo": (-200, 200),   # net uzun dalga radyasyon, negatif OLABILIR
    "RadSum": (0, 10000),    # gunluk kumulatif radyasyon, gece yarisi sifirlanir
}

TRAIN_FRAC, VAL_FRAC = 0.70, 0.15
INPUT_STEPS, OUTPUT_STEPS, STRIDE = 288, 72, 12


def _status(ok: bool, warn: bool = False) -> str:
    if warn:
        return "WARN"
    return "PASS" if ok else "FAIL"


# ----------------------------------------------------------------------
# KONTROL 1: Zaman ekseni surekliligi  (EN KRITIK)
# ----------------------------------------------------------------------
def check_time_continuity(df: pd.DataFrame, team: str, tol: pd.Timedelta = pd.Timedelta(seconds=2)) -> dict:
    """Zaman ekseni surekliligi.

    TOLERANSLI karsilastirma sart: kaynak CSV'deki Excel seri numaralari ~5 ondalik
    basamaga yuvarlanmis (0.00347 gun = 4:59.808), bu yuzden hicbir adim TAM olarak
    5 dakika degil (~192ms sapma). Bu bir veri sorunu DEGIL, format sorunu.
    Asil aradigimiz sey EKSIK SATIR: yaz saati gecisi veya kesinti nedeniyle
    beklenen adimdan belirgin sapan (>2sn) yerler.
    """
    t = df["Time"].sort_values()
    diffs = t.diff().dropna()
    deviation = (diffs - EXPECTED_STEP).abs()

    real_gaps = diffs[deviation > tol]
    max_jitter = deviation[deviation <= tol].max() if (deviation <= tol).any() else pd.Timedelta(0)

    gap_detail = []
    for i in real_gaps.index[:10]:
        prev = t.loc[i - 1] if (i - 1) in t.index else "?"
        gap_detail.append(f"{prev} -> {t.loc[i]} ({diffs.loc[i]})")

    return {
        "team": team,
        "check": "1_zaman_surekliligi",
        "status": _status(len(real_gaps) == 0),
        "gercek_bosluk_sayisi": int(len(real_gaps)),
        "max_jitter_ms": round(max_jitter.total_seconds() * 1000, 1),
        "toplam_adim": int(len(diffs)),
        "gercek_bosluklar": gap_detail if gap_detail else "yok",
    }


# ----------------------------------------------------------------------
# KONTROL 2: Duplike timestamp
# ----------------------------------------------------------------------
def check_duplicate_timestamps(df: pd.DataFrame, team: str) -> dict:
    n_dup = int(df["Time"].duplicated().sum())
    return {
        "team": team,
        "check": "2_duplike_timestamp",
        "status": _status(n_dup == 0),
        "n_duplike": n_dup,
    }


# ----------------------------------------------------------------------
# KONTROL 4: Temizlik sonrasi per-kolon NaN dokumu
# ----------------------------------------------------------------------
def check_nan_breakdown(df: pd.DataFrame, team: str, targets: list[str]) -> dict:
    nan_pct = (df.isna().mean() * 100).sort_values(ascending=False)
    nonzero = nan_pct[nan_pct > 0]
    target_nan = {c: round(float(nan_pct.get(c, 0)), 3) for c in targets if nan_pct.get(c, 0) > 0}
    return {
        "team": team,
        "check": "4_nan_dokumu",
        "status": "WARN" if target_nan else ("PASS" if nonzero.empty else "WARN"),
        "nan_iceren_kolon_sayisi": int(len(nonzero)),
        "en_kotu_5_kolon": {k: round(float(v), 3) for k, v in list(nonzero.items())[:5]},
        "HEDEF_kolonlarda_nan": target_nan if target_nan else "yok",
    }


# ----------------------------------------------------------------------
# KONTROL 5: Sabit / neredeyse sabit kolonlar
# ----------------------------------------------------------------------
def check_constant_columns(df: pd.DataFrame, team: str) -> dict:
    numeric = df.select_dtypes(include=[np.number])
    nunique = numeric.nunique()
    constant = nunique[nunique <= 1].index.tolist()
    near_constant = nunique[(nunique > 1) & (nunique <= 3)].index.tolist()
    return {
        "team": team,
        "check": "5_sabit_kolonlar",
        "status": _status(not constant, warn=bool(constant or near_constant)),
        "sabit": constant,
        "neredeyse_sabit_max3_deger": near_constant,
    }


# ----------------------------------------------------------------------
# KONTROL 6: TUM kolonlarda mantik disi deger taramasi
# ----------------------------------------------------------------------
def check_value_sanity(df: pd.DataFrame, team: str) -> dict:
    violations: dict[str, int] = {}
    unchecked: list[str] = []
    for col in df.select_dtypes(include=[np.number]).columns:
        if col not in SANITY_RANGES:
            unchecked.append(col)
            continue
        lo, hi = SANITY_RANGES[col]
        bad = int(((df[col] < lo) | (df[col] > hi)).sum())
        if bad:
            violations[col] = bad
    return {
        "team": team,
        "check": "6_deger_mantik_taramasi",
        "status": _status(not violations, warn=bool(violations)),
        "ihlaller": violations if violations else "yok",
        "sinir_tanimsiz_kolonlar": unchecked,
    }


# ----------------------------------------------------------------------
# KONTROL 7: En uzun bosluk nerede + hangi split'e dusuyor
# ----------------------------------------------------------------------
def check_gap_location(df: pd.DataFrame, team: str, col: str = "EC_slab1") -> dict:
    if col not in df.columns:
        return {"team": team, "check": "7_bosluk_konumu", "status": "PASS", "not": f"{col} yok"}

    df = df.sort_values("Time").reset_index(drop=True)
    is_na = df[col].isna()
    if not is_na.any():
        return {"team": team, "check": "7_bosluk_konumu", "status": "PASS", "en_uzun_bosluk": 0}

    groups = (is_na != is_na.shift()).cumsum()
    run_len = is_na.groupby(groups).sum()
    worst_group = run_len.idxmax()
    worst_len = int(run_len.max())
    block = df[groups == worst_group]
    start_pos, end_pos = int(block.index[0]), int(block.index[-1])

    n = len(df)
    train_end = int(n * TRAIN_FRAC)
    val_end = train_end + int(n * VAL_FRAC)

    def which_split(pos: int) -> str:
        return "train" if pos < train_end else ("val" if pos < val_end else "test")

    return {
        "team": team,
        "check": "7_bosluk_konumu",
        "status": "WARN" if worst_len > 12 else "PASS",
        "kolon": col,
        "en_uzun_bosluk_satir": worst_len,
        "sure_saat": round(worst_len * 5 / 60, 1),
        "baslangic": str(block["Time"].iloc[0]),
        "bitis": str(block["Time"].iloc[-1]),
        "split_baslangic": which_split(start_pos),
        "split_bitis": which_split(end_pos),
    }


# ----------------------------------------------------------------------
# KONTROL 8: Takimlar arasi hedef dagilimi
# ----------------------------------------------------------------------
def check_target_distributions(pooled: pd.DataFrame, targets: list[str]) -> pd.DataFrame:
    available = [c for c in targets if c in pooled.columns]
    stats = pooled.groupby("greenhouse_id")[available].agg(["mean", "std", "min", "max"])
    return stats.round(2)


# ----------------------------------------------------------------------
# KONTROL 3: Sema tutarliligi (pooling dogrulugu icin kritik)
# ----------------------------------------------------------------------
def check_schema_consistency(pooled: pd.DataFrame) -> dict:
    per_team_cols = {}
    for gh, grp in pooled.groupby("greenhouse_id"):
        # tamamen NaN olan kolon = concat sirasinda o takimda hic olmayan kolon olabilir
        fully_nan = set(grp.columns[grp.isna().all()])
        per_team_cols[gh] = fully_nan

    problem = {gh: sorted(cols) for gh, cols in per_team_cols.items() if cols}
    return {
        "check": "3_sema_tutarliligi",
        "status": _status(not problem),
        "not": "Bir takimda tamamen NaN olan kolon = concat sirasinda sema uyusmazligi isareti",
        "tamamen_nan_kolonlar": problem if problem else "yok",
    }


# ----------------------------------------------------------------------
# KONTROL 9: Pencere kaybi muhasebesi
# ----------------------------------------------------------------------
def check_window_accounting(df: pd.DataFrame, team: str, targets: list[str]) -> dict:
    df = df.sort_values("Time").reset_index(drop=True)
    n = len(df)
    train_end = int(n * TRAIN_FRAC)
    val_end = train_end + int(n * VAL_FRAC)
    bounds = {"train": (0, train_end), "val": (train_end, val_end), "test": (val_end, n)}

    available = [c for c in targets if c in df.columns]
    target_arr = df[available].to_numpy()

    teorik = kabul = purge_sinir = purge_nan = 0
    last_start = n - (INPUT_STEPS + OUTPUT_STEPS)
    for s in range(0, last_start + 1, STRIDE):
        teorik += 1
        end = s + INPUT_STEPS + OUTPUT_STEPS
        split = next((k for k, (lo, hi) in bounds.items() if lo <= s < hi), None)
        if split is None:
            continue
        if end > bounds[split][1]:
            purge_sinir += 1
            continue
        if np.isnan(target_arr[s + INPUT_STEPS:end]).any():
            purge_nan += 1
            continue
        kabul += 1

    return {
        "team": team,
        "check": "9_pencere_muhasebesi",
        "status": _status(kabul > 0, warn=(kabul / max(teorik, 1) < 0.5)),
        "teorik_pencere": teorik,
        "kabul_edilen": kabul,
        "atilan_split_siniri": purge_sinir,
        "atilan_hedef_nan": purge_nan,
        "kabul_orani_pct": round(kabul / max(teorik, 1) * 100, 1),
    }


# ----------------------------------------------------------------------
# ANA CALISTIRICI
# ----------------------------------------------------------------------
def run_all(base_dir: Path, use_grodan: bool = True) -> None:
    fname = "common_core_with_grodan_strict.parquet" if use_grodan else "common_core_strict.parquet"
    pooled = pd.read_parquet(base_dir / fname)
    targets = CORE_TARGETS + (GRODAN_TARGETS if use_grodan else [])

    print("=" * 78)
    print(f"VERI DOGRULAMA — {fname}")
    print(f"Pooled sekil: {pooled.shape}")
    print("=" * 78)

    rows: list[dict] = []
    for team, grp in pooled.groupby("greenhouse_id", sort=False):
        grp = grp.sort_values("Time").reset_index(drop=True)
        rows.append(check_time_continuity(grp, team))
        rows.append(check_duplicate_timestamps(grp, team))
        rows.append(check_nan_breakdown(grp, team, targets))
        rows.append(check_constant_columns(grp, team))
        rows.append(check_value_sanity(grp, team))
        rows.append(check_gap_location(grp, team))
        rows.append(check_window_accounting(grp, team, targets))

    schema = check_schema_consistency(pooled)

    # --- Ozet tablo ---
    summary = pd.DataFrame([{"team": r.get("team", "-"), "check": r["check"], "status": r["status"]} for r in rows])
    pivot = summary.pivot(index="team", columns="check", values="status")
    print("\n--- OZET (FAIL varsa sonraki asamaya GECILMEZ) ---")
    print(pivot.to_string())
    print(f"\n[{schema['status']}] {schema['check']}: {schema['tamamen_nan_kolonlar']}")

    # --- Detaylar: sadece PASS olmayanlar ---
    print("\n--- DETAY (yalnizca WARN/FAIL) ---")
    for r in rows:
        if r["status"] == "PASS":
            continue
        print(f"\n[{r['status']}] {r['team']} / {r['check']}")
        for k, v in r.items():
            if k in ("team", "check", "status"):
                continue
            print(f"    {k}: {v}")

    # --- Kontrol 8 ayri (tablo formatinda) ---
    print("\n--- 8_hedef_dagilimi (takimlar arasi karsilastirma) ---")
    print(check_target_distributions(pooled, CORE_TARGETS).to_string())

    pd.DataFrame(rows).to_csv(base_dir / "data_verification_report.csv", index=False)
    print(f"\nDetayli rapor: {base_dir / 'data_verification_report.csv'}")

    n_fail = sum(1 for r in rows if r["status"] == "FAIL") + (schema["status"] == "FAIL")
    print("\n" + "=" * 78)
    print(f"SONUC: {n_fail} FAIL. " + ("Sonraki asamaya GECILEBILIR." if n_fail == 0 else "DUZELTILMEDEN GECILMEZ."))
    print("=" * 78)


if __name__ == "__main__":
    BASE_DIR = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")
    run_all(BASE_DIR, use_grodan=True)
