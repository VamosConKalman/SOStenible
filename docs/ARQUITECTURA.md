# Arquitectura del generador de carga neta (`NetLoadForecaster`)

Especificación para implementar el generador que usa `BatteryAgent` (Datathon UPC Sostenible 2026). Cualquier implementación que cumpla este contrato se puede enchufar al agente sin tocar el LP.

La clase base está en `forecaster_base.py` (se entrega junto a este documento). **No la modifiques**: hereda de ella.

> **Equipo generador de escenarios:** si partís de `scenario_api`, id directamente al §10. El puente ya cumple este contrato. Antes de invertir en mejorar el modelo, leed REPARTO_EQUIPO.md §0: en semanas normales la previsión no cambia el score.

---

## 1. Qué hace y qué no hace

**Hace:** cada hora `t`, predice la **carga neta** del campus para las horas `t, t+1, …, t+H−1`:

$$N_k = \text{load\_kw}_k - \text{pv\_kw}_k \quad (\text{kW, media horaria})$$

**No hace:** no decide nada sobre la batería, no lee precios para optimizar y no guarda estado entre llamadas a `predict` (todo el contexto le llega en los argumentos).

---

## 2. Cómo se entrega

```
submission.zip                (estructura plana, sin carpetas)
├── agent.py                  (no lo tocas)
├── lp_model.py               (no lo tocas)
├── forecaster_base.py        (no lo tocas)
├── forecaster_impl.py        ← tu clase
├── forecaster.pkl            ← tu instancia entrenada (joblib)
└── parametres.json
```

- El agente hace `joblib.load(Path(__file__).parent / "forecaster.pkl")` dentro de un `try`. Si falla, funciona sin generador (modo v1) **sin avisar**: comprobad siempre que la carga funciona desde una carpeta plana (§7.1).
- **Entrena y guarda el `.pkl` desde la carpeta del zip** con `from forecaster_impl import TuClase`, para que el pickle referencie el módulo `forecaster_impl` y no `src.forecaster_impl`, `generators.gaussian_mc` o similar.
- Nombre de la clase: libre. Debe heredar de `NetLoadForecaster`.

---

## 3. Contrato

### 3.1 Métodos

```python
class TuClase(NetLoadForecaster):
    def fit(self, hourly_df: pd.DataFrame) -> "TuClase": ...      # solo en local
    def predict(self, obs: dict, history: list, horizon: int): ...  # en el servidor
```

**`fit(hourly_df)`** (solo se ejecuta en local, antes de guardar el `.pkl`):

- `hourly_df`: DataFrame horario con columnas `Fecha` (datetime), `load_kw`, `pv_kw`, `precio_eur_per_kwh`, `co2_kg_per_kwh`. Es la salida de `data_loader.load_hourly_df()` con `reset_index()`.
- Puede tener huecos (horas sin datos). Las semanas de evaluación se excluyen **antes** de llamar a `fit` (§6).

**`predict(obs, history, horizon)`** (se llama una vez por hora, 2.016 veces en el test):

| Argumento | Tipo | Contenido |
|---|---|---|
| `obs` | `dict` | El diccionario del simulador **sin modificar** (ver §3.2) |
| `history` | `list[tuple]` | `[(ts_medida, load_kw, pv_kw), ...]`, ordenada en el tiempo. `ts_medida` es el **inicio** de la hora medida (`pd.Timestamp`). La última entrada, si existe, es normalmente `t − 1h`. Solo contiene medidas válidas (§3.3) |
| `horizon` | `int` | H, entre 1 y 24 |

### 3.2 Campos de `obs`

