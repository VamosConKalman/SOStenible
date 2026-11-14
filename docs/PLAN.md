# PLAN — `BatteryAgent`: MPC con LP (HiGHS) + generador de carga neta

## 0. Resumen

Cada hora `t`, el agente:

1. Lee de `obs` el **precio y el CO₂ de las horas t..t+23**. Son datos exactos y no hay que predecirlos.
2. Pide al **generador** la **carga neta prevista** $\hat N$ (consumo − solar). Es lo único incierto.
3. Resuelve un **LP** con HiGHS sobre el horizonte y aplica solo la decisión de la hora `t` (MPC / *rolling horizon*).

Sin generador (o si falla), el agente funciona en **modo v1**, sin carga neta. Es el modo seguro.

### Cambios respecto a la versión anterior

| # | Antes | Ahora |
|---|---|---|
| 1 | `net_forecast` se rellenaba desde fuera | El servidor solo llama a `act(obs)`, así que **la previsión se genera dentro del agente**, con un generador incluido en el zip |
| 2 | `solve_lp` vivía dentro de `agent.py` | Pasa a **`lp_model.py`**: el modelo se separa del orquestador para probarlo de forma aislada |
| 3 | No había contrato con el generador | **Interfaz `NetLoadForecaster`** (§3) y un **adaptador** que alinea índices, rellena huecos y gestiona los fallos |
| 4 | No había historial | `self.history` acumula la carga neta medida (`noves_dades_5min`) |
| 5 | La verificación solo comparaba v1 con el oráculo | **Escalera de 6 variantes** que separa la pérdida por horizonte de la pérdida por previsión (§7) |
| 6 | Generador en t+1..t+23 | **El LP también necesita $\hat N_t$** (hora actual), que tampoco se conoce. Ver §3.2 |

---

## 1. Arquitectura

```
submission.zip                        (estructura plana: sin subcarpetas ni paquetes)
├── agent.py               Orquestador: BatteryAgent.act(obs)
├── lp_model.py            solve_lp(): construcción + resolución del LP (puro, sin estado)
├── forecaster_base.py     Interfaz abstracta NetLoadForecaster
├── forecaster_impl.py     Tu implementación concreta (la clase del generador)
├── forecaster.pkl         Instancia entrenada (joblib)
└── parametres.json        kappa, q / v_coef, eps, delta, w_co2, w_cost, use_forecaster

herramientas locales (no se entregan)
├── prep_data.py           CSV → hourly.csv + diagnóstico (% horas con N<500)
├── common.py              semanas, κ, totales, score oficial (1 pt/infracción)
├── calibrate.py           κ + duales del oráculo → q o v_coef
├── backtest.py            escalera de variantes (§7)
└── tests/test_lp.py       pruebas unitarias del LP (§7.1)
```

### Responsabilidades

| Módulo | Hace | No hace |
|---|---|---|
| `agent.py` | Parsear `obs`, mantener el historial, calcular H, w y V, llamar al generador y al LP, recortar | Construir matrices ni predecir |
| `lp_model.py` | Recibir `w, s0, V, net` y devolver la solución | Leer `obs` ni saber nada de fechas |
| `forecaster_*.py` | Recibir el contexto y devolver $\hat N$ | Leer precios ni decidir |
| `parametres.json` | Valores calibrados | — |

### Flujo de una hora

```
obs ──► BatteryAgent.act(obs)
          │
          ├─ 1. ts = pd.Timestamp(obs["timestamp"]); soc = obs["soc_kwh"]
          ├─ 2. history.append(ts − 1h, ultim_consum_kw − ultima_solar_kw)
          ├─ 3. H, is_end = _horizon(ts, n)                   (§5)
          ├─ 4. w'_k = 0,7·co2_k + 0,3·κ·preu_k,  k = 0..H−1  (exacto, de obs)
          ├─ 5. V = _terminal_value(w', is_end)               (§4.3)
          ├─ 6. N̂ = _get_forecast(obs, H)  → adaptador (§3.2); None si falla
          ├─ 7. res = lp_model.solve_lp(w', soc, V, net=N̂, eps, delta)
          └─ 8. P = clip(c₀ − d₀)  → return float
```

