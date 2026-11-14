# Plan — Modelo LP del `BatteryAgent` (HiGHS)

Alcance: **solo el modelo de optimización**. En cada llamada a `act(obs)` se resuelve un LP sobre las próximas H hores y se aplica solo la primera decisión (MPC / *rolling horizon*).

---

## 1. Datos de entrada del LP

| Símbolo | Origen | Descripción |
|---|---|---|
| $s_0$ | `obs["soc_kwh"]` | Energía almacenada actual (kWh) |
| $\text{preu}_k$ | `obs["preus_properes_24h"][k]` | Precio de la hora $k$ (€/kWh). **$k=0$ es la hora actual** |
| $\text{co2}_k$ | `obs["co2_properes_24h"][k]` | Intensidad de CO₂ de la hora $k$ (kg/kWh) |
| $H$ | `len(...)`, truncado a 24 | Horizonte (≤ 24) |
| $\hat N_k$ | `self.net_forecast` (opcional) | Carga neta prevista = consumo − solar (kW) |
| $\kappa$ | `parametres.json` | $\kappa = E_b / C_b$ (kg CO₂ / €), estimado en entrenamiento |
| $q$ | `parametres.json` | Cuantil para valor terminal (inicial 0.5) |
| $\varepsilon$ | `parametres.json` | Margen de seguridad del SOC (≈ 0,5 kWh) |

**Constantes:** $P_{\max}=500$ kW, $E_{\max}=2000$ kWh, $\eta_c=\eta_d=\sqrt{0{,}9}$, $\Delta t = 1$ h.

**Peso horario:**

$$w_k = 0{,}7\,\text{co2}_k + 0{,}3\,\kappa\,\text{preu}_k$$

Con $\kappa = E_b/C_b$ estimado en entrenamiento:
$\kappa = \frac{\sum_t \max(0, \text{load}_t - \text{pv}_t)\,\text{co2}_t}{\sum_t \max(0, \text{load}_t - \text{pv}_t)\,\text{preu}_t}$.
Valor inicial: ~0,55 kg/€ (tutorial: 12958,2 / 23544,12). Se recalcula con todo el train y se guarda en `parametres.json`.

---

## 2. Formulación (variante v1, sin previsión de carga neta)

Esta es la variante **por defecto** (cuando `self.net_forecast` es `None`).

### Variables ($k = 0,\dots,H-1$)

| Variable | Dominio | Significado |
|---|---|---|
| $c_k$ | $[0,\ P_{\max}]$ | Potencia de carga (kW) |
| $d_k$ | $[0,\ P_{\max}]$ | Potencia de descarga (kW) |
| $s_{k+1}$ | $[\varepsilon,\ E_{\max}-\varepsilon]$ | Energía al final de la hora $k$ (kWh) |

**Tamaño:** $3H$ variables.

### Función objetivo

$$\min \;\; \sum_{k=0}^{H-1} w_k\,(c_k - d_k)$$

Justificación: la energía real de la red es $\text{grid}_k = \text{load}_k - \text{pv}_k + P_k$, donde $P_k = c_k - d_k$ es la potencia de la batería que aplica el entorno. Como $\text{load} - \text{pv}$ es constante, minimizar $w \cdot \text{grid}$ equivale a minimizar $w \cdot (c - d)$.

**Sin valor terminal:** $V = 0$. La energía sobrante al final del horizonte no se puntúa.

### Restricciones

**(R1) Dinámica de la batería**

$$s_{k+1} - s_k - \eta_c\, c_k + \frac{d_k}{\eta_d} = s_0\,\delta_{k0}, \qquad k = 0,\dots,H-1$$

### Consigna devuelta

$$P = c_0 - d_0$$

recortada a $\big[-\min(P_{\max},\ (s_0-\varepsilon)\,\eta_d),\ \min(P_{\max},\ (E_{\max}-s_0-\varepsilon)/\eta_c)\big]$.

---

## 3. Variante completa: con previsión de carga neta

Se incluye la variable $g_k$ y la restricción R2. Usar cuando `self.net_forecast` aporta estimaciones fiables de $\hat N_k = \text{load}_k - \text{pv}_k$.

### Variables ($k = 0,\dots,H-1$)

| Variable | Dominio | Significado |
|---|---|---|
| $c_k$ | $[0,\ P_{\max}]$ | Potencia de carga (kW) |
| $d_k$ | $[0,\ P_{\max}]$ | Potencia de descarga (kW) |
| $s_{k+1}$ | $[\varepsilon,\ E_{\max}-\varepsilon]$ | Energía al final de la hora $k$ (kWh) |
| $g_k$ | $[0,\ \infty)$ | Importación de la red (kW) |

**Tamaño:** $4H$ variables.

### Función objetivo

$$\min \;\; \sum_{k=0}^{H-1} w_k\, g_k$$

### Restricciones

**(R1) Dinámica de la batería** (igual que v1)

