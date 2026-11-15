"""
agent.py — BatteryAgent orquestador (MPC con LP HiGHS).

Flujo por hora:
  1. Parsear obs y validar la medida de t-1 (noves_dades_5min)
  2. Alinear los vectores de precio y CO2 (detección robusta de desfase)
  3. Calcular H, w' y V
  4. Previsión de carga neta: generador (si está activo) o, si no,
     regla de corte / persistencia a partir de la medida de t-1
  5. Resolver LP → P = c_0 - d_0, recortar y devolver
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Optional, Any, Union

import numpy as np
import pandas as pd

import lp_model as lp
from forecaster_base import NetLoadForecaster

ONE_HOUR = pd.Timedelta(hours=1)

# Detección de vectores desplazados (índice 0 = t+1 en vez de t)
SHIFT_ABS_TOL = 1e-4      # diferencia mínima absoluta para contar una hora como desfasada
SHIFT_REL_TOL = 1e-3      # ... o relativa al valor
SHIFT_MIN_OBS = 6         # llamadas mínimas antes de decidir
SHIFT_MAJORITY = 0.5      # fracción de horas desfasadas para activar el desplazamiento


def _to_float_or_none(x) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _differs(a: float, b: float) -> bool:
    return abs(a - b) > max(SHIFT_ABS_TOL, SHIFT_REL_TOL * abs(b))


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
        "use_measured_net",
        "month_end_horizon",
        "terminal_value",
        "eta_c",
        "eta_d",
        "p_max",
        "e_max",
        "net_forecast",
        "history",
        "n_forecast_fail",
        "n_fail",
        "n_index_shift",
        "n_cortes",
        "n_persist",
        "period_end_override",
        "last_info",
        "_forecaster",
        "_last_ts",
        "_shift_seen",
        "_shift_bad",
        "_shift_on",
    )

    # ------------------------------------------------------------------
    # Constructor
    # ------------------------------------------------------------------
    def __init__(self):
        self._path = Path(__file__).parent

        # Valores por defecto (se usan si falta parametres.json o una clave)
        self.kappa = 0.587335
        self.q = 0.3
        self.eps = 0.5
        self.delta = 1e-6
        self.w_co2 = 0.7
        self.w_cost = 0.3
        self.forecaster_quantile = 0.3
        self.use_forecaster = False
        self.use_measured_net = True
        self.month_end_horizon = False   # cortar H y forzar V=0 a fin de mes (el starter kit no lo hace)
        self.terminal_value = False      # valor terminal V > 0 (el starter kit no lo usa)
        self.v_coef = None

        try:
            with open(self._path / "parametres.json", "r") as f:
                params = json.load(f)
            self.kappa = float(params.get("kappa", self.kappa))
            self.q = float(params.get("q", self.q))
            self.eps = float(params.get("eps", self.eps))
            self.delta = float(params.get("delta", self.delta))
            self.w_co2 = float(params.get("w_co2", self.w_co2))
            self.w_cost = float(params.get("w_cost", self.w_cost))
            self.forecaster_quantile = float(
                params.get("forecaster_quantile", self.forecaster_quantile)
            )
            self.use_forecaster = bool(params.get("use_forecaster", False))
            self.use_measured_net = bool(params.get("use_measured_net", True))
            self.month_end_horizon = bool(params.get("month_end_horizon", False))
            self.terminal_value = bool(params.get("terminal_value", False))
            v_coef_raw = params.get("v_coef")
            self.v_coef = (
                tuple(float(v) for v in v_coef_raw)
                if v_coef_raw is not None
                else None
            )
        except Exception:
            pass

        # Constantes físicas
        self.eta_c = lp.ETA_C
        self.eta_d = lp.ETA_D
        self.p_max = lp.P_MAX
        self.e_max = lp.E_MAX

        # Historial de medidas válidas: [(ts_inicio_hora, load_kw, pv_kw), ...]
        self.history: list = []
        self._last_ts: Optional[pd.Timestamp] = None

        self.net_forecast: Optional[np.ndarray] = None

        # Contadores (diagnóstico)
        self.n_forecast_fail = 0
        self.n_fail = 0
        self.n_index_shift = 0
        self.n_cortes = 0
        self.n_persist = 0

        # Estado de la detección de vectores desplazados
        self._shift_seen = 0
        self._shift_bad = 0
        self._shift_on = False

        # Override para backtest (fin de periodo); nunca lo fija el obs
        self.period_end_override: Optional[pd.Timestamp] = None

        self.last_info: dict = {}

        self._forecaster: Optional[NetLoadForecaster] = None
        if self.use_forecaster:
            self._load_forecaster()

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
    # Horizonte: fin de periodo desde ts real
    # ------------------------------------------------------------------
    def _horizon(self, ts: pd.Timestamp, preus: list, co2s: list) -> tuple:
        n = min(len(preus), len(co2s))

        if self.period_end_override is not None:
            period_end = self.period_end_override
        elif self.month_end_horizon:
            first_next = ts.replace(day=1) + pd.DateOffset(months=1)
            last_day = first_next - pd.Timedelta(days=1)
            period_end = pd.Timestamp(
                last_day.year, last_day.month, last_day.day, 23, 0, 0,
            )
        else:
            # Como el starter kit: el horizonte lo marca la longitud de los vectores
            H = max(1, min(n, 24))
            return H, n < 24

        hours_left = (period_end - ts).total_seconds() / 3600.0 + 1.0
        hours_left = max(0.0, hours_left)

        H = min(n, 24, int(hours_left))
        is_end = hours_left <= 24 or n < 24
        if H < 1:
            H = 1
        return H, is_end

    # ------------------------------------------------------------------
    # Adaptador de formatos del generador
    # ------------------------------------------------------------------
    def _reduce_forecast(self, pred: Union[np.ndarray, dict]) -> np.ndarray:
        """Convierte puntual / cuantiles / escenarios en un único vector N̂."""
        q = self.forecaster_quantile

        if isinstance(pred, dict) and "scenarios" in pred:
            S = np.atleast_2d(np.asarray(pred["scenarios"], dtype=np.float64))
            n_s = S.shape[0]
            p = pred.get("probs")
            p = (np.full(n_s, 1.0 / n_s) if p is None
                 else np.clip(np.asarray(p, dtype=np.float64).reshape(-1), 0.0, None))
            if p.size != n_s or not np.isfinite(p).all() or p.sum() <= 0:
                p = np.full(n_s, 1.0 / n_s)
            p = p / p.sum()
            out = np.full(S.shape[1], np.nan)
            for k in range(S.shape[1]):
                col = S[:, k]
                ok = np.isfinite(col)
                if not ok.any():
                    continue
                order = np.argsort(col[ok])
                vals, pk = col[ok][order], p[ok][order]
                cum = np.cumsum(pk) / pk.sum()
                idx = int(np.searchsorted(cum, q - 1e-12))
                out[k] = vals[min(idx, len(vals) - 1)]
            return out

        if isinstance(pred, dict):
            levels, arrays = [], []
            for key, val in pred.items():
                ks = str(key)
                try:
                    lev = float(ks[1:]) / 100.0 if ks.startswith("p") else float(ks)
                except ValueError:
                    continue
                levels.append(lev)
                arrays.append(np.asarray(val, dtype=np.float64).reshape(-1))
            if not levels:
                raise ValueError("dict sin cuantiles reconocibles")
            order = np.argsort(levels)
            lv = np.asarray(levels)[order]
            M = np.vstack([arrays[i] for i in order])          # (n_niveles, H)
            qq = min(max(q, lv[0]), lv[-1])                     # recorte al rango presente
            return np.array([np.interp(qq, lv, M[:, k]) for k in range(M.shape[1])])

        return np.asarray(pred, dtype=np.float64).reshape(-1)

    _interp_quantile = _reduce_forecast   # nombre antiguo (tests)

    def _get_forecast(self, obs: dict, horizon: int) -> Optional[np.ndarray]:
        if not self.use_forecaster or self._forecaster is None:
            return None
        try:
            pred = self._forecaster.predict(obs, self.history, horizon)
            if pred is None:
                self.n_forecast_fail += 1
                return None
            vec = self._reduce_forecast(pred)
            if vec.size == 0:
                self.n_forecast_fail += 1
                return None
            out = np.full(horizon, np.inf, dtype=np.float64)
            n = min(horizon, vec.size)
            out[:n] = vec[:n]
            out[~np.isfinite(out)] = np.inf
            if not np.isfinite(out).any():
                return None
            return out
        except Exception:
            self.n_forecast_fail += 1
            return None

    # ------------------------------------------------------------------
    def _terminal_value(self, w: np.ndarray, is_end: bool) -> float:
        if not self.terminal_value:
            return 0.0
        return lp.compute_terminal_value(w, is_end, self.q, self.v_coef)

    # ------------------------------------------------------------------
    # Medida de la hora anterior
    # ------------------------------------------------------------------
    def _read_measure(self, obs: dict, ts: pd.Timestamp) -> tuple:
        """Devuelve (load, pv) de t-1 si la medida es válida, o None.

        Válida = noves_dades_5min es un dict con ambos valores numéricos y
        finitos (sin valores por defecto) y la llamada anterior fue ts - 1h.
        """
        prev_ts = self._last_ts
        self._last_ts = ts
        if prev_ts is None or ts - prev_ts != ONE_HOUR:
            return None
        nd = obs.get("noves_dades_5min")
        if not isinstance(nd, dict):
            return None
        load = _to_float_or_none(nd.get("ultim_consum_kw"))
        pv = _to_float_or_none(nd.get("ultima_solar_kw"))
        if load is None or pv is None:
            return None
        return load, pv

    # ------------------------------------------------------------------
    # Vectores de precio y CO2 alineados con la hora t
    # ------------------------------------------------------------------
    def _aligned_vectors(self, obs: dict) -> tuple:
        preus = [float(x) for x in obs.get("preus_properes_24h", [])][:24]
        co2s = [float(x) for x in obs.get("co2_properes_24h", [])][:24]
        pa = _to_float_or_none(obs.get("preu_actual"))
        ca = _to_float_or_none(obs.get("co2_actual"))

        if preus and co2s and pa is not None and ca is not None:
            if not self._shift_on:
                self._shift_seen += 1
                if _differs(preus[0], pa) and _differs(co2s[0], ca):
                    self._shift_bad += 1
                if (self._shift_seen >= SHIFT_MIN_OBS
                        and self._shift_bad > SHIFT_MAJORITY * self._shift_seen):
                    self._shift_on = True
            if self._shift_on:
                self.n_index_shift += 1
                preus = [pa] + preus[:23]
                co2s = [ca] + co2s[:23]
        return preus, co2s

    # ------------------------------------------------------------------
    # act()
    # ------------------------------------------------------------------
    def act(self, obs: dict) -> float:
        try:
            return float(self._act(obs))
        except Exception:
            self.n_fail += 1
            self.last_info["error"] = "exception"
            return 0.0

    def _act(self, obs: dict) -> float:
        ts = pd.Timestamp(obs["timestamp"])
        soc0 = float(obs["soc_kwh"])

        # 1. Medida de t-1 e historial
        meas = self._read_measure(obs, ts)
        in_corte = meas is not None and meas[0] == 0.0 and meas[1] == 0.0
        if meas is not None and not in_corte:
            self.history.append((ts - ONE_HOUR, meas[0], meas[1]))

        # 2. Precio y CO2 alineados
        preus, co2s = self._aligned_vectors(obs)

        # 3. H, w', V
        H, is_end = self._horizon(ts, preus, co2s)
        w = lp.compute_weights(
            np.asarray(co2s[:H], dtype=np.float64),
            np.asarray(preus[:H], dtype=np.float64),
            self.kappa,
            w_co2=self.w_co2,
            w_cost=self.w_cost,
        )
        V = self._terminal_value(w, is_end)

        # 4. Previsión de carga neta
        net = self._get_forecast(obs, H)
        source = "forecast" if net is not None else "v1"
        if self.use_measured_net and meas is not None:
            if in_corte:
                # Corte de datos: el simulador puntúa la hora con carga neta 0
                if net is None:
                    net = np.full(H, np.inf, dtype=np.float64)
                net[0] = 0.0
                self.n_cortes += 1
                source = "corte"
            elif net is None:
                # Persistencia: N̂_k = N_{t-1} (sin recortar)
                net = np.full(H, meas[0] - meas[1], dtype=np.float64)
                self.n_persist += 1
                source = "persistencia"

        # 5. LP
        x = lp.solve_lp(w, s0=soc0, V=V, net=net, eps=self.eps, delta=self.delta)
        if x is not None and len(x) >= 2:
            P = float(x[0]) - float(x[H])
            P = lp.clip_consigna(P, soc0, self.eps)
        else:
            P = 0.0

        self.last_info = {
            "H": H,
            "V": round(V, 6),
            "is_end": is_end,
            "mode": source,
            "P": round(P, 2),
            "soc": round(soc0, 2),
            "net_provided": net is not None,
            "n_forecast_fail": self.n_forecast_fail,
            "n_fail": self.n_fail,
            "n_index_shift": self.n_index_shift,
            "n_cortes": self.n_cortes,
            "n_persist": self.n_persist,
        }
        return P
