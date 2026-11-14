"""
data_loader.py — Cargador de datos de train para tests (solo lectura).

Proporciona:
- hourly_df: DataFrame horario con load_kw, pv_kw, precio, co2
- weekly_df: DataFrame de una semana (168 h)
- small_df: DataFrame pequeño para tests rápidos
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional


# Ruta al directorio de datos (relative to this file or absolute)
_DATA_DIR: Optional[Path] = None


def set_data_dir(path: Path | str):
    """Establece la ruta al directorio de datos de train."""
    global _DATA_DIR
    _DATA_DIR = Path(path)


def _get_data_dir() -> Path:
    if _DATA_DIR is not None:
        return _DATA_DIR
    # Default: parent of this file / data/train
    return Path(__file__).parent.parent / "data" / "train"


def load_hourly_df() -> pd.DataFrame:
    """
    Carga y agrega las 6 columnas principales a frecuencia horaria.

    Devuelve DataFrame con:
    - Fecha (DatetimeIndex)
    - load_kw, pv_kw, precio_eur_per_kwh, co2_kg_per_kwh
    """
    data_dir = _get_data_dir()

    # --- Contador ---
    df_contador = pd.read_csv(data_dir / "contador.csv", parse_dates=["Fecha"])
    df_contador_idx = df_contador.set_index("Fecha")
    load_5min = (
        -df_contador_idx["Contador - POTENCIA ACTIVA EXPORTADA (kW)"]
    ).clip(lower=0, upper=5000)
    load_hourly = (
        load_5min.resample("1h").mean()
        .asfreq("1h")
        .interpolate(limit=3, limit_area="inside")
        .dropna()
    )

    # --- Inversor ---
    df_inversor = pd.read_csv(data_dir / "inversor.csv", parse_dates=["Fecha"])
    df_inversor_idx = df_inversor.set_index("Fecha")

    def _find_pv_col(prefix: str, columns):
        for c in columns:
            c_str = str(c).upper()
            if (
                prefix in c_str
                and "POTENCIA ACTIVA" in c_str
                and "FASE" not in c_str
            ):
                return c
        return None

    p1 = _find_pv_col("INVERSOR 1", df_inversor_idx.columns)
    p2 = _find_pv_col("INVERSOR 2", df_inversor_idx.columns)
    p3 = _find_pv_col("INVERSOR 3", df_inversor_idx.columns)

    pv_total_5min = (
        df_inversor_idx[p1].fillna(0)
        + df_inversor_idx[p2].fillna(0)
        + df_inversor_idx[p3].fillna(0)
    ).clip(lower=0)
    pv_hourly = (
        pv_total_5min.resample("1h").mean()
        .asfreq("1h")
        .interpolate(limit=3, limit_area="inside")
        .dropna()
    )

    # --- PVPC y CO2 ---
    df_pvpc = pd.read_csv(data_dir / "precio_pvpc.csv", parse_dates=["Fecha"])
    df_pvpc = df_pvpc.set_index("Fecha")

    df_co2 = pd.read_csv(data_dir / "co2_red.csv", parse_dates=["Fecha"])
    df_co2 = df_co2.set_index("Fecha")

    # --- Consolidar ---
    df = pd.DataFrame(
        {
            "load_kw": load_hourly,
            "pv_kw": pv_hourly,
            "precio_eur_per_kwh": df_pvpc["precio_eur_per_kwh"],
            "co2_kg_per_kwh": df_co2["co2_kg_per_kwh"],
        }
    ).dropna()

    return df


def get_weekly_df(start: int = 0, n_weeks: int = 1) -> pd.DataFrame:
    """
    Devuelve un DataFrame de n_weeks semanas (168 h por semana).

    Parámetros
    ----------
    start : int
        Índice de la primera hora (default 0).
    n_weeks : int
        Número de semanas (default 1).

    Devuelve DataFrame con las 4 columnas principales.
    """
    df = load_hourly_df()
    return df.iloc[start : start + n_weeks * 168]


def get_small_df(n_hours: int = 24) -> pd.DataFrame:
    """
    Devuelve un DataFrame artificial de n_hours horas para tests rápidos.

    Contiene:
    - load_kw: 500 kW constante
    - pv_kw: 0 kW (noche)
    - precio_eur_per_kwh: oscilación simple (baja noche, alta tarde)
    - co2_kg_per_kwh: 0.07 constante

    Usa np.resize para cualquier n_hours.
    """
    dates = pd.date_range("2026-01-05", periods=n_hours, freq="1h")

    # Patrón de 24 h → se redimensiona para cualquier n_hours
    pattern = np.array(
        [0.08] * 6 + [0.12] * 4 + [0.16] * 4 + [0.20] * 4 + [0.10] * 6 + [0.08] * 4,
        dtype=float,
    )
    prices = np.resize(pattern, n_hours)[:n_hours]

    return pd.DataFrame(
        {
            "Fecha": dates,
            "load_kw": 500.0,
            "pv_kw": 0.0,
            "precio_eur_per_kwh": prices,
            "co2_kg_per_kwh": 0.07,
        }
    )


def get_const_df(n_hours: int = 24) -> pd.DataFrame:
    """
    Devuelve un DataFrame con precio y CO₂ constantes (para test de coherencia).

    Con valores constantes, el LP debe devolver P = 0 (arbitraje imposible).
    """
    dates = pd.date_range("2026-01-05", periods=n_hours, freq="1h")

    return pd.DataFrame(
        {
            "Fecha": dates,
            "load_kw": 500.0,
            "pv_kw": 0.0,
            "precio_eur_per_kwh": 0.12,
            "co2_kg_per_kwh": 0.07,
        }
    )