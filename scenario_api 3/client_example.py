"""Exemple de client (NO es pot fer servir dins agent.py: l'escàner del repte rebutja requests/socket).
Serveix per a visualitzacions i per optimitzar fora de línia.

    python client_example.py --url http://localhost:8000
"""
import argparse
import numpy as np
import pandas as pd
import requests


def obs_to_payload(obs, generator="gaussian", n_paths=1000, k=8, seed=0):
    """Converteix l'obs de l'environment en el cos de POST /generate."""
    nd = obs["noves_dades_5min"]
    return {"generator": generator, "timestamp": pd.Timestamp(obs["timestamp"]).isoformat(),
            "price_forecast": obs["preus_properes_24h"], "co2_forecast": obs["co2_properes_24h"],
            "last_dem_kw": nd["ultim_consum_kw"], "last_sol_kw": nd["ultima_solar_kw"],
            "n_paths": n_paths, "seed": seed, "return_paths": False,
            "reduce": {"k": k}}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    a = ap.parse_args()
    obs = {"timestamp": "2026-03-10 17:00", "preus_properes_24h": [0.12] * 24, "co2_properes_24h": [0.08] * 24,
           "noves_dades_5min": {"ultim_consum_kw": 1350.0, "ultima_solar_kw": 40.0}}
    r = requests.post(f"{a.url}/generate", json=obs_to_payload(obs)).json()
    red = r["reduced"]
    print("probabilitats:", red["prob"], "\nqualitat:", red["quality"])
    print("escenari 1, demanda neta (kW):", np.round(red["paths"]["net"][0], 0))
