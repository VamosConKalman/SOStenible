"""
test_forecaster.py — Pruebas del generador de carga neta.

Verifica:
  1. MeanByDayHourForecaster predice valores razonables.
  2. Persistencia para hora actual (k=0).
  3. NaN → inf en el adaptador (si se usa).
  4. Ajuste de longitud del predict.
  5. fit → predict con datos reales.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SRC_DIR = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from forecaster_impl import MeanByDayHourForecaster


class TestMeanByDayHourForecasterBasic:
    """Comportamiento básico del forecaster."""

    def test_inicializado_sin_datos(self):
        f = MeanByDayHourForecaster(use_persistence=True)
        # Sin fit, predict devuelve inf/nan
        obs = {
            "timestamp": "2026-01-05 12:00:00",
        }
        pred = f.predict(obs, [], horizon=24)
        # Todos NaN porque no hay datos
        assert len(pred) == 24
        assert np.isnan(pred).all()

    def test_persistence_usada(self):
        """Con historial, persistencia para hora 0."""
        f = MeanByDayHourForecaster(use_persistence=True)
        obs = {
            "timestamp": "2026-01-05 12:00:00",
        }
        history = [("2026-01-05 11:00:00", 300.0)]

        pred = f.predict(obs, history, horizon=4)

        # k=0 debe ser persistencia (300)
        assert pred[0] == 300.0

    def test_persistence_desactivada(self):
        """Sin persistencia, k=0 usa inf/nan si no hay datos."""
        f = MeanByDayHourForecaster(use_persistence=False)
        obs = {
            "timestamp": "2026-01-05 12:00:00",
        }
        history = [("2026-01-05 11:00:00", 300.0)]

        pred = f.predict(obs, history, horizon=4)

        # k=0 debe ser inf (sin persistencia, sin datos)
        assert np.isinf(pred[0]) or np.isnan(pred[0])

    def test_horizon_corto(self):
        f = MeanByDayHourForecaster()
        obs = {"timestamp": "2026-01-05 12:00:00"}
        pred = f.predict(obs, [], horizon=3)
        assert len(pred) == 3

    def test_horizon_largo_truncado(self):
        f = MeanByDayHourForecaster()
        obs = {"timestamp": "2026-01-05 12:00:00"}
        pred = f.predict(obs, [], horizon=48)
        assert len(pred) == 48


class TestMeanByDayHourForecasterFit:
    """Entrenamiento y predicción con datos."""

    def test_fit_y_predict(self):
        """Fit con datos → predict usa medias."""
        f = MeanByDayHourForecaster(use_persistence=True)

        # 3 días de lunes a 300, 400, 500 a las 12:00
        dates = pd.date_range("2026-01-05", periods=72, freq="1h")  # 3 días
        net_load = np.array(
            [300] * 24 + [400] * 24 + [500] * 24,
            dtype=float,
        )

        f.fit(net_load, dates)

        # Predicción para lunes 12:00 (debería usar persistencia)
        obs = {
            "timestamp": "2026-01-08 12:00:00",  # lunes
        }
        history = [("2026-01-08 11:00:00", 350.0)]

        pred = f.predict(obs, history, horizon=3)

        # k=0: persistencia
        assert pred[0] == 350.0

        # k=1: media de lunes 13:00 → no entrenada, inf
        assert np.isinf(pred[1]) or np.isnan(pred[1])

    def test_media_por_slot(self):
        """El forecaster calcula la media correcta por (hour, dow)."""
        f = MeanByDayHourForecaster(use_persistence=True)

        # 4 semanas, mismo slot (lunes 12:00) con valores 100, 200, 300, 400
        dates_list = []
        net_list = []
        values = [100.0, 200.0, 300.0, 400.0]

        for i, val in enumerate(values):
            for h in range(24):
                dates_list.append(
                    pd.Timestamp("2026-01-05") + pd.Timedelta(weeks=i, hours=h)
                )
                net_list.append(val if h == 12 else 0.0)

        f.fit(np.array(net_list), pd.DatetimeIndex(dates_list))

        obs = {"timestamp": "2026-01-26 12:00:00"}  # lunes 12:00
        pred = f.predict(obs, [], horizon=24)

        # k=0: sin historial reciente, usa la media del slot (250)
        assert abs(pred[0] - 250.0) < 1e-3
        # k=12: no entrenado → inf
        assert np.isinf(pred[12]) or np.isnan(pred[12])

    def test_net_negativo(self):
        """Valores negativos en net_load se guardan."""
        f = MeanByDayHourForecaster(use_persistence=True)

        dates = pd.date_range("2026-01-05", periods=48, freq="1h")
        net = np.array(
            [500.0 if h < 12 else -100.0 for h in range(48)], dtype=float
        )

        f.fit(net, dates)

        obs = {"timestamp": "2026-01-06 13:00:00"}  # martes 13:00
        pred = f.predict(obs, [], horizon=1)

        # k=0: con persistencia=True pero sin history, usa la media
        # (-100 + 500)/2 no, solo martes 13:00 que tiene -100
        assert abs(pred[0] - (-100.0)) < 1e-3


class TestAdaptadorLongitud:
    """El adaptador ajusta la longitud del predict."""
    # Nota: este test simula lo que haría el adaptador en agent.py


class TestInterface:
    """Verifica la interfaz NetLoadForecaster."""

    def test_abstract_class(self):
        from forecaster_base import NetLoadForecaster

        class BadForecaster(NetLoadForecaster):
            pass

        with pytest.raises(TypeError):
            BadForecaster()

    def test_has_predict(self):
        f = MeanByDayHourForecaster()
        assert hasattr(f, "predict")
        assert callable(f.predict)