"""
agent.py — BatteryAgent orquestador (MPC con LP HiGHS).

Flujo por hora:
  1. Parsear obs, registrar historial
  2. Calcular H (horizonte truncado desde mes real)
  3. Calcular w' (pesos horarios exactos de obs)
  4. Calcular V (valor terminal)
  5. Llamar al generador → N̂ (o None = modo v1)
  6. Resolver LP → P = c_0 - d_0
  7. Clip físico → return float
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Any, Union

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
        "w_co2",
        "w_cost",
        "forecaster_quantile",
        "use_forecaster",
        "eta_c",
        "eta_d",
        "p_max",
        "e_max",
        "net_forecast",
        "history",
        "n_forecast_fail",
        "n_fail",
        "n_index_shift",
        "period_end_override",
        "last_info",
        "_forecaster",
        "_last_ts",
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
            self.forecaster_quantile = float(
                params.get("forecaster_quantile", 0.5)
            )
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
            self.forecaster_quantile = 0.5
            self.use_forecaster = False
            self.v_coef = None

        # Constantes físicas
        self.eta_c = lp.ETA_C  # ≈ 0.948683
        self.eta_d = lp.ETA_D
        self.p_max = lp.P_MAX  # 500
        self.e_max = lp.E_MAX  # 2000

        # Historial de carga neta medida: [(timestamp, net_load_kw), ...]
        self.history: list[tuple] = []
        self._last_ts: Optional[pd.Timestamp] = None

        # Previsión neta (se actualiza en _get_forecast)
        self.net_forecast: Optional[np.ndarray] = None

        # Contadores de fallos (diagnóstico)
        self.n_forecast_fail: int = 0
        self.n_fail: int = 0
        self.n_index_shift: int = 0

        # Override para backtest (fin de periodo)
        self.period_end_override: Optional[pd.Timestamp] = None

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
    # Horizonte: fin de periodo desde ts real (correc. 0.7)
    # ------------------------------------------------------------------
    def _horizon(self, ts: pd.Timestamp, preus: list, co2s: list) -> tuple:
        """
        Calcula H y is_end.

        Usa el fin de mes real, o period_end_override si se fija.
        hours_left incluye la hora actual (+1).
        """
        n = min(len(preus), len(co2s))

        # Determinar fin de periodo
        if self.period_end_override is not None:
            period_end = self.period_end_override
        else:
            # Último día del mes de ts a las 23:00
            first_next = ts.replace(day=1) + pd.DateOffset(months=1)
            last_day = first_next - pd.Timedelta(days=1)
            period_end = pd.Timestamp(
                last_day.year, last_day.month, last_day.day, 23, 0, 0,
            )

        hours_left = (period_end - ts).total_seconds() / 3600.0 + 1.0  # +1 incluye t
        hours_left = max(0.0, hours_left)

        H = min(n, 24, int(hours_left))
        is_end = hours_left <= 24 or n < 24

        if H < 1:
            H = 1

        return H, is_end

    # ------------------------------------------------------------------
    # Adaptador de cuantiles (correc. 0.11)
    # ------------------------------------------------------------------
    def _interp_quantile(self, pred: Union[np.ndarray, dict]) -> np.ndarray:
        """
        Si pred es dict con p10, p50, p90 interpola en self.forecaster_quantile.
        Si es ndarray, lo devuelve tal cual.
        """
        if isinstance(pred, dict):
            keys = sorted(pred.keys())

            def _parse_q(k):
                """Extrai el valor de quantile d'una clau: 'p10' → 0.1, '0.5' → 0.5."""
                ks = str(k)
                if ks.startswith("p"):
                    return float(ks[1:]) / 100.0
                return float(ks)

            q = self.forecaster_quantile
            # Recortar a [0.1, 0.9]
            q_clamped = max(0.1, min(0.9, q))

            # Construir parells (quantile, clau) i ordenar
            kv_pairs = [(_parse_q(k), k) for k in keys]
            kv_pairs.sort(key=lambda x: x[0])

            # Trobar quantils veïns
            lower_key = None
            upper_key = None
            for q_val, k in kv_pairs:
                if q_val <= q_clamped:
                    lower_key = k
                if upper_key is None and q_val >= q_clamped:
                    upper_key = k
                    break

            if lower_key is None:
                # q < tots: recortar al menor
                result = np.full(len(pred[kv_pairs[0][1]]), float(pred[kv_pairs[0][1]]))
            elif upper_key is None:
                # q > tots: recortar al major
                result = np.full(len(pred[kv_pairs[-1][1]]), float(pred[kv_pairs[-1][1]]))
            elif lower_key == upper_key:
                # Exacte
                result = np.array(pred[lower_key], dtype=np.float64)
            else:
                # Interpolació lineal
                lower_val = np.array(pred[lower_key], dtype=np.float64)
                upper_val = np.array(pred[upper_key], dtype=np.float64)
                lower_q = _parse_q(lower_key)
                upper_q = _parse_q(upper_key)
                if abs(upper_q - lower_q) < 1e-12:
                    result = lower_val
                else:
                    frac = (q_clamped - lower_q) / (upper_q - lower_q)
                    result = lower_val + frac * (upper_val - lower_val)

            return result

        return np.asarray(pred, dtype=np.float64)

    # ------------------------------------------------------------------
    # Generador de previsión de carga neta (correc. 0.11)
    # ------------------------------------------------------------------
    def _get_forecast(
        self,
        obs: dict,
        horizon: int,
    ) -> Optional[np.ndarray]:
        """
        Pide la previsión al generador y la adapta.
        """
        if not self.use_forecaster or self._forecaster is None:
            return None

        try:
            pred = self._forecaster.predict(obs, self.history, horizon)

            if pred is None or len(pred) == 0:
                self.n_forecast_fail += 1
                return None

            # Interpolar cuantiles si es dict
            pred = self._interp_quantile(pred)

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

        # ------------------------------------------------------------------
        # 0.9: Historial: (ts - 1h, N_medida), validado
        # ------------------------------------------------------------------
        try:
            nova = obs.get("noves_dades_5min", {})
            last_load = float(nova.get("ultim_consum_kw", 0.0))
            last_pv = float(nova.get("ultima_solar_kw", 0.0))
            last_net = max(0.0, last_load - last_pv)

            # Marcamos como no válida si:
            # - es la primera llamada del agente
            # - salto de más de 1h desde el último ts registrado
            # - consumo y solar son ambos exactamente 0
            valid = True
            if self._last_ts is None:
                valid = False  # primera llamada
            else:
                diff = abs((ts - self._last_ts).total_seconds())
                if diff > 3600.0 + 1:  # salto > 1h
                    valid = False
            if last_load == 0.0 and last_pv == 0.0:
                valid = False

            if valid:
                self.history.append((ts - pd.Timedelta(hours=1), last_net))
            self._last_ts = ts
        except Exception:
            pass

        # ------------------------------------------------------------------
        # 0.10: Guard del índice 0
        # ------------------------------------------------------------------
        preus_raw = obs.get("preus_properes_24h", [])
        co2s_raw = obs.get("co2_properes_24h", [])

        preu_actual = float(obs.get("preu_actual", 0.0))
        co2_actual = float(obs.get("co2_actual", 0.0))

        shift_detected = False
        if len(preus_raw) > 0 and len(co2s_raw) > 0:
            if (abs(preus_raw[0] - preu_actual) > 1e-9
                    or abs(co2s_raw[0] - co2_actual) > 1e-9):
                shift_detected = True
                self.n_index_shift += 1
                # Anteponer preu_actual y co2_actual
                preus = [preu_actual] + list(preus_raw[:23])
                co2s = [co2_actual] + list(co2s_raw[:23])
            else:
                preus = list(preus_raw[:24])
                co2s = list(co2s_raw[:24])
        else:
            preus = []
            co2s = []

        # ------------------------------------------------------------------
        # 2. Calcular H y is_end (desde mes real)
        # ------------------------------------------------------------------
        H, is_end = self._horizon(ts, preus, co2s)

        # ------------------------------------------------------------------
        # 3. Calcular pesos w'
        # ------------------------------------------------------------------
        w = lp.compute_weights(
            np.asarray(co2s[:H], dtype=np.float64),
            np.asarray(preus[:H], dtype=np.float64),
            self.kappa,
            w_co2=self.w_co2,
            w_cost=self.w_cost,
        )

        # ------------------------------------------------------------------
        # 4. Calcular V
        # ------------------------------------------------------------------
        V = self._terminal_value(w, is_end)

        # ------------------------------------------------------------------
        # 5. Obtener previsión de carga neta
        # ------------------------------------------------------------------
        net = self._get_forecast(obs, H)

        # ------------------------------------------------------------------
        # 6. Resolver LP
        # ------------------------------------------------------------------
        x = lp.solve_lp(
            w,
            s0=soc0,
            V=V,
            net=net,
            eps=self.eps,
            delta=self.delta,
        )

        # ------------------------------------------------------------------
        # 7. Extraer P = c_0 - d_0 y recortar
        # ------------------------------------------------------------------
        if x is not None and len(x) >= 2:
            P = float(x[0]) - float(x[H])  # c_0 - d_0
            P = lp.clip_consigna(P, soc0, self.eps)
        else:
            P = 0.0

        # ------------------------------------------------------------------
        # 8. Registrar info de diagnóstico
        # ------------------------------------------------------------------
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
            "n_index_shift": self.n_index_shift,
        }

        return P