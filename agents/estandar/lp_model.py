"""
lp_model.py — Modelo LP puro (sin estado).

Recibe los datos del LP y devuelve la solución óptima usando scipy HiGHS.
No sabe nada de `obs`, fechas ni del entorno.

Formulación:
  - Horas R = {k : N̂_k finita}: importación g_k con R2 (g_k ≥ N̂_k + c_k − d_k, g_k ≥ 0).
    Con N̂_k ≥ P_max la restricción nunca está activa y equivale exactamente a v1.
  - Horas sin previsión (NaN/inf o net=None): coste de v1 directo en c_k, d_k.
  - Objetivo: Σ_{k∉R} w(c_k−d_k) + Σ_{k∈R} w·g_k + δ·Σ(c_k+d_k) − V·s_H
  - Cotas del SOC relajadas a [min(eps, s0), max(E_MAX−eps, s0)] en todos los modos.
"""

from __future__ import annotations

import numpy as np
from scipy import sparse
from scipy.optimize import linprog
from typing import Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Constantes físicas
# ---------------------------------------------------------------------------
P_MAX: float = 500.0
E_MAX: float = 2000.0
ETA: float = 0.9
ETA_C: float = ETA ** 0.5  # ≈ 0.948683
ETA_D: float = ETA ** 0.5
DT: float = 1.0


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------
def solve_lp(
    w: np.ndarray,
    s0: float,
    V: float,
    net: Optional[np.ndarray] = None,
    eps: float = 0.5,
    delta: float = 1e-6,
    return_result: bool = False,
) -> np.ndarray | linprog.OptimizeResult | None:
    """
    Resuelve el LP para el horizonte de H horas.

    Parámetros
    ----------
    w : np.ndarray de longitud H
        Peso horario w'_k = 0.7·co2_k + 0.3·κ·preu_k
    s0 : float
        SOC inicial (kWh)
    V : float
        Valor terminal (€/kWh al final del horizonte)
    net : np.ndarray | None
        Carga neta prevista N̂_k (kW). NaN/inf = sin previsión para esa hora.
        None = modo v1 (sin g_k).
    eps : float
        Margen de seguridad del SOC (default 0.5).
    delta : float
        Regularizador para evitar ciclos inútiles (default 1e-6).

    Devuelve
    --------
    np.ndarray | None
        Vector solución x = [c, d, s, g] o None si falla.
    """
    H = len(w)
    if H == 0:
        return np.zeros(0)

    # ------------------------------------------------------------------
    # Determinar horas en R y orden de g
    # ------------------------------------------------------------------
    has_forecast = net is not None
    g_indices: list[int] = []      # índices k ∈ R
    g_order: dict[int, int] = {}   # k → posición en bloque g

    if has_forecast:
        for k in range(H):
            n_val = net[k] if k < len(net) else np.nan
            if np.isfinite(n_val):
                pos = len(g_indices)
                g_order[k] = pos
                g_indices.append(k)

    n_g = len(g_indices)

    # ------------------------------------------------------------------
    # Dimensiones del vector de decisión
    # ------------------------------------------------------------------
    # x = [c_0..c_{H-1}, d_0..d_{H-1}, s_1..s_H, g_0..g_{|R|}]
    m = 3 * H + n_g

    # ------------------------------------------------------------------
    # Función de coste
    # ------------------------------------------------------------------
    c_vec = np.zeros(m, dtype=np.float64)

    for k in range(H):
        # Coste por carga
        coeff_c = w[k] + delta
        # Coste por descarga (negativo: queremos descargar cuando w es alto)
        coeff_d = -w[k] + delta

        if has_forecast and k in g_order:
            # Hora en R: coste en g_k, no en c_k ni d_k
            g_pos = g_order[k]
            c_vec[k] = delta              # c: solo penalización delta
            c_vec[H + k] = delta          # d: solo penalización delta
            c_vec[3 * H + g_pos] = w[k]   # g: peso horario
        else:
            # Hora fuera de R: coste directo en c, d
            c_vec[k] = coeff_c
            c_vec[H + k] = coeff_d

    # Valor terminal: -V·s_H
    c_vec[3 * H - 1] -= V

    # ------------------------------------------------------------------
    # Igualdades: R1 — dinámica SOC
    # ------------------------------------------------------------------
    # s_{k+1} - s_k - eta_c * c_k + d_k / eta_d = 0  (k≥1)
    # s_1            - eta_c * c_0 + d_0 / eta_d = s0  (k=0)
    rows_eq = H
    cols_eq = m

    eq_rows: list[int] = []
    eq_cols: list[int] = []
    eq_vals: list[float] = []

    for k in range(H):
        # s_{k+1} → índice 2H + k
        eq_rows.append(k); eq_cols.append(2 * H + k); eq_vals.append(1.0)

        if k >= 1:
            # -s_k → índice 2H + k - 1
            eq_rows.append(k); eq_cols.append(2 * H + k - 1); eq_vals.append(-1.0)

        # -eta_c * c_k → índice k
        eq_rows.append(k); eq_cols.append(k); eq_vals.append(-ETA_C)

        # +d_k / eta_d → índice H + k
        eq_rows.append(k); eq_cols.append(H + k); eq_vals.append(1.0 / ETA_D)

    A_eq = sparse.csr_matrix(
        (eq_vals, (eq_rows, eq_cols)), shape=(rows_eq, cols_eq)
    )

    b_eq = np.zeros(H, dtype=np.float64)
    b_eq[0] = s0

    # ------------------------------------------------------------------
    # Desigualdades: R2 — g_k ≥ N̂_k + c_k - d_k
    # ------------------------------------------------------------------
    if n_g > 0:
        ub_rows, ub_cols, ub_vals = [], [], []
        for j, k in enumerate(g_indices):
            ub_rows += [j, j, j]
            ub_cols += [k, H + k, 3 * H + j]     # +c_k, -d_k, -g_k
            ub_vals += [1.0, -1.0, -1.0]
        A_ub = sparse.csr_matrix(
            (ub_vals, (ub_rows, ub_cols)), shape=(n_g, cols_eq)
        )
        b_ub = np.array([-float(net[k]) for k in g_indices], dtype=np.float64)
    else:
        A_ub = sparse.csr_matrix((0, m), dtype=np.float64)
        b_ub = np.array([], dtype=np.float64)

    # ------------------------------------------------------------------
    # Cotas (bounds)
    # ------------------------------------------------------------------
    # c ∈ [0, P_MAX]
    # d ∈ [0, P_MAX]
    # s ∈ [eps_relaxed, E_MAX - eps_relaxed]
    # g ∈ [0, ∞)

    soc_min_safe = min(eps, s0)
    soc_max_safe = max(E_MAX - eps, s0)

    bounds: list[tuple[float, float | None]] = []
    for _ in range(H):
        bounds.append((0.0, P_MAX))          # c
    for _ in range(H):
        bounds.append((0.0, P_MAX))          # d
    for _ in range(H):
        bounds.append((soc_min_safe, soc_max_safe))  # s
    for _ in range(n_g):
        bounds.append((0.0, None))           # g

    # ------------------------------------------------------------------
    # Resolver
    # ------------------------------------------------------------------
    result = linprog(
        c_vec,
        A_ub=A_ub,
        b_ub=b_ub,
        A_eq=A_eq,
        b_eq=b_eq,
        bounds=bounds,
        method="highs",
    )

    if result.success:
        if return_result:
            return result
        return result.x
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def compute_weights(
    co2: np.ndarray,
    price: np.ndarray,
    kappa: float,
    w_co2: float = 0.7,
    w_cost: float = 0.3,
) -> np.ndarray:
    """
    Calcula el vector de pesos w' = w_co2·co2 + w_cost·κ·price.

    Parámetros
    ----------
    co2 : np.ndarray de longitud H
        Intensidad de CO₂ (kg/kWh).
    price : np.ndarray de longitud H
        Precio PVPC (€/kWh).
    kappa : float
        κ = E_b / C_b (kg CO₂ / €).

    Devuelve
    --------
    np.ndarray de longitud H
    """
    return w_co2 * co2 + w_cost * kappa * price


