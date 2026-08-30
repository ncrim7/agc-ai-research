"""
AGC 2. Edisyon - Hafta 1: 6 Takim Icin Parametrik Temizlik Pipeline'i
=======================================================================
Uretir: common_core_strict.parquet, common_core_with_grodan_strict.parquet
        (hem pooled hem takim bazinda) + data_health_report_week1.csv

Karar gunlugundeki (AGC_Proje_Karar_Gunlugu.md, Bolum 2) genellestirme
planinin kod hali. Colab'da tek hucreye yapistirip BASE_DIR'i kendi
yoluna gore degistirip calistir.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------
# KONFIGURASYON
# ----------------------------------------------------------------------

BASE_DIR = Path("/content/drive/MyDrive/AutonomousGreenhouseChallenge_edition2")
TEAMS = ["AICU", "Automatoes", "Digilog", "IUACAAS", "Reference", "TheAutomators"]

GRODAN_COLS = ["EC_slab1", "EC_slab2", "WC_slab1", "WC_slab2", "t_slab1", "t_slab2"]

# Fiziksel sinirlar: ihlaller MASKLENIR (NaN yapilir), satir SILINMEZ.
PHYSICAL_BOUNDS: dict[str, tuple[float, float]] = {
    "Tair": (0, 50),
    "CO2air": (0, 2500),
    "Rhair": (0, 100),
    "HumDef": (0, 30),
    "Tot_PAR": (0, 3000),
    "EC_slab1": (0, 15),
    "EC_slab2": (0, 15),
    "WC_slab1": (0, 100),
    "WC_slab2": (0, 100),
    "t_slab1": (0, 50),
    "t_slab2": (0, 50),
}

SLAB_CORR_THRESHOLD = 0.7          # bunun altinda capraz doldurma yapilmaz
MAX_INTERP_GAP_STEPS = 6           # 6 x 5dk = 30 dk. Uzun bosluklar interpolasyonla kapatilmaz.


# ----------------------------------------------------------------------
# YARDIMCI FONKSIYONLAR
# ----------------------------------------------------------------------

def resolve_team_dir(team: str, base_dir: Path) -> Path:
    """'TheAutomators' / 'The Automators' gibi isim varyasyonlarina karsi dayanikli klasor cozumleme."""
    direct = base_dir / team
    if direct.exists():
        return direct
    normalized_target = team.replace(" ", "").lower()
    for folder in base_dir.iterdir():
        if folder.is_dir() and folder.name.replace(" ", "").lower() == normalized_target:
            return folder
    raise FileNotFoundError(f"'{team}' icin klasor bulunamadi: {base_dir}")


def find_file(folder: Path, name_contains: str) -> Path:
    candidates = list(folder.glob(f"*{name_contains}*"))
    if not candidates:
        raise FileNotFoundError(f"'{name_contains}' icin dosya bulunamadi: {folder}")
    return candidates[0]


def excel_serial_to_datetime(series: pd.Series) -> pd.Series:
    """Excel seri numarasi -> datetime.

    .dt.round("5min") ZORUNLU: kaynak CSV'deki seri numaralari ~5 ondalik basamaga
    yuvarlanmis, bu yuzden adimlar 00:04:59.808 gibi cikiyor (~192ms sapma, yer yer
    ~700ms'e kadar). Veri nominal olarak 5 dakikalik izgarada oldugu icin 5 dakikaya
    yuvarlamak bu gurultuyu tamamen siler. Gercek bosluklari (eksik satir, kesinti)
    KORUR: eksik satir yuvarlamayla geri gelmez, 75 dakikalik bir kesinti 75 dakika
    kalir. Saniyeye yuvarlamak yetmez cunku sapma bazen 500ms'i asabiliyor.
    """
    dt = pd.Timestamp("1899-12-30") + pd.to_timedelta(pd.to_numeric(series, errors="coerce"), unit="D")
    return dt.dt.round("5min")


def force_numeric(df: pd.DataFrame, exclude: list[str]) -> pd.DataFrame:
    for col in df.columns:
        if col in exclude:
            continue
        if df[col].dtype == "object":
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def longest_nan_run(series: pd.Series) -> int:
    """En uzun ardisik NaN blogunun satir sayisi."""
    is_na = series.isna().astype(int)
    if is_na.sum() == 0:
        return 0
    groups = (is_na != is_na.shift()).cumsum()
    run_lengths = is_na.groupby(groups).sum()
    return int(run_lengths.max())


# ----------------------------------------------------------------------
# VERI YUKLEME
# ----------------------------------------------------------------------

def load_weather(base_dir: Path) -> pd.DataFrame:
    path = base_dir / "Weather.csv"
    if not path.exists():
        weather_dir = base_dir / "Weather"
        path = find_file(weather_dir, "Weather") if weather_dir.exists() else find_file(base_dir, "eather")

    weather = pd.read_csv(path, skipinitialspace=True)
    weather.columns = weather.columns.str.strip()
    time_col = [c for c in weather.columns if "time" in c.lower()][0]
    weather["Time"] = excel_serial_to_datetime(weather[time_col])
    weather = weather.drop(columns=[time_col])
    weather = force_numeric(weather, exclude=["Time"])
    return weather


def load_team_raw(team: str, base_dir: Path) -> pd.DataFrame:
    team_dir = resolve_team_dir(team, base_dir)
    climate = pd.read_csv(find_file(team_dir, "GreenhouseClimate"), skipinitialspace=True)
    grodan = pd.read_csv(find_file(team_dir, "GrodanSens"), skipinitialspace=True)

    for df in (climate, grodan):
        df.columns = df.columns.str.strip()

    t_clim = [c for c in climate.columns if "time" in c.lower()][0]
    t_grod = [c for c in grodan.columns if "time" in c.lower()][0]
    climate["Time"] = excel_serial_to_datetime(climate[t_clim])
    grodan["Time"] = excel_serial_to_datetime(grodan[t_grod])
    climate = climate.drop(columns=[t_clim])
    grodan = grodan.drop(columns=[t_grod])

    merged = pd.merge(climate, grodan, on="Time", how="inner", validate="one_to_one")
    merged = force_numeric(merged, exclude=["Time"])
    return merged


# ----------------------------------------------------------------------
# TEK TAKIM TEMIZLIK PIPELINE'I
# ----------------------------------------------------------------------

def clean_team(team: str, base_dir: Path, weather: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    diag: dict[str, Any] = {"team": team}

    df = load_team_raw(team, base_dir)
    df = pd.merge(df, weather, on="Time", how="left", validate="many_to_one")
    df = df.sort_values("Time").reset_index(drop=True)
    diag["raw_rows"] = len(df)

    # 1. SP kolonlarini at, sadece VIP (gerceklesen) tut.
    #    Token-bazli eslesme kullanilir (sadece endswith('_sp') degil): 'water_sup_intervals_sp_min'
    #    gibi kolonlar '_sp' ile BITMIYOR ama icinde 'sp' token'i geciyor - bunu da yakalamamiz lazim.
    #    'water_sup' ve 'water_sup_intervals_vip_min' gibi kolonlar YANLISLIKLA yakalanmaz
    #    (token 'sup', 'vip' - 'sp' degil).
    sp_cols = [c for c in df.columns if "sp" in c.split("_")]
    df = df.drop(columns=sp_cols)
    diag["dropped_sp_cols"] = len(sp_cols)

    # 2. LED off-state dogrulama + 0-fill (sadece int_*_vip - ekran/perde kolonlarina uygulanmiyor,
    #    onlarin "kapali = NaN" varsayimi LED kadar guclu kanitlanmadi).
    led_cols = [c for c in df.columns if c.startswith("int_") and c.endswith("_vip")]
    if led_cols and "AssimLight" in df.columns:
        nan_mask = df[led_cols[0]].isna()
        if nan_mask.sum() > 0:
            off_state_match = (df.loc[nan_mask, "AssimLight"] == 0).mean()
            diag["led_offstate_match_pct"] = round(float(off_state_match) * 100, 1)
        else:
            diag["led_offstate_match_pct"] = None
    if led_cols:
        df[led_cols] = df[led_cols].fillna(0.0)

    # 3. Slab capraz onarim - SADECE korelasyon esigi (0.7) gecilirse.
    for a, b in [("EC_slab1", "EC_slab2"), ("WC_slab1", "WC_slab2"), ("t_slab1", "t_slab2")]:
        if a in df.columns and b in df.columns:
            corr = df[[a, b]].corr().iloc[0, 1]
            diag[f"corr_{a}_{b}"] = round(float(corr), 3) if pd.notna(corr) else None
            if pd.notna(corr) and corr >= SLAB_CORR_THRESHOLD:
                df[a] = df[a].fillna(df[b])
                df[b] = df[b].fillna(df[a])
            # esigin altindaysa DOKUNMA - yanlis yamadan NaN birakmak daha guvenli.

    # 4. Fiziksel sinir kontrolu - ihlaller MASKLENIR, satir SILINMEZ.
    #    Interpolasyondan ONCE yapiliyor: izole imkansiz degerler (tek satirlik) boylece
    #    asagidaki adimda normal bir bosluk gibi meselelaninca interpolasyonla kapatilabilir;
    #    uzun bosluklar zaten limit asildigi icin interpolasyon yine doldurmayacak.
    violations: dict[str, int] = {}
    for col, (lo, hi) in PHYSICAL_BOUNDS.items():
        if col in df.columns:
            bad = (df[col] < lo) | (df[col] > hi)
            n_bad = int(bad.sum())
            if n_bad > 0:
                df.loc[bad, col] = np.nan
                violations[col] = n_bad
    diag["physical_violations"] = violations if violations else "yok"

    # 5. En uzun ardisik NaN blogu (fiziksel maskeleme SONRASI, gercek durumu yansitir)
    #    + zaman-bazli SINIRLI interpolasyon.
    numeric_cols = [c for c in df.select_dtypes(include=[np.number]).columns]
    max_gaps = {c: longest_nan_run(df[c]) for c in numeric_cols}
    if max_gaps:
        worst_col = max(max_gaps, key=max_gaps.get)
        diag["max_gap_col"] = worst_col
        diag["max_gap_len_rows"] = max_gaps[worst_col]

    df = df.set_index("Time")
    df[numeric_cols] = df[numeric_cols].interpolate(
        method="time", limit=MAX_INTERP_GAP_STEPS, limit_direction="both"
    )
    df = df.reset_index()

    df["greenhouse_id"] = team
    diag["final_rows"] = len(df)
    diag["remaining_nan_total"] = int(df.isna().sum().sum())
    return df, diag


# ----------------------------------------------------------------------
# ANA ORKESTRASYON
# ----------------------------------------------------------------------

def build_common_core(base_dir: Path, teams: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    weather = load_weather(base_dir)
    all_dfs: list[pd.DataFrame] = []
    all_diags: list[dict[str, Any]] = []

    for team in teams:
        print(f"Isleniyor: {team}")
        try:
            df, diag = clean_team(team, base_dir, weather)
        except Exception as exc:  # noqa: BLE001 - hata gizlenmiyor, loglanip devam ediliyor
            print(f"  HATA ({team}): {exc}")
            all_diags.append({"team": team, "error": str(exc)})
            continue
        all_dfs.append(df)
        all_diags.append(diag)

        team_dir = resolve_team_dir(team, base_dir)
        df.to_parquet(team_dir / f"{team}_common_core_with_grodan_strict.parquet", index=False)
        df.drop(columns=[c for c in GRODAN_COLS if c in df.columns]).to_parquet(
            team_dir / f"{team}_common_core_strict.parquet", index=False
        )

    pooled_with_grodan = pd.concat(all_dfs, ignore_index=True)
    pooled_core = pooled_with_grodan.drop(columns=[c for c in GRODAN_COLS if c in pooled_with_grodan.columns])

    pooled_with_grodan.to_parquet(base_dir / "common_core_with_grodan_strict.parquet", index=False)
    pooled_core.to_parquet(base_dir / "common_core_strict.parquet", index=False)

    diag_df = pd.DataFrame(all_diags)
    diag_df.to_csv(base_dir / "data_health_report_week1.csv", index=False)

    print("\n" + "=" * 80)
    print("OZET - data_health_report_week1.csv'ye kaydedildi")
    print("=" * 80)
    print(diag_df.to_string(index=False))
    print(f"\nPooled common_core_strict: {pooled_core.shape}")
    print(f"Pooled common_core_with_grodan_strict: {pooled_with_grodan.shape}")

    return pooled_core, diag_df


if __name__ == "__main__":
    pooled_core_df, diagnostics_df = build_common_core(BASE_DIR, TEAMS)
