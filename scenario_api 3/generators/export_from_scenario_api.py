
"""LOCAL. Convierte un GaussianMCGenerator ajustado (scenario_api) en GaussianNetForecaster y guarda forecaster.pkl.
Uso: python export_from_scenario_api.py <ruta_scenario_api> <salida.pkl>"""
import sys
import joblib
sys.path.insert(0, sys.argv[1])
from generators.base import ScenarioGenerator  # noqa: E402
import generators  # noqa: F401,E402
from forecaster_impl import GaussianNetForecaster  # noqa: E402

g = ScenarioGenerator.load(sys.argv[1] + "/artifacts/gaussian.joblib")
mm = g.mean_model
f = GaussianNetForecaster(coef=mm.reg.coef_, month_table=mm.table, sd=g.sd.to_numpy(),
                          cov=g.cov, sol_cap=g.sol_cap.to_numpy(), condition_known=g.condition_known)
joblib.dump(f, sys.argv[2])
print("ok", sys.argv[2])