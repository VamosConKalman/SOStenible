"""FastAPI application for the Battery Datathon Challenge."""

from __future__ import annotations

import math
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Add starter_kit and the backend root to the path
_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_BACKEND / "starter_kit"))

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.data_loader import (
    build_hourly,
    build_meteo,
    compute_indices,
    get_day_data,
    get_valid_days,
    is_valid_day,
    scale_for_mode,
)
from app.agent_loader import load_agent_class, load_agent_module, load_parametres
from app.agent_config import DEFAULT_MODE, public_agent_catalog
from app.simulator import (MODE_SPECS, SCENARIO_DEFAULTS, instrument_agent_module, run_agent,
                           run_rolling_horizon, run_user_actions, _evaluate)
from app.models import (
    DayRequest,
    CompareRequest,
    RollingHorizonRequest,
    DayListItem,
    DayResponse,
    ModelDayResponse,
    CompareResponse,
    CompareRequest as CompareReqModel,
    ModelInfoResponse,
    ModelInfoEntry,
    ScoreDetail,
    HourlyCompare,
)

# ---------------------------------------------------------------------------
# Globals — loaded on startup
# ---------------------------------------------------------------------------
df_all: pd.DataFrame | None = None
meteo_all: pd.DataFrame | None = None
valid_days: list[str] = []
day_indices: dict[str, dict[str, Any]] = {}
df_mode: dict[str, pd.DataFrame] = {}      # per-mode hourly data (dificil: solar x12)

model_day_cache: OrderedDict = OrderedDict()  # (date, mode) -> full result dict
MAX_CACHE = 100


def _check_cache(key):
    if key in model_day_cache:
        return model_day_cache[key]
    return None


def _set_cache(key, value):
    model_day_cache[key] = value
    if len(model_day_cache) > MAX_CACHE:
        model_day_cache.pop(list(model_day_cache.keys())[0])


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

app = FastAPI(title="UPC Sostenible 2026 — Battery Challenge")


@app.on_event("startup")
def startup():
    global df_all, meteo_all, valid_days, day_indices
    print("Loading data…")
    df_all = build_hourly()
    print(f"  Hourly data: {len(df_all)} rows, {df_all.index.min()} → {df_all.index.max()}")
    meteo_all = build_meteo()
    print(f"  Meteo data: {len(meteo_all)} rows")
    valid_days = get_valid_days(df_all)
    print(f"  Valid days: {len(valid_days)}")
    day_indices = compute_indices(df_all, valid_days)
    for m in MODE_SPECS:
        df_mode[m] = scale_for_mode(df_all, m)
    print("  Done.")


def _frames(date: str, mode: str):
    """(target day, 48 h heat-up, meteo) for a valid date, with the mode's solar scale.
    Meteo is passed whole: the env looks up t-1 by timestamp, also during the target day."""
    d = pd.Timestamp(date)
    df = df_mode.get(mode)
    if df is None:
        df = scale_for_mode(df_all, mode)
        df_mode[mode] = df
    day_df = get_day_data(df, date)
    df_heat = df.loc[d - pd.Timedelta(hours=48):d - pd.Timedelta(hours=1)]
    if len(df_heat) < 24:
        df_heat = df.loc[d - pd.Timedelta(hours=24):d - pd.Timedelta(hours=1)]
    if len(df_heat) < 24:
        raise HTTPException(400, "Not enough historical data for heatup.")
    meteo = meteo_all if mode == "dificil" else None
    return day_df, df_heat, meteo


def _agent_class(mode: str):
    instrument_agent_module(load_agent_module(mode))
    return load_agent_class(mode)


# ---------------------------------------------------------------------------
# Agent catalog
# ---------------------------------------------------------------------------
@app.get("/api/agents")
def api_agents():
    return public_agent_catalog()


# ---------------------------------------------------------------------------
# 1. GET /api/days
# ---------------------------------------------------------------------------

@app.get("/api/days")
def api_days(
    mode: str = Query(DEFAULT_MODE, description="Enabled agent id from /api/agents"),
    month: int | None = Query(None, ge=1, le=12),
    year: int | None = Query(None, ge=2020, le=2030),
):
    if mode not in MODE_SPECS:
        raise HTTPException(400, f"mode must be 'estandar' or 'dificil', got '{mode}'")

    days = day_indices
    if month:
        days = {k: v for k, v in days.items() if pd.Timestamp(k).month == month}
    if year:
        days = {k: v for k, v in days.items() if pd.Timestamp(k).year == year}

    result = sorted(days.values(), key=lambda x: x["date"])
    return [DayListItem(**d) for d in result]