**(R2) Importación ≥ carga neta + batería**

$$g_k \ge \hat N_k + c_k - d_k, \qquad k = 0,\dots,H-1$$

Si $\hat N_k \ge P_{\max}$ o no se proporciona para hora $k$, no se añade R2 para esa hora.

**Sin valor terminal:** $V = 0$.

---

## 4. Forma matricial para `scipy.optimize.linprog(method="highs")`

### Vector de decisión (v1, tamaño $3H$)

$$x = [\,c_0..c_{H-1} \;|\; d_0..d_{H-1} \;|\; s_1..s_H\,]$$

| Bloque | Índices en $x$ |
|---|---|
| $c$ | `0 : H` |
| $d$ | `H : 2H` |
| $s$ | `2H : 3H` |

**Coste `c_vec`:**
- Bloque $c$: $+w_k$.
- Bloque $d$: $-w_k$.
- Bloque $s$: todo 0 (V = 0).

**Igualdades `A_eq x = b_eq`** ($H$ filas, R1). Fila $k$:
- `A[k, 2H+k] = 1` ($s_{k+1}$)
- `A[k, 2H+k-1] = -1` si $k \ge 1$ ($-s_k$)
- `A[k, k] = -η_c` ($c_k$)
- `A[k, H+k] = 1/η_d` ($d_k$)
- `b[k] = s_0` si $k=0$; si no, 0

**Desigualdades:** ninguna (`A_ub` vacío).

**Cotas `bounds`:** `[(0,500)]*2H + [(ε, 2000-ε)]*H` (relajar si $s_0 < \varepsilon$ o $s_0 > E_{\max}-\varepsilon$).

### Llamada

```python
res = linprog(c_vec, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")
P = res.x[0] - res.x[H] if res.success else 0.0
```

Usar `scipy.sparse` para las matrices. ~72 variables para H=24, ~96 para variante completa.

---

## 5. Reglas de horizonte

1. **El índice 0 es la hora actual.** El simulador construye la ventana con `iloc[t : t+24]`.
2. **Truncar por longitud:** $H = \min(\text{len(vector)}, 24)$.
3. **Fin de semana:** si el horizonte llega a un lunes 00:00, `is_end = True`. En la práctica, $V = 0$ siempre.
4. **Rolling horizon MPC:** cada paso, el LP se resuelve sobre la ventana de 24h y se aplica solo la primera decisión ($P_0$).

---

## 6. Interfaz de `self.net_forecast`

- Atributo `self.net_forecast: Optional[np.ndarray] = None`.
- Si es `None` → variante v1 ($3H$ variables, sin R2).
- Si es un `np.ndarray` en kW (índice 0 = hora actual): variante completa con R2.
  - Si `len(net_forecast) < H`, las horas faltantes no tienen R2.
  - Si $\hat N_k \ge P_{\max}$ para hora $k$, no se añade R2 para esa hora.
- No usar `noves_dades_5min` para predecir nada en esta fase.

---

## 7. Implementación (`agent.py`)

```
BatteryAgent
├── __init__()              carga parametres.json (kappa, q, eps) con Path(__file__).parent
│                           · eta_c = eta_d = sqrt(0.9), P_max = 500, E_max = 2000
│                           · net_forecast = None
├── _horizon(obs)           calcula H
├── _build_weights(co2, price)  w_k = 0.7*co2_k + 0.3*kappa*preu_k
├── _build_lp(H, w, soc0, is_end)  v1 o completa → (c_vec, A_eq, b_eq, A_ub, b_ub, bounds)
├── _solve(...)             linprog HiGHS → x; None si falla
├── _clip(P, soc)           recorte físico con ε
└── act(obs)                pd.Timestamp(obs["timestamp"]) → H → w → LP → clip → float
```

- `act()` captura cualquier excepción y devuelve `0.0` en caso de fallo.
- `pd.Timestamp(obs["timestamp"])`, porque el validador lo pasa como string.
- Nada de `os`, `sys`, `eval`, `exec`, etc.
- Rutas con `pathlib.Path(__file__).parent`.
- `parametres.json` con: `kappa`, `q`, `eps`.

---

## 8. Comprobaciones

- [x] `check_submission.py` pasa (sin `os`/`sys`; `timestamp` llega como string).
- [x] Funciona con vectores de longitud < 24 y con SOC en 0 y en 2000.
- [x] 0 infracciones en el simulador local.
- [x] Coherencia: con precio y CO₂ constantes, el LP devuelve $P = 0$ (arbitraje imposible con eficiencia < 100%).
- [x] Tiempo total de 2 016 llamadas ≈ 3 s (< 30 s).
- [x] Score en train: ~6.8 (muy superior al heuristic del starter kit: 2.16).

---

## 9. Parámetros

- $\kappa$: se calcula del train completo y se guarda en `parametres.json`.
- $q$: cuantil para V (actualmente V = 0, no se usa).
- $\varepsilon = 0{,}5$.