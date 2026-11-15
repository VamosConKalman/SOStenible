"""Entrenamiento e inferencia de consumo electrico del campus a 5 minutos."""

from __future__ import annotations

import argparse
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

if __package__:
    from .solar_forecast import (
        DEFAULT_DATA_DIR,
        WEATHER_COLUMNS,
        _find_column,
        load_telemetry as load_solar_weather,
    )
else:
    from solar_forecast import (
        DEFAULT_DATA_DIR,
        WEATHER_COLUMNS,
        _find_column,
        load_telemetry as load_solar_weather,
    )


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL_PATH = BASE_DIR / "load_forecast.joblib"
LOAD_COLUMN_TOKEN = "POTENCIA ACTIVA EXPORTADA (kW)"
LOAD_LAGS = (0, 1, 2, 3, 6, 12)
SOLAR_LAGS = (0, 1, 2, 3, 6, 12)
WEATHER_LAGS = (0, 1, 2)


def load_consumption_telemetry(data_dir: str | Path = DEFAULT_DATA_DIR) -> pd.DataFrame:
    """Alinea consumo, generacion solar y meteo usando timestamps exactos."""
    data_dir = Path(data_dir)
    counter_path = data_dir / "contador.csv"
    columns = pd.read_csv(counter_path, nrows=0).columns.tolist()
    load_column = _find_column(columns, LOAD_COLUMN_TOKEN)
    counter = pd.read_csv(counter_path, usecols=["Fecha", load_column])
    counter["timestamp"] = pd.to_datetime(counter.pop("Fecha"), errors="coerce")
    exported_kw = pd.to_numeric(counter.pop(load_column), errors="coerce")
    counter["load_kw"] = (-exported_kw).clip(lower=0.0)
    counter = counter[["timestamp", "load_kw"]].dropna(subset=["timestamp"])

    solar_weather = load_solar_weather(data_dir)
    telemetry = solar_weather.merge(
        counter,
        on="timestamp",
        how="inner",
        validate="one_to_one",
    )
    return telemetry.sort_values("timestamp").reset_index(drop=True)


def build_features(telemetry: pd.DataFrame) -> pd.DataFrame:
    """Construye variables disponibles en t para predecir el consumo en t+5m."""
    required = {"timestamp", "load_kw", "solar_kw", *WEATHER_COLUMNS}
    missing = required.difference(telemetry.columns)
    if missing:
        raise ValueError(f"Faltan columnas normalizadas de telemetria: {sorted(missing)}")

    data = telemetry.copy().sort_values("timestamp").reset_index(drop=True)
    data["timestamp"] = pd.to_datetime(data["timestamp"], errors="coerce")
    for column in ("load_kw", "solar_kw", *WEATHER_COLUMNS):
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data["load_kw"] = data["load_kw"].clip(lower=0.0)
    data["solar_kw"] = data["solar_kw"].clip(lower=0.0)

    segment = data["timestamp"].diff().ne(pd.Timedelta(minutes=5)).cumsum()
    grouped = data.groupby(segment, sort=False)
    features = pd.DataFrame(index=data.index)
    for lag in LOAD_LAGS:
        features[f"load_lag_{lag}"] = grouped["load_kw"].shift(lag)
    for lag in SOLAR_LAGS:
        features[f"solar_lag_{lag}"] = grouped["solar_kw"].shift(lag)
    for column in WEATHER_COLUMNS:
        data[column] = grouped[column].ffill()
        for lag in WEATHER_LAGS:
            features[f"{column}_lag_{lag}"] = data.groupby(segment, sort=False)[column].shift(lag)

    features["load_change_5m"] = features["load_lag_0"] - features["load_lag_1"]
    features["load_change_15m"] = features["load_lag_0"] - features["load_lag_3"]
    features["solar_change_5m"] = features["solar_lag_0"] - features["solar_lag_1"]
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
    features["is_weekend"] = (day_of_week >= 5).astype(int)
    return features.replace([np.inf, -np.inf], np.nan)


def make_training_set(
    telemetry: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    features = build_features(telemetry)
    data = telemetry.sort_values("timestamp").reset_index(drop=True)
    timestamps = pd.to_datetime(data["timestamp"], errors="coerce")
    next_timestamp = timestamps.shift(-1)
    target_next = pd.to_numeric(data["load_kw"], errors="coerce").shift(-1)
    valid = (next_timestamp - timestamps == pd.Timedelta(minutes=5)) & target_next.notna()
    valid &= timestamps.notna()
    return (
        features.loc[valid].reset_index(drop=True),
        target_next.loc[valid].reset_index(drop=True),
        timestamps.loc[valid].reset_index(drop=True),
    )


def _new_model() -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        learning_rate=0.04,
        max_iter=150,
        max_leaf_nodes=15,
        l2_regularization=10.0,
        random_state=42,
        early_stopping=False,
    )


def train_model(
    data_dir: str | Path = DEFAULT_DATA_DIR,
    model_path: str | Path = DEFAULT_MODEL_PATH,
) -> dict[str, float | str]:
    telemetry = load_consumption_telemetry(data_dir)
    features, target, timestamps = make_training_set(telemetry)
    if len(features) < 100:
        raise ValueError(f"No hay suficientes muestras validas para entrenar: {len(features)}")

    split = int(len(features) * 0.8)
    train_x, valid_x = features.iloc[:split], features.iloc[split:]
    train_y, valid_y = target.iloc[:split], target.iloc[split:]
    model = _new_model()
    train_baseline = train_x["load_lag_0"].fillna(0.0).to_numpy()
    model.fit(train_x, train_y.to_numpy() - train_baseline)
    valid_baseline = valid_x["load_lag_0"].fillna(0.0).to_numpy()
    prediction = np.maximum(0.0, valid_baseline + model.predict(valid_x))
    persistence = valid_baseline
    metrics = {
        "mae_kw": float(mean_absolute_error(valid_y, prediction)),
        "rmse_kw": float(np.sqrt(mean_squared_error(valid_y, prediction))),
        "r2": float(r2_score(valid_y, prediction)),
        "persistence_mae_kw": float(mean_absolute_error(valid_y, persistence)),
        "validation_samples": float(len(valid_y)),
        "validation_start": str(timestamps.iloc[split]),
        "validation_end": str(timestamps.iloc[-1]),
    }

    final_model = _new_model()
    final_baseline = features["load_lag_0"].fillna(0.0).to_numpy()
    final_model.fit(features, target.to_numpy() - final_baseline)
    model_path = Path(model_path)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": final_model,
            "feature_names": features.columns.tolist(),
            "horizon_minutes": 5,
            "target": "consumo medio del campus en kW",
            "target_mode": "delta_from_last_load_kw",
        },
        model_path,
    )
    return metrics


def predict_next_5min(
    telemetry_history: pd.DataFrame,
    model_path: str | Path = DEFAULT_MODEL_PATH,
) -> float:
    artifact = joblib.load(model_path)
    features = build_features(telemetry_history)
    row = features.iloc[[-1]].reindex(columns=artifact["feature_names"])
    baseline = float(row["load_lag_0"].iloc[0])
    delta = float(artifact["model"].predict(row)[0])
    return max(0.0, baseline + delta)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--model-out", type=Path, default=DEFAULT_MODEL_PATH)
    args = parser.parse_args()
    metrics = train_model(args.data_dir, args.model_out)
    print(f"Modelo guardado en: {args.model_out}")
    print("Validacion temporal:")
    for name, value in metrics.items():
        print(f"  {name}: {value:.4f}" if isinstance(value, float) else f"  {name}: {value}")


if __name__ == "__main__":
    main()