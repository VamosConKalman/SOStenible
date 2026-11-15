"""Data loading and preprocessing from data/train/."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]  # Go up to backend/, then to repo root
DATA_DIR = ROOT / "data" / "train"


def build_hourly() -> pd.DataFrame:
    """Build the master hourly DataFrame with load_kw, pv_kw, precio_eur_per_kwh, co2_kg_per_kwh."""
    cont = pd.read_csv(DATA_DIR / "contador.csv", parse_dates=["Fecha"]).set_index("Fecha")
    inv = pd.read_csv(DATA_DIR / "inversor.csv", parse_dates=["Fecha"]).set_index("Fecha")
    pvpc = pd.read_csv(DATA_DIR / "precio_pvpc.csv", parse_dates=["Fecha"]).set_index("Fecha")
    co2 = pd.read_csv(DATA_DIR / "co2_red.csv", parse_dates=["Fecha"]).set_index("Fecha")

    load = (-cont["Contador - POTENCIA ACTIVA EXPORTADA (kW)"]).clip(lower=0, upper=5000)
    cols = [
        [c for c in inv.columns
         if f"INVERSOR {i}" in c.upper() and "POTENCIA ACTIVA" in c.upper()
         and "FASE" not in c.upper()][0]
        for i in (1, 2, 3)
    ]
    pv = sum(inv[c].fillna(0) for c in cols).clip(lower=0)

    df = pd.DataFrame({
        "load_kw": load.resample("1h").mean(),
        "pv_kw": pv.resample("1h").mean(),
        "precio_eur_per_kwh": pvpc["precio_eur_per_kwh"],
        "co2_kg_per_kwh": co2["co2_kg_per_kwh"],
    }).dropna()

    # Ensure 1h frequency and interpolate gaps up to 3h
    df = df.asfreq("1h")
    numeric_cols = ["load_kw", "pv_kw", "precio_eur_per_kwh", "co2_kg_per_kwh"]
    df[numeric_cols] = df[numeric_cols].interpolate(method="linear", limit=3, limit_area="inside")

    return df


def build_meteo() -> pd.DataFrame:
    """Load meteo.csv (5 min) and resample to hourly means with standard column names.

    The column names in the CSV use "(ºC)"; matching is done by keyword over all
    columns so that small differences in the units do not drop the temperatures.
    """
    df = pd.read_csv(DATA_DIR / "meteo.csv", parse_dates=["Fecha"]).set_index("Fecha")
    cols = list(df.columns)

    def pick(*keys, exclude=()):
        for c in cols:
            u = c.upper()
            if all(k in u for k in keys) and not any(e in u for e in exclude):
                return c
        return None

    mapping = {
        "irradiancia_wm2": pick("IRRADIANCIA (W/M2)") or pick("IRRADIANCIA", exclude=("ERROR", " 1 ", " 2 ")),
        "temp_ambient_c": pick("TEMPERATURA AMBIENTE"),
        "temp_panel_c": pick("TEMPERATURA PANEL"),
        "vent_ms": pick("VIENTO"),
    }
    out = pd.DataFrame(index=df.resample("1h").mean(numeric_only=True).index)
    for std, col in mapping.items():
        if col is not None:
            out[std] = pd.to_numeric(df[col], errors="coerce").resample("1h").mean()
    return out.interpolate(method="linear", limit=3, limit_area="inside")


def scale_for_mode(df: pd.DataFrame, mode: str, pv_scale: float = 12.0) -> pd.DataFrame:
    """Hard mode: the campus has 12x the solar installation (same as the official hard server)."""
    if mode != "dificil":
        return df
    out = df.copy()
    out["pv_kw"] = out["pv_kw"] * pv_scale
    return out


def is_valid_day(df: pd.DataFrame, date_str: str) -> bool:
    """Check if a day has 24 valid hours with load_kw > 0."""
    try:
        d = pd.Timestamp(date_str)
    except Exception:
        return False
    day_df = df.loc[d:d + pd.Timedelta(hours=23)]
    if len(day_df) != 24:
        return False
    if not day_df.dropna(subset=["load_kw", "pv_kw", "precio_eur_per_kwh", "co2_kg_per_kwh"]).shape[0] == 24:
        return False
    if (day_df["load_kw"] > 0).all() == False:
        return False
    # Also need the previous day full
    prev_day_df = df.loc[d - pd.Timedelta(days=1):d - pd.Timedelta(hours=1)]
    if len(prev_day_df) != 24:
        return False
    if not prev_day_df.dropna(subset=["load_kw", "pv_kw", "precio_eur_per_kwh", "co2_kg_per_kwh"]).shape[0] == 24:
        return False
    if (prev_day_df["load_kw"] > 0).all() == False:
        return False
    return True


def get_valid_days(df: pd.DataFrame) -> list[str]:
    """Return list of valid day date strings."""
    days = sorted(df.index.normalize().unique())
    valid = []
    for d in days:
        ds = str(d.date())
        if is_valid_day(df, ds):
            valid.append(ds)
    return valid


def get_day_data(df: pd.DataFrame, date_str: str) -> pd.DataFrame:
    """Return 24h DataFrame for a given date."""
    d = pd.Timestamp(date_str)
    return df.loc[d:d + pd.Timedelta(hours=23)].copy()


def compute_indices(df: pd.DataFrame, valid_days: list[str]) -> dict:
    """Compute solarIdx and activityIdx for each valid day."""
    indices = {}
    for date_str in valid_days:
        d = pd.Timestamp(date_str)
        day_df = df.loc[d:d + pd.Timedelta(hours=23)]
        solar_day = day_df["pv_kw"].sum()
        demand_day = day_df["load_kw"].sum()

        # solarIdx: solar of day / mean solar of days in same month
        month_days = [ds for ds in valid_days
                      if pd.Timestamp(ds).month == d.month]
        solar_vals = []
        for ds in month_days:
            dd = pd.Timestamp(ds)
            solar_vals.append(df.loc[dd:dd + pd.Timedelta(hours=23), "pv_kw"].sum())
        solar_mean = np.mean(solar_vals) if solar_vals else 1.0
        solar_idx = float(solar_day / max(solar_mean, 1e-9))

        # activityIdx: demand of day / mean demand of same month and type (weekday/weekend)
        is_weekend = d.dayofweek >= 5
        month_type_days = [ds for ds in valid_days
                          if pd.Timestamp(ds).month == d.month
                          and (pd.Timestamp(ds).dayofweek >= 5) == is_weekend]
        dem_vals = []
        for ds in month_type_days:
            dd = pd.Timestamp(ds)
            dem_vals.append(df.loc[dd:dd + pd.Timedelta(hours=23), "load_kw"].sum())
        dem_mean = np.mean(dem_vals) if dem_vals else 1.0
        activity_idx = float(demand_day / max(dem_mean, 1e-9))

        # Label
        months_ca = ["", "gener", "febrer", "març", "abril", "maig", "juny",
                     "juliol", "agost", "setembre", "octubre", "novembre", "desembre"]
        label = f"{d.day} de {months_ca[d.month]}"

        indices[date_str] = {
            "date": date_str,
            "label": label,
            "weekday": int(d.dayofweek),
            "solarIdx": round(solar_idx, 3),
            "activityIdx": round(activity_idx, 3),
        }
    return indices