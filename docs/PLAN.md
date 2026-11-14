# PLAN — Correcciones + generador de escenarios + generador oráculo

Contexto: `BatteryAgent` (MPC con LP HiGHS) del Datathon UPC Sostenible 2026. Este plan **no cambia la formulación del LP** (PLAN.md §4) salvo la corrección 0.2. Objetivo: poder probar el agente de principio a fin sobre escenarios realistas y con previsiones de error controlado, mientras el equipo termina su generador real (*generation*).

---

## 0. Reglas generales

### 0.1 Ficheros que se entregan vs. herramientas locales

```
ENTREGA (submission.zip, estructura plana)
├── agent.py
├── lp_model.py
├── forecaster_base.py
├── forecaster_impl.py
├── forecaster.pkl          (opcional)
└── parametres.json

LOCAL (no se entregan)
├── data_loader.py
├── environment.py          (mock del simulador)
├── scenarios.py            Fase 1: construcción de escenarios
├── oracle_forecaster.py    Fase 2: generador oráculo con ruido
├── baselines.py            Fase 3: heurística B y oráculo semanal F
├── run_scenarios.py        Fase 3: harness y métricas
├── scenarios_config.json   parámetros de escenarios y del oráculo
└── tests/
    ├── test_fixes.py       Fase 0
    ├── test_scenarios.py   Fase 1
    └── test_oracle.py      Fase 2
```

### 0.2 Restricciones de los ficheros que se entregan

- Solo `numpy`, `pandas`, `scipy`, `scikit-learn`, `joblib`, `xgboost`, `lightgbm` y los módulos estándar `math`, `random`, `datetime`, `collections`, `itertools`, `json`, `pathlib`, `copy`, `typing`.
- **Prohibido** (rechazo por AST): `os`, `sys`, `subprocess`, `importlib`, `eval`, `exec`, red, lectura de ficheros fuera de `Path(__file__).parent`.
- `act()` nunca lanza excepciones: `try → return 0.0`.
- Presupuesto: **2.016 llamadas a `act()` < 30 s en local** (la mitad del límite de 60 s, por margen frente al servidor).

### 0.3 Lo que NO va en `parametres.json`

`sigma`, `ar_phi` y cualquier parámetro del oráculo son **solo locales** (`scenarios_config.json`). El oráculo usa la carga real futura: nunca se entrega.

### 0.4 Forma de trabajar

Fase a fase. Al acabar cada fase: ejecutar sus tests, mostrar la salida y parar. No pasar a la siguiente fase con tests en rojo.

---

## Fase 0 — Correcciones (con un test por corrección en `tests/test_fixes.py`)

