"""Protocol d'avaluació COMÚ per a tots els generadors (leave-one-month-out).

Per cada mes: s'ajusta amb la resta de mesos i es generen escenaris des de molts orígens t del mes
mantingut fora, amb preu/CO2 reals com a previsió (així és com ho dóna l'environment).
Mètriques per a dem i sol:  RMSE per pas, cobertura 50%/90%, pinball loss i energy score (joint).

    python evaluate.py --data data/train --generator gaussian
"""
import argparse, copy, json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.spatial.distance import pdist

from generators import REGISTRY, GenRequest
from data import load_hourly

QS = np.arange(0.05, 1.0, 0.05)


def _origins(hourly, month, H, stride):
    idx = hourly.index
    ok = []
    for t in idx[idx.month == month]:
        w = pd.date_range(t - pd.Timedelta(hours=1), periods=H + 1, freq="h")
        if w.isin(idx).all():
            ok.append(t)
    return ok[::stride]


def _score(paths, y):
    """paths (n,h), y (h,)  ->  dict de mètriques per aquest origen."""
    n = paths.shape[0]
    q = np.quantile(paths, QS, axis=0)                                   # (nq, h)
    d = y[None, :] - q
    pin = np.mean(np.maximum(QS[:, None] * d, (QS[:, None] - 1) * d))
    es = np.mean(np.linalg.norm(paths - y, axis=1)) - pdist(paths).sum() / n ** 2
    lo50, hi50 = np.quantile(paths, [0.25, 0.75], axis=0)
    lo90, hi90 = np.quantile(paths, [0.05, 0.95], axis=0)
    return {"err": paths.mean(0) - y, "pin": pin, "es": es,
            "c50": np.mean((y >= lo50) & (y <= hi50)), "c90": np.mean((y >= lo90) & (y <= hi90))}


def evaluate(factory, hourly, H=24, n_paths=200, stride=5, months=None, variants=None, seed=0, verbose=True):
    variants = variants or {"base": {}}
    months = months or sorted(set(hourly.index.month))
    acc = {name: {v: {"err": [], "pin": [], "es": [], "c50": [], "c90": []} for v in ("dem", "sol")} for name in variants}
    for m in months:
        train = hourly[hourly.index.month != m]
        orig = _origins(hourly, m, H, stride)
        if not orig:
            continue
        model = factory().fit(train)
        if verbose:
            print(f"  mes {m:02d}: {len(orig)} orígens")
        for name, attrs in variants.items():
            g = copy.copy(model)
            for a, val in attrs.items():
                setattr(g, a, val)
            for i, t in enumerate(orig):
                w = hourly.loc[t - pd.Timedelta(hours=1): t + pd.Timedelta(hours=H - 1)]
                req = GenRequest(timestamp=t, price_forecast=w["price"].values[1:], co2_forecast=w["co2"].values[1:],
                                 last_dem=w["dem"].values[0], last_sol=w["sol"].values[0],
                                 n_paths=n_paths, seed=seed + i, horizon=H)
                res = g.generate(req)
                for v in ("dem", "sol"):
                    s = _score(res.paths[v], w[v].values[1:])
                    for key in acc[name][v]:
                        acc[name][v][key].append(s[key])
    out = {}
    for name in variants:
        out[name] = {}
        for v in ("dem", "sol"):
            a = acc[name][v]
            err = np.array(a["err"])
            out[name][v] = {"rmse": round(float(np.sqrt((err ** 2).mean())), 3),
                            "rmse_by_step": np.sqrt((err ** 2).mean(0)).round(3).tolist(),
                            "coverage50": round(float(np.mean(a["c50"])), 3),
                            "coverage90": round(float(np.mean(a["c90"])), 3),
                            "pinball": round(float(np.mean(a["pin"])), 3),
                            "energy_score": round(float(np.mean(a["es"])), 2),
                            "n_origins": int(len(a["es"]))}
    return out


VARIANTS = {"climatologia": {"condition_known": False, "condition_last": False},
            "+preu/CO2": {"condition_known": True, "condition_last": False},
            "+preu/CO2 +ultim_valor": {"condition_known": True, "condition_last": True}}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/train")
    ap.add_argument("--generator", default="gaussian")
    ap.add_argument("--out", default="artifacts")
    ap.add_argument("--n-paths", type=int, default=200)
    ap.add_argument("--stride", type=int, default=5)
    a = ap.parse_args()
    hourly = load_hourly(a.data)
    cls = REGISTRY[a.generator]
    variants = VARIANTS if a.generator == "gaussian" else {"base": {}}
    res = evaluate(cls, hourly, n_paths=a.n_paths, stride=a.stride, variants=variants)
    Path(a.out).mkdir(parents=True, exist_ok=True)
    (Path(a.out) / f"evaluation_{a.generator}.json").write_text(json.dumps(res, indent=1))
    for name, r in res.items():
        print(f"\n== {name}")
        print(pd.DataFrame(r).drop(index="rmse_by_step").to_string())