# ---------------------------------------------------------------------------
# 2. GET /api/day
# ---------------------------------------------------------------------------

@app.get("/api/day")
def api_day(
    date: str = Query(..., description="AAAA-MM-DD"),
    mode: str = Query(DEFAULT_MODE, description="Enabled agent id from /api/agents"),
):
    if mode not in MODE_SPECS:
        raise HTTPException(400, f"mode must be 'estandar' or 'dificil', got '{mode}'")

    # Validate date format
    try:
        d = pd.Timestamp(date)
    except Exception:
        raise HTTPException(400, f"Invalid date format: '{date}'. Use AAAA-MM-DD.")

    if date not in valid_days:
        raise HTTPException(400, f"Date '{date}' is not a valid day. Check /api/days for valid dates.")

    day_df = get_day_data(df_all, date)

    # Apply x12 multiplier for solar in dificil mode
    pv = day_df["pv_kw"].tolist()
    if mode == "dificil":
        pv = [v * 12 for v in pv]

    units = {
        "demand": "kW",
        "solar": "kW" + (" × 12 (dificil)" if mode == "dificil" else ""),
        "price": "€/kWh",
        "co2": "kg CO₂/kWh",
    }

    return DayResponse(
        date=date,
        hours=[f"{h:02d}:00" for h in day_df.index.hour],
        demand=[round(v, 2) for v in day_df["load_kw"]],
        solar=[round(v, 2) for v in pv],
        price=[round(v, 6) for v in day_df["precio_eur_per_kwh"]],
        co2=[round(v, 6) for v in day_df["co2_kg_per_kwh"]],
        units=units,
    )


# ---------------------------------------------------------------------------
# 3. POST /api/model-day
# ---------------------------------------------------------------------------

@app.post("/api/model-day", response_model=ModelDayResponse)
def api_model_day(req: DayRequest):
    if req.mode not in MODE_SPECS:
        raise HTTPException(400, f"mode must be 'estandar' or 'dificil', got '{req.mode}'")

    # Validate date
    try:
        d = pd.Timestamp(req.date)
    except Exception:
        raise HTTPException(400, f"Invalid date format: '{req.date}'. Use AAAA-MM-DD.")

    if req.date not in valid_days:
        raise HTTPException(400, f"Date '{req.date}' is not valid. Check /api/days.")

    result = _get_model_day_result(req.date, req.mode)
    return ModelDayResponse(**{k: result[k] for k in [
        "actions", "power", "soc", "soc_final", "grid",
        "score", "dCO2", "dCost", "infracciones",
    ]})


# ---------------------------------------------------------------------------
# 4. POST /api/compare
# ---------------------------------------------------------------------------