| Clave | Tipo | Notas |
|---|---|---|
| `timestamp` | `Timestamp` o `str` | Hora actual `t`. Usa siempre `pd.Timestamp(obs["timestamp"])` |
| `hour`, `day_of_week` | `int` | 0–23; 0 = lunes |
| `soc_kwh`, `soc_pct` | `float` | Estado de la batería (no lo necesitas) |
| `preu_actual`, `co2_actual` | `float` | Precio (€/kWh) y CO₂ (kg/kWh) de la hora t |
| `preus_properes_24h`, `co2_properes_24h` | `list[float]` | Próximas 24 h, **exactos** (no son previsión). Índice 0 = t (el agente lo comprueba). Pueden tener menos de 24 valores al final de la serie |
| `noves_dades_5min` | `dict` | `ultim_consum_kw`, `ultima_solar_kw`: medias de la hora t−1. Ya están incluidas en `history` si son válidas: **no las uses directamente** |

**No hay meteorología en el test.** `meteo.csv` solo existe en train. Lo que puedes usar en `predict` es: calendario, `history`, los vectores de precio y CO₂, y lo que hayas aprendido en `fit`.

> Pista: el CO₂ y el precio peninsulares de mañana a mediodía bajan cuando hace sol en España. Es un indicador del sol del día siguiente conocido de antemano, y puede servir para prever `pv_kw`.

### 3.3 Reglas de `history`

- El agente añade `(ts − 1h, ultim_consum_kw, ultima_solar_kw)` en cada hora, **salvo** si la medida no es válida: es la primera hora del agente, la hora anterior no es exactamente `ts − 1h` (salto entre semanas de test), o consumo y solar son ambos exactamente 0.
- Por tanto `history` **puede tener saltos** (el test son 12 semanas separadas, una por mes). Usa los timestamps, nunca las posiciones (`history[-24]` **no** es "hace 24 h" en general).
- `history` puede estar vacía (primera hora del test).

> Estado en `main` (`8631320`): el agente todavía guarda `(ts − 1h, max(0, N))`. Está en la lista de correcciones del equipo agente (REPARTO_EQUIPO.md §2, n.º 2). Programad contra este contrato, no contra `main`.

### 3.4 Salida: tres formatos aceptados

En todos: valores en **kW**, **índice 0 = hora actual t**, longitud `horizon` en la dimensión temporal, `np.float64`. `NaN` o `inf` = "sin previsión para esa hora" (el agente lo trata como hora sin generador). La carga neta **puede ser negativa** (excedente solar): **no la recortes a 0**.

| Formato | Tipo | Forma |
|---|---|---|
| **Puntual** | `np.ndarray` | `(H,)` |
| **Cuantiles** (recomendado) | `dict[str, np.ndarray]` | claves `"p10"`, `"p50"`, `"p90"` obligatorias, cada una `(H,)`. Puedes añadir otras (`"p05"`, `"p30"`…). Deben cumplir p10 ≤ p50 ≤ p90 en cada hora |
| **Escenarios** | `dict` | `"scenarios"`: `np.ndarray (S, H)`, S ≤ 50; `"probs"`: `np.ndarray (S,)`, ≥ 0, suma 1 (si falta, equiprobables) |

Si la longitud es menor que H, el agente rellena con `inf`; si es mayor, recorta. Aun así, devuelve longitud H.

---

## 4. Cómo usa el agente tu salida (y qué conviene optimizar)

1. **Reducción a un vector.** El agente convierte cualquier formato en un único N̂ de longitud H:
   - Puntual → tal cual.
   - Cuantiles → interpolación lineal entre niveles en `q = forecaster_quantile` (de `parametres.json`).
   - Escenarios → cuantil ponderado por `probs`, hora a hora, en el mismo `q`.
2. **El LP solo usa N̂ donde N̂ < 500 kW.** Por encima de 500 kW la batería (±500 kW) no puede llevar la importación a 0 y la decisión no depende de la carga. **Un error en horas con N ≥ 500 kW no cambia nada.** En train solo el **0,5 %** de las horas tiene N < 500 kW.
3. **El error es asimétrico.**
   - Si **sobrestimas** N en horas con N < 500 → el agente descarga más de lo que el campus consume → esa energía se exporta gratis y **se pierde**.
   - Si **subestimas** N → descarga menos de lo posible, pero la energía **sigue en la batería** y se usa más tarde.
   - Por eso el agente usa un cuantil bajo (q ≈ 0,3, a calibrar). Una distribución bien calibrada (cuantiles o escenarios) vale más que una media muy precisa.
