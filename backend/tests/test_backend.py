"""Tests for the Battery Datathon Challenge backend."""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_BACKEND / "starter_kit"))

from app.data_loader import build_hourly, get_valid_days, get_day_data
from app.simulator import MODE_SPECS, run_agent, run_user_actions, make_env
from app.agent_loader import load_agent_class


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def df_all():
    return build_hourly()


@pytest.fixture()
def valid_days(df_all):
    return get_valid_days(df_all)


@pytest.fixture()
def day_df(valid_days):
    """A known valid day for testing."""
    # Pick the first valid day
    day_str = valid_days[0] if valid_days else "2026-03-10"
    return get_day_data(
        build_hourly(), day_str
    )


@pytest.fixture()
def day_date(valid_days):
    if valid_days:
        return valid_days[0]
    return "2026-03-10"


# ---------------------------------------------------------------------------
# Test (a): model score matches official simulator with those actions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode", ["estandar", "dificil"])
def test_model_score_matches_simulator(mode, day_df, day_date, valid_days):
    """(a) The model's score on a day matches the simulator's evaluation with the same actions."""
    AgentClass = load_agent_class(mode)

    # Run heatup (48h before target)
    d = pd.Timestamp(day_date)
    heat_start = d - pd.Timedelta(hours=48)
    heat_end = d - pd.Timedelta(hours=1)
    df_heat = build_hourly().loc[heat_start:heat_end]
    if len(df_heat) < 24:
        heat_start = d - pd.Timedelta(hours=24)
        heat_end = d - pd.Timedelta(hours=1)
        df_heat = build_hourly().loc[heat_start:heat_end]

    # Build meteo for dificil
    meteo = None
    if mode == "dificil":
        meteo_path = _BACKEND.parent / "data" / "train" / "meteo.csv"
        if meteo_path.exists():
            m = pd.read_csv(meteo_path, parse_dates=["Fecha"]).set_index("Fecha")
            irr_col = [c for c in m.columns if "IRRADIANCIA" in c or "IRRADIANCE" in c.upper()]
            temp_a_col = [c for c in m.columns if "TEMPERATURA AMBIENTE" in c or "TEMP_AMBIENT" in c.upper()]
            temp_p_col = [c for c in m.columns if "TEMPERATURA PANEL" in c or "TEMP_PANEL" in c.upper()]
            vent_col = [c for c in m.columns if "VIENTO" in c or "WIND" in c.upper()]
            if irr_col and temp_a_col and temp_p_col and vent_col:
                meteo = pd.DataFrame({
                    "irradiancia_wm2": m[irr_col[0]],
                    "temp_ambient_c": m[temp_a_col[0]],
                    "temp_panel_c": m[temp_p_col[0]],
                    "vent_ms": m[vent_col[0]],
                })

    # Run agent
    result = run_agent(AgentClass, day_df, df_heat, mode, meteo=meteo)

    # Verify: the actions and soc_series should produce the same score when re-evaluated
    env = make_env(day_df, mode)
    spec = MODE_SPECS[mode]
    env.soc = spec["soc_init"] * spec["capacity_kwh"]
    obs = env.reset()
    for kw in result["power"]:
        obs, done = env.step(kw)

    # Evaluate
    grid = np.asarray(env.grid)
    price = day_df["precio_eur_per_kwh"].values[:len(grid)]
    co2 = day_df["co2_kg_per_kwh"].values[:len(grid)]
    load = day_df["load_kw"].values[:len(grid)]
    pv = day_df["pv_kw"].values[:len(grid)]
    base_grid = np.maximum(load - pv, 0.0)

    cost_p = float(np.sum(grid * price))
    co2_p = float(np.sum(grid * co2))
    cost_b = float(np.sum(base_grid * price))
    co2_b = float(np.sum(base_grid * co2))
    d_co2 = (co2_b - co2_p) / co2_b if co2_b > 0 else 0.0
    d_cost = (cost_b - cost_p) / cost_b if cost_b > 0 else 0.0
    expected_score = 100.0 * (0.7 * d_co2 + 0.3 * d_cost) - env.clipped - env.violations

    assert abs(result["score"] - expected_score) < 0.01, \
        f"Score mismatch: got {result['score']}, expected {expected_score}"


