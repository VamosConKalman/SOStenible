"""forecaster_impl.py — Puente scenario_api (Monte Carlo gaussiano) -> NetLoadForecaster.

Mismo modelo que generators/gaussian_mc.py, pero:
  * solo numpy (sin sklearn ni el paquete `generators` dentro del .pkl),
  * cuantiles de N en forma cerrada (sin muestrear): rápido y determinista.
Aproximación: no aplica el recorte de la solar a [0, cap] salvo de noche (cap < 1e-3 -> sol = 0).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from forecaster_base import NetLoadForecaster

H_MAX = 24
NB = 14
# z de la normal estándar para los cuantiles que se devuelven
_QZ = {"p10": -1.2815515655, "p20": -0.8416212336, "p30": -0.5244005127, "p40": -0.2533471031,
       "p50": 0.0, "p60": 0.2533471031, "p70": 0.5244005127, "p80": 0.8416212336, "p90": 1.2815515655}
_OFF = {"dem": 0, "sol": H_MAX + 1, "price": 2 * H_MAX + 2, "co2": 3 * H_MAX + 2}
_V = {"dem": 0, "sol": 1, "price": 2, "co2": 3}


class GaussianNetForecaster(NetLoadForecaster):
    def __init__(self, coef, month_table, sd, cov, sol_cap, condition_known=True):
        self.coef = np.asarray(coef, float)            # (4, 24*NB) ridge sin intercepto
        self.month_table = np.asarray(month_table, float)  # (12, 12)
        self.sd = np.asarray(sd, float)                # (24, 4) por hora
        self.cov = np.asarray(cov, float)              # (4H+2, 4H+2)
        self.sol_cap = np.asarray(sol_cap, float)      # (24,)
        self.condition_known = bool(condition_known)

    def _mu(self, hours, wk, months):
        n = len(hours)
        B = np.hstack([np.ones((n, 1)), wk[:, None], self.month_table[months - 1]])
        X = np.zeros((n, 24 * NB))
        X[np.arange(n)[:, None], hours[:, None] * NB + np.arange(NB)[None, :]] = B
        return X @ self.coef.T                          # (n, 4)

    def predict(self, obs, history, horizon):
        try:
            t = pd.Timestamp(obs["timestamp"]).floor("h")
            pr = np.asarray(obs.get("preus_properes_24h", []), float)
            co = np.asarray(obs.get("co2_properes_24h", []), float)
            h = int(min(horizon, H_MAX))
            ext = t + pd.to_timedelta(np.arange(-1, h), "h")      # t-1 .. t+h-1
            hrs = ext.hour.to_numpy()
            mu = self._mu(hrs, (ext.dayofweek.to_numpy() >= 5).astype(float), ext.month.to_numpy())
            sd = self.sd[hrs]
            idx = {v: _OFF[v] + np.arange(h + 1) for v in ("dem", "sol")}
            idx.update({v: _OFF[v] + np.arange(h) for v in ("price", "co2")})
            unk = np.concatenate([idx["dem"][1:], idx["sol"][1:]])
            kidx, kval = [], []
            hk = min(h, len(pr), len(co))
            if self.condition_known and hk > 0:
                for v, fc in (("price", pr), ("co2", co)):
                    j = _V[v]
                    z = (np.log(np.clip(fc[:hk], 1e-4, None)) - mu[1:hk + 1, j]) / sd[1:hk + 1, j]
                    kidx.append(idx[v][:hk]); kval.append(z)
            if history and pd.Timestamp(history[-1][0]) == t - pd.Timedelta(hours=1):
                _, ld, pv = history[-1]
                for v, last in (("dem", ld), ("sol", pv)):
                    if last is not None and np.isfinite(last):
                        j = _V[v]
                        kidx.append(idx[v][:1]); kval.append(np.array([(float(last) - mu[0, j]) / sd[0, j]]))
            S = self.cov
            Suu = S[np.ix_(unk, unk)]
            if kidx:
                k = np.concatenate(kidx); zk = np.concatenate(kval)
                Skk = S[np.ix_(k, k)] + 1e-8 * np.eye(len(k))
                Suk = S[np.ix_(unk, k)]
                G = np.linalg.solve(Skk, Suk.T)
                mc, Sc = G.T @ zk, Suu - Suk @ G
            else:
                mc, Sc = np.zeros(len(unk)), Suu
            sdd, sds = sd[1:, 0], sd[1:, 1]
            night = self.sol_cap[hrs[1:]] < 1e-3
            sds = np.where(night, 0.0, sds)
            m_dem = mu[1:, 0] + sdd * mc[:h]
            m_sol = np.where(night, 0.0, mu[1:, 1] + sds * mc[h:])
            dd, ss = np.diag(Sc)[:h], np.diag(Sc)[h:]
            ds = np.diag(Sc[:h, h:])
            var = sdd ** 2 * dd + sds ** 2 * ss - 2 * sdd * sds * ds
            m, s = m_dem - m_sol, np.sqrt(np.clip(var, 0.0, None))
            out = {key: (m + z * s).astype(np.float64) for key, z in _QZ.items()}
            if h < horizon:
                out = {key: np.concatenate([v, np.full(horizon - h, np.nan)]) for key, v in out.items()}
            return out
        except Exception:
            return np.full(int(horizon), np.nan)