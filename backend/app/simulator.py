"""Simulation logic: runs an agent or user actions through the CampusBatteryEnv."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Add starter_kit directory to sys.path BEFORE any other imports
_KIT_DIR = str(Path(__file__).resolve().parents[2] / "starter_kit")
if _KIT_DIR not in sys.path:
    sys.path.insert(0, _KIT_DIR)

from environment import CampusBatteryEnv

ROOT = Path(__file__).resolve().parents[2]  # Go up to backend/, then to repo root
with open(ROOT / "starter_kit" / "battery_spec.json") as f:
    _DEFAULT_SPEC = json.load(f)

# Battery specs for each mode
MODE_SPECS = {
    "estandar": {
        "capacity_kwh": 2000,
        "power_kw": 500,
        "efficiency": 0.9,
        "soc_init": 0.5,
        "soc_min": 0,
        "soc_max": 1,
        "dt_hours": 1,
        "forecast_horizon": 24,
    },
    "dificil": {
        "capacity_kwh": 6000,
        "power_kw": 1500,
        "efficiency": 0.9,
        "soc_init": 0.5,
        "soc_min": 0,
        "soc_max": 1,
        "dt_hours": 1,
        "forecast_horizon": 3,
    },
}


class DificilEnv(CampusBatteryEnv):
    """CampusBatteryEnv customized for the dificil mode:
    - 3h forecast instead of 24h
    - meteo data in noves_dades_5min
    - cap_max_kwh and power_max_kw in obs
    """

    def __init__(self, df: pd.DataFrame, spec: dict, meteo: pd.DataFrame | None = None):
        self._meteo = meteo if meteo is not None and not meteo.empty else None
        super().__init__(df, spec=spec)

    def _get_obs(self):
        if self.t >= self.n:
            return None
        row = self.df.iloc[self.t]
        ts = row["Fecha"]

        # Only 3 hours of forecast
        h_end = min(self.t + 3, self.n)
        future_prices = self.df["precio_eur_per_kwh"].iloc[self.t:h_end].values.tolist()
        future_co2 = self.df["co2_kg_per_kwh"].iloc[self.t:h_end].values.tolist()

        last_load = float(self.df["load_kw"].iloc[self.t - 1]) if self.t > 0 else float(row["load_kw"])
        last_pv = float(self.df["pv_kw"].iloc[self.t - 1]) if self.t > 0 else float(row["pv_kw"])

        # Get meteo for t-1
        meteo_data = {}
        if self._meteo is not None and self.t > 0:
            ts_prev = self.df.iloc[self.t - 1]["Fecha"]
            if ts_prev in self._meteo.index:
                mrow = self._meteo.loc[ts_prev]
                for col in ("irradiancia_wm2", "temp_ambient_c", "temp_panel_c", "vent_ms"):
                    val = mrow.get(col)
                    if pd.notna(val):
                        meteo_data[col] = float(val)

        obs = {
            "timestamp": ts,
            "hour": ts.hour,
            "day_of_week": ts.dayofweek,
            "soc_kwh": float(self.soc),
            "soc_pct": float(self.soc / self.cap),
            "soc_percent": float(self.soc / self.cap * 100),
            "preu_actual": float(row["precio_eur_per_kwh"]),
            "co2_actual": float(row["co2_kg_per_kwh"]),
            "preus_properes_24h": future_prices,
            "co2_properes_24h": future_co2,
            "noves_dades_5min": {
                "ultim_consum_kw": last_load,
                "ultima_solar_kw": last_pv,
                **meteo_data,
            },
            "cap_max_kwh": float(self.cap),
            "power_max_kw": float(self.power),
        }
        return obs


def make_env(df: pd.DataFrame, mode: str, meteo: pd.DataFrame | None = None) -> CampusBatteryEnv:
    """Create a CampusBatteryEnv for the given mode."""
    spec = MODE_SPECS[mode].copy()
    if mode == "dificil":
        return DificilEnv(df, spec=spec, meteo=meteo)
    else:
        return CampusBatteryEnv(df, spec=spec)


def run_agent(agent_class, df_day: pd.DataFrame, df_heat: pd.DataFrame, mode: str, meteo: pd.DataFrame | None = None) -> dict:
    """Run a BatteryAgent on a full 24h day.

    The agent is instantiated ONCE. Heatup runs on df_heat (48h or 24h before target),
    building the agent's memory. Then a fresh env is created for the target day with SOC=50%,
    and the agent continues.

    Returns dict with all results including hourly details.
    """
    spec = MODE_SPECS[mode].copy()
    cap = spec["capacity_kwh"]

    # Create agent instance
    agent = agent_class()

    # Phase 1: Heatup — run the agent through the heatup period with a dummy env
    # This builds the agent's internal memory (preus, co2, meas, perfiles, etc.)
    heat_env = make_env(df_heat, mode, meteo=meteo)
    heat_env.soc = spec["soc_init"] * cap
    heat_obs = heat_env.reset()
    while heat_obs is not None:
        agent.act(heat_obs)
        heat_obs, done = heat_env.step(0.0)  # dummy action, just advance
        if done:
            break

    # Phase 2: Target day — same agent, fresh env with SOC=50%
    target_env = make_env(df_day, mode, meteo=meteo)
    target_env.soc = spec["soc_init"] * cap  # Override SOC to 50%

    obs = target_env.reset()
    while obs is not None:
        action = agent.act(obs)
        obs, done = target_env.step(action)

    result = _evaluate(target_env, df_day, mode)
    result["hourly"] = [
        {"h": h, "user": a, "userKw": p}
        for h, (a, p) in enumerate(zip(result["actions"], result["power"]))
    ]
    return result


def run_user_actions(actions_raw: list, df_day: pd.DataFrame, mode: str,
                     soc_override: float | None = None, meteo: pd.DataFrame | None = None) -> dict:
    """Simulate user actions through the environment.

    Args:
        actions_raw: list of 24 values - either numbers in kW (with sign) or "carga"/"descarga"/"espera" strings.
        df_day: 24h DataFrame for the target day.
        mode: "estandar" or "dificil".
        soc_override: If provided, set SOC at start to this value.
        meteo: Optional meteo DataFrame.

    Returns:
        dict similar to run_agent result but with user actions.
    """
    spec = MODE_SPECS[mode].copy()
    cap = spec["capacity_kwh"]
    pmax = spec["power_kw"]

    env = make_env(df_day, mode, meteo=meteo)
    if soc_override is not None:
        env.soc = soc_override
    elif env.spec["soc_init"] is not None:
        env.soc = env.spec["soc_init"] * cap

    hourly = []
    obs = env.reset()
    action_idx = 0
    while obs is not None and action_idx < 24:
        raw = actions_raw[action_idx] if action_idx < len(actions_raw) else "espera"

        if isinstance(raw, (int, float)):
            action_kw = float(raw)
        elif raw == "carga":
            action_kw = pmax
        elif raw == "descarga":
            action_kw = -pmax
        elif raw == "espera":
            action_kw = 0.0
        else:
            action_kw = 0.0

        new_obs, done = env.step(action_kw)

        h_idx = env.t - 1
        action_str = "carga" if action_kw > 1 else ("descarga" if action_kw < -1 else "espera")

        hourly.append({
            "h": h_idx,
            "user": action_str,
            "userKw": round(action_kw, 2),
            "soc": round(env.soc_series[h_idx] if h_idx < len(env.soc_series) else env.soc, 2),
        })

        obs = new_obs
        action_idx += 1

    result = _evaluate(env, df_day, mode)
    result["hourly"] = hourly
    return result


def _evaluate(env: CampusBatteryEnv, df_day: pd.DataFrame, mode: str) -> dict:
    """Evaluate results using the official scoring formula (from the task spec)."""
    grid = np.asarray(env.grid)
    price = df_day["precio_eur_per_kwh"].values[:len(grid)]
    co2 = df_day["co2_kg_per_kwh"].values[:len(grid)]
    load = df_day["load_kw"].values[:len(grid)]
    pv = df_day["pv_kw"].values[:len(grid)]

    # Baseline sin batería: grid_base = max(0, load - pv)
    base_grid = np.maximum(load - pv, 0.0)

    cost_participant = float(np.sum(grid * price))
    co2_participant = float(np.sum(grid * co2))
    cost_base = float(np.sum(base_grid * price))
    co2_base = float(np.sum(base_grid * co2))

    d_co2 = (co2_base - co2_participant) / co2_base if co2_base > 0 else 0.0
    d_cost = (cost_base - cost_participant) / cost_base if cost_base > 0 else 0.0

    # Infractions
    infraccions = int(env.clipped + env.violations)

    # Score: NOT clamped to 0 (user sees if they do worse than no battery)
    # score = 100 * (0.7 * dCO2 + 0.3 * dCost) - infraccions
    score = 100.0 * (0.7 * d_co2 + 0.3 * d_cost) - infraccions

    # Per-hour points: pts_h = 100 * (0.7 * co2_h/E_b + 0.3 * price_h/C_b) * (red_base_h - red_h)
    E_b = co2_base
    C_b = cost_base
    pts_per_hour = []
    for h in range(len(grid)):
        ptsh = 100.0 * (0.7 * co2[h] / E_b + 0.3 * price[h] / C_b) * (base_grid[h] - grid[h])
        pts_per_hour.append(round(ptsh, 4))

    # Per-hour soc values
    soc_list = [round(s, 2) for s in env.soc_series]
    soc_final = soc_list[-1] if soc_list else env.soc

    # Convert actions to string labels
    actions_str = []
    for a in env.actions:
        if isinstance(a, str):
            actions_str.append(a)
        elif a > 1:
            actions_str.append("carga")
        elif a < -1:
            actions_str.append("descarga")
        else:
            actions_str.append("espera")

    return {
        "actions": actions_str,
        "power": [round(a, 2) for a in env.actions],
        "soc": soc_list,
        "soc_final": round(soc_final, 2),
        "grid": [round(g, 2) for g in env.grid],
        "score": round(score, 2),
        "dCO2": round(d_co2 * 100, 2),
        "dCost": round(d_cost * 100, 2),
        "infracciones": infraccions,
        "pts_per_hour": pts_per_hour,
        "co2_base": E_b,
        "cost_base": C_b,
    }

# ===========================================================================
# Rolling horizon: what the solver plans at every hour + scenario generator
# ===========================================================================

import copy
import importlib.util as _ilu
import math as _math
import threading as _threading

_tl = _threading.local()          # per-request recording buffer (FastAPI runs sync endpoints in threads)

# Generic LP (any capacity / power) used for the perfect-information reference
_spec_oracle = _ilu.spec_from_file_location("_oracle_lp", ROOT / "agents" / "dificil" / "lp_model.py")
_oracle_lp = _ilu.module_from_spec(_spec_oracle)
_spec_oracle.loader.exec_module(_oracle_lp)


class _RecordingLP:
    """Stands in for the agent's `lp` module: same functions, but every solve_lp call
    (inputs and solution) is stored in the thread-local buffer."""

    def __init__(self, real):
        self._real = real

    def __getattr__(self, name):
        return getattr(self._real, name)

    def solve_lp(self, w, s0, V=0.0, net=None, *args, **kwargs):
        x = self._real.solve_lp(w, s0, V, net, *args, **kwargs)
        buf = getattr(_tl, "calls", None)
        if buf is not None:
            xx = getattr(x, "x", x)
            buf.append({"w": np.asarray(w, dtype=float).copy(), "s0": float(s0), "V": float(V),
                        "net": None if net is None else np.asarray(net, dtype=float).copy(),
                        "x": None if xx is None else np.asarray(xx, dtype=float).copy()})
        return x


def instrument_agent_module(mod):
    """Install the recorder in an agent module once (idempotent)."""
    if getattr(mod, "_rh_instrumented", False):
        return
    if hasattr(mod, "lp") and not isinstance(mod.lp, _RecordingLP):
        mod.lp = _RecordingLP(mod.lp)
    cls = getattr(mod, "BatteryAgent", None)
    if cls is not None and hasattr(cls, "_forecast_lasso"):
        orig = cls._forecast_lasso

        def _fl(self, *a, **k):
            out = orig(self, *a, **k)
            buf = getattr(_tl, "fc", None)
            if buf is not None:
                buf.append(tuple(np.asarray(v, dtype=float).copy() for v in out))
            return out
        cls._forecast_lasso = _fl
    mod._rh_instrumented = True


# ---------------------------------------------------------------------------
# Scenario generator
# ---------------------------------------------------------------------------

SCENARIO_DEFAULTS = {
    "demand_scale": 1.0,    # × consum
    "demand_noise": 0.0,    # σ relativa del soroll AR(1) del consum
    "solar_scale": 1.0,     # × solar
    "solar_noise": 0.0,     # σ relativa del soroll AR(1) de la solar
    "price_scale": 1.0,
    "price_noise": 0.0,
    "co2_scale": 1.0,
    "co2_noise": 0.0,
    "persistence": 0.7,     # φ del AR(1): 0 = soroll blanc, 0.95 = errors que duren hores
    "cloud_start": 12, "cloud_hours": 0, "cloud_depth": 0.8,   # núvol: −depth de solar
    "shock_start": 18, "shock_hours": 0, "shock_kw": 300.0,    # pic de demanda inesperat
    "cut_start": 10, "cut_hours": 0,                           # tall de dades (load = pv = 0)
    "seed": 0,
}


def _ar1(rng, n, sigma, phi):
    if sigma <= 0:
        return np.zeros(n)
    e = np.zeros(n)
    z = rng.standard_normal(n)
    e[0] = z[0]
    for i in range(1, n):
        e[i] = phi * e[i - 1] + _math.sqrt(max(0.0, 1 - phi * phi)) * z[i]
    return sigma * e


def _window(n, start, hours):
    m = np.zeros(n, dtype=bool)
    if hours > 0:
        m[int(start):int(start) + int(hours)] = True
    return m


def perturb_day(df_day: pd.DataFrame, params: dict, seed: int | None = None):
    """Return (perturbed df_day, solar factor per hour). Only the target day is altered:
    the agent's memory (heat-up) is the real history, so a perturbation is a surprise for it."""
    p = {**SCENARIO_DEFAULTS, **(params or {})}
    rng = np.random.default_rng(int(p["seed"] if seed is None else seed))
    n = len(df_day)
    phi = float(np.clip(p["persistence"], 0.0, 0.99))
    out = df_day.copy()

    e_l = _ar1(rng, n, float(p["demand_noise"]), phi)
    e_s = _ar1(rng, n, float(p["solar_noise"]), phi)
    e_p = _ar1(rng, n, float(p["price_noise"]), phi)
    e_c = _ar1(rng, n, float(p["co2_noise"]), phi)

    cloud = np.where(_window(n, p["cloud_start"], p["cloud_hours"]), 1.0 - float(p["cloud_depth"]), 1.0)
    solar_factor = np.clip(float(p["solar_scale"]) * (1 + e_s) * cloud, 0.0, None)
    shock = np.where(_window(n, p["shock_start"], p["shock_hours"]), float(p["shock_kw"]), 0.0)

    out["load_kw"] = np.clip(out["load_kw"].to_numpy() * float(p["demand_scale"]) * (1 + e_l) + shock, 0.0, None)
    out["pv_kw"] = out["pv_kw"].to_numpy() * solar_factor
    out["precio_eur_per_kwh"] = np.clip(out["precio_eur_per_kwh"].to_numpy() * float(p["price_scale"]) * (1 + e_p), 1e-4, None)
    out["co2_kg_per_kwh"] = np.clip(out["co2_kg_per_kwh"].to_numpy() * float(p["co2_scale"]) * (1 + e_c), 1e-4, None)

    cut = _window(n, p["cut_start"], p["cut_hours"])
    out.loc[out.index[cut], ["load_kw", "pv_kw"]] = 0.0
    return out, solar_factor


