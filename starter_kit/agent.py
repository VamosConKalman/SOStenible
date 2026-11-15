"""
agent.py — BatteryAgent amb model LP (HiGHS via scipy)
Model MPC: cada crida a act(obs) resol un LP sobre les properes H hores
i aplica només la primera consigna.
"""

import json
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.optimize import linprog


class BatteryAgent:
    """Agent de control de bateria basat en Programació Lineal (LP)."""

    # ------------------------------------------------------------------
    # Constructor
    # ------------------------------------------------------------------
    def __init__(self):
        self._path = Path(__file__).parent
        params_path = self._path / "parametres.json"

        with open(params_path, "r") as f:
            self._params = json.load(f)

        self.kappa = float(self._params["kappa"])
        self.quantile_q = float(self._params["q"])
        self.eps = float(self._params["eps"])

        self.eta_c = 0.9 ** 0.5  # ≈ 0.948683
        self.eta_d = 0.9 ** 0.5
        self.P_max = 500.0
        self.E_max = 2000.0

        # Previsió neta opcional (la aporta un component extern)
        self.net_forecast: Optional[np.ndarray] = None

    # ------------------------------------------------------------------
    # Helpers del LP
    # ------------------------------------------------------------------
    def _horizon(self, obs: dict) -> tuple:
        """Retorna (H, is_end_of_week)."""
        raw = obs.get("preus_properes_24h", [])
        H = min(len(raw), 24)

        is_end = False
        try:
            ts = pd.Timestamp(obs["timestamp"])
            end_ts = ts + pd.Timedelta(hours=H)
            is_end = (end_ts.dayofweek == 0 and end_ts.hour == 0)
        except Exception:
            pass

        return H, is_end

    def _build_weights(self, co2: list, price: list) -> np.ndarray:
        """
        W'_k = 0.7·co2_k + 0.3·kappa·price_k
        """
        co2_arr = np.asarray(co2, dtype=np.float64)
        price_arr = np.asarray(price, dtype=np.float64)
        return 0.7 * co2_arr + 0.3 * self.kappa * price_arr

    # ------------------------------------------------------------------
    # Variant v1: sense previsió de càrrega neta
    # ------------------------------------------------------------------
    def _build_lp_v1(
        self, H: int, w: np.ndarray, soc0: float, is_end: bool
    ) -> tuple:
        m = 3 * H  # c, d, s

        # --- Cost ---
        # grid_k = load_k - pv_k + c_k - d_k (P_actual = c_k - d_k)
        # objective: min w · grid_k = w · (load - pv + c - d)
        # load - pv constant → min w · (c_k - d_k)
        c_vec = np.zeros(m, dtype=np.float64)
        c_vec[0:H] = w            # c: +w_k
        c_vec[H:2 * H] = -w       # d: -w_k
        # s_H no té valor terminal (no es puntua energia sobrant)
        # c_vec[2 * H - 1] = 0

        # --- A_eq: dinàmica SOC (R1) ---
        rows, cols = H, m
        ijs_i, ijs_j, ijs_v = [], [], []

        for k in range(H):
            # s_{k+1}
            ijs_i.append(k); ijs_j.append(2 * H + k); ijs_v.append(1.0)
            if k >= 1:
                # -s_k
                ijs_i.append(k); ijs_j.append(2 * H + k - 1); ijs_v.append(-1.0)
            # -eta_c * c_k
            ijs_i.append(k); ijs_j.append(k); ijs_v.append(-self.eta_c)
            # +d_k / eta_d
            ijs_i.append(k); ijs_j.append(H + k); ijs_v.append(1.0 / self.eta_d)

        A_eq = sparse.csr_matrix((ijs_v, (ijs_i, ijs_j)), shape=(rows, cols))
        b_eq = np.zeros(H, dtype=np.float64)
        b_eq[0] = soc0

        # --- A_ub: cap (només A_eq i cotas) ---
        A_ub = sparse.csr_matrix((0, m), dtype=np.float64)
        b_ub = np.zeros(0, dtype=np.float64)

        # --- Bounds ---
        bounds: list[tuple] = []
        bounds.extend([(0.0, self.P_max)] * H)  # c
        bounds.extend([(0.0, self.P_max)] * H)  # d
        s_lo = self.eps
        s_hi = self.E_max - self.eps
        if soc0 < self.eps:
            s_lo = 0.0
        if soc0 > self.E_max - self.eps:
            s_hi = self.E_max
        bounds.extend([(s_lo, s_hi)] * H)  # s

        return c_vec, A_eq, b_eq, A_ub, b_ub, bounds

    # ------------------------------------------------------------------
    # Variant completa: amb net_forecast
    # ------------------------------------------------------------------
    def _build_lp_full(
        self, H: int, w: np.ndarray, soc0: float, is_end: bool
    ) -> tuple:
        m = 4 * H  # c, d, s, g

        # --- Cost ---
        c_vec = np.zeros(m, dtype=np.float64)
        # c i d: cost 0 (g absorbeix el cost de grid)
        # s: s_H (sense valor terminal)
        # g: cost w_k (grid energy)
        c_vec[3 * H:4 * H] = w

        # --- A_eq: dinàmica SOC (R1) ---
        rows_eq = H
        cols_eq = m
        ijs_i: List[int] = []
        ijs_j: List[int] = []
        ijs_v: List[float] = []

        for k in range(H):
            ijs_i.append(k); ijs_j.append(2 * H + k); ijs_v.append(1.0)
            if k >= 1:
                ijs_i.append(k); ijs_j.append(2 * H + k - 1); ijs_v.append(-1.0)
            ijs_i.append(k); ijs_j.append(k); ijs_v.append(-self.eta_c)
            ijs_i.append(k); ijs_j.append(H + k); ijs_v.append(1.0 / self.eta_d)

        A_eq = sparse.csr_matrix((ijs_v, (ijs_i, ijs_j)), shape=(rows_eq, cols_eq))
        b_eq = np.zeros(H, dtype=np.float64)
        b_eq[0] = soc0

        # --- A_ub: R2 c_k - d_k - g_k ≤ -N̂_k (per N̂_k < P_max) ---
        N_hat = self.net_forecast
        n_ub = 0
        if N_hat is not None and len(N_hat) > 0:
            for k in range(H):
                if k < len(N_hat) and N_hat[k] < self.P_max:
                    n_ub += 1

        if n_ub > 0:
            A_ub = sparse.lil_matrix((n_ub, m), dtype=np.float64)
            b_ub_vals = np.empty(n_ub, dtype=np.float64)
            row = 0
            for k in range(H):
                if N_hat is not None and k < len(N_hat) and N_hat[k] < self.P_max:
                    A_ub[row, k] = 1.0            # +c_k
                    A_ub[row, H + k] = -1.0       # -d_k
                    A_ub[row, 3 * H + k] = -1.0   # -g_k
                    b_ub_vals[row] = -N_hat[k]
                    row += 1
            A_ub = A_ub.tocsr()
        else:
            A_ub = sparse.csr_matrix((0, m), dtype=np.float64)
            b_ub_vals = np.array([], dtype=np.float64)

        # --- Bounds ---
        bounds: list[tuple] = []
        bounds.extend([(0.0, self.P_max)] * H)  # c
        bounds.extend([(0.0, self.P_max)] * H)  # d
        s_lo = self.eps
        s_hi = self.E_max - self.eps
        bounds.extend([(s_lo, s_hi)] * H)  # s
        bounds.extend([(0.0, None)] * H)   # g

        return c_vec, A_eq, b_eq, A_ub, b_ub_vals, bounds

    # ------------------------------------------------------------------
    # Solver
    # ------------------------------------------------------------------
    def _solve(
        self, c_vec, A_eq, b_eq, A_ub, b_ub, bounds
    ):
        res = linprog(
            c_vec,
            A_ub=A_ub, b_ub=b_ub,
            A_eq=A_eq, b_eq=b_eq,
            bounds=bounds,
            method="highs",
        )
        if res.success:
            return res.x
        return None

    # ------------------------------------------------------------------
    # Clip físic
    # ------------------------------------------------------------------
    def _clip(self, P: float, soc: float) -> float:
        eps = self.eps
        lo = max(0.0, soc - eps)
        hi = self.E_max - soc - eps

        max_charge = min(self.P_max, hi / self.eta_c if hi > 0 else 0.0)
        max_discharge = min(self.P_max, lo * self.eta_d if lo > 0 else 0.0)

        return float(np.clip(P, -max_discharge, max_charge))

    # ------------------------------------------------------------------
    # Interfície pública
    # ------------------------------------------------------------------
    def act(self, obs: dict, net_forecast: Optional[np.ndarray] = None) -> float:
        try:
            if net_forecast is not None:
                self.net_forecast = np.asarray(net_forecast, dtype=np.float64)

            ts = pd.Timestamp(obs["timestamp"])

            preus = obs.get("preus_properes_24h", [])
            co2s = obs.get("co2_properes_24h", [])

            soc0 = float(obs["soc_kwh"])
            H, is_end = self._horizon(obs)
            w = self._build_weights(co2s[:H], preus[:H])

            has_forecast = (
                self.net_forecast is not None
                and len(self.net_forecast) > 0
            )

            if has_forecast:
                c_vec, A_eq, b_eq, A_ub, b_ub, bounds = self._build_lp_full(
                    H, w, soc0, is_end
                )
            else:
                c_vec, A_eq, b_eq, A_ub, b_ub, bounds = self._build_lp_v1(
                    H, w, soc0, is_end
                )

            x = self._solve(c_vec, A_eq, b_eq, A_ub, b_ub, bounds)

            if x is not None:
                P = float(x[0]) - float(x[H])  # c_0 - d_0
                P = self._clip(P, soc0)
                return float(np.clip(P, -500, 500))
            else:
                return 0.0

        except Exception:
            return 0.0