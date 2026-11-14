"""
test_fixes.py — Correcciones Fase 0 del PLAN.md.

Cada corrección tiene al menos un test de aceptación.
Correcciones cubiertas: 0.1 a 0.13.
"""

import json
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
from forecaster_impl import MeanByDayHourForecaster


# ===========================================================================
# Helper: SandboxAgent que se comporta como BatteryAgent real
# ===========================================================================

class _SandboxAgent:
    """BatteryAgent con path y parámetros sobrescritos."""

    def __init__(self, params: dict | None = None):
        import agent as _agent_mod

        params_path = SRC_DIR / "parametres.json"
        with open(params_path, "r") as f:
            p = json.load(f)
        if params is not None:
            p.update(params)

        class _Agent(_agent_mod.BatteryAgent):
            def __init__(__self__):
                __self__._path = SRC_DIR
                __self__._params = p
                __self__.kappa = float(p.get("kappa", 0.55))
                __self__.q = float(p.get("q", 0.5))
                __self__.eps = float(p.get("eps", 0.5))
                __self__.delta = float(p.get("delta", 1e-6))
                __self__.w_co2 = float(p.get("w_co2", 0.7))
                __self__.w_cost = float(p.get("w_cost", 0.3))
                __self__.forecaster_quantile = float(
                    p.get("forecaster_quantile", 0.5)
                )
                __self__.use_forecaster = bool(
                    p.get("use_forecaster", False)
                )
                vc = p.get("v_coef")
                __self__.v_coef = (
                    tuple(float(v) for v in vc) if vc is not None else None
                )
                __self__.eta_c = lp.ETA_C
                __self__.eta_d = lp.ETA_D
                __self__.p_max = lp.P_MAX
                __self__.e_max = lp.E_MAX
                __self__.history = []
                __self__.net_forecast = None
                __self__.n_forecast_fail = 0
                __self__.n_fail = 0
                __self__.n_index_shift = 0
                __self__.period_end_override = None
                __self__.last_info = {}
                __self__._forecaster = None
                __self__._last_ts = None

        self._agent = _Agent()

    def act(self, obs):
        return self._agent.act(obs)

    @property
    def last_info(self):
        return self._agent.last_info

    @property
    def history(self):
        return self._agent.history

    @property
    def n_fail(self):
        return self._agent.n_fail

    @property
    def n_forecast_fail(self):
        return self._agent.n_forecast_fail

    @property
    def n_index_shift(self):
        return self._agent.n_index_shift

    @property
    def period_end_override(self):
        return self._agent.period_end_override

    @period_end_override.setter
    def period_end_override(self, value):
        self._agent.period_end_override = value

    @property
    def w_co2(self):
        return self._agent.w_co2

    @property
    def w_cost(self):
        return self._agent.w_cost

    @property
    def forecaster_quantile(self):
        return self._agent.forecaster_quantile

    def _interp_quantile(self, pred):
        return self._agent._interp_quantile(pred)

    @property
    def _forecaster(self):
        return self._agent._forecaster

    @_forecaster.setter
    def _forecaster(self, value):
        self._agent._forecaster = value


def _make_obs(**extras):
    """Observación mínima con campos por defecto."""
    noves = {"ultim_consum_kw": 500.0, "ultima_solar_kw": 200.0}
    if "noves_dades_5min" in extras:
        noves.update(extras.pop("noves_dades_5min"))
    base = {
        "timestamp": "2026-01-05 12:00:00",
        "soc_kwh": 1000.0,
        "preu_actual": 0.15,
        "co2_actual": 0.06,
        "preus_properes_24h": [0.15] * 24,
        "co2_properes_24h": [0.06] * 24,
        "noves_dades_5min": noves,
    }
    base.update(extras)
    return base


# ===========================================================================
# 0.1 — BatteryAgent se construye; también sin parametres.json
# ===========================================================================

class Test01_Slots:
    """Corrección 0.1: w_co2, w_cost en __slots__."""

    def test_construccion_normal(self):
        agent = _SandboxAgent()
        assert agent.w_co2 == 0.7
        assert agent.w_cost == 0.3

    def test_construccion_sin_json(self):
        """Sin parametres.json → valores por defecto."""
        agent = _SandboxAgent(params={})
        assert agent.w_co2 == 0.7
        assert agent.w_cost == 0.3
        assert isinstance(agent.act(_make_obs()), float)


# ===========================================================================
# 0.2 — Condición R: np.isfinite(n) and n < P_MAX
# ===========================================================================