def _perturb_meteo(meteo: pd.DataFrame | None, df_day: pd.DataFrame, solar_factor: np.ndarray):
    """Keep the irradiance sensor consistent with the perturbed solar production."""
    if meteo is None or meteo.empty or "irradiancia_wm2" not in meteo.columns:
        return meteo
    idx = df_day.index.intersection(meteo.index)
    if len(idx) == 0:
        return meteo
    m = meteo.copy()
    f = pd.Series(solar_factor, index=df_day.index).reindex(idx).to_numpy()
    m.loc[idx, "irradiancia_wm2"] = m.loc[idx, "irradiancia_wm2"].to_numpy() * f
    return m


# ---------------------------------------------------------------------------
# Simulation hour by hour, recording the solver plan
# ---------------------------------------------------------------------------

def _clean(a, nd=2):
    """np array -> JSON list (inf/nan -> None)."""
    if a is None:
        return None
    return [None if not _math.isfinite(float(v)) else round(float(v), nd) for v in np.asarray(a, dtype=float)]


def _kappa(agent) -> float:
    p = getattr(agent, "p", None)
    if isinstance(p, dict) and "kappa" in p:
        return float(p["kappa"])
    return float(getattr(agent, "kappa", 0.6))


def warm_agent(agent_class, df_heat: pd.DataFrame, mode: str, meteo=None):
    """Heat-up: the agent sees the 48 h before the day (action ignored) to build its memory."""
    spec = MODE_SPECS[mode]
    agent = agent_class()
    env = make_env(df_heat, mode, meteo=meteo)
    env.soc = spec["soc_init"] * spec["capacity_kwh"]
    obs = env.reset()
    while obs is not None:
        agent.act(obs)
        obs, done = env.step(0.0)
        if done:
            break
    return agent


