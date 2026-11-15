"""Entrenamiento e inferencia de produccion solar total a 5 minutos."""

from __future__ import annotations

import argparse
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = BASE_DIR.parent / "data" / "train"
DEFAULT_MODEL_PATH = BASE_DIR / "solar_forecast.joblib"
SOLAR_COLUMNS = [f"Inversor {number} - POTENCIA ACTIVA (kW)" for number in range(1, 4)]
WEATHER_TOKENS = {
    "irradiance_w_m2": "IRRADIANCIA (W/m2)",
    "ambient_temp_c": "TEMPERATURA AMBIENTE",
    "panel_temp_c": "TEMPERATURA PANEL",
    "wind_speed_m_s": "VELOCIDAD VIENTO",
}
WEATHER_COLUMNS = list(WEATHER_TOKENS)
SOLAR_LAGS = (0, 1, 2, 3, 6, 12)
WEATHER_LAGS = (0, 1, 2)


def _find_column(columns: list[str], token: str) -> str:
    matches = [column for column in columns if token in column]
    if token == "IRRADIANCIA (W/m2)":
        matches = [column for column in matches if "IRRADIANCIA 1" not in column and "IRRADIANCIA 2" not in column]
    if not matches:
        raise ValueError(f"No se encontro una columna para '{token}'.")
    return matches[0]


def load_telemetry(data_dir: str | Path = DEFAULT_DATA_DIR) -> pd.DataFrame:
    """Carga y alinea inversores y meteo por timestamp.

    Devuelve timestamp, solar_kw y las cuatro variables meteorologicas
    normalizadas. Los lags se calculan despues, sin cruzar huecos temporales.
    """
    data_dir = Path(data_dir)
    inverter_path = data_dir / "inversor.csv"
    weather_path = data_dir / "meteo.csv"
    inverter_header = pd.read_csv(inverter_path, nrows=0).columns.tolist()
    weather_header = pd.read_csv(weather_path, nrows=0).columns.tolist()

    missing_solar = [column for column in SOLAR_COLUMNS if column not in inverter_header]
    if missing_solar:
        raise ValueError(f"Faltan columnas de potencia de inversores: {missing_solar}")
    weather_source_columns = {
        name: _find_column(weather_header, token)
        for name, token in WEATHER_TOKENS.items()
    }

    inverter = pd.read_csv(inverter_path, usecols=["Fecha", *SOLAR_COLUMNS])
    weather = pd.read_csv(
        weather_path,
        usecols=["Fecha", *weather_source_columns.values()],
    )
    inverter["timestamp"] = pd.to_datetime(inverter.pop("Fecha"), errors="coerce")
    weather["timestamp"] = pd.to_datetime(weather.pop("Fecha"), errors="coerce")
    inverter["solar_kw"] = inverter[SOLAR_COLUMNS].apply(pd.to_numeric, errors="coerce").sum(
        axis=1, min_count=len(SOLAR_COLUMNS)
    ).clip(lower=0.0)
    inverter = inverter[["timestamp", "solar_kw"]].dropna(subset=["timestamp"])

    weather = weather.rename(columns={source: name for name, source in weather_source_columns.items()})
    for column in WEATHER_COLUMNS:
        weather[column] = pd.to_numeric(weather[column], errors="coerce")
    weather = weather[["timestamp", *WEATHER_COLUMNS]].dropna(subset=["timestamp"])

    telemetry = inverter.merge(weather, on="timestamp", how="left", validate="one_to_one")
    telemetry = telemetry.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    return telemetry


def build_features(telemetry: pd.DataFrame) -> pd.DataFrame:
    """Crea variables disponibles en t para pronosticar la potencia en t+5m."""
    required = {"timestamp", "solar_kw", *WEATHER_COLUMNS}
    missing = required.difference(telemetry.columns)
    if missing:
        raise ValueError(f"Faltan columnas normalizadas de telemetria: {sorted(missing)}")

    data = telemetry.copy().sort_values("timestamp").reset_index(drop=True)
    data["timestamp"] = pd.to_datetime(data["timestamp"], errors="coerce")
    data["solar_kw"] = pd.to_numeric(data["solar_kw"], errors="coerce").clip(lower=0.0)
    for column in WEATHER_COLUMNS:
        data[column] = pd.to_numeric(data[column], errors="coerce")

    segment = data["timestamp"].diff().ne(pd.Timedelta(minutes=5)).cumsum()
    grouped = data.groupby(segment, sort=False)
    features = pd.DataFrame(index=data.index)

    for lag in SOLAR_LAGS:
        features[f"solar_lag_{lag}"] = grouped["solar_kw"].shift(lag)
    for column in WEATHER_COLUMNS:
        # Relleno hacia atras en el tiempo solamente: nunca se usa una lectura futura.
        data[column] = grouped[column].ffill()
        for lag in WEATHER_LAGS:
            features[f"{column}_lag_{lag}"] = data.groupby(segment, sort=False)[column].shift(lag)

    features["solar_change_5m"] = features["solar_lag_0"] - features["solar_lag_1"]
    features["solar_change_15m"] = features["solar_lag_0"] - features["solar_lag_3"]
    features["irradiance_change_5m"] = (
        features["irradiance_w_m2_lag_0"] - features["irradiance_w_m2_lag_1"]
    )
    timestamp = data["timestamp"]
    hour = timestamp.dt.hour + timestamp.dt.minute / 60.0
    day_of_year = timestamp.dt.day_of_year
    day_of_week = timestamp.dt.day_of_week
    features["hour_sin"] = np.sin(2.0 * np.pi * hour / 24.0)
    features["hour_cos"] = np.cos(2.0 * np.pi * hour / 24.0)
    features["year_sin"] = np.sin(2.0 * np.pi * day_of_year / 365.25)
    features["year_cos"] = np.cos(2.0 * np.pi * day_of_year / 365.25)
    features["weekday_sin"] = np.sin(2.0 * np.pi * day_of_week / 7.0)
    features["weekday_cos"] = np.cos(2.0 * np.pi * day_of_week / 7.0)
    return features.replace([np.inf, -np.inf], np.nan)


