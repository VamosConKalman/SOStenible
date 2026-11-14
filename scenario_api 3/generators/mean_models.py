"""Mitjana estacional: regressió ridge per hora del dia x [1, cap de setmana, mes]."""
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from .base import MeanModel, VARS, to_model

NB = 14   # 1 + weekend + 12 mesos


class SeasonalMeanModel(MeanModel):
    def __init__(self, alpha=1.0):
        self.alpha = alpha

    def _month_table(self):
        """Fila m-1 = vector de mes. Mesos sense dades (p.ex. novembre) = mitjana dels mesos veïns."""
        T = np.zeros((12, 12))
        for m in range(12):
            if self.month_n[m] > 0:
                T[m, m] = 1.0
                continue
            for d in range(1, 7):
                near = [x for x in ((m - d) % 12, (m + d) % 12) if self.month_n[x] > 0]
                if near:
                    T[m, near] = 1.0 / len(near)
                    break
        return T

    def _features(self, times):
        times = pd.DatetimeIndex(times)
        n = len(times)
        wk = (times.dayofweek.values >= 5).astype(float)
        B = np.hstack([np.ones((n, 1)), wk[:, None], self.table[times.month.values - 1]])
        X = np.zeros((n, 24 * NB))
        X[np.arange(n)[:, None], times.hour.values[:, None] * NB + np.arange(NB)[None, :]] = B
        return X

    def fit(self, hourly):
        d = hourly[list(VARS)].dropna()
        self.month_n = np.bincount(d.index.month - 1, minlength=12)
        self.table = self._month_table()
        Y = np.column_stack([to_model(v, d[v].values) for v in VARS])
        self.reg = Ridge(alpha=self.alpha, fit_intercept=False).fit(self._features(d.index), Y)
        return self

    def predict(self, times, ctx=None):
        times = pd.DatetimeIndex(times)
        return pd.DataFrame(self.reg.predict(self._features(times)), index=times, columns=list(VARS))
