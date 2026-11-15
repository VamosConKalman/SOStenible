"""features.py — Features de las previsiones LASSO (compartido por el ajuste local y por el agente).

Todo vectorizado: cada argumento es un array de longitud n (una fila por muestra).
En el agente, n = H (una fila por horizonte k); en el ajuste, n = número de instantes t.
Solo usa información disponible en la hora t: perfiles, los 3 valores conocidos de precio/CO2,
la medida de t-1 (consumo, solar, meteo) y lo observado 24 h antes de la hora destino.
"""
from __future__ import annotations

import numpy as np

N_FEAT = 24 + 4 + 8 + 6 + 8 + 4 + 24 + 24   # = 102


def build(hour_tau, weekend_tau, month_tau,
          ap, ac,                      # (n, 3) anomalías relativas de precio y CO2 conocidas (t, t+1, t+2)
          l1, has_l1,                  # anomalía de consumo en t-1 (kW) y si existe
          lk, has_lk,                  # anomalía de claridad de la última hora de sol (24 h) y si existe
          ly, has_ly, ky, has_ky,      # ayer (τ-24): anomalía de consumo y de claridad
          py, cy, has_pcy,             # ayer (τ-24): anomalías relativas de precio y CO2
          irr, tamb, tpan, vent, has_met,   # meteo de t-1
          env_tau):                    # envolvente de cielo claro en τ (kW, ya ×12)
    n = len(hour_tau)
    H1 = np.zeros((n, 24)); H1[np.arange(n), hour_tau.astype(int)] = 1.0
    cal = np.column_stack([weekend_tau, np.sin(2 * np.pi * month_tau / 12), np.cos(2 * np.pi * month_tau / 12),
                           env_tau / 1000.0])
    known = np.column_stack([ap, ac])                                     # 6
    known = np.column_stack([known, ap.mean(1), ac.mean(1)])              # 8
    last = np.column_stack([l1 / 100.0, has_l1, lk, has_lk, ly / 100.0, has_ly])   # 6
    yest = np.column_stack([ky, has_ky, py, cy, has_pcy,
                            py * has_pcy, cy * has_pcy, (ky * env_tau / 1000.0)])   # 8
    met = np.column_stack([irr / 1000.0, tamb / 30.0, tpan / 40.0, vent / 10.0]) * has_met[:, None]   # 4
    inter_l = H1 * (l1 / 100.0)[:, None]            # persistencia del consumo distinta por hora destino
    inter_k = H1 * (lk * env_tau / 1000.0)[:, None]  # persistencia de la claridad pesada por el sol posible
    X = np.column_stack([H1, cal, known, last, yest, met, inter_l, inter_k])
    return np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