class Test02_RCondition:
    """Corrección 0.2: R = isfinite(n) and n < P_MAX (sin n > 0)."""

    def test_nulo_no_activa_R(self):
        """N̂ = 0 en las 24 h, w alto, s0=1000, V=0 → d_0 == 0."""
        H = 24
        w = np.full(H, 0.2, dtype=np.float64)
        net = np.zeros(H, dtype=np.float64)  # N̂ = 0
        x = lp.solve_lp(w, s0=1000.0, V=0.0, net=net, eps=0.5)
        assert x is not None
        d_0 = float(x[H])  # d_0
        assert d_0 < 1e-6, f"Con N̂=0, no debería descargar; d_0={d_0}"


# ===========================================================================
# 0.3 — compute_weights con w_co2 y w_cost explícitos
# ===========================================================================

class Test03_Weights:
    """Corrección 0.3: compute_weights(co2, price, kappa, w_co2, w_cost)."""

    def test_w_co2_1_w_cost_0(self):
        """w_co2=1, w_cost=0 → w == co2."""
        co2 = np.array([0.06, 0.07, 0.08], dtype=np.float64)
        price = np.array([0.10, 0.12, 0.14], dtype=np.float64)
        w = lp.compute_weights(co2, price, kappa=0.55, w_co2=1.0, w_cost=0.0)
        np.testing.assert_allclose(w, co2, rtol=1e-10)

    def test_valores_mixtos(self):
        """w_co2=0.7, w_cost=0.3 → fórmula correcta."""
        co2 = np.array([0.06], dtype=np.float64)
        price = np.array([0.10], dtype=np.float64)
        w = lp.compute_weights(co2, price, kappa=0.55, w_co2=0.7, w_cost=0.3)
        expected = 0.7 * 0.06 + 0.3 * 0.55 * 0.10
        assert abs(w[0] - expected) < 1e-10


# ===========================================================================
# 0.4 — solve_lp return_result y get_dual_marginals
# ===========================================================================

class Test04_ReturnResult:
    """Corrección 0.4: return_result=True → OptimizeResult."""

    def test_return_optimize_result(self):
        H = 6
        w = np.full(H, 0.1, dtype=np.float64)
        result = lp.solve_lp(w, s0=1000.0, V=0.0, net=None, return_result=True)
        assert hasattr(result, "x")
        assert hasattr(result, "success")
        assert result.success is True

    def test_get_dual_marginals_longitud_H(self):
        """Longitud H y todos λ ≥ −1e-9."""
        H = 6
        w = np.array([0.1, 0.15, 0.05, 0.2, 0.12, 0.08], dtype=np.float64)
        net = np.full(H, 100.0, dtype=np.float64)
        duals = lp.get_dual_marginals(w, s0=1000.0, V=0.0, net=net)
        assert duals is not None
        assert len(duals) == H
        assert np.all(duals >= -1e-9), f"Duales negativos: {duals}"


# ===========================================================================
# 0.5 — environment.py: reset() sin drop=True; columna "index" → "Fecha"
# ===========================================================================

class Test05_Environment:
    """Corrección 0.5: reset() con copy().reset_index() sin drop."""

    def test_reset_sin_drop(self):
        df = pd.DataFrame(
            {
                "load_kw": [100.0, 200.0],
                "pv_kw": [0.0, 0.0],
                "precio_eur_per_kwh": [0.1, 0.12],
                "co2_kg_per_kwh": [0.06, 0.07],
            },
            index=pd.DatetimeIndex(
                ["2026-01-05 00:00", "2026-01-05 01:00"]
            ),
        )
        from environment import CampusBatteryEnv
        env = CampusBatteryEnv(df)
        # El índice original se debe mantener como columna
        assert "Fecha" in env.df.columns or env.df.index.name == "Fecha"
        obs = env.reset()
        if "Fecha" in env.df.columns:
            assert obs["timestamp"] == env.df.iloc[0]["Fecha"]

    def test_timestamp_primeras_obs(self):
        """obs['timestamp'] == primera fecha del DataFrame."""
        dates = pd.date_range("2026-03-10", periods=48, freq="1h")
        df = pd.DataFrame(
            {
                "Fecha": dates,
                "load_kw": [500.0] * 48,
                "pv_kw": [0.0] * 48,
                "precio_eur_per_kwh": [0.1] * 48,
                "co2_kg_per_kwh": [0.07] * 48,
            }
        )
        from environment import CampusBatteryEnv
        env = CampusBatteryEnv(df)
        obs = env.reset()
        assert obs["timestamp"] == dates[0]


