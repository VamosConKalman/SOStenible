# Cómo generar y ver los escenarios (Mac / VS Code)

Sigue estos pasos en orden. No hace falta Docker.

## 1. Preparar la carpeta de datos

Dentro de `scenario_api`, crea `data/train/` y copia estos cuatro CSV originales:

- `contador.csv`
- `inversor.csv`
- `precio_pvpc.csv`
- `co2_red.csv`

Los nombres pueden llevar un prefijo delante, siempre que terminen exactamente en esos sufijos (por ejemplo, `1794657406853_contador.csv`). `meteo.csv` y `entradas_salidas.csv` no se usan en esta versión.

La estructura debe quedar así:

```text
scenario_api/
  data/
    train/
      ..._contador.csv
      ..._inversor.csv
      ..._precio_pvpc.csv
      ..._co2_red.csv
```

## 2. Abrir el proyecto

Descomprime el ZIP y, desde Visual Studio Code, abre la carpeta `scenario_api` (no abras un archivo suelto).

## 3. Preparar Python (solo la primera vez)

En VS Code abre `Terminal > New Terminal` y ejecuta:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
mkdir -p data/train artifacts
```

## 4. Entrenar y guardar el generador gaussiano

En ese mismo terminal, ejecuta:

```bash
python build_artifacts.py --data data/train --out artifacts
```

Debe terminar mostrando que ha guardado `gaussian` en `artifacts/gaussian.joblib`.

## 5. Arrancar la API

En el mismo terminal:

```bash
uvicorn api:app --reload
```

Déjalo abierto. La API queda activa en `http://127.0.0.1:8000`.

Comprueba en el navegador que abre:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/docs`

## 6. Generar y visualizar los escenarios

Abre un **segundo terminal** en VS Code. Entra en la carpeta del proyecto si el terminal no está ya allí y activa el entorno:

```bash
source .venv/bin/activate
python visualize_scenarios.py
```

Se generarán 2.000 trayectorias Monte Carlo y se reducirán a 8 escenarios mediante k-means. Se abrirá una ventana con tres gráficas: demanda, solar y demanda neta.

También se guardarán en la carpeta del proyecto:

- `escenarios_generados.png`: gráfica de los escenarios.
- `escenarios_generados.json`: datos numéricos completos, incluidos los perfiles y sus probabilidades.

La petición usa valores demostrativos constantes de precio (0,12 €/kWh) y CO₂ (0,08 kg/kWh), y una observación anterior de 1.350 kW de demanda y 40 kW solares. Para simular un instante real, cambia esos valores en `visualize_scenarios.py` por los valores de `obs`.

## 7. Cerrar

Para parar la API, vuelve al primer terminal y pulsa `Control + C`.

## Si algo falla

- `No encuentro '*contador.csv'`: los CSV no están dentro de `data/train/` o el nombre no termina en `contador.csv`.
- `No puedo conectar con ...`: la API no está arrancada en el primer terminal.
- Error de carga de CSV: comprueba que los cuatro ficheros tienen la columna `Fecha` y las columnas esperadas por `data.py`.