4. **La hora t (índice 0) es la más importante**: es la única decisión que se ejecuta. Las demás solo orientan el plan.
5. **No hace falta** correlación temporal entre horas: el agente reduce hora a hora. Los escenarios solo aportan si te resulta más fácil generarlos que los cuantiles.

---

## 5. Restricciones técnicas (`forecaster_impl.py` y `forecaster.pkl`)

| Restricción | Valor |
|---|---|
| Imports permitidos (enunciado) | `numpy`, `pandas`, `scipy`, `scikit-learn`, `joblib`, `xgboost`, `lightgbm`, `math`, `random`, `datetime`, `collections`, `itertools`, `json`, `pathlib`, `typing`, `dataclasses`, `functools`, `heapq`, `bisect`, `re`, `copy`, `pickle`, y `forecaster_base` |
| Prohibido (rechazo por análisis AST del servidor) | red (`requests`, `urllib`, `socket`, `http`…), `os.system`, `os.popen`, `subprocess`, `sys.exit`, `shutil.rmtree`, `pty`, `posix`, `eval`, `exec`, rutas fuera de la carpeta del zip. **Por prudencia, no importes `os` ni `sys`**: no hacen falta |
| Ficheros auxiliares | Solo en `__init__` del agente o al cargar el `.pkl`, siempre con `Path(__file__).parent`. Nunca abrir ficheros en `predict` |
| Tiempo de `predict` | **p99 < 10 ms** (2.016 llamadas + LP deben caber holgadamente en 60 s) |
| Tamaño del `.pkl` | < 15 MB (el zip entero ≤ 25 MB) |
| Excepciones | `predict` no debería lanzar ninguna. Si algo falla, devuelve `np.full(horizon, np.nan)` |
| Determinismo | Misma entrada → misma salida. Si usas aleatoriedad (escenarios), `np.random.default_rng(semilla)` con semilla derivada del timestamp |
| Estado | `predict` no modifica `self` (se llama con el objeto cargado del pickle) |
| Versiones | Si usas `scikit-learn`, `xgboost` o `lightgbm`, la versión de entrenamiento debe coincidir con la del servidor. **Recomendado:** modelos que se guarden como arrays de `numpy` (tablas por hora y día, coeficientes de regresión, árboles exportados), que no dependen de versiones |

---

## 6. Entrenamiento y evaluación local

**División de datos (sin fuga de información):**

- **Evaluación** (`real_val`): días 15–21 de cada mes de train, 00:00 → 23:00. Con los datos actuales hay 9 semanas completas (noviembre no tiene datos, junio tiene 2 h de hueco que interpola `data_loader`, agosto acaba el día 16).
- **Entrenamiento**: todo lo demás. El `.pkl` de evaluación se entrena **sin** las semanas `real_val`. El `.pkl` final que se entrega puede reentrenarse con todo.

**Simulación honesta:** al evaluar, recorre cada semana `real_val` hora a hora y construye `history` exactamente como el agente (§3.3), empezando vacía en la primera semana y con saltos entre semanas.

**Métricas a reportar** (en las horas con N real < 500 kW, salvo que se diga otra cosa):

| Métrica | Para |
|---|---|
| MAE del índice 0 y MAE medio de los índices 1..23 | todos los formatos (sobre p50 o la mediana de los escenarios) |
| Pérdida *pinball* en q = 0,1 / 0,3 / 0,5 / 0,9 | cuantiles y escenarios |
| Cobertura del intervalo p10–p90 (ideal ≈ 80 %) | cuantiles y escenarios |
| % de horas con N̂_q > N real y N real < 500 (sobrestimación dañina, §4.3) | todos |
| Tiempo de `predict`: p50 y p99 | todos |