def _copy_agent(agent):
    """Cheap deep copy that shares the (read-only, large) trained profiles."""
    memo = {}
    for attr in ("prof", "_forecaster"):
        v = getattr(agent, attr, None)
        if v is not None:
            memo[id(v)] = v
    return copy.deepcopy(agent, memo)


def simulate_with_plans(agent, df_day: pd.DataFrame, mode: str, meteo=None, record: bool = True) -> dict:
    """Run the (already warmed) agent on the day. For each hour t store the LP the solver
    solved: forecast net load, weights, planned charge/discharge and planned SOC."""
    spec = MODE_SPECS[mode]
    cap, pmax = spec["capacity_kwh"], spec["power_kw"]
    env = make_env(df_day, mode, meteo=meteo)
    env.soc = spec["soc_init"] * cap
    obs = env.reset()
    kappa = _kappa(agent)
    steps = []
    t = 0
    while obs is not None:
        soc0 = float(obs["soc_kwh"])
        _tl.calls, _tl.fc = ([], []) if record else (None, None)
        P = float(agent.act(obs))
        calls, fcs = _tl.calls, _tl.fc
        _tl.calls = _tl.fc = None
        if record:
            st = {"t": t, "soc0": round(soc0, 1), "P": round(P, 1),
                  "seenPrices": len(obs.get("preus_properes_24h", [])),
                  "meas": [round(float(obs["noves_dades_5min"].get("ultim_consum_kw", 0)), 1),
                           round(float(obs["noves_dades_5min"].get("ultima_solar_kw", 0)), 1)]
                  if isinstance(obs.get("noves_dades_5min"), dict) else None}
            c = calls[-1] if calls else None
            if c is not None and c["x"] is not None:
                H = len(c["w"])
                x = c["x"]
                ch, dis, s = x[:H], x[H:2 * H], x[2 * H:3 * H]
                st.update({"H": H, "w": _clean(c["w"] * 1000, 4), "V": round(c["V"] * 1000, 4),
                           "c": _clean(ch, 1), "d": _clean(dis, 1),
                           "soc": _clean(np.r_[c["s0"], s], 1),
                           "net": _clean(c["net"], 1) if c["net"] is not None else None})
            else:
                st.update({"H": 0, "w": None, "V": 0.0, "c": None, "d": None, "soc": None, "net": None})
            raw = getattr(agent, "_net_raw", None)
            st["netRaw"] = _clean(raw, 1) if raw is not None else st.get("net")
            if fcs:
                pr, cr, _ = fcs[-1]
                st["priceFc"], st["co2Fc"] = _clean(pr, 5), _clean(cr, 5)
            else:
                n = min(len(obs.get("preus_properes_24h", [])), len(obs.get("co2_properes_24h", [])))
                st["priceFc"] = _clean(obs["preus_properes_24h"][:n], 5)
                st["co2Fc"] = _clean(obs["co2_properes_24h"][:n], 5)
            steps.append(st)
        obs, done = env.step(P)
        t += 1

    res = _evaluate(env, df_day, mode)
    soc_path = [spec["soc_init"] * cap] + list(env.soc_series)
    # applied power (after the physical limits): from the SOC change
    applied = []
    for h in range(len(env.soc_series)):
        ds = soc_path[h + 1] - soc_path[h]
        applied.append(ds / env.eta_c if ds > 0 else ds * env.eta_d)
    res["socPath"] = [round(v, 1) for v in soc_path]
    res["applied"] = [round(v, 1) for v in applied]
    res["steps"] = steps
    res["kappa"] = kappa
    return res


