"""Pipeline de dades OFICIAL (el de la guia pràctica del repte) -> DataFrame horari.

Columnes de sortida: dem (kW), sol (kW), price (EUR/kWh), co2 (kg/kWh), index = Fecha horària.
"""
from pathlib import Path
import pandas as pd


def _find(data_dir, suffix):
    files = sorted(Path(data_dir).glob(f"*{suffix}"))
    if not files:
        raise FileNotFoundError(f"No trobo '*{suffix}' a {data_dir}")
    return files[0]


def load_hourly(data_dir) -> pd.DataFrame:
    c = pd.read_csv(_find(data_dir, "contador.csv"), parse_dates=["Fecha"]).set_index("Fecha")
    dem = (-c["Contador - POTENCIA ACTIVA EXPORTADA (kW)"]).clip(lower=0, upper=5000)
    dem = dem.resample("1h").mean().dropna()

    i = pd.read_csv(_find(data_dir, "inversor.csv"), parse_dates=["Fecha"]).set_index("Fecha")
    inv_cols = [col for col in i.columns if "POTENCIA ACTIVA (kW)" in col]      # 3 inversors
    sol = i[inv_cols].sum(axis=1).clip(lower=0).resample("1h").mean().dropna()

    p = pd.read_csv(_find(data_dir, "precio_pvpc.csv"), parse_dates=["Fecha"]).set_index("Fecha")
    k = pd.read_csv(_find(data_dir, "co2_red.csv"), parse_dates=["Fecha"]).set_index("Fecha")

    df = pd.DataFrame({"dem": dem, "sol": sol,
                       "price": p["precio_eur_per_kwh"], "co2": k["co2_kg_per_kwh"]}).dropna()
    df.index.name = "Fecha"
    return df


def to_env_frame(hourly: pd.DataFrame) -> pd.DataFrame:
    """Format que espera starter_kit/environment.py."""
    return hourly.rename(columns={"dem": "load_kw", "sol": "pv_kw",
                                  "price": "precio_eur_per_kwh", "co2": "co2_kg_per_kwh"})
