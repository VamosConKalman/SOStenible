"""Reducció k-means de trajectòries simulades -> K escenaris amb probabilitat."""
import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score


def _features(paths, weights):
    w = {"dem": 1.0, "sol": 1.0}
    w.update(weights or {})
    F = []
    for v in ("dem", "sol"):
        a = paths[v]
        F.append((a - a.mean()) / (a.std() + 1e-9) * w[v])     # estandarditza per VARIABLE (conserva la forma intradia)
    return np.hstack(F)


def reduce_paths(paths, k=8, weights=None, representative="mean", seed=0, n_init=5):
    n = paths["dem"].shape[0]
    k = int(min(k, n))
    F = _features(paths, weights)
    km = KMeans(k, n_init=n_init, random_state=seed).fit(F)
    lab = km.labels_
    prob = np.bincount(lab, minlength=k) / n
    out = {}
    for v in ("dem", "sol"):
        if representative == "medoid":
            idx = [np.where(lab == c)[0][np.argmin(((F[lab == c] - km.cluster_centers_[c]) ** 2).sum(1))] for c in range(k)]
            out[v] = paths[v][idx]
        else:
            out[v] = np.vstack([paths[v][lab == c].mean(0) for c in range(k)])
    order = np.argsort(-prob)
    out = {v: a[order] for v, a in out.items()}
    prob = prob[order]
    quality = {}
    for v in ("dem", "sol"):
        m = prob @ out[v]
        v_red = prob @ (out[v] - m) ** 2
        quality[v] = round(float(100 * v_red.sum() / (paths[v].var(0).sum() + 1e-12)), 1)
    return {"paths": out, "net": out["dem"] - out["sol"], "prob": prob,
            "quality": {"var_retinguda_pct": quality, "inertia": float(km.inertia_), "k": k}}


def k_curve(paths, ks=range(2, 16), weights=None, seed=0):
    F = _features(paths, weights)
    rows = []
    for k in ks:
        km = KMeans(k, n_init=5, random_state=seed).fit(F)
        rows.append({"k": k, "inertia": float(km.inertia_),
                     "silhouette": float(silhouette_score(F, km.labels_, sample_size=min(len(F), 2000), random_state=seed))})
    return rows