Como en `real_val` casi no hay horas con N < 500, calculad estas métricas también sobre las familias atípicas de `scenarios.py` (festivos, agosto, `pv × 1,5`, `load × 0,5`).

**Juez final:** el score del agente con tu generador frente al agente sin generador (variantes D y C de `run_scenarios.py`), **en todas las familias**. Si D − C < 0 en alguna familia razonable, el generador no se entrega.

---

## 7. Tests de conformidad que debe pasar (`tests/test_forecaster_contract.py`)

1. Carga: `joblib.load("forecaster.pkl")` **desde una carpeta plana que solo contenga los ficheros del zip** (sin el paquete del proyecto en el `PYTHONPATH`) devuelve una instancia de `NetLoadForecaster`.
2. Para H ∈ {1, 5, 24}, con `history` vacía, con 1 entrada y con un salto de 7 días: la salida tiene el formato y la longitud de §3.4, sin excepciones.
3. `obs["timestamp"]` como `str` y como `pd.Timestamp` → misma salida.
4. Dos llamadas idénticas → salida idéntica; `self` no cambia (comparar `joblib.hash` antes y después).
5. Cuantiles: p10 ≤ p50 ≤ p90. Escenarios: `probs` ≥ 0 y suma 1 ± 1e−9.
6. Hay valores negativos posibles: en una hora de verano a mediodía con `pv_kw` alto en train, la predicción puede ser < 0 (no está recortada).
7. Tiempo: 2.016 llamadas seguidas sobre las semanas `real_val` → p99 < 10 ms.
8. Análisis de imports: ningún módulo fuera de la lista de §5.

---

## 8. Entregables

- `forecaster_impl.py` con la clase.
- `train_forecaster.py` (local): carga datos, excluye `real_val`, llama a `fit`, guarda `forecaster.pkl`.
- `eval_forecaster.py` (local): métricas de §6 en una tabla.
- `tests/test_forecaster_contract.py` (§7) en verde.
- Una línea en el informe: formato de salida elegido, métricas de §6 y versiones de las librerías usadas.

---

## 9. Esqueleto mínimo

```python
# forecaster_impl.py
from __future__ import annotations

import numpy as np
import pandas as pd

from forecaster_base import NetLoadForecaster


class PerfilCuantilesForecaster(NetLoadForecaster):
    """Cuantiles de N por (hora, tipo de día), corregidos con la última medida."""

    def __init__(self) -> None:
        self.tabla = np.full((24, 2, 3), np.nan)  # (hora, laborable/finde, p10/p50/p90)

    def fit(self, hourly_df: pd.DataFrame) -> "PerfilCuantilesForecaster":
        df = hourly_df.dropna(subset=["load_kw", "pv_kw"])
        n = (df["load_kw"] - df["pv_kw"]).to_numpy()
        fecha = pd.to_datetime(df["Fecha"])
        hora = fecha.dt.hour.to_numpy()
        finde = (fecha.dt.dayofweek >= 5).to_numpy().astype(int)
        for h in range(24):
            for f in range(2):
                v = n[(hora == h) & (finde == f)]
                if len(v):
                    self.tabla[h, f] = np.quantile(v, [0.1, 0.5, 0.9])
        return self

    def predict(self, obs: dict, history: list, horizon: int):
        try:
            t = pd.Timestamp(obs["timestamp"])
            out = np.full((3, horizon), np.nan)
            for k in range(horizon):
                ts = t + pd.Timedelta(hours=k)
                out[:, k] = self.tabla[ts.hour, int(ts.dayofweek >= 5)]
            return {"p10": out[0], "p50": out[1], "p90": out[2]}
        except Exception:
            return np.full(horizon, np.nan)
```

Es solo un punto de partida para comprobar el contrato. Si partís de `scenario_api`, usad el §10.

---

## 10. Partir de `scenario_api` (equipo generador de escenarios)