---

## 2. Datos de entrada

| Símbolo | Origen | Exacto o previsto |
|---|---|---|
| $s_0$ | `obs["soc_kwh"]` | exacto |
| $\text{preu}_k$, $\text{co2}_k$ | `obs["preus_properes_24h"]`, `obs["co2_properes_24h"]` (índice 0 = hora `t`) | **exacto** |
| $N_{t-1}$ | `noves_dades_5min` | exacto, medido |
| $\hat N_k$, $k = 0..H-1$ | generador | **previsto** |
| $\kappa,\ q/v_\text{coef},\ \varepsilon,\ \delta$ | `parametres.json` | calibrado |

**Peso horario** (el gradiente exacto del score oficial):

$$w'_k = 0{,}7\,\text{co2}_k + 0{,}3\,\kappa\,\text{preu}_k, \qquad \kappa = \frac{E_b}{C_b} = \frac{\sum \max(0,\text{load}-\text{pv})\,\text{co2}}{\sum \max(0,\text{load}-\text{pv})\,\text{preu}}$$

---

## 3. Generador de carga neta

### 3.1 Interfaz

```python
# forecaster_base.py
from abc import ABC, abstractmethod
import numpy as np

class NetLoadForecaster(ABC):
    """Contrato con BatteryAgent."""

    @abstractmethod
    def predict(self, obs: dict, history: list, horizon: int) -> np.ndarray:
        """
        obs      : el diccionario de la hora actual (sin modificar).
        history  : lista [(timestamp, N_medida_kW), ...] de horas pasadas, la última = t-1.
        horizon  : H (≤ 24).
        Devuelve : array float de longitud `horizon`, en kW, ÍNDICE 0 = HORA ACTUAL t.
                   NaN o inf = "sin previsión para esa hora".
        """
```

Si la interfaz que te den usa otros nombres, se adapta en `_get_forecast` (§3.2) sin tocar el LP.

### 3.2 Adaptador en `agent.py` (`_get_forecast`)

1. Si `use_forecaster` es falso o no hay `forecaster.pkl` → `None` (modo v1).
2. Llamar a `predict` dentro de `try`. Si lanza una excepción → `None` y `self.n_forecast_fail += 1`.
3. **Alinear el índice 0 con la hora `t`.**
   - Si el generador devuelve **t+1..t+23** (23 valores), $\hat N_t$ falta. Pero es **la hora más importante**: es la única decisión que se ejecuta.
   - Opciones, por orden de preferencia:
     a) que el generador incluya `t` (devolver t..t+23);
     b) una estimación propia para `t`: **persistencia** $\hat N_t = N_{t-1}$, o mejor, el valor del generador para t+1 si suele estar más cerca;
     c) `inf` en el índice 0, que equivale a v1 en esa hora.
   - Hay que decidir cuál según el backtest (§7.3).
4. Ajustar la longitud a H: si sobra, se recorta; si falta, se rellena con `inf`.
5. Cambiar `NaN` por `inf`.
6. **Primera hora de cada semana:** el simulador da como "última hora" la hora actual (`t = 0`), o la última hora de la semana anterior si las semanas van concatenadas. Si el historial tiene un salto de más de 1 h, el generador no debe usar ese punto como si fuera `t−1`.

### 3.3 Reglas de empaquetado del `.pkl`

- Entrena y guarda el objeto **desde la carpeta del zip**, importando `from forecaster_impl import MiForecaster`. Así el pickle referencia el módulo `forecaster_impl`, no `src.forecaster_impl`.
- `forecaster_impl.py` y `forecaster_base.py` **van en el zip**. `check_submission.py` analiza todos los `.py`: nada de `os`, `sys`, `importlib`…
- Carga con `joblib.load(Path(__file__).parent / "forecaster.pkl")` dentro de un `try`.
- Las versiones de scikit-learn, xgboost y lightgbm deben coincidir con las del servidor. Si no se puede cargar, el agente cae a v1.
- **Presupuesto de tiempo:** 2.016 llamadas × (LP ≈ 3 ms + `predict`) < 30 s → **`predict` < 10 ms**. Mídelo.