def oracle_day(df_day: pd.DataFrame, mode: str) -> dict:
    """Perfect information: one LP over the day with the real net load, price and CO2,
    with the exact score weights. Upper bound for any agent on this scenario."""
    spec = MODE_SPECS[mode]
    cap, pmax = spec["capacity_kwh"], spec["power_kw"]
    load, pv = df_day["load_kw"].to_numpy(), df_day["pv_kw"].to_numpy()
    price, co2 = df_day["precio_eur_per_kwh"].to_numpy(), df_day["co2_kg_per_kwh"].to_numpy()
    base = np.maximum(load - pv, 0.0)
    E_b, C_b = float(base @ co2), float(base @ price)
    if E_b <= 0 or C_b <= 0:
        return {"score": 0.0, "socPath": [spec["soc_init"] * cap] * (len(df_day) + 1), "power": [0.0] * len(df_day)}
    w = 0.7 * co2 / E_b + 0.3 * price / C_b
    x = _oracle_lp.solve_lp(w / w.mean(), spec["soc_init"] * cap, 0.0, net=load - pv, eps=0.5, delta=1e-7,
                            p_max=pmax, e_max=cap)
    H = len(w)
    P = np.zeros(H) if x is None else x[:H] - x[H:2 * H]
    env = make_env(df_day, mode)
    env.soc = spec["soc_init"] * cap
    env.reset()
    for h in range(H):
        env.step(float(np.clip(P[h], -pmax, pmax)))
    r = _evaluate(env, df_day, mode)
    return {"score": r["score"], "dCO2": r["dCO2"], "dCost": r["dCost"],
            "socPath": [round(spec["soc_init"] * cap, 1)] + [round(v, 1) for v in env.soc_series],
            "power": [round(float(v), 1) for v in P]}


