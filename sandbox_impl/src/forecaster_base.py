"""
forecaster_base.py — Interfaz abstracta para el generador de carga neta.

Contrato con BatteryAgent: el generador recibe obs, historial y horizonte,
y devuelve la carga neta prevista N̂_0..N̂_{H-1}.
"""

from abc import ABC, abstractmethod
from typing import Any
import numpy as np


class NetLoadForecaster(ABC):
    """Contrato con BatteryAgent."""

    @abstractmethod
    def predict(
        self,
        obs: dict,
        history: list[tuple],
        horizon: int,
    ) -> np.ndarray:
        """
        Predice la carga neta para el horizonte de `horizon` horas.

        Parámetros
        ----------
        obs : dict
            El diccionario de la hora actual (sin modificar).
        history : list of tuple
            Lista [(timestamp, N_medida_kW), ...] de horas pasadas,
            la última = t-1.
        horizon : int
            H (≤ 24).

        Devuelve
        --------
        np.ndarray de longitud `horizon`
            En kW, ÍNDICE 0 = HORA ACTUAL t.
            NaN o inf = "sin previsión para esa hora".

        Notas
        -----
        Si la interfaz que te den usa otros nombres, se adapta en
        _get_forecast (agent.py) sin tocar el LP.
        """