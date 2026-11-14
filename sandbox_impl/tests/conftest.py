"""
conftest.py — Fixtures para todos los tests de sandbox_impl.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Asegurar que los módulos se encuentran
SANDBOX_DIR = Path(__file__).parent
SRC_DIR = SANDBOX_DIR / "src"
sys.path.insert(0, str(SRC_DIR))


@pytest.fixture(scope="session")
def params():
    """Carga los parámetros de parametres.json."""
    params_path = SRC_DIR / "parametres.json"
    with open(params_path, "r") as f:
        return json.load(f)


@pytest.fixture
def hourly_df():
    """DataFrame horario de prueba (pequeño, 48 h, 2 días)."""
    dates = pd.date_range("2026-01-05", periods=48, freq="1h")

    # Simulación realista: carga diurna alta, solar mediodía
    load = np.array(
        [300] * 6          # 00-05: noche baja
        + [800] * 6         # 06-11: mañana
        + [600] * 6         # 12-17: tarde moderada (con solar)
        + [900] * 6         # 18-23: pico vespertino
        + [400] * 6         # siguiente día
        + [300] * 6,        # siguiente día noche
        dtype=float,
    )[:48]

    pv = np.array(
        [0] * 6
        + [0] * 2
        + [200] * 2
        + [500] * 2
        + [300] * 2
        + [0] * 12
        + [0] * 6
        + [0] * 2
        + [200] * 2
        + [500] * 2
        + [300] * 2
        + [0] * 12,
        dtype=float,
    )[:48]

    precio = np.array(
        [0.08] * 6 + [0.10] * 4 + [0.18] * 4 + [0.20] * 4  # día 1
        + [0.12] * 4 + [0.10] * 4 + [0.08] * 6 + [0.10] * 6  # día 2
        + [0.18] * 4 + [0.20] * 4 + [0.12] * 4 + [0.10] * 4,  # más
        dtype=float,
    )[:48]

    co2 = np.array(
        [0.06] * 12 + [0.05] * 12 + [0.08] * 12 + [0.07] * 12,
        dtype=float,
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


@pytest.fixture
def const_df():
    """DataFrame con precio y CO₂ constantes (test coherencia)."""
    dates = pd.date_range("2026-01-05", periods=24, freq="1h")
    return pd.DataFrame(
        {
            "Fecha": dates,
            "load_kw": 500.0,
            "pv_kw": 0.0,
            "precio_eur_per_kwh": 0.12,
            "co2_kg_per_kwh": 0.07,
        }
    )


@pytest.fixture
def sample_obs():
    """Observación de prueba para act(obs)."""
    return {
        "timestamp": "2026-01-05 12:00:00",
        "hour": 12,
        "day_of_week": 0,  # lunes
        "soc_kwh": 1000.0,
        "soc_pct": 0.5,
        "preu_actual": 0.15,
        "co2_actual": 0.06,
        "preus_properes_24h": [0.15 + i * 0.01 for i in range(24)],
        "co2_properes_24h": [0.06 + i * 0.002 for i in range(24)],
        "noves_dades_5min": {
            "ultim_consum_kw": 500.0,
            "ultima_solar_kw": 200.0,
        },
    }


@pytest.fixture
def low_soc_obs():
    """Observación con SOC muy bajo."""
    return {
        "timestamp": "2026-01-05 12:00:00",
        "hour": 12,
        "day_of_week": 0,
        "soc_kwh": 1.0,
        "soc_pct": 0.0005,
        "preu_actual": 0.15,
        "co2_actual": 0.06,
        "preus_properes_24h": [0.15] * 24,
        "co2_properes_24h": [0.06] * 24,
        "noves_dades_5min": {
            "ultim_consum_kw": 500.0,
            "ultima_solar_kw": 200.0,
        },
    }


@pytest.fixture
def full_soc_obs():
    """Observación con SOC lleno."""
    return {
        "timestamp": "2026-01-05 12:00:00",
        "hour": 12,
        "day_of_week": 0,
        "soc_kwh": 1999.0,
        "soc_pct": 0.9995,
        "preu_actual": 0.15,
        "co2_actual": 0.06,
        "preus_properes_24h": [0.15] * 24,
        "co2_properes_24h": [0.06] * 24,
        "noves_dades_5min": {
            "ultim_consum_kw": 500.0,
            "ultima_solar_kw": 200.0,
        },
    }


@pytest.fixture
def agent(params):
    """Instancia de BatteryAgent con los parámetros de test."""
    import os
    import json as _json

    # Ajustar rutas del agente para que apunten a la sandbox
    agent_path = SRC_DIR / "agent.py"

    class TestBatteryAgent:
        """BatteryAgent que carga sus archivos desde sandbox_impl/src/."""

        def __init__(self):
            import importlib

            # Importar módulos desde SRC_DIR
            sys.path.insert(0, str(SRC_DIR))

            import lp_model as _lp
            import agent as _agent_mod

            # Hack: modificar __file__ del módulo agent
            import types

            self._lp = _lp
            self._agent_cls = _agent_mod.BatteryAgent

            # Sobrescribir el agente para usar SRC_DIR como __file__
            agent_path = SRC_DIR / "agent.py"

            class PatchedAgent(_agent_mod.BatteryAgent):
                def __init__(self):
                    # Sobrescribir _path
                    import importlib

                    # Recargar con path corregido
                    self._path = SRC_DIR

                    params_path = self._path / "parametres.json"
                    try:
                        with open(params_path, "r") as f:
                            self._params = json.load(f)
                    except Exception:
                        self._params = params

                    self.kappa = float(self._params.get("kappa", 0.55))
                    self.q = float(self._params.get("q", 0.5))
                    self.eps = float(self._params.get("eps", 0.5))
                    self.delta = float(
                        self._params.get("delta", 1e-6)
                    )
                    self.w_co2 = float(
                        self._params.get("w_co2", 0.7)
                    )
                    self.w_cost = float(
                        self._params.get("w_cost", 0.3)
                    )
                    self.use_forecaster = bool(
                        self._params.get("use_forecaster", False)
                    )
                    v_coef_raw = self._params.get("v_coef")
                    self.v_coef = (
                        tuple(float(v) for v in v_coef_raw)
                        if v_coef_raw is not None
                        else None
                    )

                    self.eta_c = _lp.ETA_C
                    self.eta_d = _lp.ETA_D
                    self.p_max = _lp.P_MAX
                    self.e_max = _lp.E_MAX
                    self.history = []
                    self.net_forecast = None
                    self.n_forecast_fail = 0
                    self.n_fail = 0
                    self.last_info = {}
                    self._forecaster = None

            self._agent = PatchedAgent()

        def act(self, obs):
            return self._agent.act(obs)

        @property
        def _lp_model(self):
            return self._lp

    return TestBatteryAgent()


@pytest.fixture
def empty_obs():
    """Observación mínima (sin campos opcionales)."""
    return {
        "timestamp": "2026-01-05 12:00:00",
        "soc_kwh": 1000.0,
    }


@pytest.fixture
def short_horizon_obs():
    """Observación con solo 3 horas de previsión."""
    return {
        "timestamp": "2026-01-05 12:00:00",
        "hour": 12,
        "day_of_week": 0,
        "soc_kwh": 1000.0,
        "soc_pct": 0.5,
        "preu_actual": 0.15,
        "co2_actual": 0.06,
        "preus_properes_24h": [0.15, 0.16, 0.17],
        "co2_properes_24h": [0.06, 0.07, 0.08],
        "noves_dades_5min": {
            "ultim_consum_kw": 500.0,
            "ultima_solar_kw": 200.0,
        },
    }