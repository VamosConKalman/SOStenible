# Reparto del equipo — `BatteryAgent` (Datathon UPC Sostenible 2026)

Tres equipos: **agente**, **generador de escenarios** y **front**. Este documento fija qué es de cada uno, las dos interfaces congeladas entre ellos y las correcciones pendientes en `main` (commit `8631320`).

---

## 0. Lo que dicen los números (leer antes de repartir esfuerzo)

Medido sobre las semanas `real_val` (días 15–21) con datos completos: **9 semanas** (sep, oct, dic, ene–jul). Noviembre no tiene datos, junio tiene 2 h de hueco y agosto acaba el día 16. Score sobre totales agregados, con la fórmula correcta (ver corrección 1):

| Variante | Score | ΔCO₂ % | ΔCoste % | Infracciones | Tiempo `act()` |
|---|---:|---:|---:|---:|---:|
| C — v1, sin generador | 5,629 | 5,20 | 6,62 | 0 | 4,1 s |
| D — generador gaussiano (q = 0,1 / 0,3 / 0,5) | 5,629 | 5,20 | 6,62 | 0 | 5,3 s |
| F — oráculo semanal (168 h, todo conocido) | 5,629 | 5,20 | 6,62 | 0 | — |

- **El agente ya está en el techo** en estas semanas: las acciones del MPC coinciden con las del oráculo semanal (diferencia máxima 0,0 kW en la semana de marzo).
- **Por qué la previsión no aporta:** solo el **0,5 %** de las horas tiene N = load − pv < 500 kW. Fuera de esas horas la previsión no cambia ninguna decisión (ARQUITECTURA_GENERADOR §4.2).
- **Consecuencia:** el generador es un **seguro** para semanas atípicas (festivos, agosto, mucho sol), no una fuente de puntos en semanas normales. Mejorar su RMSE sobre `real_val` no mueve el score. El esfuerzo rinde más en **robustez** (que la entrega no falle ni tenga infracciones en ningún caso) y en probar semanas atípicas.

---

## 1. Equipos

| Equipo | Es dueño de | Entrega | Documentos |
|---|---|---|---|
| **Agente** | `agent.py`, `lp_model.py`, `parametres.json`, `environment.py` (mock), `run_scenarios.py`, `baselines.py`, `check_submission` | `submission.zip` final; `results/*.json` para el front | PLAN.md, LP_MODEL.md, PLAN_ESCENARIOS.md (Fases 0 y 3) |
| **Generador de escenarios** | `forecaster_impl.py`, `forecaster.pkl`, `train_forecaster.py`, `eval_forecaster.py`, `scenarios.py`, `oracle_forecaster.py`, `scenario_api/` | Generador que cumple el contrato + familias de escenarios para el harness + valor de `forecaster_quantile` | **ARQUITECTURA_GENERADOR.md** (contrato, §10 para partir de `scenario_api`), PLAN_ESCENARIOS.md (Fases 1, 2 y 4) |
| **Front** | `frontend/` | Visualización de una simulación | §4 de este documento |

### Interfaces congeladas (solo se cambian de acuerdo entre los dos equipos)

| Interfaz | Entre | Definida en |
|---|---|---|
| `forecaster_base.py` + formato de `history` + formatos de salida | agente ↔ generador | ARQUITECTURA_GENERADOR.md §3 |
| `Scenario` (dataclass) + `build_scenarios(family)` | generador → harness del agente | PLAN_ESCENARIOS.md §1.1 |
| `results/run_<variante>.json` | agente → front | §4 de este documento |

---

## 2. Correcciones pendientes en `main` (equipo agente)

Los 93 tests de `sandbox_impl` pasan, pero varias correcciones de la Fase 0 están a medias y algún test no comprueba lo que dice.