# ---------------------------------------------------------------------------
# Test (b): sum of hourly pts matches score without infraccions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode", ["estandar", "dificil"])
def test_hourly_pts_sum_matches_score(mode, day_df, day_date, valid_days):
    """(b) The sum of per-hour points equals the score without infraccions."""
    AgentClass = load_agent_class(mode)

    d = pd.Timestamp(day_date)
    heat_start = d - pd.Timedelta(hours=48)
    heat_end = d - pd.Timedelta(hours=1)
    df_heat = build_hourly().loc[heat_start:heat_end]
    if len(df_heat) < 24:
        df_heat = build_hourly().loc[d - pd.Timedelta(hours=24):d - pd.Timedelta(hours=1)]

    meteo = None
    if mode == "dificil":
        meteo_path = _BACKEND.parent / "data" / "train" / "meteo.csv"
        if meteo_path.exists():
            m = pd.read_csv(meteo_path, parse_dates=["Fecha"]).set_index("Fecha")
            irr_col = [c for c in m.columns if "IRRADIANCIA" in c or "IRRADIANCE" in c.upper()]
            temp_a_col = [c for c in m.columns if "TEMPERATURA AMBIENTE" in c or "TEMP_AMBIENT" in c.upper()]
            temp_p_col = [c for c in m.columns if "TEMPERATURA PANEL" in c or "TEMP_PANEL" in c.upper()]
            vent_col = [c for c in m.columns if "VIENTO" in c or "WIND" in c.upper()]
            if irr_col and temp_a_col and temp_p_col and vent_col:
                meteo = pd.DataFrame({
                    "irradiancia_wm2": m[irr_col[0]],
                    "temp_ambient_c": m[temp_a_col[0]],
                    "temp_panel_c": m[temp_p_col[0]],
                    "vent_ms": m[vent_col[0]],
                })

    result = run_agent(AgentClass, day_df, df_heat, mode, meteo=meteo)

    # Sum of pts_per_hour (without infraccions)
    pts_sum = sum(result["pts_per_hour"])

    # Score without infraccions (dCO2 and dCost are already in %)
    score_no_infr = 0.7 * result["dCO2"] + 0.3 * result["dCost"]

    assert abs(pts_sum - score_no_infr) < 0.1, \
        f"pts_per_hour sum {pts_sum} != score-no-infr {score_no_infr}"


# ---------------------------------------------------------------------------
# Test (c): all "espera" → score 0
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode", ["estandar", "dificil"])
def test_all_espera_gives_zero_score(day_df, mode):
    """(c) userActions all 'espera' → score = 0 (or very close, depending on physics).

    If the user never touches the battery, grid = max(0, load - pv) = baseline,
    so dCO2 = 0, dCost = 0, and score = 0 - infraccions.
    There should be no infraccions since no action = no violation.
    """
    user_actions = ["espera"] * 24
    result = run_user_actions(user_actions, day_df, mode)

    # Score should be 0 or very close (within rounding)
    # Actually, if the user does nothing, grid might differ slightly from baseline
    # if solar is 0 at night and load > 0... no, grid_base = max(0, load-pv) = load when pv=0
    # and grid = load - 0 + 0 = load. So they match.
    assert abs(result["score"]) < 1.0, \
        f"Score for all 'espera' should be ~0, got {result['score']}"


