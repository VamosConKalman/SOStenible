"""PLANTILLA per al generador de gradient boosting (companya de l'equip).

Copia aquest fitxer a generators/gbm_generator.py, implementa fit/generate i desa l'objecte:
    g = GBMGenerator().fit(load_hourly("data/train")); g.save("artifacts/gbm.joblib")
L'API el carregarà sol (nom "gbm") i el podrà cridar amb  POST /generate {"generator": "gbm", ...}.

Cal retornar TRAJECTÒRIES conjuntes, no només la mitjana:
    paths["dem"], paths["sol"]  amb forma (n_paths, h)  (kW, hores t .. t+h-1)
Opcions per passar de mitjana a trajectòries:
    - bootstrap de residus (blocs de h hores consecutives dels residus out-of-fold)
    - residus gaussians amb la covariància de generators.gaussian_mc (-> generador híbrid)
Fes servir req.price_forecast / req.co2_forecast (t..t+23), req.last_dem / last_sol (t-1) i req.timestamp.
Valida'l amb el mateix protocol:  python evaluate.py --generator gbm
"""
from .base import ScenarioGenerator, GenRequest, GenResult
from .registry import register

# Descomenta quan el tinguis llest perquè el registre l'exposi (l'API només el carrega si existeix artifacts/gbm.joblib)
# @register("gbm")
class GBMGenerator(ScenarioGenerator):
    def fit(self, hourly):
        raise NotImplementedError("TODO: entrenar els models de boosting (p.ex. LightGBM) per dem i sol, h = 1..24")

    def generate(self, req: GenRequest) -> GenResult:
        raise NotImplementedError("TODO: predir la mitjana + mostrejar residus -> GenResult")