| # | Fichero | Corrección | Test de aceptación |
|---|---|---|---|
| 0.1 | `agent.py` | Añadir `w_co2`, `w_cost` (y los atributos nuevos de esta fase) a `__slots__` | `BatteryAgent()` se construye; también sin `parametres.json` (valores por defecto) |
| 0.2 | `lp_model.py` | En `solve_lp`, condición de R = `np.isfinite(n) and n < P_MAX` (quitar `n > 0`) | (a) N̂ = 0 en las 24 h, w alto, s0 = 1000, V = 0 → `d_0 == 0`. (b) N̂ = −200 en las 12 primeras horas (w bajo) y N̂ = +300 en las 12 siguientes (w alto), s0 = 1000 → `c_0 ≥ 199` |
| 0.3 | `lp_model.py` | `compute_weights(co2, price, kappa, w_co2=0.7, w_cost=0.3)`; `agent.py` pasa `self.w_co2`, `self.w_cost` | Con `w_co2 = 1, w_cost = 0` → `w == co2` |
| 0.4 | `lp_model.py` | `solve_lp(..., return_result=False)`: si `True`, devuelve el objeto `OptimizeResult`. `get_dual_marginals` devuelve `-result.eqlin.marginals` (longitud H) | Caso aleatorio: longitud H y todos los λ ≥ −1e−9 |
| 0.5 | `environment.py` | `self.df = hourly_data.copy().reset_index()` (sin `drop=True`); si la columna se llama `index`, renombrarla a `Fecha` | `obs["timestamp"]` de la primera hora == primera fecha del DataFrame |
| 0.6 | `environment.py` | Score oficial: `score = max(0, 70·d_co2 + 30·d_cost − 1·infraccions)` con `d_*` en fracción (equivale a % × peso) | Misma semana, mismas acciones salvo t = 0: consigna 900 kW (recortada a 500, 1 infracción) frente a 500 kW. Efecto físico idéntico → la diferencia de score es exactamente 1,00 (elegir una semana con score > 1) |
| 0.7 | `agent.py` | **Fin de periodo desde `ts`**: `period_end = último día del mes de ts a las 23:00`. `hours_left = (period_end − ts)/1h + 1` (incluye la hora actual). `H = min(n, 24, hours_left)`, `is_end = hours_left ≤ 24 or n < 24`. Se elimina el uso de `obs["period_ends"]` | `2026-01-31 23:00` → H = 1, is_end, V = 0. `2026-01-31 00:00` → H = 24, is_end. `2026-01-15 10:00` → H = 24, no is_end |
| 0.8 | `agent.py` | **Override para backtest**: atributo `self.period_end_override: pd.Timestamp | None` (en `__slots__`, por defecto `None`). Si no es `None`, sustituye al fin de mes. Lo fija el harness, nunca el `obs` | Con override = `2026-01-21 23:00` y ts = `2026-01-21 20:00` → H = 4, is_end |
| 0.9 | `agent.py` | **Historial**: se guarda `(ts − 1h, N_medida)`. Se marca como **no válida** (no se guarda) la medida si: es la primera llamada del agente, o el `ts` anterior registrado no es exactamente `ts − 1h` (salto de semana), o consumo y solar son ambos exactamente 0 | Primera hora de una semana → historial sin cambios; hora siguiente → entrada con timestamp `ts − 1h` |
| 0.10 | `agent.py` | **Guard del índice 0**: si `abs(preus[0] − preu_actual) > 1e−9` o `abs(co2s[0] − co2_actual) > 1e−9`, se asume que los vectores empiezan en t+1 → anteponer `preu_actual` y `co2_actual`. Contador `self.n_index_shift` (en `__slots__`) | Vector desplazado → w[0] calculado con `preu_actual`; contador = 1 |
| 0.11 | `agent.py` | **Adaptador de cuantiles** en `_get_forecast`: acepta `ndarray` de forma (H,) (puntual) o `dict` con claves `p10`, `p50`, `p90` (cada una de longitud H). Si es dict, interpola linealmente en `q = self.forecaster_quantile` (de `parametres.json`, por defecto 0.5) entre los cuantiles vecinos; fuera de [0.1, 0.9] se recorta. Si es puntual, se usa tal cual (q no aplica) | dict con p10 = 0, p50 = 100, p90 = 200 y q = 0.3 → 50 en todas las horas |
| 0.12 | `forecaster_impl.py` | Quitar el monkeypatch; `import pandas as pd` arriba. Persistencia solo si `history[-1][0] == ts − 1h` | Round-trip `joblib.dump/load` y `predict` devuelve longitud H |
| 0.13 | `data_loader.py` | `get_small_df`: construir el vector de precios con `np.resize` para cualquier `n_hours`. `load_hourly_df`: `asfreq("1h")` antes del `dropna` final, e interpolar huecos ≤ 3 h (`interpolate(limit=3, limit_area="inside")`) | `get_small_df(48)` funciona; el índice de `load_hourly_df` es estrictamente horario dentro de cada tramo |

`parametres.json` tras la Fase 0:

```json
{
  "kappa": 0.55,
  "q": 0.5,
  "v_coef": null,
  "eps": 0.5,
  "delta": 1.0e-06,
  "w_co2": 0.7,
  "w_cost": 0.3,
  "use_forecaster": false,
  "forecaster_quantile": 0.3
}
```

Además: los tests del PLAN.md §7.1 que ya existan deben seguir pasando.

---

## Fase 1 — Escenarios de datos (`scenarios.py`)

### 1.1 Estructura

```python
@dataclass
class Scenario:
    name: str                 # p. ej. "real_val/2025-10" o "perturbed/s3/2025-10"
    df: pd.DataFrame          # columnas: Fecha, load_kw, pv_kw, precio_eur_per_kwh, co2_kg_per_kwh
                              # 168 filas, horas consecutivas, sin NaN
    period_end: pd.Timestamp  # última hora del periodo (se pasa al agente como override)
    family: str               # "real_val" | "real_rolling" | "perturbed" | "stress"
    seed: int | None
```

`build_scenarios(family, **kwargs) -> list[Scenario]`. Todo determinista dada la semilla (`np.random.default_rng(seed)`).

### 1.2 Familias