@app.post("/api/compare", response_model=CompareResponse)
def api_compare(req: CompareReqModel):
    if req.mode not in MODE_SPECS:
        raise HTTPException(400, f"mode must be 'estandar' or 'dificil', got '{req.mode}'")

    # Validate date
    try:
        d = pd.Timestamp(req.date)
    except Exception:
        raise HTTPException(400, f"Invalid date format: '{req.date}'. Use AAAA-MM-DD.")

    if req.date not in valid_days:
        raise HTTPException(400, f"Date '{req.date}' is not valid. Check /api/days.")

    # Validate userActions: must be 24 items
    if len(req.userActions) != 24:
        raise HTTPException(400, f"userActions must have exactly 24 items, got {len(req.userActions)}")

    # Get model result (cached or compute)
    model_result = _get_model_day_result(req.date, req.mode)

    day_df, _, _ = _frames(req.date, req.mode)

    # Get the SOC that the model starts the day with (50% of capacity per task spec)
    spec = MODE_SPECS[req.mode]
    soc_init = spec["soc_init"] * spec["capacity_kwh"]

    # Run user actions
    user_result = run_user_actions(req.userActions, day_df, req.mode, soc_override=soc_init)

    # Build hourly comparison
    hourly = []
    diagnosis_parts: list[str] = []

    for i in range(24):
        user_h = user_result["hourly"][i] if i < len(user_result["hourly"]) else {"h": i, "user": "espera", "userKw": 0, "soc": soc_init}
        model_h = model_result["hourly"][i] if i < len(model_result.get("hourly", [])) else {"h": i, "user": "espera", "userKw": 0}

        # Get pts from model result
        model_pts = model_result.get("pts_per_hour", [0] * 24)[i] if i < len(model_result.get("pts_per_hour", [])) else 0
        user_pts = user_result.get("pts_per_hour", [0] * 24)[i] if i < len(user_result.get("pts_per_hour", [])) else 0

        hourly.append(HourlyCompare(
            h=i,
            user=user_h["user"],
            model=model_h["user"],
            userKw=user_h["userKw"],
            modelKw=model_h["userKw"],
            userPts=round(user_pts, 4),
            modelPts=round(model_pts, 4),
        ))

    # Generate diagnosis
    diagnosis_parts = _generate_diagnosis(user_result, model_result, hourly, day_df, req.mode)

    # Build response
    return CompareResponse(
        userScore=user_result["score"],
        modelScore=model_result["score"],
        user=ScoreDetail(
            dCO2=user_result["dCO2"],
            dCost=user_result["dCost"],
            infracciones=user_result["infracciones"],
        ),
        model=ScoreDetail(
            dCO2=model_result["dCO2"],
            dCost=model_result["dCost"],
            infracciones=model_result["infracciones"],
        ),
        hourly=hourly,
        diagnosis=diagnosis_parts,
    )