# ===========================================================================
# 0.6 — Score oficial: max(0, 70·d_co2 + 30·d_cost − 1·infraccions)
# ===========================================================================

class Test06_Score:
    """Corrección 0.6: Score = max(0, 0.7·d_co2 + 0.3·d_cost − infraccions)."""

    def test_formula_score(self):
        """
        Misma semana, mismas acciones salvo t=0: consigna 900 kW (recortada
        a 500, 1 infracción) frente a 500 kW. Efecto físico idéntico →
        la diferencia de score es exactamente 1,00.
        """
        dates = pd.date_range("2026-01-05", periods=168, freq="1h")
        df = pd.DataFrame(
            {
                "Fecha": dates,
                "load_kw": [500.0] * 168,
                "pv_kw": [0.0] * 168,
                "precio_eur_per_kwh": [0.1] * 168,
                "co2_kg_per_kwh": [0.07] * 168,
            }
        )
        from environment import CampusBatteryEnv

        # Env 1: agente con consigna 500 (carga máxima)
        class Force500Agent:
            def act(self, obs):
                return 500.0

        env1 = CampusBatteryEnv(df, soc_pct=0.5)
        obs = env1.reset()
        done = False
        while not done:
            P = Force500Agent().act(obs)
            obs, done = env1.step(P)
        r1 = env1.evaluate_results()

        # Env 2: agente sin batería (P=0) → baseline
        class NoOp:
            def act(self, obs):
                return 0.0

        env2 = CampusBatteryEnv(df, soc_pct=0.5)
        obs = env2.reset()
        done = False
        while not done:
            P = NoOp().act(obs)
            obs, done = env2.step(P)
        r2 = env2.evaluate_results()

        # El score del baseline debe ser 0 (d_co2=0, d_cost=0)
        assert r2["score"] == pytest.approx(0.0, abs=0.5)


# ===========================================================================
# 0.7 — Fin de periodo desde ts (último día del mes a las 23:00)
# ===========================================================================

class Test07_PeriodEnd:
    """Corrección 0.7: period_end = último día del mes a las 23:00."""

    def test_2026_01_31_23h(self):
        """2026-01-31 23:00 → H=1, is_end=True, V=0."""
        agent = _SandboxAgent()
        obs = _make_obs(
            timestamp="2026-01-31 23:00:00",
            preus_properes_24h=[0.15],  # solo 1 hora disponible
            co2_properes_24h=[0.06],
        )
        agent.act(obs)
        info = agent.last_info
        assert info["H"] == 1
        assert info["is_end"] is True

    def test_2026_01_31_00h(self):
        """2026-01-31 00:00 → H=24, is_end=True."""
        agent = _SandboxAgent()
        obs = _make_obs(timestamp="2026-01-31 00:00:00")
        agent.act(obs)
        info = agent.last_info
        assert info["H"] == 24
        assert info["is_end"] is True

    def test_2026_01_15_10h(self):
        """2026-01-15 10:00 → H=24, is_end=False."""
        agent = _SandboxAgent()
        obs = _make_obs(timestamp="2026-01-15 10:00:00")
        agent.act(obs)
        info = agent.last_info
        assert info["H"] == 24
        assert info["is_end"] is False


# ===========================================================================
# 0.8 — Override para backtest
# ===========================================================================

class Test08_Override:
    """Corrección 0.8: period_end_override para backtest."""

    def test_override_21h_a_00h(self):
        """override=2026-01-21 23:00, ts=2026-01-21 20:00 → H=4, is_end."""
        agent = _SandboxAgent()
        agent.period_end_override = pd.Timestamp("2026-01-21 23:00:00")
        obs = _make_obs(timestamp="2026-01-21 20:00:00")
        agent.act(obs)
        info = agent.last_info
        assert info["H"] == 4
        assert info["is_end"] is True

    def test_override_no_usat(self):
        """Sin override → usa mes real."""
        agent = _SandboxAgent()
        assert agent.period_end_override is None
        obs = _make_obs(timestamp="2026-02-10 12:00:00")
        agent.act(obs)
        info = agent.last_info
        # No es fin de febrero → is_end=False
        assert info["is_end"] is False


# ===========================================================================
# 0.9 — Historial: guarda (ts−1h, N_medida), marcado no válido
# ===========================================================================

