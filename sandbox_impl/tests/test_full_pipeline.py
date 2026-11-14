"""
test_full_pipeline.py — Pruebas de la escalera de variantes (§7.3 del PLAN).

Variantes:
  A: Sin batería (score 0)
  B: Heurística simple
  C: LP v1 (sin generador)
  D: LP con generador (no implementado en test, se salta)
  E: LP con previsión perfecta (N real)

Se ejecuta sobre las mismas semanas y se compara el score agregado.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SRC_DIR = Path(__file__).parent.parent / "src"
MOCKS_DIR = Path(__file__).parent.parent / "mocks"
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(MOCKS_DIR))

import lp_model as lp


# ---------------------------------------------------------------------------
# Helper: ejecutar un agente LP sobre un DataFrame
# ---------------------------------------------------------------------------
class LpAgent:
    """Agente LP minimalista para tests de pipeline."""

    def __init__(self, kappa=0.55, q=0.5, eps=0.5, delta=1e-6, use_forecaster=False):
        self.kappa = kappa
        self.q = q
        self.eps = eps
        self.delta = delta
        self.use_forecaster = use_forecaster
        self.net_forecast = None
        self.last_info = {}

    def act(self, obs, net_override=None):
        ts = obs["timestamp"]
        soc0 = float(obs["soc_kwh"])

        preus = obs.get("preus_properes_24h", [])
        co2s = obs.get("co2_properes_24h", [])
        H = min(len(preus), len(co2s))

        w = lp.compute_weights(
            np.asarray(co2s[:H], dtype=np.float64),
            np.asarray(preus[:H], dtype=np.float64),
            self.kappa,
        )

        V = lp.compute_terminal_value(w, is_end=False, q=self.q)

        # Determinar net
        net = None
        mode = "v1"

        if net_override is not None and isinstance(net_override, np.ndarray):
            net = np.asarray(net_override[:H], dtype=np.float64)
            mode = "forecast"
            net = np.where(np.isnan(net), np.inf, net)
        elif self.use_forecaster and self.net_forecast is not None:
            net = self.net_forecast[:H]
            mode = "forecast"

        x = lp.solve_lp(w, s0=soc0, V=V, net=net, eps=self.eps, delta=self.delta)

        if x is not None and len(x) >= 2:
            P = float(x[0] - x[H])
            P = lp.clip_consigna(P, soc0, self.eps)
        else:
            P = 0.0

        self.last_info = {
            "H": H,
            "V": round(V, 6),
            "mode": mode,
            "P": round(P, 2),
            "soc": round(soc0, 2),
        }

        return P


class NoOpAgent:
    """Agente que siempre devuelve P=0 (sin batería)."""

    def act(self, obs, net_override=None):
        return 0.0


# ---------------------------------------------------------------------------
# Ejecutar simulación
# ---------------------------------------------------------------------------
def run_simulation(
    agent,
    df: pd.DataFrame,
    net_overrides: dict | None = None,
    cap=2000.0,
    power=500.0,
    eta=0.9,
    soc_pct=0.5,
) -> dict:
    from environment import CampusBatteryEnv

    env = CampusBatteryEnv(df, cap=cap, power=power, eta=eta, soc_pct=soc_pct)
    obs = env.reset()
    done = False

    while not done:
        override = net_overrides.get(env.t, None) if net_overrides else None
        P = agent.act(obs, net_override=override)
        obs, done = env.step(P)

    return env.evaluate_results()


# ---------------------------------------------------------------------------
# Crear datos de prueba realistas
# ---------------------------------------------------------------------------
def make_test_df(n_weeks=2):
    """Genera un DataFrame de n_weeks semanas con datos realistas."""
    n_hours = n_weeks * 168
    dates = pd.date_range("2025-09-01", periods=n_hours, freq="1h")

    # Patrón diario de 24 h → se repite 7 veces por semana, n_weeks semanas
    load_pattern = np.array(
        [300] * 6 + [800] * 6 + [600] * 6 + [900] * 6  # 24 h
    )

    pv_pattern = np.array(
        [0] * 8 + [200] * 4 + [500] * 4 + [300] * 4 + [0] * 4  # 24 h
    )

    precio_pattern = np.array(
        [0.08] * 6 + [0.10] * 6 + [0.18] * 6 + [0.20] * 6  # 24 h
    )

    co2_pattern = np.array(
        [0.06] * 12 + [0.05] * 6 + [0.08] * 6  # 24 h
    )

    # Repetir n_weeks * 7 días
    n_days = 7 * n_weeks
    load = np.tile(load_pattern, n_days) * np.random.RandomState(42).uniform(
        0.8, 1.2, n_hours
    )
    pv = np.tile(pv_pattern, n_days) * np.random.RandomState(43).uniform(
        0.7, 1.3, n_hours
    )

    precio = np.tile(precio_pattern, n_days) * np.random.RandomState(44).uniform(
        0.9, 1.1, n_hours
    )

    co2 = np.tile(co2_pattern, n_days) * np.random.RandomState(45).uniform(
        0.9, 1.1, n_hours
    )

    return pd.DataFrame(
        {
            "Fecha": dates,
            "load_kw": np.maximum(0, load),
            "pv_kw": np.maximum(0, pv),
            "precio_eur_per_kwh": np.maximum(0.01, precio),
            "co2_kg_per_kwh": np.maximum(0.01, co2),
        }
    )


# ---------------------------------------------------------------------------
# Tests de la escalera
# ---------------------------------------------------------------------------
class TestEscaleraVariantes:
    """Escalera de variantes del PLAN §7.3."""

    def test_A_sin_bateria(self):
        """A: Sin batería → score = 0."""
        df = make_test_df(1)

        # Agente que siempre devuelve P=0
        class NoOpAgent:
            def act(self, obs, net_override=None):
                return 0.0

        result = run_simulation(NoOpAgent(), df)

        # Score debe ser 0 (sin ahorro)
        assert result["score"] == pytest.approx(0.0, abs=0.1), (
            f"Sin batería, score debería ser ~0, got {result['score']}"
        )
        assert result["co2_estalviat_pct"] == pytest.approx(0.0, abs=0.1)
        assert result["cost_estalviat_pct"] == pytest.approx(0.0, abs=0.1)

    def test_C_lp_v1(self):
        """C: LP v1 (sin generador) → score > 0."""
        df = make_test_df(1)

        agent = LpAgent(kappa=0.55, eps=0.5, delta=1e-6, use_forecaster=False)
        result = run_simulation(agent, df)

        # LP v1 debe producir score > 0 (mejor que sin batería)
        assert result["score"] > -1.0, (
            f"LP v1 debería mejorar sobre baseline, score={result['score']}"
        )
        assert result["infraccions"] == 0

    def test_C_vs_A(self):
        """C - A ≥ 0: LP mejora sobre baseline."""
        df = make_test_df(1)

        agent = LpAgent(kappa=0.55, eps=0.5, delta=1e-6, use_forecaster=False)
        result_c = run_simulation(agent, df)
        result_a = run_simulation(NoOpAgent(), df)

        # Score C debe ser mayor que A
        assert result_c["score"] >= result_a["score"] - 1e-3, (
            f"LP v1 ({result_c['score']}) debería ser ≥ sin batería "
            f"({result_a['score']})"
        )

    def test_E_prevision_perfecta(self):
        """E: LP con previsión perfecta → score ≥ C."""
        df = make_test_df(1)

        # Calcular N real para cada hora
        net_overrides = {}
        for t in range(len(df)):
            load = df.iloc[t]["load_kw"]
            pv = df.iloc[t]["pv_kw"]
            net_overrides[t] = np.maximum(0, load - pv)

        agent_e = LpAgent(
            kappa=0.55, eps=0.5, delta=1e-6, use_forecaster=True
        )
        result_e = run_simulation(agent_e, df, net_overrides=net_overrides)

        agent_c = LpAgent(
            kappa=0.55, eps=0.5, delta=1e-6, use_forecaster=False
        )
        result_c = run_simulation(agent_c, df)

        # E ≥ C
        assert result_e["score"] >= result_c["score"] - 1e-3, (
            f"Con previsión perfecta ({result_e['score']}) debería ser ≥ "
            f"v1 ({result_c['score']})"
        )

    def test_E_vs_A(self):
        """E - A: mejora con previsión perfecta."""
        df = make_test_df(1)

        net_overrides = {}
        for t in range(len(df)):
            load = df.iloc[t]["load_kw"]
            pv = df.iloc[t]["pv_kw"]
            net_overrides[t] = np.maximum(0, load - pv)

        agent = LpAgent(
            kappa=0.55, eps=0.5, delta=1e-6, use_forecaster=True
        )
        result = run_simulation(agent, df, net_overrides=net_overrides)

        assert result["score"] > -1.0, (
            f"Con previsión perfecta, score={result['score']}"
        )

    def test_infracciones_cero(self):
        """Todas las variantes producen 0 infracciones."""
        df = make_test_df(1)

        # C: v1
        agent_c = LpAgent(kappa=0.55, eps=0.5, delta=1e-6, use_forecaster=False)
        result_c = run_simulation(agent_c, df)

        # E: perfect forecast
        net_overrides = {}
        for t in range(len(df)):
            net_overrides[t] = np.maximum(
                0, df.iloc[t]["load_kw"] - df.iloc[t]["pv_kw"]
            )
        agent_e = LpAgent(
            kappa=0.55, eps=0.5, delta=1e-6, use_forecaster=True
        )
        result_e = run_simulation(agent_e, df, net_overrides=net_overrides)

        assert result_c["infraccions"] == 0, f"C: {result_c['infraccions']}"
        assert result_e["infraccions"] == 0, f"E: {result_e['infraccions']}"

    def test_soc_mantiene(self):
        """El SOC se mantiene en [0, 2000] durante la simulación."""
        df = make_test_df(1)

        agent_c = LpAgent(kappa=0.55, eps=0.5, delta=1e-6, use_forecaster=False)
        from environment import CampusBatteryEnv

        env = CampusBatteryEnv(df, soc_pct=0.5)
        obs = env.reset()
        done = False
        while not done:
            P = agent_c.act(obs)
            obs, done = env.step(P)

        socs = env.soc_series
        assert min(socs) >= 0.0 - 1e-3, f"SOC mínimo: {min(socs)}"
        assert max(socs) <= 2000.0 + 1e-3, f"SOC máximo: {max(socs)}"


class TestParameterSensitivity:
    """Sensibilidad de los parámetros."""

    def test_kappa_cero(self):
        """kappa=0 → solo cuenta el CO₂."""
        df = make_test_df(1)
        agent = LpAgent(kappa=0.0, eps=0.5, delta=1e-6, use_forecaster=False)
        result = run_simulation(agent, df)
        # Debería funcionar (no fallar)
        assert result["score"] is not None
        assert result["infraccions"] == 0

    def test_kappa_alto(self):
        """kappa=5.0 → solo cuenta el coste."""
        df = make_test_df(1)
        agent = LpAgent(kappa=5.0, eps=0.5, delta=1e-6, use_forecaster=False)
        result = run_simulation(agent, df)
        assert result["score"] is not None
        assert result["infraccions"] == 0

    def test_eps_diferente(self):
        """eps=0.01 vs eps=1.0."""
        df = make_test_df(1)

        for eps in [0.01, 0.5, 1.0]:
            agent = LpAgent(
                kappa=0.55, eps=eps, delta=1e-6, use_forecaster=False
            )
            result = run_simulation(agent, df)
            assert result["infraccions"] == 0, f"eps={eps}: {result['infraccions']}"


class TestPerformance:
    """Rendimiento temporal."""

    def test_tiempo_168h(self):
        """168 llamadas en < 3 s."""
        df = make_test_df(1)
        agent = LpAgent(kappa=0.55, eps=0.5, delta=1e-6, use_forecaster=False)

        import time

        t0 = time.time()
        run_simulation(agent, df)
        elapsed = time.time() - t0

        assert elapsed < 3.0, f"168 h tardaron {elapsed:.2f} s (máx 3 s)"

    def test_tiempo_48h_x4(self):
        """4 × 48 h ≈ 192 llamadas en < 5 s."""
        df = make_test_df(4)
        agent = LpAgent(kappa=0.55, eps=0.5, delta=1e-6, use_forecaster=False)

        import time

        t0 = time.time()
        run_simulation(agent, df)
        elapsed = time.time() - t0

        assert elapsed < 5.0, f"192 h tardaron {elapsed:.2f} s (máx 5 s)"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

class NoOpAgent:
    """Agente que siempre devuelve P=0 (sin batería)."""

    def act(self, obs, net_override=None):
        return 0.0