1. **`real_val`** (réplica del test): para cada mes de train, la semana de los días 15–21 (00:00 del día 15 → 23:00 del día 21). 12 semanas = 2.016 h. `period_end` = día 21 a las 23:00. Si una semana tiene un hueco > 3 h tras la interpolación, se descarta y se informa.
2. **`real_rolling`**: todas las semanas completas de train que empiezan en lunes 00:00, excluyendo las de `real_val` (sirven para entrenar y calibrar sin fuga de información).
3. **`perturbed`**: `n_replicas` copias de `real_val` con semillas distintas. **Solo se perturban `load_kw` y `pv_kw`** (precio y CO₂ los da el `obs` exactos):
   - Consumo: factor diario `~ N(1, σ_day_load)` × ruido horario AR(1) multiplicativo (`φ_load`, `σ_h_load`). Recortar a [0, 5000].
   - Solar: factor diario de nubosidad `~ U(pv_min, pv_max)`, igual para las 24 h del día. Recortar a ≥ 0.
   - Opcional: *bootstrap* de días completos entre días del mismo mes y el mismo tipo (laborable / fin de semana).
4. **`stress`** (semanas sintéticas o derivadas de una semana real):
   - `const_price_co2`: precio y CO₂ constantes → el agente debe dar P ≈ 0 todo el tiempo.
   - `pv_surplus`: N < 0 de 10:00 a 16:00 todos los días → debe cargar gratis en esas horas.
   - `high_load`: N ≥ 600 kW siempre → el generador no puede cambiar nada (D == C).
   - `price_spikes`: picos de precio y CO₂ ×5 en 3 horas aisladas.
   - `zero_load`: N = 0 en las 168 h → no debe descargar nunca (comprueba la corrección 0.2).
   - `short_horizon`: semana que acaba a mitad de un día (comprueba H < 24 e is_end).

### 1.3 `scenarios_config.json` (solo local)

```json
{
  "data_dir": "data/train",
  "perturbed": {"n_replicas": 5, "sigma_day_load": 0.05, "phi_load": 0.7,
                "sigma_h_load": 0.03, "pv_min": 0.3, "pv_max": 1.1, "bootstrap_days": false},
  "oracle": {"sigma_abs": 20.0, "sigma_rel": 0.10, "growth": 1.0, "phi": 0.8,
             "bias": 0.0, "p_nan": 0.0, "p_exception": 0.0, "mode": "point",
             "drop_t": false, "latency_ms": 0.0},
  "seed": 12345
}
```

### 1.4 Tests (`tests/test_scenarios.py`)

- `real_val`: 12 semanas, 168 h cada una, horas consecutivas, sin NaN, `Fecha` dentro de los días 15–21.
- `real_rolling` y `real_val` no se solapan.
- `perturbed` con la misma semilla → idéntico; con otra semilla → distinto; precio y CO₂ idénticos al original.
- Todas las familias: `load_kw` ∈ [0, 5000], `pv_kw` ≥ 0.

---

## Fase 2 — Generador oráculo (`oracle_forecaster.py`)

### 2.1 Clase

```python
class OracleForecaster(NetLoadForecaster):
    def __init__(self, true_net: pd.Series, *, sigma_abs, sigma_rel, growth, phi,
                 bias, p_nan, p_exception, mode, drop_t, latency_ms, seed): ...
    def predict(self, obs, history, horizon): ...
```

- `true_net`: serie N real = `load_kw − pv_kw` (**sin** recortar a 0), indexada por `Fecha`. Se busca por `pd.Timestamp(obs["timestamp"]) + k h`. Si la hora no existe → NaN.
- **Error**, para k = 0..H−1:
  - `σ_k = (sigma_abs + sigma_rel·|N_k|) · (1 + growth · k/23)`
  - `e_0 = σ_0·ξ_0`, `e_k = φ·e_{k−1}·(σ_k/σ_{k−1}) + sqrt(1−φ²)·σ_k·ξ_k`
  - `ξ ~ N(0,1)` con `rng = default_rng(hash((seed, ts)))` (reproducible por hora y semilla).
  - `N̂_k = N_k + bias + e_k`
- **`mode = "point"`** → `ndarray` (H,). **`mode = "quantiles"`** → `dict` con `p50 = N̂`, `p10 = N̂ − 1.2816·σ_k`, `p90 = N̂ + 1.2816·σ_k`.
- **Fallos simulados**: con probabilidad `p_exception` lanza `RuntimeError`; con `p_nan` cada valor pasa a NaN; si `drop_t`, devuelve solo t+1..t+H−1 (longitud H−1, comprueba el relleno del adaptador); `latency_ms` añade una espera activa.
- Se inyecta en el agente sin pickle: `agent._forecaster = oracle; agent.use_forecaster = True`.

### 2.2 Tests (`tests/test_oracle.py`)

