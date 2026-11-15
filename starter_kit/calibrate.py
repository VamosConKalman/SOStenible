"""
calibrate.py — Estima kappa y el valor terminal V a partir de los duales del oráculo.

1. kappa = E_b / C_b sobre las semanas de calibración.
2. Para cada semana: LP con información perfecta (168 h, V=0 al final, carga neta real).
   lambda_k = -eqlin.marginals[k] = valor marginal de 1 kWh en s_{k+1}.
3. Para cada ventana de 24 h que no toca el fin de semana:
   objetivo V* = lambda en s_{t+24};  q_t = rango de V*/eta_d dentro de w'_{t..t+23}.
4. q = mediana(q_t).  Si IQR(q_t) > 0.2 se ajusta V ≈ a + b·mediana(w') + c·max(w').
5. Escribe parametres.json.

Uso:  python calibrate.py [hourly.csv]
"""
import json
import sys

import numpy as np

from agent import solve_lp, ETA_D, DEFAULTS
from common import load_hourly, weeks, kappa

CALIB_DAYS = [(1, 7), (8, 14)]     # los días 15-21 quedan para validación (backtest.py)


def oracle_duals(blk, kap, eps, delta):
    w = 0.7 * blk["co2_kg_per_kwh"].values + 0.3 * kap * blk["precio_eur_per_kwh"].values
    net = (blk["load_kw"] - blk["pv_kw"]).values
    res, H, _ = solve_lp(w, 1000.0, 0.0, net=net, eps=eps, delta=delta)
    if res.status != 0:
        return None, None, None
    lam = -np.asarray(res.eqlin.marginals)     # lam[k] = valor de s_{k+1}
    return w, lam, res


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "hourly.csv"
    df = load_hourly(path)
    blocks = weeks(df, CALIB_DAYS)
    if not blocks:
        raise SystemExit("No hay semanas completas de calibración")

    import pandas as pd
    kap = kappa(pd.concat(blocks))
    eps, delta = DEFAULTS["eps"], DEFAULTS["delta"]

    qs, X, y = [], [], []
    for blk in blocks:
        w, lam, _ = oracle_duals(blk, kap, eps, delta)
        if w is None:
            continue
        for t in range(0, 168 - 24):           # ventanas que no llegan al fin de semana
            win = w[t:t + 24]
            v_star = lam[t + 23]               # valor de s_{t+24}
            qs.append(float(np.mean(win <= v_star / ETA_D)))
            X.append([1.0, np.median(win), np.max(win)])
            y.append(v_star)

    qs = np.array(qs)
    q = float(np.median(qs))
    iqr = float(np.quantile(qs, 0.75) - np.quantile(qs, 0.25))
    print(f"semanas: {len(blocks)}  kappa = {kap:.4f} kg/€")
    print(f"lambda < 0 en {100 * np.mean(np.array(y) < -1e-9):.2f}% de ventanas (debería ser ~0)")
    print(f"q calibrado = {q:.3f}  (IQR {iqr:.3f}, n={len(qs)})")

    # Conserva las claves que ya existan en parametres.json y actualiza solo las calibradas
    params = {}
    try:
        with open("parametres.json", encoding="utf-8") as f:
            params = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        params = dict(DEFAULTS)
    params.update({"kappa": kap, "q": q, "v_coef": None})
    if iqr > 0.2:
        coef, *_ = np.linalg.lstsq(np.array(X), np.array(y), rcond=None)
        params["v_coef"] = [float(c) for c in coef]
        print(f"IQR > 0.2 -> regresión V = {coef[0]:.4f} + {coef[1]:.4f}·med(w) + {coef[2]:.4f}·max(w)")

    with open("parametres.json", "w", encoding="utf-8") as f:
        json.dump(params, f, indent=2)
    print("parametres.json escrito")


if __name__ == "__main__":
    main()