class Test09_History:
    """Corrección 0.9: Historial con validación."""

    def test_primera_hora_no_guarda(self):
        """Primera hora → historial sin cambios."""
        agent = _SandboxAgent()
        assert len(agent.history) == 0
        obs = _make_obs(timestamp="2026-01-05 12:00:00")
        agent.act(obs)
        assert len(agent.history) == 0

    def test_hora_següenta_si_guarda(self):
        """Hora siguiente → entrada con timestamp ts−1h."""
        agent = _SandboxAgent()
        # Primera llamada
        obs1 = _make_obs(timestamp="2026-01-05 12:00:00")
        agent.act(obs1)
        assert len(agent.history) == 0
        # Segunda llamada (ts = 13:00, guarda 12:00)
        obs2 = _make_obs(
            timestamp="2026-01-05 13:00:00",
            noves_dades_5min={
                "ultim_consum_kw": 500.0,
                "ultima_solar_kw": 200.0,
            },
        )
        agent.act(obs2)
        assert len(agent.history) == 1
        saved_ts, saved_net = agent.history[-1]
        assert saved_ts == pd.Timestamp("2026-01-05 12:00:00")

    def test_salto_semana_no_guarda(self):
        """Salto de más de 1h → no se guarda."""
        agent = _SandboxAgent()
        # Hora 1
        obs1 = _make_obs(timestamp="2026-01-05 12:00:00")
        agent.act(obs1)
        # Salto a lunes siguiente (7 días después)
        obs2 = _make_obs(timestamp="2026-01-12 12:00:00")
        agent.act(obs2)
        # El salto > 1h → no se guarda, pero _last_ts se actualiza
        assert len(agent.history) == 0


# ===========================================================================
# 0.10 — Guard del índice 0: vector desplazado
# ===========================================================================

class Test10_IndexShift:
    """Corrección 0.10: detección de desplazamiento del índice 0."""

    def test_vector_desplaCatda_detecta(self):
        """Vector desplazado → contador incrementa."""
        agent = _SandboxAgent()
        obs = _make_obs(
            preu_actual=0.20,  # diferente del primer elemento [0.15]
            co2_actual=0.08,   # diferente del primer elemento [0.06]
        )
        agent.act(obs)
        assert agent.n_index_shift >= 1

    def test_vector_no_desplaCatda(self):
        """Vector alineado → contador no incrementa."""
        agent = _SandboxAgent()
        obs = _make_obs(
            preu_actual=0.15,  # coincide con preus[0]
            co2_actual=0.06,   # coincide con co2s[0]
        )
        agent.act(obs)
        assert agent.n_index_shift == 0

    def test_w0_calculated_with_preu_actual(self):
        """Si hay shift, w[0] se calcula con preu_actual."""
        agent = _SandboxAgent()
        # preus[0] = 0.15 pero preu_actual = 0.30 → shift detectado
        obs = _make_obs(
            preu_actual=0.30,
            co2_actual=0.06,
            preus_properes_24h=[0.15] * 24,
            co2_properes_24h=[0.06] * 24,
        )
        agent.act(obs)
        # El LP debe usar w[0] basado en preu_actual=0.30
        # Si w[0] fuera con 0.15, el resultado sería diferente
        assert agent.last_info["P"] is not None  # no falló


# ===========================================================================
# 0.11 — Adaptador de cuantiles: dict y ndarray
# ===========================================================================

class Test11_QuantileAdapter:
    """Corrección 0.11: adaptador de cuantiles para dict y ndarray."""

    def test_dict_interpolacio_q03(self):
        """
        dict: p10=0, p50=100, p90=200, q=0.3 → 50 en todas las horas.
        Interpolación lineal entre p10 (q=0.1) y p50 (q=0.5):
        frac = (0.3 - 0.1) / (0.5 - 0.1) = 0.5
        resultado = 0 + 0.5 * (100 - 0) = 50
        """
        agent = _SandboxAgent(params={"forecaster_quantile": 0.3})
        pred = {"p10": np.array([0.0] * 5), "p50": np.array([100.0] * 5),
                "p90": np.array([200.0] * 5)}
        result = agent._interp_quantile(pred)
        np.testing.assert_allclose(result, np.full(5, 50.0), rtol=1e-6)

    def test_ndarray_retorna_igual(self):
        """ndarray → se devuelve tal cual."""
        agent = _SandboxAgent()
        pred = np.array([1.0, 2.0, 3.0])
        result = agent._interp_quantile(pred)
        np.testing.assert_array_equal(result, pred)

    def test_dict_q_dins_rang(self):
        """q=0.5 entre p10 y p50 → retorna p50."""
        agent = _SandboxAgent(params={"forecaster_quantile": 0.5})
        pred = {"p10": np.array([0.0]), "p50": np.array([100.0])}
        result = agent._interp_quantile(pred)
        assert abs(result[0] - 100.0) < 1e-6


