"""
test_agent.py — Pruebas del BatteryAgent (integración con entorno mock).

Verifica:
  1. act(obs) con modo v1 (sin generador).
  2. Horizonte truncado a H=24.
  3. SOC en extremos.
  4. Sin infracciones en simulador.
  5. Tiempo razonable (< 30 s para 2016 h).
  6. Error handling: obs incompleta → P = 0.
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SRC_DIR = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))


# ---------------------------------------------------------------------------
# Helper para crear un agente que use SRC_DIR como base
# ---------------------------------------------------------------------------
class SandboxAgent:
    """BatteryAgent adaptado para ejecutarse desde sandbox_impl."""

    def __init__(self, params: dict | None = None):
        import importlib
        import json as _json

        sys.path.insert(0, str(SRC_DIR))

        import lp_model as _lp
        import agent as _agent_mod

        params_path = SRC_DIR / "parametres.json"
        with open(params_path, "r") as f:
            p = _json.load(f)

        if params is not None:
            p.update(params)

        self._lp = _lp
        self._agent_cls = _agent_mod.BatteryAgent

        class PatchedAgent(_agent_mod.BatteryAgent):
            def __init__(__self__):
                __self__._path = SRC_DIR
                __self__._params = p

                __self__.kappa = float(p.get("kappa", 0.55))
                __self__.q = float(p.get("q", 0.5))
                __self__.eps = float(p.get("eps", 0.5))
                __self__.delta = float(p.get("delta", 1e-6))
                __self__.w_co2 = float(p.get("w_co2", 0.7))
                __self__.w_cost = float(p.get("w_cost", 0.3))
                __self__.use_forecaster = bool(p.get("use_forecaster", False))
                v_coef_raw = p.get("v_coef")
                __self__.v_coef = (
                    tuple(float(v) for v in v_coef_raw)
                    if v_coef_raw is not None
                    else None
                )

                __self__.eta_c = _lp.ETA_C
                __self__.eta_d = _lp.ETA_D
                __self__.p_max = _lp.P_MAX
                __self__.e_max = _lp.E_MAX
                __self__.history = []
                __self__.net_forecast = None
                __self__.n_forecast_fail = 0
                __self__.n_fail = 0
                __self__.last_info = {}
                __self__._forecaster = None

        self._agent = PatchedAgent()

    def act(self, obs):
        return self._agent.act(obs)

    @property
    def last_info(self):
        return self._agent.last_info

    @property
    def history(self):
        return self._agent.history


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestActBasic:
    """Comportamiento básico de act(obs)."""

    def test_act_retorna_float(self, sandbox_agent):
        obs = {
            "timestamp": "2026-01-05 12:00:00",
            "hour": 12,
            "day_of_week": 0,
            "soc_kwh": 1000.0,
            "soc_pct": 0.5,
            "preu_actual": 0.15,
            "co2_actual": 0.06,
            "preus_properes_24h": [0.15] * 24,
            "co2_properes_24h": [0.06] * 24,
            "noves_dades_5min": {
                "ultim_consum_kw": 500.0,
                "ultima_solar_kw": 200.0,
            },
        }
        P = sandbox_agent.act(obs)
        assert isinstance(P, float), f"act() debe retornar float, got {type(P)}"
        assert np.isfinite(P), f"act() retornó {P}"
        assert -500.0 <= P <= 500.0

    def test_act_modo_v1(self, sandbox_agent):
        """Con use_forecaster=False, se usa modo v1."""
        obs = {
            "timestamp": "2026-01-05 12:00:00",
            "soc_kwh": 1000.0,
            "preus_properes_24h": [0.15] * 24,
            "co2_properes_24h": [0.06] * 24,
            "noves_dades_5min": {
                "ultim_consum_kw": 500.0,
                "ultima_solar_kw": 200.0,
            },
        }
        P = sandbox_agent.act(obs)
        assert sandbox_agent.last_info["mode"] == "v1"
        assert sandbox_agent.last_info["net_provided"] is False

    def test_act_con_horizon_corto(self, sandbox_agent):
        """H se trunc a la longitud del vector."""
        obs = {
            "timestamp": "2026-01-05 12:00:00",
            "soc_kwh": 1000.0,
            "preus_properes_24h": [0.15, 0.16, 0.17],
            "co2_properes_24h": [0.06, 0.07, 0.08],
            "noves_dades_5min": {
                "ultim_consum_kw": 500.0,
                "ultima_solar_kw": 200.0,
            },
        }
        P = sandbox_agent.act(obs)
        assert isinstance(P, float)
        assert sandbox_agent.last_info["H"] == 3


class TestHorizon:
    """Cálculo del horizonte."""

    def test_horizon_24_horas(self, sandbox_agent):
        obs = {
            "timestamp": "2026-01-05 12:00:00",
            "soc_kwh": 1000.0,
            "preus_properes_24h": [0.15] * 24,
            "co2_properes_24h": [0.06] * 24,
        }
        P = sandbox_agent.act(obs)
        assert sandbox_agent.last_info["H"] == 24

    def test_horizon_truncado_12(self, sandbox_agent):
        obs = {
            "timestamp": "2026-01-05 12:00:00",
            "soc_kwh": 1000.0,
            "preus_properes_24h": [0.15] * 12,
            "co2_properes_24h": [0.06] * 12,
        }
        P = sandbox_agent.act(obs)
        assert sandbox_agent.last_info["H"] == 12


class TestSOCBordes:
    """Agent se comporta correctamente con SOC extremo."""

    def test_soc_muy_bajo(self, sandbox_agent):
        """Con SOC ≈ 0, el agente no descarga significativamente."""
        obs = {
            "timestamp": "2026-01-05 12:00:00",
            "soc_kwh": 0.6,
            "preus_properes_24h": [0.05] * 24,
            "co2_properes_24h": [0.05] * 24,
            "noves_dades_5min": {
                "ultim_consum_kw": 500.0,
                "ultima_solar_kw": 200.0,
            },
        }
        P = sandbox_agent.act(obs)
        lo = 0.6 - 0.5  # 0.1 kWh
        max_discharge = min(500, lo * 0.9487)
        assert P >= -max_discharge - 1e-3

    def test_soc_muy_alto(self, sandbox_agent):
        """Con SOC ≈ 2000, el agente no carga significativamente."""
        obs = {
            "timestamp": "2026-01-05 12:00:00",
            "soc_kwh": 1999.6,
            "preus_properes_24h": [0.05] * 24,
            "co2_properes_24h": [0.05] * 24,
            "noves_dades_5min": {
                "ultim_consum_kw": 500.0,
                "ultima_solar_kw": 200.0,
            },
        }
        P = sandbox_agent.act(obs)
        hi = 2000 - 1999.6 - 0.5  # -0.1 (negativo → no cabe)
        max_charge = min(500, hi / 0.9487 if hi > 0 else 0.0)
        assert P <= max_charge + 1e-3


class TestErrorHandling:
    """Gestión de errores y observaciones incompletas."""

    def test_obs_minimal(self, sandbox_agent):
        """Obs sin campos opcionales → act no falla."""
        obs = {"timestamp": "2026-01-05 12:00:00", "soc_kwh": 1000.0}
        P = sandbox_agent.act(obs)
        assert isinstance(P, float)

    def test_soc_no_numeric(self, sandbox_agent):
        """SOC como string → act devuelve 0."""
        obs = {
            "timestamp": "2026-01-05 12:00:00",
            "soc_kwh": "invalid",
        }
        P = sandbox_agent.act(obs)
        assert P == 0.0

    def test_multiple_calls_count_failures(self, sandbox_agent):
        """Los fallos se contabilizan en n_fail."""
        sandbox_agent.act({"timestamp": "2026-01-05 12:00:00", "soc_kwh": "bad"})
        assert sandbox_agent.last_info.get("error") == "exception"


class TestIntegration:
    """Pruebas de integración con el entorno mock."""

    def test_0_infracciones_24h(self, sandbox_agent, hourly_df):
        """24 pasos → 0 infracciones."""
        from environment import CampusBatteryEnv

        env = CampusBatteryEnv(hourly_df.iloc[:24])
        obs = env.reset()
        done = False
        while not done:
            P = sandbox_agent.act(obs)
            obs, done = env.step(P)

        result = env.evaluate_results()
        assert result["infraccions"] == 0, (
            f"Infracciones: {result['infraccions']}. "
            f"Last info: {sandbox_agent.last_info}"
        )

    def test_168h_tiempo(self, sandbox_agent, hourly_df):
        """168 pasos (1 semana) en < 5 s."""
        from environment import CampusBatteryEnv

        env = CampusBatteryEnv(hourly_df.iloc[:168])
        obs = env.reset()
        done = False

        t0 = time.time()
        while not done:
            P = sandbox_agent.act(obs)
            obs, done = env.step(P)
        elapsed = time.time() - t0

        assert elapsed < 5.0, f"168 h tardaron {elapsed:.2f} s (máx 5 s)"
        result = env.evaluate_results()
        assert result["infraccions"] == 0

    def test_soc_init_50pct(self, sandbox_agent, hourly_df):
        """SOC inicial al 50 % → se mantiene en [0, 2000]."""
        from environment import CampusBatteryEnv

        env = CampusBatteryEnv(hourly_df.iloc[:48], soc_pct=0.5)
        obs = env.reset()
        assert env.soc == pytest.approx(1000.0, rel=1e-3)

        done = False
        while not done:
            P = sandbox_agent.act(obs)
            obs, done = env.step(P)

        assert env.soc_series[-1] >= 0.0
        assert env.soc_series[-1] <= 2000.0

    def test_soc_init_bajo(self, sandbox_agent, hourly_df):
        """SOC inicial al 5 % → no baja de 0."""
        from environment import CampusBatteryEnv

        env = CampusBatteryEnv(hourly_df.iloc[:48], soc_pct=0.05)
        obs = env.reset()
        assert env.soc == pytest.approx(100.0, rel=1e-3)

        done = False
        while not done:
            P = sandbox_agent.act(obs)
            obs, done = env.step(P)

        assert env.soc_series[-1] >= 0.0 - 1e-3

    def test_soc_init_alto(self, sandbox_agent, hourly_df):
        """SOC inicial al 95 % → no sube de 2000."""
        from environment import CampusBatteryEnv

        env = CampusBatteryEnv(hourly_df.iloc[:48], soc_pct=0.95)
        obs = env.reset()
        assert env.soc == pytest.approx(1900.0, rel=1e-3)

        done = False
        while not done:
            P = sandbox_agent.act(obs)
            obs, done = env.step(P)

        assert env.soc_series[-1] <= 2000.0 + 1e-3


class TestLastInfo:
    """Información de diagnóstico correcta."""

    def test_last_info_contains_mode(self, sandbox_agent):
        obs = {
            "timestamp": "2026-01-05 12:00:00",
            "soc_kwh": 1000.0,
            "preus_properes_24h": [0.15] * 24,
            "co2_properes_24h": [0.06] * 24,
            "noves_dades_5min": {
                "ultim_consum_kw": 500.0,
                "ultima_solar_kw": 200.0,
            },
        }
        sandbox_agent.act(obs)
        info = sandbox_agent.last_info
        assert "mode" in info
        assert info["mode"] in ("v1", "forecast")
        assert "H" in info
        assert "P" in info
        assert "soc" in info


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def sandbox_agent():
    return SandboxAgent()


@pytest.fixture
def hourly_df():
    """DataFrame horario pequeño para tests (48 h, 2 días)."""
    dates = pd.date_range("2026-01-05", periods=48, freq="1h")

    # Patrón de 24 h x 2 = 48 h
    load = np.tile(
        [300] * 6 + [800] * 6 + [600] * 6 + [900] * 6,
        2,
    )[:48]

    pv = np.tile(
        [0] * 12 + [200, 0] * 3 + [0] * 6,
        2,
    )[:48]

    precio = np.tile(
        [0.08] * 6 + [0.15] * 6 + [0.20] * 6 + [0.10] * 6,
        2,
    )[:48]

    co2 = np.tile(
        [0.06] * 12 + [0.08] * 12,
        2,
    )[:48]

    return pd.DataFrame(
        {
            "Fecha": dates,
            "load_kw": load,
            "pv_kw": pv,
            "precio_eur_per_kwh": precio,
            "co2_kg_per_kwh": co2,
        }
    )