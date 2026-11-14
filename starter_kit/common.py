"""common.py — utilidades compartidas por calibrate.py y backtest.py (no se entrega)."""
import numpy as np
import pandas as pd

SPEC = {"capacity_kwh": 2000.0, "power_kw": 500.0, "efficiency": 0.90,
        "soc_init": 0.5, "soc_min": 0.0, "soc_max": 1.0, "dt_hours": 1.0}


def load_hourly(path="hourly.csv") -> pd.DataFrame:
    return pd.read_csv(path, parse_dates=["Fecha"], index_col="Fecha").sort_index()


def weeks(df: pd.DataFrame, day_ranges):
    """Bloques semanales completos (168 h contiguas) por mes. day_ranges = [(1,7), (8,14), ...]."""
    out = []
    for (y, m), g in df.groupby([df.index.year, df.index.month]):
        for d0, d1 in day_ranges:
            blk = g[(g.index.day >= d0) & (g.index.day <= d1)]
            if len(blk) == 168 and (blk.index[-1] - blk.index[0]) == pd.Timedelta(hours=167):
                out.append(blk)
    return out


def kappa(df: pd.DataFrame) -> float:
    base = np.maximum(df["load_kw"] - df["pv_kw"], 0.0)
    return float((base * df["co2_kg_per_kwh"]).sum() / (base * df["precio_eur_per_kwh"]).sum())


def totals(load, pv, price, co2, grid):
    base = np.maximum(np.asarray(load) - np.asarray(pv), 0.0)
    grid = np.asarray(grid)
    return {"Eb": float(base @ co2), "Cb": float(base @ price),
            "Ea": float(grid @ co2), "Ca": float(grid @ price)}


def official_score(t, infr=0):
    dco2 = 100 * (t["Eb"] - t["Ea"]) / t["Eb"]
    dcost = 100 * (t["Cb"] - t["Ca"]) / t["Cb"]
    return max(0.0, 0.7 * dco2 + 0.3 * dcost - 1.0 * infr), dco2, dcost