### 10.1 Qué se puede reutilizar y qué no

| Pieza de `scenario_api` | ¿Sirve dentro del agente? | Motivo |
|---|---|---|
| API HTTP (`api.py`, Docker) | **No** | Red prohibida en el zip. Sirve para visualizar y analizar fuera de línea |
| `artifacts/gaussian.joblib` tal cual | **No** | El pickle referencia `generators.gaussian_mc`, `generators.mean_models` y `sklearn` → en el zip plano `joblib.load` falla y el agente cae a v1 sin avisar |
| El modelo (media ridge hora × finde × mes, covarianza Ledoit-Wolf de ventanas de 24 h, condicionamiento gaussiano a precio/CO₂ y a t−1) | **Sí**, vía el puente | Se exporta a arrays de `numpy` |
| `reduction.py` (k-means) | No hace falta | El agente reduce hora a hora (§4.5); devolver cuantiles es más barato y exacto |

### 10.2 El puente (ficheros adjuntos)

- **`forecaster_impl.py` → `GaussianNetForecaster(NetLoadForecaster)`.** Mismo modelo que `GaussianMCGenerator`, pero:
  - solo `numpy` y `pandas`; guarda `coef` (4 × 336), `month_table` (12 × 12), `sd` (24 × 4), `cov` (98 × 98) y `sol_cap` (24);
  - **sin muestreo**: antes de recortar, N = dem − sol es lineal en el vector gaussiano condicionado, así que sus cuantiles salen en forma cerrada (media ± z·σ). Devuelve `p10, p20, …, p90`;
  - toma t−1 de `history` (solo si la última entrada es exactamente `t − 1h`, §3.3), no de `noves_dades_5min`.
- **`export_from_scenario_api.py`** (local): `python export_from_scenario_api.py <ruta_scenario_api> forecaster.pkl`. Carga el `GaussianMCGenerator` ajustado y guarda el `GaussianNetForecaster`.

**Aproximación:** no recorta la solar a [0, cap] salvo de noche (cap < 1e−3 → sol = 0, varianza 0). En horas de sol con mucha incertidumbre, la cola baja de `sol` puede quedar por debajo de 0 en el modelo; el efecto en N es pequeño.

### 10.3 Comprobado (con el `gaussian.joblib` de `main`)

| Prueba | Resultado |
|---|---|
| Carga desde carpeta plana, sin `sklearn` ni `generators` importados | OK, 88 KB |
| Cuantiles p10 / p50 / p90 frente al Monte Carlo de la API (20.000 trayectorias, 16-04-2026 08:00) | iguales ± 3 kW en todas las horas |
| `predict`, 2.016 llamadas | p50 0,75 ms; p99 1,24 ms |
| `str` frente a `Timestamp`; H = 1, 5, 24; `history` vacía; monotonía p10 ≤ p50 ≤ p90 | OK |
| Agente completo, 9 semanas `real_val`, q ∈ {0,1; 0,3; 0,5} | 0 infracciones, 0 fallos; score igual a v1 (REPARTO_EQUIPO §0) |

### 10.4 Semántica de `dem` (cierra el punto 1 de REVISION_TECNICA.md)

`dem = −contador`, recortado a [0, 5000], es exactamente el `load_kw` del starter kit (`prep_data.py`) y del simulador, y `net = dem − sol` es la N del agente. Hay que usar la misma definición que el simulador, porque el score se calcula con ella.

### 10.5 Pendiente para este equipo

1. Reentrenar sin las semanas `real_val` (el artefacto actual las incluye).
2. Pasar los tests del §7 con el `.pkl` reentrenado.
3. Evaluar D frente a C en las familias atípicas de `scenarios.py` y proponer `forecaster_quantile`.
4. El GBM (`gbm_template.py`) solo merece la pena si mejora la pérdida *pinball* en horas con N < 500. Si se hace, exportarlo también a `numpy` o fijar la versión de `lightgbm`/`xgboost` del servidor.