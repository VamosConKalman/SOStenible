# Architecture — BatteryAgent MPC with LP (HiGHS)

## Overview

A model predictive control (MPC) system that schedules battery charge/discharge
to minimize CO₂ emissions (70%) and electricity cost (30%) using a linear
program solved by HiGHS at each hour.

The system is separated into:

- **Orchestrator** (`agent.py`): parses `obs`, manages history, calls the
  forecaster and LP solver, clips the output.
- **LP model** (`lp_model.py`): pure function that builds and solves the LP.
  No knowledge of `obs`, timestamps, or the environment.
- **Forecaster** (`forecaster_base.py`, `forecaster_impl.py`): optional module
  that predicts net load (load − solar). The LP works without it (mode v1).

## Directory Structure

```
sandbox_impl/
├── src/
│   ├── lp_model.py            # Pure LP solver (HiGHS via scipy)
│   ├── forecaster_base.py     # ABC: NetLoadForecaster interface
│   ├── forecaster_impl.py     # MeanByDayHourForecaster
│   ├── agent.py               # BatteryAgent orchestrator
│   └── parametres.json        # κ, q, eps, delta, v_coef
├── mocks/
│   ├── environment.py         # CampusBatteryEnv mock (for tests)
│   └── data_loader.py         # Train data loader (read-only)
├── tests/
│   ├── conftest.py            # Fixtures
│   ├── test_lp.py             # LP unit tests (§7.1)
│   ├── test_agent.py          # Agent integration tests (§7.2)
│   ├── test_forecaster.py     # Forecaster unit tests
│   └── test_full_pipeline.py  # Variant ladder tests (§7.3)
└── architecture.md            # This file
```

## Data Flow

```
obs (dict)
  │
  ├─ 1. Parse: ts = pd.Timestamp(obs["timestamp"]), soc = obs["soc_kwh"]
  ├─ 2. Record: history.append((ts, load - pv))
  ├─ 3. Horizon: H = min(len(preus), len(co2), 24), is_end
  ├─ 4. Weights: w' = 0.7·co2 + 0.3·κ·price  (exact, from obs)
  ├─ 5. Terminal: V = compute_terminal_value(w', is_end)
  ├─ 6. Forecast: N̂ = forecaster.predict(obs, history, H)  (or None → v1)
  ├─ 7. LP: solve_lp(w', soc, V, net=N̂, eps, delta) → x
  └─ 8. Clip: P = clip(x[0] - x[H])  → return float
```

## LP Formulation

### Variables (per hour k ∈ [0, H-1])

| Variable | Range | Meaning |
|---|---|---|
| c_k | [0, P_max] | Charge power (kW) |
| d_k | [0, P_max] | Discharge power (kW) |
| s_k | [ε, E_max−ε] | SOC at end of hour k (kWh) |
| g_k | [0, ∞) | Grid import (only for k where N_k < P_max) |

### Objective

```
min  Σ_{k∉R} w'(c_k − d_k) + Σ_{k∈R} w'·g_k + δ·Σ(c_k+d_k) − V·s_H
```

Where R = {k : N_k < P_max}, δ = 10⁻⁶ (tie-breaker), V = terminal value.

### Constraints

```
R1:  s_{k+1} − s_k − η_c·c_k + d_k/η_d = s₀·δ_{k0}     (SOC dynamics)
R2:  c_k − d_k − g_k ≤ −N_k     for k ∈ R                (grid ≥ net + bat)
```

### Hybrid Formulation (PLAN §4.1)

For hours where N_k ≥ P_max, the grid import is always positive, so the cost
can be placed directly on c_k and d_k without g_k. This reduces the number
of variables and constraints, without losing optimality (verified with 200
random cases).

## Parameter Calibration

- **κ (kappa)** = E_b / C_b (kg CO₂ / €). Calculated from training data:
  κ = Σ max(0, load−pv)·co₂ / Σ max(0, load−pv)·price
  Default: 0.55

- **q (quantile)**: Used in V = η_d · Q_q(w'). Default: 0.5

- **ε (eps)**: SOC safety margin. Default: 0.5 kWh

- **δ (delta)**: Tie-breaker to avoid simultaneous charge+discharge.
  Default: 10⁻⁶

## Variant Ladder (PLAN §7.3)

| Variant | Description | N̂ |
|---|---|---|
| A | No battery (baseline) | — |
| B | Heuristic policy | — |
| C | LP v1 (no forecaster) | None |
| D | LP with forecaster (delivery version) | Model |
| E | LP with perfect forecast | Oracle (load−pv) |
| F | Oracle (all 168h known) | Full week |

Key differences:
- **F − E**: Horizon loss (24h vs 168h)
- **E − D**: Forecast error impact
- **D − C**: Value of the forecaster (should be ≥ 0)

## Robustness

- `act()` wrapped in try/except → returns 0.0 on failure
- Forecaster fails → falls back to v1 (no g_k)
- `pd.Timestamp()` parses string timestamps from the validator
- SOC relaxed if s₀ < ε or s₀ > E_max − ε
- 0 violations on all tested scenarios

## Performance

- LP size: ~72 variables (v1), ~96 (with g_k) for H=24
- HiGHS solve time: ~3 ms per call
- 2016 calls (12 weeks): < 30 s total (target < 3 s)

## Testing Strategy

### Level 1: LP Model (§7.1)
- Constant price/CO₂ → P = 0
- SOC at boundaries → no impossible actions
- Short horizons (H=3) work
- N̂ = 100 kW → discharge ≤ 100
- Hybrid formulation matches full R2 (200 random cases)

### Level 2: Integration (§7.2)
- 0 violations in simulation
- Time < 30 s for 2016 h
- Works without forecaster.pkl (fallback to v1)

### Level 3: Variant Ladder (§7.3)
- E ≥ C ≥ A
- SOC stays within [0, 2000]
- Performance under time budget