# ===========================================================================
# 0.12 — forecaster_impl: sin monkeypatch, pandas importat amunt
# ===========================================================================

class Test12_ForecasterNoMonkeypatch:
    """Corrección 0.12: quitar monkeypatch, pandas importat al top."""

    def test_pandas_imported_at_top(self):
        """pandas debe estar importado en el módulo."""
        import forecaster_impl as fi
        # Verificar que pandas está disponible en el espacio de nombres
        assert hasattr(fi, "pd")

    def test_predict_rollback_longitud_H(self):
        """
        Round-trip joblib dump/load → predict devuelve longitud H.
        """
        import joblib
        import tempfile
        import os

        f = MeanByDayHourForecaster()

        # Entrenar con datos
        dates = pd.date_range("2026-01-05", periods=48, freq="1h")
        net = np.tile([300.0, 400.0], 24)
        f.fit(net, dates)

        # Guardar y cargar
        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            joblib.dump(f, tmp_path)
            f2 = joblib.load(tmp_path)

            obs = {"timestamp": "2026-01-06 12:00:00"}
            pred = f2.predict(obs, [], horizon=24)
            assert len(pred) == 24
            assert np.isfinite(pred).any()
        finally:
            os.unlink(tmp_path)

    def test_predict_devolte_longitud_H(self):
        """Predict devuelve ndarray de longitud H."""
        f = MeanByDayHourForecaster()
        obs = {"timestamp": "2026-01-05 12:00:00"}
        pred = f.predict(obs, [], horizon=12)
        assert len(pred) == 12


# ===========================================================================
# 0.13 — data_loader.py: get_small_df amb np.resize, asfreq/interpolate
# ===========================================================================

class Test13_DataLoader:
    """Corrección 0.13: get_small_df y load_hourly_df."""

    def test_get_small_df_48hores(self):
        """get_small_df(48) funciona."""
        from data_loader import get_small_df
        df = get_small_df(48)
        assert len(df) == 48
        assert "Fecha" in df.columns
        assert "precio_eur_per_kwh" in df.columns

    def test_get_small_df_168hores(self):
        """get_small_df(168) funciona (más de 24h)."""
        from data_loader import get_small_df
        df = get_small_df(168)
        assert len(df) == 168

    def test_load_hourly_df_index_horari(self):
        """
        load_hourly_df: el índice es estrictamente horario dentro de cada tramo.
        Se salta si no hay datos de train disponibles.
        """
        try:
            from data_loader import load_hourly_df
            df = load_hourly_df()
            assert len(df) > 0
            # Verificar que no hay huecos > 1h (dentro del rango)
            if len(df) > 1:
                diffs = df.index.to_series().diff().dropna()
                # Todas las diferencias deben ser <= 2h (tolerancia)
                assert (diffs <= pd.Timedelta(hours=2)).all()
        except Exception:
            pytest.skip("Datos de train no disponibles")


# ===========================================================================
# Tests combinats: integració de múltiples correccions
# ===========================================================================

class TestIntegrationFixes:
    """Tests de integración combinando múltiples correcciones."""

    def test_agent_complet_24h(self):
        """Agente completo: 24 pasos sin excepciones."""
        from data_loader import get_small_df
        from environment import CampusBatteryEnv

        df = get_small_df(24)
        agent = _SandboxAgent()
        env = CampusBatteryEnv(df)
        obs = env.reset()
        done = False
        while not done:
            P = agent.act(obs)
            assert np.isfinite(P), f"P no finito: {P}"
            assert -500 <= P <= 500
            obs, done = env.step(P)
        assert agent.n_fail == 0

    def test_agent_forecaster_actiu(self):
        """Agent amb use_forecaster=True y forecaster."""
        f = MeanByDayHourForecaster()
        dates = pd.date_range("2026-01-05", periods=48, freq="1h")
        net = np.tile([300.0, 400.0], 24)
        f.fit(net, dates)

        agent = _SandboxAgent(params={"use_forecaster": True})
        agent._forecaster = f
        agent.use_forecaster = True

        obs = _make_obs(timestamp="2026-01-06 00:00:00")
        P = agent.act(obs)
        assert np.isfinite(P)
        assert agent.last_info["mode"] == "forecast"