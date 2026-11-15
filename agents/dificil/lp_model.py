"""lp_model.py — LP de la batería (HiGHS) para cualquier capacidad y potencia.

x = [c_0..c_{H-1}, d_0..d_{H-1}, s_1..s_H, g_k (k con N̂_k finita)]
min Σ_{k∉R} w_k (c_k − d_k) + Σ_{k∈R} w_k g_k + δ Σ (c_k + d_k) − V s_H
s.a. s_{k+1} = s_k + η_c c_k − d_k/η_d ;  g_k ≥ N̂_k + c_k − d_k, g_k ≥ 0 (k ∈ R)
     0 ≤ c, d ≤ p_max ;  s ∈ [min(eps, s0), max(e_max − eps, s0)]
"""
from __future__ import annotations

import numpy as np
from scipy import sparse
from scipy.optimize import linprog

ETA = 0.9
ETA_C = ETA ** 0.5
ETA_D = ETA ** 0.5


def solve_lp(w, s0, V, net=None, eps=0.5, delta=1e-6, p_max=1500.0, e_max=6000.0):
    w = np.asarray(w, dtype=np.float64)
    H = len(w)
    if H == 0:
        return None
    R = np.zeros(0, dtype=int)
    if net is not None:
        net = np.asarray(net, dtype=np.float64)[:H]
        R = np.flatnonzero(np.isfinite(net))
    nR = len(R)
    m = 3 * H + nR

    cost = np.zeros(m)
    cost[:H] = w + delta
    cost[H:2 * H] = -w + delta
    if nR:
        cost[R] = delta
        cost[H + R] = delta
        cost[3 * H:] = w[R]
    cost[3 * H - 1] -= V

    k = np.arange(H)
    rows = np.r_[k, k[1:], k, k]
    cols = np.r_[2 * H + k, 2 * H + k[1:] - 1, k, H + k]
    vals = np.r_[np.ones(H), -np.ones(H - 1), np.full(H, -ETA_C), np.full(H, 1.0 / ETA_D)]
    A_eq = sparse.csr_matrix((vals, (rows, cols)), shape=(H, m))
    b_eq = np.zeros(H); b_eq[0] = s0

    if nR:
        j = np.arange(nR)
        A_ub = sparse.csr_matrix((np.r_[np.ones(nR), -np.ones(nR), -np.ones(nR)],
                                  (np.r_[j, j, j], np.r_[R, H + R, 3 * H + j])), shape=(nR, m))
        b_ub = -net[R]
    else:
        A_ub, b_ub = None, None

    lo, hi = min(eps, s0), max(e_max - eps, s0)
    bounds = [(0.0, p_max)] * (2 * H) + [(lo, hi)] * H + [(0.0, None)] * nR
    r = linprog(cost, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")
    return r.x if r.status == 0 else None


def clamp(P, soc, p_max, e_max, eps=0.5):
    """Consigna físicamente segura (márgenes eps en kWh)."""
    max_c = max(0.0, min(p_max, (e_max - eps - soc) / ETA_C))
    max_d = max(0.0, min(p_max, (soc - eps) * ETA_D))
    return float(max(-max_d, min(max_c, P)))


def solve_lp_stoch(w, s0, nets, probs, eps=0.5, delta=1e-6, p_max=1500.0, e_max=6000.0):
    """LP estocástico en dos etapas.

    nets: (S, H) carga neta por escenario; probs: (S,).
    Variables por escenario s: c_s (H), d_s (H), e_s (H), g_s (H)  → bloque de 4H.
    min Σ_s p_s Σ_k [ w_k g_{s,k} + δ (c_{s,k} + d_{s,k}) ]
    s.a. e_{s,k} = e_{s,k-1} + η_c c_{s,k} − d_{s,k}/η_d ;  g_{s,k} ≥ N_{s,k} + c_{s,k} − d_{s,k} ;  g ≥ 0
         no anticipación: c_{s,0} = c_{1,0}, d_{s,0} = d_{1,0}
    Devuelve (c_0, d_0) o None.
    """
    w = np.asarray(w, dtype=np.float64)
    nets = np.asarray(nets, dtype=np.float64)
    probs = np.asarray(probs, dtype=np.float64)
    S, H = nets.shape[0], len(w)
    nets = nets[:, :H]
    B = 4 * H
    m = S * B
    k = np.arange(H)

    cost = np.zeros(m)
    for s in range(S):
        o = s * B
        cost[o + k] = probs[s] * delta
        cost[o + H + k] = probs[s] * delta
        cost[o + 3 * H + k] = probs[s] * w

    # Balance de la batería (H filas por escenario)
    rows, cols, vals = [], [], []
    for s in range(S):
        o, r = s * B, s * H
        rows += [r + k, r + k[1:], r + k, r + k]
        cols += [o + 2 * H + k, o + 2 * H + k[1:] - 1, o + k, o + H + k]
        vals += [np.ones(H), -np.ones(H - 1), np.full(H, -ETA_C), np.full(H, 1.0 / ETA_D)]
    b_eq = np.zeros(S * H)
    b_eq[np.arange(S) * H] = s0
    # No anticipación (2 filas por escenario s ≥ 1)
    r0 = S * H
    for s in range(1, S):
        rr = r0 + 2 * (s - 1)
        rows += [np.array([rr, rr]), np.array([rr + 1, rr + 1])]
        cols += [np.array([0, s * B]), np.array([H, s * B + H])]
        vals += [np.array([1.0, -1.0]), np.array([1.0, -1.0])]
    n_eq = S * H + 2 * (S - 1)
    b_eq = np.r_[b_eq, np.zeros(2 * (S - 1))]
    A_eq = sparse.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(n_eq, m))

    # Importación: c − d − g ≤ −N
    rows, cols, vals = [], [], []
    for s in range(S):
        o, r = s * B, s * H
        rows += [r + k, r + k, r + k]
        cols += [o + k, o + H + k, o + 3 * H + k]
        vals += [np.ones(H), -np.ones(H), -np.ones(H)]
    A_ub = sparse.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(S * H, m))
    b_ub = -nets.reshape(-1)

    lo, hi = min(eps, s0), max(e_max - eps, s0)
    bnd = [(0.0, p_max)] * (2 * H) + [(lo, hi)] * H + [(0.0, None)] * H
    r = linprog(cost, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bnd * S, method="highs")
    if r.status != 0:
        return None
    return float(r.x[0]), float(r.x[H])
