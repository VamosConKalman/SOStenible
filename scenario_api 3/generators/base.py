"""Contracte comú dels generadors d'escenaris.

Qualsevol generador (Monte Carlo gaussià, gradient boosting, híbrid...) rep un GenRequest i
retorna un GenResult. L'API, el k-means i l'avaluació només coneixen aquest contracte.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import joblib
import numpy as np
import pandas as pd

VARS = ("dem", "sol", "price", "co2")       # dem, sol = a simular | price, co2 = previsions conegudes
LOG_VARS = ("price", "co2")                 # es modelen en log (positives)
H_MAX = 24


def to_model(var, x):
    x = np.asarray(x, float)
    return np.log(np.clip(x, 1e-4, None)) if var in LOG_VARS else x


def from_model(var, z):
    return np.exp(z) if var in LOG_VARS else z


@dataclass
class GenRequest:
    """Estat conegut a l'hora t (el moment en què l'agent ha de decidir).

    price_forecast / co2_forecast: previsions t .. t+23 (== obs["preus_properes_24h"], obs["co2_properes_24h"]).
    last_dem / last_sol: demanda i solar mesurades a t-1 (== obs["noves_dades_5min"]).
    Es simulen demanda i solar per a les hores t .. t+horizon-1.
    """
    timestamp: pd.Timestamp
    price_forecast: np.ndarray
    co2_forecast: np.ndarray
    last_dem: float | None = None
    last_sol: float | None = None
    n_paths: int = 1000
    seed: int = 0
    horizon: int | None = None
    history: pd.DataFrame | None = None     # opcional (el GBM de la companya el pot necessitar)

    @classmethod
    def from_obs(cls, obs: dict, n_paths=1000, seed=0, horizon=None, history=None):
        nd = obs.get("noves_dades_5min") or {}
        return cls(timestamp=pd.Timestamp(obs["timestamp"]),
                   price_forecast=np.asarray(obs["preus_properes_24h"], float),
                   co2_forecast=np.asarray(obs["co2_properes_24h"], float),
                   last_dem=nd.get("ultim_consum_kw"), last_sol=nd.get("ultima_solar_kw"),
                   n_paths=n_paths, seed=seed, horizon=horizon, history=history)


@dataclass
class GenResult:
    times: pd.DatetimeIndex                 # t .. t+h-1
    paths: dict                             # {"dem": (n,h), "sol": (n,h)} en kW
    prob: np.ndarray                        # (n,)  suma 1
    known: dict                             # {"price": (h,), "co2": (h,)} (eco de les previsions)
    meta: dict = field(default_factory=dict)

    @property
    def net(self):                          # demanda neta = dem - sol
        return self.paths["dem"] - self.paths["sol"]


class ScenarioGenerator(ABC):
    name = "base"
    horizon_max = H_MAX

    @abstractmethod
    def fit(self, hourly: pd.DataFrame) -> "ScenarioGenerator":
        """hourly: columnes dem, sol, price, co2; index horari (pot tenir forats)."""

    @abstractmethod
    def generate(self, req: GenRequest) -> GenResult:
        """Ha de retornar paths['dem'] i paths['sol'] de forma (n_paths, h) amb h <= horizon_max."""

    def save(self, path):
        joblib.dump(self, path)

    @staticmethod
    def load(path):
        return joblib.load(path)

    def info(self) -> dict:
        return {"name": self.name, "horizon_max": self.horizon_max, **getattr(self, "fit_info", {})}


class MeanModel(ABC):
    """Peça intercanviable: la mitjana esperada de cada variable (espai del model: log per preu/CO2).
    El generador híbrid = MeanModel del GBM + el mateix mostrejador de residus gaussià."""

    @abstractmethod
    def fit(self, hourly: pd.DataFrame) -> "MeanModel": ...

    @abstractmethod
    def predict(self, times: pd.DatetimeIndex, ctx: dict | None = None) -> pd.DataFrame:
        """DataFrame (index=times, columnes=VARS). ctx: previsions conegudes, última observació..."""

    def predict_train(self, times: pd.DatetimeIndex) -> pd.DataFrame:
        """Mitjana sobre el train per calcular residus. Un GBM hauria de retornar prediccions
        out-of-fold perquè els residus no quedin subestimats."""
        return self.predict(times)