---

## 4. Modelo LP (`lp_model.py`)

### 4.1 Formulación

Sea $R = \{k : \hat N_k < P_{\max}\}$, las horas en las que la importación puede llegar a 0. Si no hay previsión, $R = \emptyset$.

**Variables:**

| Variable | Dominio |
|---|---|
| $c_k$ (carga) | $[0, 500]$ |
| $d_k$ (descarga) | $[0, 500]$ |
| $s_{k+1}$ (energía) | $[\min(\varepsilon,s_0),\ \max(2000-\varepsilon,s_0)]$ |
| $g_k$ (importación), $k \in R$ | $[0,\infty)$ |

**Objetivo:**

$$\min \sum_{k\notin R} w'_k(c_k - d_k) + \sum_{k\in R} w'_k g_k + \delta\sum_k (c_k+d_k) - V s_H$$

**Restricciones:**

$$\text{R1:}\quad s_{k+1} - s_k - \eta_c c_k + d_k/\eta_d = s_0\,\delta_{k0}$$

$$\text{R2:}\quad c_k - d_k - g_k \le -\hat N_k, \qquad k \in R$$

**Consigna:** $P = c_0 - d_0$, recortada a $[-\min(500,(s_0-\varepsilon)\eta_d),\ \min(500,(2000-\varepsilon-s_0)/\eta_c)]$.

**Justificaciones:**
- **Horas fuera de R** ($\hat N_k \ge 500$): la importación $\hat N_k + c_k - d_k \ge 0$ siempre, así que es lineal y el coste va directamente en $c$ y $d$. Verificado: da el mismo resultado que poner R2 en todas las horas (200 casos, diferencia de 10⁻¹³).
- **Horas dentro de R:** como $w'_k > 0$, el óptimo cumple $g_k = \max(0, \hat N_k + c_k - d_k)$. Es una relajación exacta: sigue siendo un LP sin binarias.
- **$\delta = 10^{-6}$:** deshace los empates (carga y descarga simultáneas, ciclos inútiles).

### 4.2 Forma matricial

| Bloque | Índices en $x$ |
|---|---|
| $c$ | `0:H` |
| $d$ | `H:2H` |
| $s$ | `2H:3H` ($s_H$ = `3H−1`) |
| $g$ | `3H:3H+|R|` |

- **`A_eq`** ($H$ filas): `(k,2H+k)=1`, `(k,2H+k−1)=−1` si $k \ge 1$, `(k,k)=−η_c`, `(k,H+k)=1/η_d`, `b_eq=[s0,0,…]`.
- **`A_ub`** ($|R|$ filas): `(j,R_j)=1`, `(j,H+R_j)=−1`, `(j,3H+j)=−1`, `b_ub=−N̂_{R_j}`.
- Matrices en `scipy.sparse` y `linprog(method="highs")`.
- Tamaño máximo: 96 variables y 48 restricciones, unos 3 ms por llamada.

### 4.3 Valor terminal $V$

- $V = 0$ si `is_end`.
- Si no, $V = a + b\cdot\text{med}(w') + c\cdot\max(w')$ cuando hay `v_coef`, o $V = \eta_d\,Q_q(w')$ en caso contrario. Siempre acotado a $[0, \max(w')/\eta_c]$.
- **Calibración** (`calibrate.py`): duales del oráculo semanal. $\lambda_k = -$`eqlin.marginals[k]` es el valor marginal de un kWh almacenado. $q$ = mediana de los rangos percentiles de $\lambda_{t+23}/\eta_d$ en cada ventana. Si el IQR es mayor que 0,2, se ajusta la regresión.

---

## 5. Horizonte

- $n = \min(\text{len(preus)}, \text{len(co2)})$.
- Fin de periodo: último día del mes a las 23:00 (en backtest, `agent.period_ends`).
- $H = \min(n, 24, \text{horas hasta fin de periodo})$ e `is_end = (hours_left ≤ H)`.
- **H = 24 casi siempre.** Solo baja durante las últimas 23 h de cada semana de test, para no ver precios de otro mes.

---

## 6. Robustez (`agent.py`)

