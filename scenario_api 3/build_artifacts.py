"""Ajusta els generadors amb les dades d'entrenament i desa artifacts/<nom>.joblib.
    python build_artifacts.py --data data/train --out artifacts
"""
import argparse
from pathlib import Path
from data import load_hourly
from generators import REGISTRY

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/train")
    ap.add_argument("--out", default="artifacts")
    ap.add_argument("--only", nargs="*", default=["gaussian"])
    a = ap.parse_args()
    hourly = load_hourly(a.data)
    print(f"{len(hourly)} hores d'entrenament ({hourly.index.min()} -> {hourly.index.max()})")
    Path(a.out).mkdir(parents=True, exist_ok=True)
    for name in a.only:
        g = REGISTRY[name]().fit(hourly)
        g.save(Path(a.out) / f"{name}.joblib")
        print(name, "->", g.info())
