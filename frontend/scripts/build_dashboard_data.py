"""
build_dashboard_data.py — Genera public/data/dashboard.json per al dashboard divulgatiu.

Llegeix les dades reals del campus (../data/train), construeix la taula horària
amb la mateixa lògica que starter_kit/prep_data.py i, per a cada dia complet,
resol un LP de 24 h (SciPy HiGHS) que decideix quan carregar/descarregar la
bateria (70 % pes CO2, 30 % pes cost, sense exportar a xarxa).

Ús (des de l'arrel del repo):
    python frontend/scripts/build_dashboard_data.py [ruta_data_train]

Quan l'agent de l'equip tingui el seu propi despatx, n'hi ha prou amb substituir
la funció `dispatch_day` per la sortida de l'agent: el frontend no canvia.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linprog

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "train"
OUT = ROOT / "frontend" / "public" / "data" / "dashboard.json"
SPEC = json.loads((ROOT / "starter_kit" / "battery_spec.json").read_text())

CAP = SPEC["capacity_kwh"]
PMAX = SPEC["power_kw"]
ETA = SPEC["efficiency"]
SOC0 = SPEC["soc_init"] * CAP
W_CO2, W_COST = 0.7, 0.3

# Equivalències divulgatives (aproximades; s'expliquen a la nota metodològica)
KG_CO2_PER_KM_COTXE = 0.12     # turisme mitjà de gasolina, kg CO2/km
KG_CO2_PER_ARBRE_ANY = 21.0    # absorció anual d'un arbre adult, kg CO2/any
KWH_PER_MOBIL = 0.015          # una càrrega completa de mòbil, kWh


def build_hourly(data_dir: Path) -> pd.DataFrame:
    cont = pd.read_csv(data_dir / "contador.csv", parse_dates=["Fecha"]).set_index("Fecha")
    inv = pd.read_csv(data_dir / "inversor.csv", parse_dates=["Fecha"]).set_index("Fecha")
    pvpc = pd.read_csv(data_dir / "precio_pvpc.csv", parse_dates=["Fecha"]).set_index("Fecha")
    co2 = pd.read_csv(data_dir / "co2_red.csv", parse_dates=["Fecha"]).set_index("Fecha")

    load = (-cont["Contador - POTENCIA ACTIVA EXPORTADA (kW)"]).clip(lower=0, upper=5000)
    cols = [[c for c in inv.columns
             if f"INVERSOR {i}" in c.upper() and "POTENCIA ACTIVA" in c.upper()
             and "FASE" not in c.upper()][0] for i in (1, 2, 3)]
    pv = sum(inv[c].fillna(0) for c in cols).clip(lower=0)

    df = pd.DataFrame({
        "load": load.resample("1h").mean(),
        "pv": pv.resample("1h").mean(),
        "price": pvpc["precio_eur_per_kwh"],
        "co2": co2["co2_kg_per_kwh"],
        "pct_fossil": co2["porcentaje_con_emisiones"],
    }).dropna()
    # Mateixa convenció que l'enunciat i l'avaluador (starter_kit/common.py):
    # demanda = -potència del comptador; càrrega neta = demanda - solar.
    df["demand"] = df["load"]
    return df


def dispatch_day(day: pd.DataFrame) -> dict:
    """LP 24 h: variables [c(24), d(24), s(25)]. Minimitza CO2 i cost ponderats."""
    T = len(day)
    net = (day["demand"] - day["pv"]).to_numpy()
    co2, price = day["co2"].to_numpy(), day["price"].to_numpy()
    Eb, Cb = float(net @ co2), float(net @ price)
    w = W_CO2 * co2 / Eb + W_COST * price / Cb  # pes per kWh importat

    n = 3 * T + 1
    cost = np.zeros(n)
    cost[:T] = w          # carregar augmenta la importació
    cost[T:2 * T] = -w    # descarregar la redueix

    A_eq, b_eq = [], []
    for t in range(T):    # s[t+1] = s[t] + eta*c[t] - d[t]
        row = np.zeros(n)
        row[2 * T + t + 1], row[2 * T + t], row[t], row[T + t] = 1, -1, -ETA, 1
        A_eq.append(row); b_eq.append(0)
    row = np.zeros(n); row[2 * T] = 1; A_eq.append(row); b_eq.append(SOC0)

    A_ub, b_ub = [], []
    for t in range(T):    # sense exportar: net + c - d >= 0
        row = np.zeros(n); row[t], row[T + t] = -1, 1
        A_ub.append(row); b_ub.append(net[t])
    row = np.zeros(n); row[3 * T] = -1; A_ub.append(row); b_ub.append(-SOC0)  # acaba igual

    bounds = [(0, PMAX)] * (2 * T) + [(0, CAP)] * (T + 1)
    r = linprog(cost, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")
    c, d, s = r.x[:T], r.x[T:2 * T], r.x[2 * T:]
    grid = net + c - d
    return {"charge": c, "discharge": d, "soc": s[1:], "grid": grid,
            "co2_base": Eb, "co2_opt": float(grid @ co2),
            "cost_base": Cb, "cost_opt": float(grid @ price)}


def r1(x, k=1):
    return [round(float(v), k) for v in x]


def day_payload(day: pd.DataFrame, label: str, desc: str) -> dict:
    res = dispatch_day(day)
    co2_saved = res["co2_base"] - res["co2_opt"]
    solar_kwh = float(day["pv"].sum())
    demand_kwh = float(day["demand"].sum())
    return {
        "id": str(day.index[0].date()),
        "label": label,
        "description": desc,
        "date": str(day.index[0].date()),
        "hours": [f"{h:02d}:00" for h in day.index.hour],
        "demand": r1(day["demand"]),
        "solar": r1(day["pv"]),
        "price": r1(day["price"], 4),
        "co2": r1(day["co2"], 4),
        "pctFossil": r1(day["pct_fossil"] * 100, 1),
        "charge": r1(res["charge"]),
        "discharge": r1(res["discharge"]),
        "soc": r1(res["soc"] / CAP * 100),
        "grid": r1(res["grid"]),
        "totals": {
            "demandKwh": round(demand_kwh),
            "solarKwh": round(solar_kwh),
            "solarShare": round(100 * solar_kwh / demand_kwh, 2),
            "co2BaseKg": round(res["co2_base"], 1),
            "co2OptKg": round(res["co2_opt"], 1),
            "co2SavedKg": round(co2_saved, 1),
            "costBaseEur": round(res["cost_base"], 2),
            "costOptEur": round(res["cost_opt"], 2),
            "costSavedEur": round(res["cost_base"] - res["cost_opt"], 2),
            "shiftedKwh": round(float(res["discharge"].sum())),
        },
    }


def main() -> None:
    df = build_hourly(DATA_DIR)
    days = [g for _, g in df.groupby(df.index.date) if len(g) == 24]

    # Escenaris representatius (els dies amb més sol de cada tipus)
    def pick(cond):
        cands = [g for g in days if cond(g.index[0])]
        return max(cands, key=lambda g: g["pv"].sum()) if cands else None

    scenarios = [
        (pick(lambda d: d.month in (5, 6) and d.weekday() < 5), "Dia lectiu assolellat",
         "Un dia de classe de final de primavera: molta activitat i molt sol."),
        (pick(lambda d: d.month in (5, 6) and d.weekday() >= 5), "Cap de setmana",
         "Edificis gairebé buits: el sol pesa més respecte al consum."),
        (pick(lambda d: d.month in (12, 1, 2) and d.weekday() < 5), "Dia lectiu d'hivern",
         "Dies curts i sol baix: la bateria treballa sobretot amb l'energia de la xarxa."),
        (pick(lambda d: d.month == 8 and d.weekday() < 5), "Agost",
         "Campus a mig gas per vacances, però amb sol d'estiu."),
    ]
    payload_days = [day_payload(g, l, s) for g, l, s in scenarios if g is not None]

    # Balanç anual sobre tots els dies complets
    tot = {"co2Base": 0.0, "co2Opt": 0.0, "costBase": 0.0, "costOpt": 0.0, "solar": 0.0, "demand": 0.0}
    for g in days:
        r = dispatch_day(g)
        tot["co2Base"] += r["co2_base"]; tot["co2Opt"] += r["co2_opt"]
        tot["costBase"] += r["cost_base"]; tot["costOpt"] += r["cost_opt"]
        tot["solar"] += g["pv"].sum(); tot["demand"] += g["demand"].sum()

    # Mitjanes mensuals i mapa de calor hora x mes de la intensitat de carboni
    monthly = df.groupby(df.index.to_period("M")).agg(
        solar=("pv", "sum"), demand=("demand", "sum"), co2=("co2", "mean"), price=("price", "mean"))
    heat = df.groupby([df.index.month, df.index.hour])["co2"].mean().unstack()

    out = {
        "generatedFrom": f"{df.index.min().date()} – {df.index.max().date()}",
        "battery": {"capacityKwh": CAP, "powerKw": PMAX, "efficiency": ETA, "socInit": SPEC["soc_init"]},
        "weights": {"co2": W_CO2, "cost": W_COST},
        "equivalences": {"kgCo2PerKmCar": KG_CO2_PER_KM_COTXE,
                         "kgCo2PerTreeYear": KG_CO2_PER_ARBRE_ANY,
                         "kwhPerPhoneCharge": KWH_PER_MOBIL},
        "days": payload_days,
        "annual": {
            "nDays": len(days),
            "co2SavedKg": round(tot["co2Base"] - tot["co2Opt"]),
            "co2SavedPct": round(100 * (tot["co2Base"] - tot["co2Opt"]) / tot["co2Base"], 2),
            "costSavedEur": round(tot["costBase"] - tot["costOpt"]),
            "costSavedPct": round(100 * (tot["costBase"] - tot["costOpt"]) / tot["costBase"], 2),
            "solarMwh": round(tot["solar"] / 1000, 1),
            "demandMwh": round(tot["demand"] / 1000, 1),
        },
        "monthly": [{"month": str(p), "solarMwh": round(v.solar / 1000, 2),
                     "demandMwh": round(v.demand / 1000, 1),
                     "co2": round(v.co2, 4), "price": round(v.price, 4)}
                    for p, v in monthly.iterrows()],
        "co2Heatmap": {"months": [int(m) for m in heat.index],
                       "values": [[round(float(x), 4) if pd.notna(x) else None for x in row]
                                  for row in heat.to_numpy()]},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False))
    print(f"Escrit {OUT} ({OUT.stat().st_size/1024:.0f} KB) · {len(payload_days)} escenaris · {len(days)} dies")
    print(json.dumps(out["annual"], indent=1))
    for d in payload_days:
        print(d["label"], d["date"], d["totals"])


if __name__ == "__main__":
    main()
