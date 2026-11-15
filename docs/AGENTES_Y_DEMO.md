# Agentes seleccionados y guía de demo

## Agentes incluidos

| ID | Batería | Potencia | Referencia histórica |
|---|---:|---:|---:|
| estandar | 2.000 kWh | ±500 kW | 6,43 |
| dificil | 6.000 kWh | ±1.500 kW | 22,94 |

Las puntuaciones son referencias de ejecuciones anteriores en servidor, no garantías de resultados locales.

## Agente estándar

Código en `agents/estandar/`: `agent.py`, `lp_model.py`, `forecaster_base.py` y `parametres.json`. Usa un LP de 24 horas y la información de mercado disponible en su observación.

## Agente difícil

Código en `agents/dificil/`: `agent.py`, `features.py`, `lp_model.py`, `perfils.json` y `parametres.json`. Predice con LASSO por horizonte, utiliza tres horas reales de precio/CO₂ y aplica corrección solar online. En simulación, la instalación solar se escala ×12; la batería es un único almacén de 6 MWh.

## Selección modular

La fuente única de configuración es `config/agents.json`.

- `enabled: true/false`: muestra u oculta el agente y habilita o bloquea su carga.
- `default_mode`: agente inicial del simulador.
- `battery`: límites físicos usados por el simulador.
- `label` y `description`: texto del selector.

Después de editar el JSON, reinicia el backend. Debe quedar al menos un agente activo. Para incorporar un tercer agente se necesita una clase compatible y ampliar el tipo de ID del frontend.

## Ejecución local

Requisitos: Python 3.12 y Node.js 22.

Backend desde la raíz:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn app.main:app --app-dir backend --reload
```

Frontend en otra terminal:
```bash
cd frontend
npm ci
npm run dev
```

Abrir `http://localhost:5173`. Vite reenvía `/api` al backend en el puerto 8000.

## Datos

La demo necesita en `data/train/`: `contador.csv`, `inversor.csv`, `precio_pvpc.csv`, `co2_red.csv` y `meteo.csv`. No necesita acceso externo ni credenciales.

## API

- `GET /api/agents`: catálogo de agentes activos y agente predeterminado.
- `GET /api/days?mode=estandar|dificil`: días disponibles.
- `POST /api/model-day`: simula el agente para un día.
- `POST /api/rolling-horizon`: inspecciona el MPC.
- `GET /docs`: Swagger.

## Checklist de demo

1. Instalar dependencias y arrancar backend/frontend.
2. Consultar `/api/agents` y verificar los dos agentes.
3. Ejecutar un día válido en cada modo.
4. Abrir Rolling Horizon en ambos modos.
5. Verificar logs y presencia de los cinco CSV.

La validación del ZIP oficial con `starter_kit/check_submission.py` es independiente de esta demo.