def compute_terminal_value(
    w: np.ndarray,
    is_end: bool,
    q: float = 0.5,
    v_coef: Optional[Sequence[float]] = None,
) -> float:
    """
    Calcula el valor terminal V.

    Parámetros
    ----------
    w : np.ndarray de longitud H
        Pesos horarios.
    is_end : bool
        True si el horizonte llega al final de la semana/mes.
    q : float
        Cuantil para la fórmula simple (default 0.5).
    v_coef : tuple(a, b, c) | None
        Coeficientes para la fórmula mixta: a + b·med(w) + c·max(w).

    Devuelve
    --------
    float
        Valor terminal V ≥ 0.
    """
    if is_end:
        return 0.0

    if len(w) == 0:
        return 0.0

    max_w = float(np.max(w))

    if v_coef is not None and len(v_coef) == 3:
        a, b, c = v_coef
        med_w = float(np.median(w))
        V = a + b * med_w + c * max_w
    else:
        V = ETA_D * float(np.quantile(w, q))

    # Acotar
    V = max(0.0, V)
    V = min(V, max_w / ETA_C if max_w > 0 else 0.0)

    return V


def clip_consigna(P: float, soc: float, eps: float = 0.5) -> float:
    """
    Recorta la consigna P a los límites físicos de la batería.

    Parámetros
    ----------
    P : float
        Consigna bruta c_0 - d_0.
    soc : float
        SOC actual (kWh).
    eps : float
        Margen de seguridad.

    Devuelve
    --------
    float
        Consigna recortada.
    """
    lo = max(0.0, soc - eps)
    hi = E_MAX - soc - eps

    max_discharge = min(P_MAX, lo * ETA_D if lo > 0 else 0.0)
    max_charge = min(P_MAX, hi / ETA_C if hi > 0 else 0.0)

    return float(np.clip(P, -max_discharge, max_charge))


def get_dual_marginals(
    w: np.ndarray,
    s0: float,
    V: float,
    net: Optional[np.ndarray] = None,
    eps: float = 0.5,
    delta: float = 1e-6,
) -> np.ndarray | None:
    """
    Devuelve los duales de las igualdades SOC (valores marginales λ_k).

    λ_k = -dual_k del LP: indica cuánto se ahorraría un kWh adicional de SOC
    en la hora k.

    Parámetros: igual que solve_lp.

    Devuelve
    --------
    np.ndarray | None
        Vector de duales de longitud H, o None si falla.
    """
    result = solve_lp(w, s0, V, net, eps, delta, return_result=True)
    if result is None:
        return None
    return -np.asarray(result.eqlin.marginals, dtype=np.float64)