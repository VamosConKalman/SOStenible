"""API FastAPI de generació d'escenaris (demanda i solar) per al repte UPC Sostenible.

    uvicorn api:app --host 0.0.0.0 --port 8000        ->  documentació interactiva a /docs
"""
import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Literal, Optional

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator

import config
from generators import GenRequest, load_generators
from reduction import reduce_paths


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.generators, app.state.status = load_generators(config.ARTIFACTS_DIR, config.DATA_DIR)
    yield


app = FastAPI(title="Scenario API - Repte UPC Sostenible", version="0.1.1", lifespan=lifespan,
              description="Simula futurs possibles de demanda i solar (t..t+23) condicionats a les previsions "
                          "de preu i CO2, i opcionalment els redueix a K escenaris amb probabilitat (k-means).")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class ReduceSpec(BaseModel):
    k: int = Field(8, ge=2, le=50)
    weights: Optional[dict[str, float]] = Field(None, description='pes relatiu per variable, p.ex. {"dem":1,"sol":0.5}')
    representative: Literal["mean", "medoid"] = "mean"
    seed: int = 0


class GenerateRequest(BaseModel):
    generator: str = Field("gaussian", description="nom del generador (veure GET /generators)")
    timestamp: datetime = Field(..., description="hora t en què es decideix (== obs['timestamp'])")
    price_forecast: list[float] = Field(..., min_length=1, max_length=48, description="== obs['preus_properes_24h'] (t..t+23)")
    co2_forecast: list[float] = Field(..., min_length=1, max_length=48, description="== obs['co2_properes_24h'] (t..t+23)")
    last_dem_kw: Optional[float] = Field(None, description="== obs['noves_dades_5min']['ultim_consum_kw'] (hora t-1)")
    last_sol_kw: Optional[float] = Field(None, description="== obs['noves_dades_5min']['ultima_solar_kw'] (hora t-1)")
    n_paths: int = Field(1000, ge=1, le=config.MAX_PATHS)
    seed: int = 0
    horizon: Optional[int] = Field(None, ge=1, le=24, description=f"hores a simular, per defecte {config.DEFAULT_HORIZON}")
    return_paths: bool = Field(True, description="false = només retornar els escenaris reduïts (resposta molt més petita)")
    reduce: Optional[ReduceSpec] = None

    @model_validator(mode="after")
    def _same_len(self):
        if len(self.price_forecast) != len(self.co2_forecast):
            raise ValueError("price_forecast i co2_forecast han de tenir la mateixa longitud")
        if not self.return_paths and self.reduce is None:
            raise ValueError("return_paths=false requereix 'reduce'")
        return self


def _l(a, nd=3):
    return np.round(np.asarray(a, float), nd).tolist()


@app.get("/health")
def health():
    return {"status": "ok", "generators_loaded": sorted(app.state.generators)}


@app.get("/generators")
def generators():
    return {name: {"loaded": name in app.state.generators, "status": st,
                   **(app.state.generators[name].info() if name in app.state.generators else {})}
            for name, st in app.state.status.items()}


@app.post("/generate")
def generate(req: GenerateRequest):
    g = app.state.generators.get(req.generator)
    if g is None:
        raise HTTPException(404, f"Generador '{req.generator}' no disponible. Disponibles: {sorted(app.state.generators)}")
    r = g.generate(GenRequest(timestamp=req.timestamp, price_forecast=np.array(req.price_forecast),
                              co2_forecast=np.array(req.co2_forecast), last_dem=req.last_dem_kw, last_sol=req.last_sol_kw,
                              n_paths=req.n_paths, seed=req.seed, horizon=req.horizon or config.DEFAULT_HORIZON))
    out = {"generator": req.generator, "horizon": len(r.times), "n_paths": req.n_paths,
           "timestamps": [t.isoformat() for t in r.times], "hour": r.times.hour.tolist(),
           "day_of_week": r.times.dayofweek.tolist(),
           "price": _l(r.known["price"], 5), "co2": _l(r.known["co2"], 5), "meta": r.meta}
    if req.return_paths:
        out["paths"] = {"dem": _l(r.paths["dem"], 1), "sol": _l(r.paths["sol"], 1), "net": _l(r.net, 1)}
        out["prob"] = _l(r.prob, 8)
    if req.reduce is not None:
        red = reduce_paths(r.paths, k=req.reduce.k, weights=req.reduce.weights,
                           representative=req.reduce.representative, seed=req.reduce.seed)
        out["reduced"] = {"k": red["quality"]["k"], "prob": _l(red["prob"], 6),
                          "paths": {"dem": _l(red["paths"]["dem"], 1), "sol": _l(red["paths"]["sol"], 1), "net": _l(red["net"], 1)},
                          "quality": red["quality"]}
    return out


@app.get("/evaluation/{generator}")
def evaluation(generator: str):
    p = config.ARTIFACTS_DIR / f"evaluation_{generator}.json"
    if not p.exists():
        raise HTTPException(404, f"No hi ha avaluació per a '{generator}'. Executa: python evaluate.py --generator {generator}")
    return json.loads(p.read_text())
