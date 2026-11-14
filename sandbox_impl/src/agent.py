"""
agent.py — BatteryAgent orquestador (MPC con LP HiGHS).

Flujo por hora:
  1. Parsear obs, registrar historial
  2. Calcular H (horizonte truncado)
  3. Calcular w' (pesos horarios exactos de obs)
  4. Calcular V (valor terminal)
  5. Llamar al generador → N̂ (o None = modo v1)
  6. Resolver LP → P = c_0 - d_0
  7. Clip físico → return float
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Any

import numpy as np
import pandas as pd

import lp_model as lp
from forecaster_base import NetLoadForecaster


class BatteryAgent:
    """Orquestador MPC: cada crida a act(obs) resuelve un LP y aplica P₀."""

    __slots__ = (
        "_path",
        "kappa",
        "q",
        "v_coef",
        "eps",
        "delta",
        "use_forecaster",
        "eta_c",
        "eta_d",
        "p_max",
        "e_max",
        "net_forecast",
        "history",
        "n_forecast_fail",
        "n_fail",
        "last_info",
        "_forecaster",
    )

    # ------------------------------------------------------------------
    # Constructor
    # ------------------------------------------------------------------
    def __init__(self):
        self._path = Path(__file__).parent

        # ------------------------------------------------------------------
        # Cargar parámetros
        # ------------------------------------------------------------------
        params_path = self._path / "parametres.json"
        try:
            with open(params_path, "r") as f:
                params = json.load(f)
            self.kappa = float(params["kappa"])
            self.q = float(params.get("q", 0.5))
            self.eps = float(params.get("eps", 0.5))
            self.delta = float(params.get("delta", 1e-6))
            self.w_co2 = float(params.get("w_co2", 0.7))
            self.w_cost = float(params.get("w_cost", 0.3))
            self.use_forecaster = bool(params.get("use_forecaster", False))
            v_coef_raw = params.get("v_coef")
            self.v_coef = (
                tuple(float(v) for v in v_coef_raw)
                if v_coef_raw is not None
                else None
            )
        except Exception:
            self.kappa = 0.55
            self.q = 0.5
            self.eps = 0.5
            self.delta = 1e-6
            self.w_co2 = 0.7
            self.w_cost = 0.3
            self.use_forecaster = False
            self.v_coef = None

        # Constantes físicas
        self.eta_c = lp.ETA_C  # ≈ 0.948683
        self.eta_d = lp.ETA_D
        self.p_max = lp.P_MAX  # 500
        self.e_max = lp.E_MAX  # 2000

        # Historial de carga neta medida: [(timestamp, net_load_kw), ...]
        self.history: list[tuple] = []

        # Previsión neta (se actualiza en _get_forecast)
        self.net_forecast: Optional[np.ndarray] = None

        # Contadores de fallos (diagnóstico)
        self.n_forecast_fail: int = 0
        self.n_fail: int = 0

        # Información del último paso
        self.last_info: dict[str, Any] = {}

        # Generador de carga neta (se carga desde .pkl si existe)
        self._forecaster: Optional[NetLoadForecaster] = None
        if self.use_forecaster:
            self._load_forecaster()

    # ------------------------------------------------------------------
    # Carga del generador desde .pkl
    # ------------------------------------------------------------------
    def _load_forecaster(self):
        """Intenta cargar forecaster.pkl con joblib."""
        try:
            import joblib
            fpath = self._path / "forecaster.pkl"
            if fpath.exists():
                self._forecaster = joblib.load(fpath)
        except Exception:
            self._forecaster = None

    # ------------------------------------------------------------------
    # Horizonte
    # ------------------------------------------------------------------
    def _horizon(
        self,
        preus: list,
        co2s: list,
        period_ends: list[str] | None = None,
    ) -> tuple[int, bool]:
        """
        Calcula H y is_end.

        Parámetros
        ----------
        preus : list
            Precios de las próximas horas.
        co2s : list
            CO₂ de las próximas horas.
        period_ends : list[str] | None
            Fechas de fin de periodo (último día del mes a 23:00).
            Si se proporciona, se trunca H para no cruzar el fin de periodo.

        Devuelve
        --------
        (H, is_end) : tuple[int, bool]
        """
        n = min(len(preus), len(co2s))
        H = min(n, 24)

        is_end = False
        if period_ends is not None and len(period_ends) > 0:
            try:
                ts_current = pd.Timestamp(
                    self.last_info.get("_timestamp", "")
                )
                if isinstance(ts_current, pd.Timestamp):
                    first_end = pd.Timestamp(period_ends[0])
                    hours_left = (first_end - ts_current).total_seconds() / 3600
                    if hours_left > 0 and hours_left <= H:
                        H = int(hours_left)
                        is_end = True
                        if H < 1:
                            H = 1
            except Exception:
                pass

        return H, is_end

    # ------------------------------------------------------------------
    # Generador de previsión de carga neta
    # ------------------------------------------------------------------
    def _get_forecast(
        self,
        obs: dict,
        horizon: int,
    ) -> Optional[np.ndarray]:
        """
        Pide la previsión al generador y la adapta.

        1. Si use_forecaster=False → None.
        2. Llamar predict() dentro de try → None si falla.
        3. Alinear: índice 0 = hora actual t.
        4. Ajustar longitud a H: recortar si sobra, rellenar con inf si falta.
        5. Cambiar NaN → inf.

        Devuelve np.ndarray de longitud H o None.
        """
        if not self.use_forecaster or self._forecaster is None:
            return None

        try:
            pred = self._forecaster.predict(obs, self.history, horizon)

            if pred is None or len(pred) == 0:
                self.n_forecast_fail += 1
                return None

            # Ajustar longitud
            if len(pred) > horizon:
                pred = pred[:horizon]
            elif len(pred) < horizon:
                filled = np.full(horizon, np.inf, dtype=np.float64)
                filled[: len(pred)] = pred
                pred = filled

            # NaN → inf
            pred = np.where(np.isnan(pred), np.inf, pred)

            return pred

        except Exception:
            self.n_forecast_fail += 1
            return None

    # ------------------------------------------------------------------
    # Valor terminal
    # ------------------------------------------------------------------
    def _terminal_value(
        self,
        w: np.ndarray,
        is_end: bool,
    ) -> float:
        """Calcula V del siguiente paso (delegado a lp_model)."""
        return lp.compute_terminal_value(w, is_end, self.q, self.v_coef)

    # ------------------------------------------------------------------
    # Orquestación principal: act()
    # ------------------------------------------------------------------
    def act(self, obs: dict) -> float:
        """
        Determina la consigna de potencia de la bateria para l'hora actual.

        Parámetros
        ----------
        obs : dict con campos del entorno.

        Devuelve
        --------
        float : P en kW (≥ 0 → carga, < 0 → descarga).
        """
        try:
            return float(self._act(obs))
        except Exception:
            self.n_fail += 1
            self.last_info["error"] = "exception"
            return 0.0

    def _act(self, obs: dict) -> float:
        # 1. Parsear timestamp y SOC
        ts = pd.Timestamp(obs["timestamp"])
        soc0 = float(obs["soc_kwh"])

        # Guardar timestamp para _horizon
        self.last_info["_timestamp"] = str(ts)

        # 2. Registrar carga neta medida en historial
        try:
            nova = obs.get("noves_dades_5min", {})
            last_load = float(nova.get("ultim_consum_kw", 0.0))
            last_pv = float(nova.get("ultima_solar_kw", 0.0))
            last_net = max(0.0, last_load - last_pv)
            self.history.append((ts, last_net))
        except Exception:
            pass

        # 3. Calcular H y is_end
        preus = obs.get("preus_properes_24h", [])
        co2s = obs.get("co2_properes_24h", [])
        period_ends = obs.get("period_ends")  # opcional

        H, is_end = self._horizon(preus, co2s, period_ends)

        # 4. Calcular pesos w'
        w = lp.compute_weights(
            np.asarray(co2s[:H], dtype=np.float64),
            np.asarray(preus[:H], dtype=np.float64),
            self.kappa,
        )

        # 5. Calcular V
        V = self._terminal_value(w, is_end)

        # 6. Obtener previsión de carga neta
        net = self._get_forecast(obs, H)

        # 7. Resolver LP
        x = lp.solve_lp(
            w,
            s0=soc0,
            V=V,
            net=net,
            eps=self.eps,
            delta=self.delta,
        )

        # 8. Extraer P = c_0 - d_0 y recortar
        if x is not None and len(x) >= 2:
            P = float(x[0]) - float(x[H])  # c_0 - d_0
            P = lp.clip_consigna(P, soc0, self.eps)
        else:
            P = 0.0

        # 9. Registrar info de diagnóstico
        mode = "forecast" if net is not None else "v1"
        self.last_info = {
            "H": H,
            "V": round(V, 6),
            "is_end": is_end,
            "mode": mode,
            "P": round(P, 2),
            "soc": round(soc0, 2),
            "net_provided": net is not None,
            "n_forecast_fail": self.n_forecast_fail,
            "n_fail": self.n_fail,
        }

        return P