- Con todo a 0 (σ = 0, sin fallos) → `predict` == N real exacto.
- Misma semilla y mismo ts → misma salida.
- Correlación empírica entre e_k y e_{k+1} ≈ φ (tolerancia 0.05 con 5.000 muestras).
- `mode="quantiles"` → p10 ≤ p50 ≤ p90.
- Con `p_exception = 1` el agente no falla: modo v1 y `n_forecast_fail` sube.
- Con `drop_t = True` el adaptador devuelve longitud H con `inf` en el hueco.

---

## Fase 3 — Harness y métricas (`baselines.py`, `run_scenarios.py`)

### 3.1 Variantes (escalera del PLAN.md §7.3)

| # | Variante | Cómo |
|---|---|---|
| A | Sin batería | acción 0 siempre (score = 0, comprobación de cordura) |
| B | Heurística | cada día: carga 500 kW en las 4 h de menor w, descarga en las 4 h de mayor w, con recorte físico |
| C | v1 | `use_forecaster = False` |
| D | Generador real | `forecaster_impl` entrenado **solo con `real_rolling`** (nunca con las semanas evaluadas) |
| E | Oráculo perfecto | `OracleForecaster` con σ = 0 |
| E(σ, q) | Oráculo con ruido | barrido de σ_rel ∈ {0.05, 0.1, 0.2, 0.3}, modo `quantiles`, q ∈ {0.1, 0.3, 0.5} |
| F | Oráculo semanal | `solve_lp` con H = 168, N real, s0 = 1000, V = 0; se aplican sus acciones en el entorno |

### 3.2 Ejecución

- **Modo `reset`**: una única instancia del agente para las 12 semanas; un entorno nuevo por semana (SOC = 50 %). Antes de cada semana: `agent.period_end_override = scenario.period_end`.
- **Modo `concat`**: las 12 semanas concatenadas en un solo entorno (SOC = 50 % solo al principio), con el override actualizado en la primera hora de cada semana.
- Medir **solo el tiempo dentro de `act()`** (`time.perf_counter` alrededor de cada llamada). Informar del tiempo del oráculo por separado: no representa el del generador real.

### 3.3 Métricas

- **Score oficial sobre totales agregados** de las 12 semanas: sumar coste y CO₂ del participante y de la línea base de todas las semanas y aplicar la fórmula una sola vez (no promediar los scores semanales). Calcularlo desde los arrays crudos del entorno (`grid`, precios, CO₂, carga, solar), no desde los valores redondeados de `evaluate_results`.
- Por variante: score, ΔCO₂ %, ΔCost %, infracciones, `n_fail`, `n_forecast_fail`, `n_index_shift`, ms/`act` (p50, p99, total).
- Diferencias: F − E, E − D, D − C, C − B.
- Curva **score frente a σ_rel** para cada q (tabla CSV + gráfico PNG con matplotlib).
- Diagnóstico de datos: % de horas con N < 500 kW (por mes) → cuánto puede aportar un generador.

### 3.4 Salidas

`results/summary.csv`, `results/sigma_sweep.csv`, `results/sigma_sweep.png` y un resumen en consola.

### 3.5 Criterios de aceptación

- **0 infracciones** en todas las variantes basadas en el agente (C, D, E, E(σ, q)), en todas las familias y en los dos modos.
- Tiempo total de `act()` para 2.016 h con el generador real < 30 s.
- E ≥ C (si no, hay un fallo en el adaptador o en el LP).
- F ≥ E ≥ C ≥ B, salvo ruido; cualquier inversión se señala en el resumen.
- `stress/const_price_co2` → |P| < 1 kW en todas las horas. `stress/zero_load` → nunca descarga.
- Decisión de entrega: si D − C < 0 en `real_val`, se entrega con `use_forecaster: false`.

---

## Fase 4 — Calibración de `forecaster_quantile` (cuando *generation* esté integrado)

- Con el barrido E(σ, q), elegir el q que maximiza el score para el σ que tenga el generador real (medido como su MAE en horas con N < 500 kW sobre `real_rolling`).
- Comprobar que el score es plano alrededor del q elegido (± 0.1). Si no lo es, preferir el q más conservador (más bajo).

---

## Pendiente de confirmar con el servidor

- Si `preus_properes_24h[0]` es la hora t (el guard 0.10 cubre ambos casos; el contador lo dirá en `check_submission.py`).
- Si el servidor reinicia el SOC por semana o ejecuta las 2.016 h seguidas (el harness prueba los dos modos).
- Qué devuelve `ultim_consum_kw` en la primera hora de cada semana (la corrección 0.9 lo descarta en cualquier caso).