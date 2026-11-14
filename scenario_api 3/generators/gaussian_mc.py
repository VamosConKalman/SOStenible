"""Generador Monte Carlo gaussià (finestres lliscants de 24 h) condicionat a:
   - previsions conegudes de preu i CO2 (t .. t+h-1)
   - última demanda i solar mesurades (t-1)

Model:  x_v(t) = mitjana_v(hora, tipus de dia, mes) + sd_v(hora) * e_v(t)     (v = dem, sol, price*, co2*)  (*en log)
        Finestra  [dem(t-1..t+H-1), sol(t-1..t+H-1), price(t..t+H-1), co2(t..t+H-1)] de e ~ N(0, Sigma)
        Sigma = Ledoit-Wolf sobre totes les finestres lliscants (qualsevol hora d'inici t).
Condicionament gaussià exacte: es mostregen nomes dem i sol de t..t+h-1 donats els coneguts.
"""
import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view
from sklearn.covariance import LedoitWolf

from .base import ScenarioGenerator, GenRequest, GenResult, VARS, H_MAX, to_model, from_model
from .mean_models import SeasonalMeanModel
from .registry import register

SOL_NIGHT_CAP = 1e-3     # kW


def _offsets(H=H_MAX):
    return {"dem": 0, "sol": H + 1, "price": 2 * H + 2, "co2": 3 * H + 2}


def _build_windows(E, H):
    e = {v: E[v].values for v in VARS}
    n = len(E) - H
    dem = sliding_window_view(e["dem"], H + 1)[:n]
    sol = sliding_window_view(e["sol"], H + 1)[:n]
    pr = sliding_window_view(e["price"], H)[1:n + 1]
    co = sliding_window_view(e["co2"], H)[1:n + 1]
    W = np.hstack([dem, sol, pr, co])
    return W[~np.isnan(W).any(axis=1)]


@register("gaussian")
class GaussianMCGenerator(ScenarioGenerator):
    def __init__(self, mean_model=None, condition_known=True, condition_last=True):
        self.mean_model = mean_model or SeasonalMeanModel()
        self.condition_known = condition_known      # condicionar a preu/CO2 coneguts
        self.condition_last = condition_last        # condicionar a dem/sol de t-1

    # ------------------------------------------------------------------ fit
    def fit(self, hourly):
        hourly = hourly[list(VARS)].sort_index()
        full = pd.date_range(hourly.index.min(), hourly.index.max(), freq="h")
        hourly = hourly.reindex(full)                                   # forats -> NaN
        self.mean_model.fit(hourly)
        mu = self.mean_model.predict_train(full)
        Z = pd.DataFrame({v: to_model(v, hourly[v].values) for v in VARS}, index=full)
        R = Z - mu
        sd = R.groupby(R.index.hour).std()
        self.sd = sd.clip(lower=1e-3 * R.std(), axis=1)                 # (24, 4)
        E = R / self.sd.loc[full.hour].values
        W = _build_windows(E, H_MAX)
        self.cov = LedoitWolf(assume_centered=True).fit(W).covariance_
        self.sol_cap = hourly["sol"].groupby(full.hour).max().reindex(range(24)).fillna(0.0)
        self.fit_info = {"n_windows": int(len(W)), "n_hours": int(hourly.dropna().shape[0]),
                         "period": [str(full[0]), str(full[-1])],
                         "mean_model": type(self.mean_model).__name__,
                         "shrinkage_dim": int(self.cov.shape[0]),
                         "versions": {"numpy": np.__version__, "pandas": pd.__version__}}
        return self

    # ------------------------------------------------------------------ generate
    def generate(self, req: GenRequest) -> GenResult:
        h = int(min(req.horizon or H_MAX, H_MAX, len(req.price_forecast), len(req.co2_forecast)))
        t0 = pd.Timestamp(req.timestamp).floor("h")
        times = t0 + pd.to_timedelta(np.arange(h), "h")
        ext = t0 + pd.to_timedelta(np.arange(-1, h), "h")                # t-1 .. t+h-1
        mu = self.mean_model.predict(ext, ctx={"price": req.price_forecast, "co2": req.co2_forecast,
                                               "last_dem": req.last_dem, "last_sol": req.last_sol})
        sd = self.sd.loc[ext.hour.values]
        o = _offsets()
        idx = {v: o[v] + np.arange(h + 1) for v in ("dem", "sol")}
        idx.update({v: o[v] + np.arange(h) for v in ("price", "co2")})

        unk = np.concatenate([idx["dem"][1:], idx["sol"][1:]])
        kidx, kval = [], []
        if self.condition_known:
            for v, fc in (("price", req.price_forecast), ("co2", req.co2_forecast)):
                z = (to_model(v, fc[:h]) - mu[v].values[1:]) / sd[v].values[1:]
                kidx.append(idx[v]); kval.append(z)
        if self.condition_last:
            for v, last in (("dem", req.last_dem), ("sol", req.last_sol)):
                if last is not None:
                    kidx.append(idx[v][:1]); kval.append(np.array([(float(last) - mu[v].values[0]) / sd[v].values[0]]))
        S = self.cov
        Suu = S[np.ix_(unk, unk)]
        if kidx:
            k = np.concatenate(kidx); zk = np.concatenate(kval)
            Skk = S[np.ix_(k, k)] + 1e-8 * np.eye(len(k))
            Suk = S[np.ix_(unk, k)]
            G = np.linalg.solve(Skk, Suk.T)
            mu_c, S_c = G.T @ zk, Suu - Suk @ G
        else:
            mu_c, S_c = np.zeros(len(unk)), Suu
        w, V = np.linalg.eigh((S_c + S_c.T) / 2)
        L = V * np.sqrt(np.clip(w, 0, None))
        rng = np.random.default_rng(req.seed)
        zs = mu_c + rng.standard_normal((req.n_paths, len(unk))) @ L.T

        hrs = times.hour.values
        dem = mu["dem"].values[1:] + sd["dem"].values[1:] * zs[:, :h]
        sol = mu["sol"].values[1:] + sd["sol"].values[1:] * zs[:, h:]
        cap = self.sol_cap.loc[hrs].values
        sol = np.clip(sol, 0.0, cap)
        sol[:, cap < SOL_NIGHT_CAP] = 0.0
        dem = np.clip(dem, 0.0, 5000.0)
        return GenResult(times=times, paths={"dem": dem, "sol": sol},
                         prob=np.full(req.n_paths, 1.0 / req.n_paths),
                         known={"price": np.asarray(req.price_forecast[:h], float),
                                "co2": np.asarray(req.co2_forecast[:h], float)},
                         meta={"generator": self.name, "horizon": h, "n_paths": req.n_paths,
                               "conditioned_on_known": self.condition_known,
                               "conditioned_on_last": bool(self.condition_last and (req.last_dem is not None or req.last_sol is not None))})
