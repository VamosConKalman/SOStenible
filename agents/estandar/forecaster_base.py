"""forecaster_base.py — Contrato entre BatteryAgent y el generador de carga neta.

NO MODIFICAR. Ver ARQUITECTURA_GENERADOR.md.
Sin `abc` a propósito: una subclase incompleta se puede seguir cargando del .pkl
y, si falla, el agente cae a modo v1 en vez de romper al deserializar.
"""
from __future__ import annotations

import numpy as np


class NetLoadForecaster:
    """Predice N = load_kw - pv_kw (kW) para las horas t .. t+H-1.

    Formatos de salida de `predict` (índice 0 = hora actual t, longitud H, np.float64):
      - puntual:    np.ndarray (H,)
      - cuantiles:  {"p10": (H,), "p50": (H,), "p90": (H,), ...}   p10 <= p50 <= p90
      - escenarios: {"scenarios": (S, H), "probs": (S,)}            S <= 50, probs >= 0, suma 1
    NaN / inf = sin previsión para esa hora. N puede ser negativa: no recortar a 0.
    """

    def fit(self, hourly_df):
        """Solo en local. hourly_df: columnas Fecha, load_kw, pv_kw, precio_eur_per_kwh, co2_kg_per_kwh."""
        return self

    def predict(self, obs: dict, history: list, horizon: int):
        """obs sin modificar; history = [(ts_inicio_hora, load_kw, pv_kw), ...] ordenada, con saltos."""
        return np.full(int(horizon), np.nan)