# ---------------------------------------------------------------------------
# Test (d): estandar and dificil give different and reproducible results
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode", ["estandar", "dificil"])
def test_agent_reproducible(mode, day_df, day_date, valid_days):
    """(d) Same agent run twice → same result (reproducibility)."""
    AgentClass = load_agent_class(mode)

    d = pd.Timestamp(day_date)
    heat_start = d - pd.Timedelta(hours=48)
    heat_end = d - pd.Timedelta(hours=1)
    df_heat = build_hourly().loc[heat_start:heat_end]
    if len(df_heat) < 24:
        df_heat = build_hourly().loc[d - pd.Timedelta(hours=24):d - pd.Timedelta(hours=1)]

    meteo = None
    if mode == "dificil":
        meteo_path = _BACKEND.parent / "data" / "train" / "meteo.csv"
        if meteo_path.exists():
            m = pd.read_csv(meteo_path, parse_dates=["Fecha"]).set_index("Fecha")
            irr_col = [c for c in m.columns if "IRRADIANCIA" in c or "IRRADIANCE" in c.upper()]
            temp_a_col = [c for c in m.columns if "TEMPERATURA AMBIENTE" in c or "TEMP_AMBIENT" in c.upper()]
            temp_p_col = [c for c in m.columns if "TEMPERATURA PANEL" in c or "TEMP_PANEL" in c.upper()]
            vent_col = [c for c in m.columns if "VIENTO" in c or "WIND" in c.upper()]
            if irr_col and temp_a_col and temp_p_col and vent_col:
                meteo = pd.DataFrame({
                    "irradiancia_wm2": m[irr_col[0]],
                    "temp_ambient_c": m[temp_a_col[0]],
                    "temp_panel_c": m[temp_p_col[0]],
                    "vent_ms": m[vent_col[0]],
                })

    r1 = run_agent(AgentClass, day_df, df_heat, mode, meteo=meteo)
    r2 = run_agent(AgentClass, day_df, df_heat, mode, meteo=meteo)

    assert r1["score"] == r2["score"], f"Reproducibility failed for {mode}: {r1['score']} != {r2['score']}"
    assert r1["actions"] == r2["actions"], f"Actions not reproducible for {mode}"


def test_modes_different(day_df, day_date, valid_days):
    """(d) estandar and dificil must give different results on the same day."""
    if not valid_days:
        pytest.skip("No valid days available")

    AgentClass_e = load_agent_class("estandar")
    AgentClass_d = load_agent_class("dificil")

    d = pd.Timestamp(day_date)
    heat_start = d - pd.Timedelta(hours=48)
    heat_end = d - pd.Timedelta(hours=1)
    df_heat = build_hourly().loc[heat_start:heat_end]
    if len(df_heat) < 24:
        df_heat = build_hourly().loc[d - pd.Timedelta(hours=24):d - pd.Timedelta(hours=1)]

    meteo = None
    meteo_path = _BACKEND.parent / "data" / "train" / "meteo.csv"
    if meteo_path.exists():
        m = pd.read_csv(meteo_path, parse_dates=["Fecha"]).set_index("Fecha")
        irr_col = [c for c in m.columns if "IRRADIANCIA" in c or "IRRADIANCE" in c.upper()]
        temp_a_col = [c for c in m.columns if "TEMPERATURA AMBIENTE" in c or "TEMP_AMBIENT" in c.upper()]
        temp_p_col = [c for c in m.columns if "TEMPERATURA PANEL" in c or "TEMP_PANEL" in c.upper()]
        vent_col = [c for c in m.columns if "VIENTO" in c or "WIND" in c.upper()]
        if irr_col and temp_a_col and temp_p_col and vent_col:
            meteo = pd.DataFrame({
                "irradiancia_wm2": m[irr_col[0]],
                "temp_ambient_c": m[temp_a_col[0]],
                "temp_panel_c": m[temp_p_col[0]],
                "vent_ms": m[vent_col[0]],
            })

    r_e = run_agent(AgentClass_e, day_df, df_heat, "estandar", meteo=None)
    r_d = run_agent(AgentClass_d, day_df, df_heat, "dificil", meteo=meteo)

    assert r_e["score"] != r_d["score"], \
        f"Modes should differ: estandar={r_e['score']}, dificil={r_d['score']}"


