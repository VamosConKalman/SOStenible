"""
forecaster_impl.py — Implementación del generador de carga neta.

Estrategia: media por hora del día de la semana, con persistencia para t=0.

El generador entrena sobre el historial de carga neta medida (load - pv)
acumulado en self.history durante la simulación.

La clase es ligera (< 10 ms de predict).
"""

from __future__ import annotations

import numpy as np
from forecaster_base import NetLoadForecaster
from typing import Optional


class MeanByDayHourForecaster(NetLoadForecaster):
    """
    Generador basado en medias por (hour_of_day, day_of_week).

    Durante el entrenamiento (preparación del .pkl), se precalculan las
    medias sobre `data/train/`. Durante la simulación, se actualizan
    incrementalmente con las mediciones.

    Para la hora actual t:
    - Si hay observación de t-1, la usa como persistencia.
    - Si no, usa la media histórica del mismo slot.
    """

    __slots__ = ("_slot_means", "_counts", "_n_fit", "_use_persistence")

    def __init__(
        self,
        use_persistence: bool = True,
    ):
        """
        Parámetros
        ----------
        use_persistence : bool
            Si True, para la hora actual usa persistencia (N_{t-1})
            antes de la media histórica.
        """
        self._slot_means: dict[tuple[int, int], list[float]] = {}
        self._counts: dict[tuple[int, int], int] = {}
        self._n_fit = 0
        self._use_persistence = use_persistence

    def fit(
        self,
        hourly_net_load: np.ndarray,
        timestamps,
    ) -> "MeanByDayHourForecaster":
        """
        Entrena las medias por (hour, day_of_week).

        Parámetros
        ----------
        hourly_net_load : np.ndarray de longitud N
            Carga neta medida load_k - pv_k (kW), siempre ≥ 0.
        timestamps : pandas.DatetimeIndex de longitud N
            Marca de tiempo de cada hora.
        """
        for i, net_val in enumerate(hourly_net_load):
            if not np.isfinite(net_val):
                continue
            ts = timestamps[i]
            key = (ts.hour, ts.dayofweek)
            if key not in self._slot_means:
                self._slot_means[key] = []
                self._counts[key] = 0
            self._slot_means[key].append(float(net_val))
            self._counts[key] += 1

        self._n_fit = len(hourly_net_load)
        return self

    def predict(
        self,
        obs: dict,
        history: list[tuple],
        horizon: int,
    ) -> np.ndarray:
        """
        Devuelve N̂_0..N̂_{H-1}.

        Para k=0: persistencia si hay N_{t-1}, sino media histórica.
        Para k>0: media histórica del slot (t+k).
        """
        result = np.full(horizon, np.nan, dtype=np.float64)

        for k in range(horizon):
            try:
                ts_k = pd.Timestamp(obs["timestamp"]) + pd.Timedelta(hours=k)
                hour = ts_k.hour
                dow = ts_k.dayofweek
            except Exception:
                continue

            key = (hour, dow)
            mean_val = self._get_mean(key)

            if k == 0 and self._use_persistence and history:
                # Persistencia: N_{t-1}
                last_ts, last_net = history[-1]
                if np.isfinite(last_net):
                    result[0] = last_net
                    continue

            if np.isfinite(mean_val):
                result[k] = mean_val

        return result

    def _get_mean(self, key: tuple[int, int]) -> float:
        if key in self._slot_means and self._slot_means[key]:
            return np.mean(self._slot_means[key])
        return np.nan


# ---------------------------------------------------------------------------
# Compatibilidad: importar pandas dentro de predict para no requerirlo en init
# ---------------------------------------------------------------------------
def _import_pandas():
    import pandas as pd
    return pd


# Patch MeanByDayHourForecaster.predict to use pandas
_original_predict = MeanByDayHourForecaster.predict


def _patched_predict(
    self,
    obs: dict,
    history: list[tuple],
    horizon: int,
) -> np.ndarray:
    import pandas as pd

    result = np.full(horizon, np.nan, dtype=np.float64)

    for k in range(horizon):
        try:
            ts_k = pd.Timestamp(obs["timestamp"]) + pd.Timedelta(hours=k)
            hour = ts_k.hour
            dow = ts_k.dayofweek
        except Exception:
            continue

        key = (hour, dow)
        mean_val = self._get_mean(key)

        if k == 0 and self._use_persistence and history:
            last_ts, last_net = history[-1]
            if np.isfinite(last_net):
                result[0] = last_net
                continue

        if np.isfinite(mean_val):
            result[k] = mean_val

    return result


MeanByDayHourForecaster.predict = _patched_predict