"""Pydantic models for API validation and responses."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.agent_config import DEFAULT_MODE


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

class DayRequest(BaseModel):
    date: str
    mode: Literal["estandar", "dificil"] = DEFAULT_MODE


class CompareRequest(BaseModel):
    date: str
    mode: Literal["estandar", "dificil"] = DEFAULT_MODE
    userActions: list[float | str]


class ScenarioParams(BaseModel):
    """Perturbations applied to the target day (see simulator.SCENARIO_DEFAULTS)."""
    demand_scale: float | None = Field(None, ge=0.0, le=3.0)
    demand_noise: float | None = Field(None, ge=0.0, le=1.0)
    solar_scale: float | None = Field(None, ge=0.0, le=3.0)
    solar_noise: float | None = Field(None, ge=0.0, le=1.0)
    price_scale: float | None = Field(None, ge=0.1, le=5.0)
    price_noise: float | None = Field(None, ge=0.0, le=1.0)
    co2_scale: float | None = Field(None, ge=0.1, le=5.0)
    co2_noise: float | None = Field(None, ge=0.0, le=1.0)
    persistence: float | None = Field(None, ge=0.0, le=0.99)
    cloud_start: int | None = Field(None, ge=0, le=23)
    cloud_hours: int | None = Field(None, ge=0, le=24)
    cloud_depth: float | None = Field(None, ge=0.0, le=1.0)
    shock_start: int | None = Field(None, ge=0, le=23)
    shock_hours: int | None = Field(None, ge=0, le=24)
    shock_kw: float | None = Field(None, ge=-2000.0, le=3000.0)
    cut_start: int | None = Field(None, ge=0, le=23)
    cut_hours: int | None = Field(None, ge=0, le=24)
    seed: int | None = Field(None, ge=0, le=10_000)


class RollingHorizonRequest(BaseModel):
    date: str
    mode: Literal["estandar", "dificil"] = DEFAULT_MODE
    scenario: ScenarioParams = Field(default_factory=ScenarioParams)
    nSamples: int = Field(1, ge=1, le=30)
    activeSeed: int | None = Field(None, ge=0, le=10_100)   # scenario shown step by step


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------

class DayListItem(BaseModel):
    date: str
    label: str
    weekday: int          # 0 = lunes … 6 = diumenge
    solarIdx: float
    activityIdx: float


class DayResponse(BaseModel):
    date: str
    hours: list[str]
    demand: list[float]
    solar: list[float]
    price: list[float]
    co2: list[float]
    units: dict[str, str]


class ModelDayResponse(BaseModel):
    actions: list[Literal["carga", "descarga", "espera"]]
    power: list[float]            # kW con signo (consigna aplicada tras recorte)
    soc: list[float]              # kWh al inicio de cada hora
    soc_final: float
    grid: list[float]             # kW importados
    score: float
    dCO2: float
    dCost: float
    infracciones: int


class HourlyCompare(BaseModel):
    h: int
    user: Literal["carga", "descarga", "espera"]
    model: Literal["carga", "descarga", "espera"]
    userKw: float
    modelKw: float
    userPts: float
    modelPts: float


class ScoreDetail(BaseModel):
    dCO2: float
    dCost: float
    infracciones: int


class CompareResponse(BaseModel):
    userScore: float
    modelScore: float
    user: ScoreDetail
    model: ScoreDetail
    hourly: list[HourlyCompare]
    diagnosis: list[str]


class ModelInfoEntry(BaseModel):
    zip: str
    score_servidor: float
    descripcion: str
    parametres: dict


class ModelInfoResponse(BaseModel):
    estandar: ModelInfoEntry
    dificil: ModelInfoEntry