def _get_model_day_result(date: str, mode: str) -> dict:
    """Get or compute model day result (returns full dict with hourly details)."""
    cache_key = (date, mode)
    cached = _check_cache(cache_key)
    if cached is not None:
        return cached

    day_df, df_heat, meteo = _frames(date, mode)
    result = run_agent(_agent_class(mode), day_df, df_heat, mode, meteo)
    _set_cache(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# 5. GET /api/model-info
# ---------------------------------------------------------------------------

@app.get("/api/model-info", response_model=ModelInfoResponse)
def api_model_info():
    estandar_params = load_parametres("estandar")
    dificil_params = load_parametres("dificil")

    return ModelInfoResponse(
        estandar=ModelInfoEntry(
            zip="envio4_sin_finmes_ni_V.zip",
            score_servidor=6.43,
            descripcion="MPC 24 h: LP (HiGHS) amb pesos 0,7·CO₂ + 0,3·κ·preu i càrrega neta de persistència.",
            parametres=estandar_params,
        ),
        dificil=ModelInfoEntry(
            zip="dificil_LASSO_online_solar_05.zip",
            score_servidor=22.94,
            descripcion="MPC 24 h + previsions LASSO per horitzó + correcció solar online (z_net 0,5).",
            parametres=dificil_params,
        ),
    )


# ---------------------------------------------------------------------------
# 6. POST /api/rolling-horizon  — solver plans hour by hour + scenario generator
# ---------------------------------------------------------------------------

@app.post("/api/rolling-horizon")
def api_rolling_horizon(req: RollingHorizonRequest):
    """Runs the agent on a (perturbed) day and returns, for every hour t, the LP plan
    the solver made at t (forecast net load, weights, planned charge/discharge and SOC
    over its horizon), the executed trajectory, the real-day baseline, the
    perfect-information reference and an ensemble of `nSamples` scenarios."""
    if req.date not in valid_days:
        raise HTTPException(400, f"Date '{req.date}' is not valid. Check /api/days.")
    day_df, df_heat, meteo = _frames(req.date, req.mode)
    scenario = {k: v for k, v in req.scenario.model_dump().items() if v is not None}
    return run_rolling_horizon(_agent_class(req.mode), day_df, df_heat, req.mode, meteo,
                               scenario=scenario, n_samples=req.nSamples,
                               active_seed=req.activeSeed)


@app.get("/api/scenario-defaults")
def api_scenario_defaults():
    return SCENARIO_DEFAULTS


# ---------------------------------------------------------------------------
# Helpers for diagnosis
# ---------------------------------------------------------------------------

def _generate_diagnosis(user_result: dict, model_result: dict, hourly: list[HourlyCompare], day_df: pd.DataFrame, mode: str) -> list[str]:
    """Generate 2-4 diagnosis sentences based on rules."""
    tips: list[dict] = []

    hours = [f"{h:02d}:00" for h in day_df.index.hour]
    prices = day_df["precio_eur_per_kwh"].values
    co2_vals = day_df["co2_kg_per_kwh"].values

    E_b = model_result.get("co2_base", 1.0)
    C_b = model_result.get("cost_base", 1.0)

    for i in range(24):
        h = hourly[i]
        user_kw = h.userKw
        model_kw = h.modelKw

        # User discharged when model didn't (and model would have been better)
        if user_kw < -1 and model_kw >= 0:
            # Check if user discharged with excess solar (export)
            if i < len(day_df):
                load = day_df["load_kw"].iloc[i]
                pv = day_df["pv_kw"].iloc[i]
                net = load - pv + user_kw
                if net < 0:  # Exported energy
                    tips.append({"gain": abs(user_kw), "text":
                        f"Has exportat energia a les {hours[i]}: la bateria ha descarregat "
                        f"{abs(user_kw):.0f} kW però la demanda només era {load:.0f} kW "
                        f"(solar {pv:.0f} kW). L'energia sobrant s'ha venut a la xarxa."})

        # User charged when model discharged (missed a good discharge hour)
        if user_kw > 1 and model_kw < -1:
            tips.append({"gain": abs(h.userPts - h.modelPts), "text":
                f"Has carregat a les {hours[i]} ({co2_vals[i]*1000:.0f} g CO₂/kWh, {prices[i]*100:.1f} c€/kWh) "
                f"quan el model descarregava i hauria aprofitat millor la bateria."})

        # User charged in expensive hours
        if user_kw > 1 and h.modelPts > h.userPts:
            # Check if this is a high-price hour
            if prices[i] > np.mean(prices) * 1.2:
                tips.append({"gain": abs(h.userPts - h.modelPts), "text":
                    f"Has carregat a les {hours[i]} a {prices[i]*100:.1f} c€/kWh, "
                    f"una hora cara. El model carrega en hores més barates."})

    # User ended with empty battery
    if user_result["soc_final"] < MODE_SPECS[mode]["capacity_kwh"] * 0.2:
        tips.append({"gain": 5, "text":
            f"Has acabat el dia amb la bateria al {user_result['soc_final']/MODE_SPECS[mode]['capacity_kwh']*100:.0f}% "
            f"({user_result['soc_final']:.0f} kWh). Has acabat la bateria i no l'has pogut usar per a hores posteriors."})

    # User ended with full battery
    if user_result["soc_final"] > MODE_SPECS[mode]["capacity_kwh"] * 0.85:
        tips.append({"gain": 5, "text":
            f"Has acabat el dia amb la bateria gairebé plena "
            f"({user_result['soc_final']:.0f} kWh, {user_result['soc_final']/MODE_SPECS[mode]['capacity_kwh']*100:.0f}%). "
            f"Aquesta energia carregada i no utilitzada només ha suposat pèrdues."})

    # Top hours where user diverged most from model
    diffs = [(abs(h.userPts - h.modelPts), i) for i, h in enumerate(hourly)]
    diffs.sort(reverse=True)
    top_mismatch = [d for d in diffs if d[0] > 0.5][:3]
    for gain, i in top_mismatch:
        if not any(f"les {hours[i]}" in t["text"] for t in tips):
            h = hourly[i]
            tips.append({"gain": gain, "text":
                f"A les {hours[i]} la diferència és màxima: tu {'carregaves' if h.userKw > 1 else 'descarregaves' if h.userKw < -1 else 'esperaves'}, "
                f"el model {'descarregava' if h.modelKw < -1 else 'carregava' if h.modelKw > 1 else 'esperava'}. "
                f"Punts: {h.userPts:.1f} vs {h.modelPts:.1f}."})

    if not tips:
        return ["Les teves decisions són similars al model: no hi ha desviacions significatives."]

    tips.sort(key=lambda t: t["gain"], reverse=True)
    return [t["text"] for t in tips[:4]]


# ---------------------------------------------------------------------------
_FRONTEND_DIST = _BACKEND.parent / "frontend" / "dist"
if _FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")


# Run with: uvicorn app.main:app --reload
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)