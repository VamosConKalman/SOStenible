"""
environment.py — Mock del simulador CampusBatteryEnv para tests.

Imita la interfaz del entorno real sin usar las dependencias completas.
Permite ejecutar tests deterministas sin cargar todos los datos de train.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Optional


class CampusBatteryEnv:
    """Entorno mock para testear BatteryAgent."""

    __slots__ = (
        "_soc_init",
        "df",
        "n",
        "t",
        "soc",
        "cap",
        "power",
        "eta_c",
        "eta_d",
        "soc_min",
        "soc_max",
        "soc_series",
        "actions",
        "grid",
        "clipped",
        "violations",
        "infraccions_per_step",
    )

    def __init__(
        self,
        hourly_data: pd.DataFrame,
        cap: float = 2000.0,
        power: float = 500.0,
        eta: float = 0.9,
        soc_pct: float = 0.5,
    ):
        self._soc_init = soc_pct * cap
        self.df = hourly_data.copy().reset_index(drop=True)
        self.n = len(self.df)

        self.cap = cap
        self.power = power
        self.eta_c = eta ** 0.5
        self.eta_d = eta ** 0.5
        self.soc_min = 0.0
        self.soc_max = cap

        self.soc = self._soc_init
        self.t = 0

        self.soc_series: list[float] = []
        self.actions: list[float] = []
        self.grid: list[float] = []
        self.clipped: int = 0
        self.violations: int = 0
        self.infraccions_per_step: list[int] = []

    def reset(self) -> dict:
        """Reinicia y devuelve la observación inicial."""
        self.t = 0
        self.soc = self._soc_init
        self.soc_series = []
        self.actions = []
        self.grid = []
        self.clipped = 0
        self.violations = 0
        self.infraccions_per_step = []
        return self._get_obs()

    def _get_obs(self) -> dict:
        if self.t >= self.n:
            return None

        row = self.df.iloc[self.t]
        ts = row["Fecha"] if "Fecha" in self.df.columns else pd.Timestamp(
            "2026-01-01"
        ) + pd.Timedelta(hours=self.t)

        h_end = min(self.t + 24, self.n)

        future_prices: list = []
        future_co2: list = []
        if "precio_eur_per_kwh" in self.df.columns:
            future_prices = (
                self.df["precio_eur_per_kwh"]
                .iloc[self.t:h_end]
                .tolist()
            )
        if "co2_kg_per_kwh" in self.df.columns:
            future_co2 = (
                self.df["co2_kg_per_kwh"]
                .iloc[self.t:h_end]
                .tolist()
            )

        last_load = (
            float(self.df["load_kw"].iloc[self.t - 1])
            if self.t > 0 and "load_kw" in self.df.columns
            else 0.0
        )
        last_pv = (
            float(self.df["pv_kw"].iloc[self.t - 1])
            if self.t > 0 and "pv_kw" in self.df.columns
            else 0.0
        )

        current_price = (
            float(self.df["precio_eur_per_kwh"].iloc[self.t])
            if "precio_eur_per_kwh" in self.df.columns
            else 0.0
        )
        current_co2 = (
            float(self.df["co2_kg_per_kwh"].iloc[self.t])
            if "co2_kg_per_kwh" in self.df.columns
            else 0.0
        )

        return {
            "timestamp": ts,
            "hour": ts.hour,
            "day_of_week": ts.dayofweek,
            "soc_kwh": float(self.soc),
            "soc_pct": float(self.soc / self.cap),
            "preu_actual": current_price,
            "co2_actual": current_co2,
            "preus_properes_24h": future_prices,
            "co2_properes_24h": future_co2,
            "noves_dades_5min": {
                "ultim_consum_kw": last_load,
                "ultima_solar_kw": last_pv,
            },
        }

    def step(self, action_kw: float) -> tuple[dict | None, bool]:
        """
        Aplica la acción y avanza 1 hora.

        Devuelve (next_obs, done).
        """
        p_req = float(action_kw)
        self.actions.append(p_req)
        infr_now = 0

        # 1. Clip a [−P_MAX, P_MAX]
        p = np.clip(p_req, -self.power, self.power)
        if p != p_req:
            self.clipped += 1
            infr_now += 1

        # 2. Dinámica del SOC
        if p > 0:  # carga
            max_c = (self.soc_max - self.soc) / (self.eta_c)
            p_actual = min(p, max(0.0, max_c))
            if p_actual < p:
                self.clipped += 1
                infr_now += 1
            self.soc += p_actual * self.eta_c
        elif p < 0:  # descarga
            max_d = (self.soc - self.soc_min) * self.eta_d
            p_actual = -min(-p, max(0.0, max_d))
            if abs(p_actual - p) > 1e-6:
                self.clipped += 1
                infr_now += 1
            self.soc += p_actual / self.eta_d
        else:
            p_actual = 0.0

        if self.soc < self.soc_min - 1e-6 or self.soc > self.soc_max + 1e-6:
            self.violations += 1
            infr_now += 1
        self.soc = float(np.clip(self.soc, self.soc_min, self.soc_max))
        self.soc_series.append(self.soc)
        self.infraccions_per_step.append(infr_now)

        # 3. Balanço de xarxa
        load = float(self.df["load_kw"].iloc[self.t]) if "load_kw" in self.df.columns else 500.0
        pv = float(self.df["pv_kw"].iloc[self.t]) if "pv_kw" in self.df.columns else 0.0

        net = load - pv + p_actual
        if net > 0:
            self.grid.append(net)
        else:
            self.grid.append(0.0)

        self.t += 1
        done = self.t >= self.n
        next_obs = None if done else self._get_obs()

        return next_obs, done

    def evaluate_results(
        self,
        alpha: float = 0.7,
        beta: float = 0.3,
    ) -> dict:
        """Calcula el score oficial."""
        grid = np.asarray(self.grid)
        price = (
            self.df["precio_eur_per_kwh"].values[: len(grid)]
            if "precio_eur_per_kwh" in self.df.columns
            else np.ones(len(grid)) * 0.1
        )
        co2 = (
            self.df["co2_kg_per_kwh"].values[: len(grid)]
            if "co2_kg_per_kwh" in self.df.columns
            else np.ones(len(grid)) * 0.07
        )

        load = (
            self.df["load_kw"].values[: len(grid)]
            if "load_kw" in self.df.columns
            else np.ones(len(grid)) * 500.0
        )
        pv = (
            self.df["pv_kw"].values[: len(grid)]
            if "pv_kw" in self.df.columns
            else np.zeros(len(grid))
        )

        base_grid = np.maximum(load - pv, 0.0)

        cost_participant = float(np.sum(grid * price))
        co2_participant = float(np.sum(grid * co2))
        cost_base = float(np.sum(base_grid * price))
        co2_base = float(np.sum(base_grid * co2))

        d_co2 = (co2_base - co2_participant) / co2_base if co2_base > 0 else 0.0
        d_cost = (cost_base - cost_participant) / cost_base if cost_base > 0 else 0.0

        infraccions = int(self.clipped + self.violations)
        penalties = 1.0 * infraccions  # 1 pt per infracció (plan §7.2)
        score = alpha * d_co2 + beta * d_cost - penalties

        return {
            "score": round(max(0.0, score * 100), 2),
            "co2_estalviat_pct": round(d_co2 * 100, 2),
            "cost_estalviat_pct": round(d_cost * 100, 2),
            "co2_estalviat_kg": round(co2_base - co2_participant, 1),
            "cost_estalviat_eur": round(cost_base - cost_participant, 2),
            "co2_participant_kg": round(co2_participant, 1),
            "cost_participant_eur": round(cost_participant, 2),
            "co2_baseline_kg": round(co2_base, 1),
            "cost_baseline_eur": round(cost_base, 2),
            "infraccions": infraccions,
        }


def run_agent_simulation(
    agent,
    hourly_data: pd.DataFrame,
    cap: float = 2000.0,
    power: float = 500.0,
    eta: float = 0.9,
    soc_pct: float = 0.5,
) -> dict:
    """Ejecuta un agente completo sobre los datos proporcionados."""
    env = CampusBatteryEnv(hourly_data, cap, power, eta, soc_pct)
    obs = env.reset()
    done = False
    while not done:
        action = agent.act(obs)
        obs, done = env.step(action)
    return env.evaluate_results()