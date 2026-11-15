# UPC Sostenible — demo de agentes de batería

**Live page:** [https://sostenible.onrender.com/](https://sostenible.onrender.com/)

Demo del Datathon UPC Sostenible 2026 con dos agentes seleccionados y simulación interactiva.

| ID | Controlador | Batería | Potencia | Referencia servidor |
|---|---|---:|---:|---:|
| estandar | MPC 24 h | 2.000 kWh | ±500 kW | 6,43 |
| dificil | MPC + LASSO + corrección solar online | 6.000 kWh | ±1.500 kW | 22,94 |

Las puntuaciones son referencias históricas, no garantías de puntuación local.

## Arranque local

Requisitos: Python 3.12 y Node.js 22.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn app.main:app --app-dir backend --reload
```

En otra terminal:
```bash
cd frontend
npm ci
npm run dev
```

Abrir http://localhost:5173. Vite proxifica /api al backend en el puerto 8000.

## Configurar agentes

Editar `config/agents.json`:
- `enabled`: activa/desactiva cada agente.
- `default_mode`: cambia el agente inicial.
- `battery`: parámetros físicos compartidos por backend y simulador.

Reiniciar el backend tras editar el JSON. Mantener al menos un agente habilitado.

Documentación técnica: [docs/AGENTES_Y_DEMO.md](docs/AGENTES_Y_DEMO.md).