def make_training_set(telemetry: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    features = build_features(telemetry)
    data = telemetry.sort_values("timestamp").reset_index(drop=True).copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"], errors="coerce")
    timestamp_next = data["timestamp"].shift(-1)
    target_next = pd.to_numeric(data["solar_kw"], errors="coerce").shift(-1)
    valid = (timestamp_next - data["timestamp"] == pd.Timedelta(minutes=5)) & target_next.notna()
    valid &= data["timestamp"].notna()
    return features.loc[valid].reset_index(drop=True), target_next.loc[valid].reset_index(drop=True), data.loc[valid, "timestamp"].reset_index(drop=True)


def _new_model() -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        learning_rate=0.06,
        max_iter=250,
        max_leaf_nodes=31,
        l2_regularization=2.0,
        random_state=42,
        early_stopping=False,
    )


def _metrics(actual: pd.Series, predicted: np.ndarray) -> dict[str, float]:
    return {
        "mae_kw": float(mean_absolute_error(actual, predicted)),
        "rmse_kw": float(np.sqrt(mean_squared_error(actual, predicted))),
        "r2": float(r2_score(actual, predicted)),
    }


def train_model(
    data_dir: str | Path = DEFAULT_DATA_DIR,
    model_path: str | Path = DEFAULT_MODEL_PATH,
) -> dict[str, dict[str, float]]:
    telemetry = load_telemetry(data_dir)
    features, target, timestamps = make_training_set(telemetry)
    if len(features) < 100:
        raise ValueError(f"No hay suficientes muestras validas para entrenar: {len(features)}")

    split = int(len(features) * 0.8)
    if split <= 0 or split >= len(features):
        raise ValueError("No se pudo crear una particion temporal de validacion.")
    train_x, valid_x = features.iloc[:split], features.iloc[split:]
    train_y, valid_y = target.iloc[:split], target.iloc[split:]
    model = _new_model()
    model.fit(train_x, train_y)
    prediction = np.clip(model.predict(valid_x), 0.0, None)

    validation = _metrics(valid_y, prediction)
    persistence = _metrics(valid_y, valid_x["solar_lag_0"].fillna(0.0).to_numpy())
    daylight = valid_y.to_numpy() > 1.0
    validation["daylight_mae_kw"] = float(mean_absolute_error(valid_y.to_numpy()[daylight], prediction[daylight])) if daylight.any() else float("nan")
    persistence["daylight_mae_kw"] = float(mean_absolute_error(valid_y.to_numpy()[daylight], valid_x["solar_lag_0"].fillna(0.0).to_numpy()[daylight])) if daylight.any() else float("nan")
    validation["validation_start"] = str(timestamps.iloc[split])
    validation["validation_samples"] = float(len(valid_y))
    validation["persistence_mae_kw"] = persistence["mae_kw"]
    validation["persistence_daylight_mae_kw"] = persistence["daylight_mae_kw"]

    final_model = _new_model()
    final_model.fit(features, target)
    model_path = Path(model_path)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": final_model,
            "feature_names": features.columns.tolist(),
            "horizon_minutes": 5,
            "target": "suma de potencia activa AC de los tres inversores (kW)",
        },
        model_path,
    )
    return {"validation": validation, "persistence": persistence}


def predict_next_5min(
    telemetry_history: pd.DataFrame,
    model_path: str | Path = DEFAULT_MODEL_PATH,
) -> float:
    """Predice solar_kw dentro de 5 minutos desde el ultimo registro de historia.

    telemetry_history debe usar las columnas normalizadas de load_telemetry y
    contener lecturas recientes ordenadas o desordenadas por timestamp.
    """
    artifact = joblib.load(model_path)
    features = build_features(telemetry_history)
    row = features.iloc[[-1]].reindex(columns=artifact["feature_names"])
    prediction = float(artifact["model"].predict(row)[0])
    return max(0.0, prediction)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--model-out", type=Path, default=DEFAULT_MODEL_PATH)
    args = parser.parse_args()
    scores = train_model(args.data_dir, args.model_out)
    print(f"Modelo guardado en: {args.model_out}")
    print("Validacion temporal (modelo):")
    for name, value in scores["validation"].items():
        print(f"  {name}: {value:.4f}" if isinstance(value, float) else f"  {name}: {value}")
    print("Persistencia (baseline):")
    for name, value in scores["persistence"].items():
        print(f"  {name}: {value:.4f}")


if __name__ == "__main__":
    main()