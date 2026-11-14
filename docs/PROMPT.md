Eres el agente de implementación del proyecto `BatteryAgent` (Datathon UPC Sostenible 2026). Tu especificación es `plan.md`, en la raíz del proyecto. Léelo entero antes de tocar nada.

## Contexto

- `agent.py` es un MPC: cada hora resuelve un LP (scipy HiGHS, en `lp_model.py`) con los precios y el CO₂ de las próximas 24 h y aplica solo la decisión de la hora actual.
- `forecaster_base.py` define la interfaz `NetLoadForecaster.predict(obs, history, horizon)` → N̂ (carga neta, kW) con índice 0 = hora actual.
- `environment.py` y `data_loader.py` son herramientas locales (mock del simulador y carga de `data/train/`).
- La formulación del LP está validada. **No la cambies** salvo la corrección 0.2 del plan.

## Cómo trabajar

1. Trabaja **fase a fase** (0 → 1 → 2 → 3). Dentro de cada fase, sigue el orden de la tabla.
2. Por cada corrección o componente: escribe primero su test (en `tests/`, con `pytest`), compruébalo en rojo, implementa y compruébalo en verde.
3. **Al terminar cada fase, para**: ejecuta `pytest -q` completo, muestra la salida y un resumen de los ficheros cambiados (con `git diff --stat` si hay repositorio). No empieces la siguiente fase hasta que te lo confirme.
4. Si algo del plan es ambiguo o contradice el código, **pregunta antes de decidir**. No inventes interfaces que no estén en el plan.
5. Cambios mínimos: no reformatees ni reorganices código que el plan no toca.

## Reglas duras para los ficheros que se entregan

(`agent.py`, `lp_model.py`, `forecaster_base.py`, `forecaster_impl.py`, `parametres.json`)

- Solo pueden importar: `numpy`, `pandas`, `scipy`, `scikit-learn`, `joblib`, `xgboost`, `lightgbm`, `math`, `random`, `datetime`, `collections`, `itertools`, `json`, `pathlib`, `copy`, `typing`, `abc`, `__future__`, y los módulos propios del zip.
- **Prohibido**: `os`, `sys`, `subprocess`, `importlib`, `eval`, `exec`, `open` fuera de `Path(__file__).parent`, cualquier acceso a red. El servidor rechaza el zip por análisis AST.
- `BatteryAgent` usa `__slots__`: **todo atributo nuevo debe añadirse a `__slots__`**.
- `act()` nunca lanza excepciones.
- Nada del oráculo (`sigma`, `phi`, etc.) va en `parametres.json`: va en `scenarios_config.json`, que es local.

Las herramientas locales (`scenarios.py`, `oracle_forecaster.py`, `baselines.py`, `run_scenarios.py`, tests) pueden usar cualquier librería, incluido `matplotlib`.

## Calidad

- Todo lo aleatorio con `np.random.default_rng(seed)`; resultados reproducibles.
- Docstrings y comentarios en castellano. Respeta exactamente los nombres de variables, columnas y claves del plan (`load_kw`, `pv_kw`, `precio_eur_per_kwh`, `co2_kg_per_kwh`, `Fecha`, `forecaster_quantile`, etc.).
- Tipado en las funciones públicas.
- Rendimiento: 2.016 llamadas a `act()` < 30 s. Al final de la Fase 3, informa de ms/`act` (p50, p99, total).

## Entregable de cada fase

Al parar, informa en este formato:

```
FASE N — estado: OK / BLOQUEADA
Tests: X pasados, Y fallidos (salida de pytest -q)
Ficheros cambiados: ...
Decisiones tomadas no explícitas en el plan: ...
Dudas abiertas: ...
```

Empieza por la Fase 0.