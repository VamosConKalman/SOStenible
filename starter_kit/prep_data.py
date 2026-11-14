"""
prep_data.py — Tabla horaria del campus (misma lógica que tutorial.ipynb) + diagnóstico.

Uso:  python prep_data.py [ruta_data_train]   ->  escribe hourly.csv
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("../data/train")


def build_hourly(data_dir: Path) -> pd.DataFrame:
    cont = pd.read_csv(data_dir / "contador.csv", parse_dates=["Fecha"]).set_index("Fecha")
    inv = pd.read_csv(data_dir / "inversor.csv", parse_dates=["Fecha"]).set_index("Fecha")
    pvpc = pd.read_csv(data_dir / "precio_pvpc.csv", parse_dates=["Fecha"]).set_index("Fecha")
    co2 = pd.read_csv(data_dir / "co2_red.csv", parse_dates=["Fecha"]).set_index("Fecha")

    load = (-cont["Contador - POTENCIA ACTIVA EXPORTADA (kW)"]).clip(lower=0, upper=5000)
    load_h = load.resample("1h").mean()

    cols = []
    for i in (1, 2, 3):
        cols.append([c for c in inv.columns
                     if f"INVERSOR {i}" in c.upper() and "POTENCIA ACTIVA" in c.upper()
                     and "FASE" not in c.upper()][0])
    pv = sum(inv[c].fillna(0) for c in cols).clip(lower=0)
    pv_h = pv.resample("1h").mean()

    df = pd.DataFrame({
        "load_kw": load_h,
        "pv_kw": pv_h,
        "precio_eur_per_kwh": pvpc["precio_eur_per_kwh"],
        "co2_kg_per_kwh": co2["co2_kg_per_kwh"],
    }).dropna()
    df.index.name = "Fecha"
    return df


def diagnose(df: pd.DataFrame) -> None:
    net = df["load_kw"] - df["pv_kw"]
    full = pd.date_range(df.index.min(), df.index.max(), freq="1h")
    print(f"Horas: {len(df)}  |  huecos en la rejilla horaria: {len(full.difference(df.index))}")
    print(f"Carga neta: min {net.min():.0f}  p5 {net.quantile(.05):.0f}  mediana {net.median():.0f} kW")
    print(f"% horas N < 500 kW: {100 * (net < 500).mean():.2f}%   |   % horas N < 0: {100 * (net < 0).mean():.2f}%")
    print((net < 500).groupby(df.index.month).mean().mul(100).round(2).rename("% N<500 por mes"))


if __name__ == "__main__":
    df = build_hourly(DATA_DIR)
    diagnose(df)
    df.to_csv("hourly.csv")
    print("hourly.csv escrito")
