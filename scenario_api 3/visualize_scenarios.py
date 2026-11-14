"""Generate Monte Carlo scenarios through the local API and plot the K representatives.

Usage:
    python visualize_scenarios.py
    python visualize_scenarios.py --k 8 --n-paths 2000

The API must already be running at http://127.0.0.1:8000 (or pass --url).
The defaults are an illustrative request; replace the price/CO2 forecasts and
last observed values with the current environment obs when integrating the agent.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import requests


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera i dibuixa escenaris de bateria")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="URL base de la Scenario API")
    parser.add_argument("--k", type=int, default=8, help="Nombre d'escenaris representatius")
    parser.add_argument("--n-paths", type=int, default=2000, help="Nombre de trajectòries Monte Carlo abans del k-means")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--output-prefix", default="escenarios_generados", help="Prefix dels fitxers PNG i JSON")
    args = parser.parse_args()

    # Petició demostrativa. Substitueix aquests valors per les previsions i
    # observacions reals de obs quan vulguis visualitzar un cas concret.
    payload = {
        "generator": "gaussian",
        "timestamp": "2026-03-10T17:00:00",
        "price_forecast": [0.12] * 24,
        "co2_forecast": [0.08] * 24,
        "last_dem_kw": 1350.0,
        "last_sol_kw": 40.0,
        "n_paths": args.n_paths,
        "seed": args.seed,
        "return_paths": False,
        "reduce": {"k": args.k, "representative": "mean", "seed": args.seed},
    }

    url = args.url.rstrip("/")
    try:
        response = requests.post(f"{url}/generate", json=payload, timeout=180)
        response.raise_for_status()
    except requests.exceptions.ConnectionError as exc:
        raise SystemExit(
            f"No puc connectar amb {url}. Primer arrenca la API en un altre terminal amb: uvicorn api:app --reload"
        ) from exc
    except requests.exceptions.HTTPError as exc:
        detail = response.text[:2000]
        raise SystemExit(f"La API ha retornat HTTP {response.status_code}: {detail}") from exc

    result = response.json()
    reduced = result.get("reduced")
    if not reduced or "paths" not in reduced:
        raise SystemExit(f"La resposta no conté escenaris reduïts. Resposta rebuda: {json.dumps(result)[:2000]}")

    probs = np.asarray(reduced["prob"], dtype=float)
    paths = reduced["paths"]
    hours = np.arange(1, len(paths["dem"][0]) + 1)

    output_prefix = Path(args.output_prefix)
    json_path = output_prefix.with_suffix(".json")
    png_path = output_prefix.with_suffix(".png")
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    series = [
        ("dem", "Demanda (kW)"),
        ("sol", "Producción solar (kW)"),
        ("net", "Demanda neta (kW)"),
    ]
    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)
    for ax, (key, title) in zip(axes, series):
        values = np.asarray(paths[key], dtype=float)
        for i, profile in enumerate(values):
            ax.plot(hours, profile, marker="o", markersize=2.5, linewidth=1.6,
                    label=f"Escenario {i + 1} · {probs[i] * 100:.1f}%")
        ax.set_title(title)
        ax.set_ylabel("kW")
        ax.grid(True, alpha=0.3)
        ax.legend(ncol=2, fontsize=8)
    axes[-1].set_xlabel("Hora del horizonte (t = 1, …, 24)")
    fig.suptitle(f"{len(probs)} escenarios representativos · {args.n_paths} simulaciones Monte Carlo")
    fig.tight_layout()
    fig.savefig(png_path, dpi=160, bbox_inches="tight")

    print("Escenarios generados correctamente")
    print(f"Número de trayectorias Monte Carlo: {result.get('n_paths', args.n_paths)}")
    print(f"Número de escenarios representativos: {len(probs)}")
    print("Probabilidades:")
    for i, prob in enumerate(probs, start=1):
        print(f"  Escenario {i}: {prob:.4f} ({prob * 100:.2f}%)")
    print(f"Suma de probabilidades: {probs.sum():.6f}")
    print(f"Gráfica guardada en: {png_path.resolve()}")
    print(f"Datos completos guardados en: {json_path.resolve()}")
    plt.show()


if __name__ == "__main__":
    main()