def _day_arrays(df_day: pd.DataFrame, kappa: float) -> dict:
    load, pv = df_day["load_kw"].to_numpy(), df_day["pv_kw"].to_numpy()
    price, co2 = df_day["precio_eur_per_kwh"].to_numpy(), df_day["co2_kg_per_kwh"].to_numpy()
    return {"load": _clean(load, 1), "pv": _clean(pv, 1), "net": _clean(load - pv, 1),
            "price": _clean(price, 5), "co2": _clean(co2, 5),
            "w": _clean((0.7 * co2 + 0.3 * kappa * price) * 1000, 4),
            "hours": [f"{h:02d}:00" for h in df_day.index.hour]}


def _lead_error(steps: list, real_net: list) -> list:
    """Mean absolute error of the net-load forecast by lead time (k hours ahead)."""
    acc: dict[int, list] = {}
    for st in steps:
        fc = st.get("netRaw")
        if not fc:
            continue
        for k, v in enumerate(fc):
            j = st["t"] + k
            if v is None or j >= len(real_net) or real_net[j] is None:
                continue
            acc.setdefault(k, []).append(abs(v - real_net[j]))
    return [{"k": k, "mae": round(float(np.mean(v)), 1), "n": len(v)} for k, v in sorted(acc.items())]


def _summary(r: dict) -> dict:
    return {k: r[k] for k in ("score", "dCO2", "dCost", "infracciones", "soc_final")}