- `act` = `try: _act(obs) except: return 0.0`, y un contador `self.n_fail` para depurar.
- Si el LP no termina en óptimo (`status ≠ 0`) → 0.0. Si falla el generador → v1. Si no hay `.pkl` → v1.
- `pd.Timestamp(obs["timestamp"])`, porque el validador lo pasa como string.
- `self.last_info = {H, V, is_end, mode: "v1"|"forecast", P, status}` para diagnóstico.

---

## 7. Verificación

### 7.1 Nivel 1: el LP es correcto (`tests/test_lp.py`)

| Prueba | Criterio |
|---|---|
| Formulación híbrida vs. R2 en todas las horas, 200 casos aleatorios | Diferencia de objetivo < 1e−8 |
| Precio y CO₂ constantes | P = 0 |
| SOC = 0 / SOC = 2000 | No descarga / no carga |
| Vector de longitud 3, último día del mes | H truncado, V = 0 |
| $\hat N$ = 100 kW, hora cara | Descarga ≤ 100 kW |
| $\hat N$ < 0, hora barata | Carga hasta $|\hat N|$ (gratis) |
| Duales del oráculo | $\lambda \ge 0$ |

### 7.2 Nivel 2: integración en el simulador

- 0 infracciones en todas las semanas de validación, en los modos reinicio y concatenado.
- Tiempo para 2.016 h **con el generador** < 30 s.
- `check_submission.py submission.zip` pasa **con el zip completo**, no solo con `agent.py`.
- Si se borra `forecaster.pkl`, el agente sigue funcionando en v1.

### 7.3 Nivel 3: escalera de variantes (`backtest.py`)

Todas sobre las mismas semanas de validación (días 15–21 de cada mes), con el score sobre los totales agregados:

| # | Variante | $\hat N$ |
|---|---|---|
| A | Sin batería | — (score 0) |
| B | Heurística del kit | — |
| C | **v1** | ninguna |
| D | **MPC + generador** | tu modelo (**la que se entrega**) |
| E | MPC + previsión perfecta | N real de t..t+H−1 |
| F | Oráculo semanal | todo conocido, 168 h |

**Diagnóstico por diferencias:**

| Diferencia | Mide | Si es grande |
|---|---|---|
| F − E | Pérdida por horizonte de 24 h y V | Recalibrar V |
| E − D | Pérdida por error de previsión | Mejorar el generador |
| D − C | Lo que aporta el generador | **Debe ser ≥ 0.** Si es negativa, entrega v1 (`use_forecaster: false`) |
| C − B | Lo que aporta el LP frente a reglas fijas | — |

**Métrica del generador:** el MAE **solo en las horas con N real < 500 kW**, con $\hat N_t$ (índice 0) por separado. Fuera de esas horas, un error no cambia ninguna decisión.

**Robustez de los parámetros:**
- Sensibilidad a $q$: el score frente a $q$ ∈ {0,3…0,7} debe ser plano alrededor del valor calibrado.
- Validación cruzada dejando un mes fuera para $q$ y κ.

---

## 8. Orden de trabajo

1. Separar `lp_model.py` de `agent.py`. Escribir `tests/test_lp.py` (§7.1) y comprobar que pasa.
2. `prep_data.py` con datos reales → % de horas con N < 500 kW. Eso indica cuánto puede aportar el generador.
3. `calibrate.py` → κ, $q$ o `v_coef`.
4. `backtest.py`: variantes A, B, C, E y F. Así se conocen el techo y lo que da v1 **antes** de integrar el generador.
5. Integrar el generador (`forecaster_base.py`, `forecaster_impl.py`, `.pkl`, adaptador §3.2). Variante D.
6. Decidir con D − C: generador sí o no. Decidir con el backtest qué hacer con $\hat N_t$ (§3.2.3).
7. Nivel 2 completo con el zip final y entregar.

## 9. Pendiente de confirmar

- La interfaz definitiva del generador (`.md` que te pasarán). Comprobar sobre todo **si incluye la hora actual t**.
- Si el servidor ejecuta las 2.016 h seguidas o reinicia en cada semana (el agente funciona en ambos casos).
- Las versiones de las librerías del servidor (para el `.pkl`).