# Scenario API · Repte UPC Sostenible

Genera futurs possibles de **demanda i solar** (hores t … t+23) condicionats a les previsions de **preu i CO2**
(que l'agent ja rep a `obs`), amb reducció opcional a K escenaris + probabilitat (k-means).
Pensada per a visualitzacions i optimització **fora de línia**: l'escàner del repte no permet xarxa dins `agent.py`.

## Arrencar (Docker local, sense API key)
```bash
mkdir -p data/train            # copia aquí contador.csv, inversor.csv, precio_pvpc.csv, co2_red.csv
docker compose up --build      # http://localhost:8000/docs
```
`artifacts/gaussian.joblib` ja inclòs; per reajustar: `python build_artifacts.py --data data/train`.

**Compatibilitat del model**: els fitxers `joblib` de pandas/scikit-learn no són portables entre qualsevol parell de versions. Si el model inclòs no es pot carregar (o scikit-learn detecta una versió diferent), l'API intenta reconstruir automàticament el generador gaussià amb els CSV de `DATA_DIR`. Per tant, mantén els quatre CSV originals a `data/train`; si no hi són i l'artefacte és incompatible, `/generators` indicarà l'error i `/generate` no podrà servir el model.
Sense Docker: `pip install -r requirements.txt && uvicorn api:app --port 8000`.

## Endpoints
| | |
|---|---|
| `GET /health`, `GET /generators` | estat i generadors carregats |
| `POST /generate` | simula (i opcionalment redueix) |
| `GET /evaluation/{generador}` | mètriques de validació (leave-one-month-out) |

Exemple (els camps són directament els de `obs`):
```bash
curl -s localhost:8000/generate -H 'content-type: application/json' -d '{
  "generator": "gaussian", "timestamp": "2026-03-10T17:00:00",
  "price_forecast": [0.12, ... 24 valors ...], "co2_forecast": [0.08, ... 24 valors ...],
  "last_dem_kw": 1350, "last_sol_kw": 40,
  "n_paths": 2000, "seed": 1, "return_paths": false, "reduce": {"k": 8}
}'
```
Resposta: `timestamps`, `hour`, `day_of_week`, `price`, `co2` (eco), `paths` {dem, sol, net} `[n][h]` + `prob`,
i si hi ha `reduce`: `reduced` {paths {dem, sol, net} `[k][h]`, prob, quality}. `return_paths=false` -> només els K escenaris.

## Horitzó
`obs` dona preu/CO2 per a t..t+23 (24 valors, el primer és l'hora actual) però la demanda/solar de l'hora **t** encara no es coneix
(només t-1). Per això es simulen **t..t+23 (24 passos)**. Per fer-ne 23: `"horizon": 23` o `DEFAULT_HORIZON=23`.
Si hi ha menys previsions (final de la sèrie), l'horitzó s'escurça sol.

## Afegir un generador (p.ex. gradient boosting)
1. Copia `generators/gbm_template.py` -> `generators/gbm_generator.py`, descomenta `@register("gbm")`, implementa `fit`/`generate`
   (retorna `GenResult` amb `paths["dem"]`, `paths["sol"]` de forma `(n_paths, h)`).
2. Importa'l a `generators/__init__.py`, desa `artifacts/gbm.joblib` (`g.save(...)`).
3. `python evaluate.py --generator gbm` -> mateix protocol que el gaussià. L'API el serveix com `"generator": "gbm"`.

**Generador híbrid**: `GaussianMCGenerator(mean_model=GBMMeanModel())`; `MeanModel` (a `generators/base.py`) només ha
d'implementar `fit`/`predict`; el mostrejador de residus gaussià es reutilitza.

## Mètode en una frase
Mitjana (hora × tipus de dia × mes, ridge) + residus estandarditzats per hora, finestres lliscants de 24 h amb covariància
Ledoit-Wolf, condicionament gaussià exacte a preu/CO2 coneguts i a dem/sol de t-1; k-means estandarditzat per variable.