_warm_cache: dict = {}     # warmed agents (never used directly: always copied)


def run_rolling_horizon(agent_class, df_day: pd.DataFrame, df_heat: pd.DataFrame, mode: str,
                        meteo=None, scenario: dict | None = None, n_samples: int = 1,
                        active_seed: int | None = None) -> dict:
    """Baseline (real day) + active scenario (seed) with every plan + optional ensemble of
    n_samples scenarios with consecutive seeds (only executed trajectories and scores)."""
    scenario = {**SCENARIO_DEFAULTS, **(scenario or {})}
    seed0 = int(scenario.get("seed", 0))
    act_seed = seed0 if active_seed is None else int(active_seed)
    key = (id(agent_class), mode, str(df_heat.index[0]), str(df_heat.index[-1]))
    warmed = _warm_cache.get(key)
    if warmed is None:
        warmed = warm_agent(agent_class, df_heat, mode, meteo)
        _warm_cache[key] = warmed
        while len(_warm_cache) > 32:
            _warm_cache.pop(next(iter(_warm_cache)))

    base = simulate_with_plans(_copy_agent(warmed), df_day, mode, meteo, record=False)
    base_oracle = oracle_day(df_day, mode)

    df_s, f = perturb_day(df_day, scenario, act_seed)
    met_s = _perturb_meteo(meteo, df_day, f)
    act = simulate_with_plans(_copy_agent(warmed), df_s, mode, met_s, record=True)
    act_oracle = oracle_day(df_s, mode)
    arrays = _day_arrays(df_s, act["kappa"])
    real = _day_arrays(df_day, act["kappa"])

    # without random noise every seed gives the same day: a single scenario is enough
    noisy = any(float(scenario.get(k, 0) or 0) > 0 for k in ("demand_noise", "solar_noise", "price_noise", "co2_noise"))
    if not noisy:
        n_samples = 1
    ensemble = []
    for i in range(max(1, int(n_samples))):
        sd = seed0 + i
        if sd == act_seed:
            r, o = act, act_oracle
        else:
            d_i, f_i = perturb_day(df_day, scenario, sd)
            r = simulate_with_plans(_copy_agent(warmed), d_i, mode, _perturb_meteo(meteo, df_day, f_i), record=False)
            o = oracle_day(d_i, mode)
        ensemble.append({"seed": sd, **_summary(r), "oracle": o["score"], "socPath": r["socPath"]})

    spec = MODE_SPECS[mode]
    return {
        "mode": mode,
        "battery": {"capacityKwh": spec["capacity_kwh"], "powerKw": spec["power_kw"],
                    "forecastHours": spec["forecast_horizon"]},
        "scenario": scenario,
        "activeSeed": act_seed,
        "stochastic": noisy,
        "real": real,
        "day": arrays,
        "baseline": {**_summary(base), "socPath": base["socPath"], "applied": base["applied"],
                     "oracle": base_oracle["score"], "oracleSoc": base_oracle["socPath"]},
        "active": {**_summary(act), "socPath": act["socPath"], "applied": act["applied"],
                   "grid": act["grid"], "ptsPerHour": act["pts_per_hour"],
                   "oracle": act_oracle["score"], "oracleSoc": act_oracle["socPath"],
                   "oraclePower": act_oracle["power"]},
        "steps": act["steps"],
        "leadError": _lead_error(act["steps"], arrays["net"]),
        "ensemble": ensemble,
    }