# ---------------------------------------------------------------------------
# Test (e): impossible action clipped and counts 1 infringement
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode", ["estandar", "dificil"])
def test_impossible_action_clip_and_infringe(day_df, mode):
    """(e) Discharging with empty battery is clipped and counts 1 infringement."""
    # Create actions: first try to discharge 10000 kW (way more than battery can provide)
    # with SOC near 0
    user_actions = ["descarga"] * 24
    spec = MODE_SPECS[mode]
    result = run_user_actions(user_actions, day_df, mode, soc_override=0.0)

    # There should be infringements because we try to discharge more than SOC allows
    assert result["infracciones"] > 0, \
        f"Expected infringements when discharging from empty battery, got {result['infracciones']}"

    # The power should be clipped to what the battery can actually provide
    # (either 0 if SOC is truly 0, or some positive amount)
    for pw in result["power"]:
        if pw < 0:
            max_d = spec["power_kw"]
            assert abs(pw) <= max_d + 0.01, f"Power {pw} exceeds max discharge {max_d}"


# ---------------------------------------------------------------------------
# Additional utility tests
# ---------------------------------------------------------------------------

def test_data_loaded(df_all):
    """Verify data loaded correctly."""
    assert len(df_all) > 0
    assert "load_kw" in df_all.columns
    assert "pv_kw" in df_all.columns
    assert "precio_eur_per_kwh" in df_all.columns
    assert "co2_kg_per_kwh" in df_all.columns


def test_valid_days_exist(valid_days):
    """There should be valid days."""
    assert len(valid_days) > 0


def test_mode_specs():
    """Mode specs match task requirements."""
    assert MODE_SPECS["estandar"]["capacity_kwh"] == 2000
    assert MODE_SPECS["estandar"]["power_kw"] == 500
    assert MODE_SPECS["dificil"]["capacity_kwh"] == 6000
    assert MODE_SPECS["dificil"]["power_kw"] == 1500
    assert MODE_SPECS["estandar"]["efficiency"] == 0.9
    assert MODE_SPECS["dificil"]["efficiency"] == 0.9

# ---------------------------------------------------------------------------
# Rolling horizon + scenario generator
# ---------------------------------------------------------------------------

def test_rolling_horizon_endpoint():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        d = c.get("/api/days").json()[50]["date"]
        r = c.post("/api/rolling-horizon", json={"date": d, "mode": "dificil", "nSamples": 4})
        assert r.status_code == 200
        j = r.json()
        assert len(j["steps"]) == 24 and len(j["active"]["socPath"]) == 25
        assert len(j["ensemble"]) == 1                      # no noise -> one scenario
        assert j["active"]["score"] == j["baseline"]["score"]
        assert j["active"]["oracle"] >= j["active"]["score"] - 1e-6
        st = j["steps"][6]
        assert st["H"] > 0 and len(st["soc"]) == st["H"] + 1 and abs(st["soc"][0] - st["soc0"]) < 1
        r2 = c.post("/api/rolling-horizon", json={"date": d, "mode": "dificil", "nSamples": 4,
                                                   "scenario": {"demand_noise": 0.2, "cloud_hours": 3}})
        j2 = r2.json()
        assert len(j2["ensemble"]) == 4 and j2["stochastic"]
        r3 = c.post("/api/rolling-horizon", json={"date": d, "mode": "dificil", "nSamples": 4, "activeSeed": 2,
                                                   "scenario": {"demand_noise": 0.2, "cloud_hours": 3}})
        j3 = r3.json()
        assert j3["activeSeed"] == 2
        assert abs(j3["active"]["score"] - [e for e in j2["ensemble"] if e["seed"] == 2][0]["score"]) < 1e-6


def test_perturb_cut_and_agent_isolation(df_all, valid_days):
    from app.simulator import perturb_day
    from app.agent_loader import load_agent_class
    day = get_day_data(df_all, valid_days[10])
    p, _ = perturb_day(day, {"cut_start": 5, "cut_hours": 2})
    assert (p["load_kw"].iloc[5:7] == 0).all() and (p["pv_kw"].iloc[5:7] == 0).all()
    A, B = load_agent_class("dificil"), load_agent_class("estandar")
    import sys
    assert sys.modules[A.__module__].lp is not sys.modules[B.__module__].lp
    assert hasattr(sys.modules[A.__module__].lp, "solve_lp_stoch") or hasattr(getattr(sys.modules[A.__module__].lp, "_real", None), "solve_lp_stoch")