| # | Dónde | Problema | Arreglo |
|---|---|---|---|
| 1 | `mocks/environment.py`, `evaluate_results` | `score = α·d_co2 + β·d_cost − infracciones` y **después** `× 100`: cada infracción resta **100 puntos**, no 1. `test_formula_score` solo comprueba que la línea base da 0 | `score = 100·(α·d_co2 + β·d_cost) − infracciones`. Reescribir el test como pide la corrección 0.6 (900 kW frente a 500 kW → diferencia exacta de 1,00) |
| 2 | `agent.py`, historial (0.9) | Guarda `(ts − 1h, max(0, load − pv))`: tupla de 2 y recortada. El contrato es `(ts − 1h, load_kw, pv_kw)` sin recortar. Con un generador que cumpla el contrato, `predict` falla al desempaquetar → todo NaN → **modo v1 sin avisar**. La validez usa `abs(diff) > 3601 s` | Guardar la tupla de 3 sin recortar; válida solo si `ts − self._last_ts == 1h` |
| 3 | `agent.py`, `_interp_quantile` (0.11) | No acepta el formato escenarios: un dict con `"scenarios"`/`"probs"` lanza `ValueError` → v1 sin avisar. `q` se recorta a [0,1; 0,9] fijo, no al rango de claves presentes; si la clave más baja es > q, `float(array)` lanza | Implementar (a)/(b)/(c) de 0.11 y sus tres tests |
| 4 | `forecaster_base.py` (0.12) | Sigue la versión con `abc` y `history = (ts, N)`. ARQUITECTURA_GENERADOR la da por sustituida | Sustituir por la versión nueva (adjunta). `MeanByDayHourForecaster` se puede borrar: lo reemplaza el del equipo generador |
| 5 | `tests/` | Falta un test de contrato agente ↔ generador | Un generador falso por formato (puntual, cuantiles, escenarios, que lanza, que devuelve H − 1) → `n_forecast_fail` y `last_info["mode"]` correctos |
| 6 | Repo | ARQUITECTURA_GENERADOR, PLAN_ESCENARIOS y este documento solo están en el Project. `scenario_api 3/` tiene un espacio en el nombre | Copiarlos a `docs/`. Renombrar a `scenario_api/` |
| 7 | `parametres.json`, κ | Es la única palanca que queda en semanas normales: el gradiente exacto usa E_b/C_b **de las semanas de test**, que no se conocen | Score frente a κ ± 20 % sobre `real_val`. Si es plano, se deja |

---

## 3. Equipo generador de escenarios: punto de partida

**Partid del merge actual** (`scenario_api 3/`) **más el puente adjunto** (`forecaster_impl.py`, `forecaster_base.py`, `export_from_scenario_api.py`). El contrato está en ARQUITECTURA_GENERADOR.md, y su §10 explica el puente.

El puente ya cumple el contrato (probado con el `gaussian.joblib` del repo):
- Carga desde una carpeta plana **sin** `sklearn` ni el paquete `generators`; 88 KB.
- `predict`: p50 0,75 ms, p99 1,2 ms (límite 10 ms).
- Cuantiles p10…p90 iguales a los del Monte Carlo de la API con 20.000 trayectorias (± 3 kW).
- Determinista; `timestamp` como `str` o `Timestamp` da lo mismo; H = 1, 5 y 24; `history` vacía.

**Tareas, por orden:**
1. **Reentrenar sin las semanas `real_val`.** El `gaussian.joblib` actual se ajustó con todo, incluidas las semanas de evaluación.
2. **`scenarios.py` (Fase 1)**, con prioridad en las semanas donde el generador puede importar: festivos y puentes, agosto, fines de semana de verano, `pv × 1,5`, `load × 0,5`, `pv_surplus`, `zero_load`. Son las únicas en las que D puede diferir de C.
3. **Demostrar D ≥ C en esas familias** y elegir `forecaster_quantile` (Fase 4). Si D < C en alguna familia razonable → `use_forecaster: false`.
4. No invertir en bajar el RMSE sobre `real_val` (§0).

---

## 4. Front: contrato de datos

El harness del agente escribe un fichero por variante y familia: `results/run_<variante>_<escenario>.json`. Las claves de `hours` son las mismas que las de `energyData` en `frontend/src/data/mockData.ts`, así que el front solo cambia el `import` por un `fetch`.

```json
{
  "meta": {
    "variant": "C",
    "scenario": "real_val/2026-03",
    "score": 5.63,
    "co2_estalviat_pct": 5.20,
    "cost_estalviat_pct": 6.62,
    "infraccions": 0,
    "generated_at": "2026-11-14T16:00:00"
  },
  "hours": [
    {
      "timestamp": "2026-03-15T00:00:00",
      "hour": "00:00",
      "load": 650.0,
      "solar": 0.0,
      "battery": -40.0,
      "grid": 610.0,
      "soc": 50.0,
      "co2": 0.42,
      "cost": 0.16,
      "mode": "v1"
    }
  ]
}
```

| Campo | Unidad | Notas |
|---|---|---|
| `load`, `solar`, `grid` | kW | `grid` = importación tras la batería (≥ 0) |
| `battery` | kW | > 0 carga, < 0 descarga (consigna aplicada tras el recorte) |
| `soc` | % | 0–100, al inicio de la hora |
| `co2` | kg/kWh | de la red en esa hora |
| `cost` | €/kWh | precio PVPC en esa hora |
| `mode` | — | `"v1"` o `"forecast"` (de `agent.last_info`) |

Responsable: equipo agente, con una función `export_run_json(...)` en `run_scenarios.py`. Hasta entonces el front sigue con `mockData.ts`, que ya tiene esta forma.