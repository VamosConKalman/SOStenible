"""Registre de generadors per nom. Afegir-ne un de nou = decorar la classe amb @register("nom")."""
from pathlib import Path
import warnings

from sklearn.exceptions import InconsistentVersionWarning
REGISTRY: dict = {}


def register(name):
    def deco(cls):
        cls.name = name
        REGISTRY[name] = cls
        return cls
    return deco


def load_generators(artifacts_dir, data_dir=None):
    """Carrega artefactes i recupera els Gaussian incompatibles reentrenant-los.

    Els fitxers joblib de scikit-learn/pandas no són portables entre versions.
    Si l'artefacte gaussià no es pot obrir (o sklearn avisa d'una versió diferent),
    es reconstrueix amb les dades originals disponibles a data_dir.
    """
    from .base import ScenarioGenerator
    artifacts_dir = Path(artifacts_dir)
    out, status = {}, {}

    for name, cls in REGISTRY.items():
        path = artifacts_dir / f"{name}.joblib"
        load_error = None

        if path.exists():
            try:
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always", InconsistentVersionWarning)
                    model = ScenarioGenerator.load(path)
                version_warnings = [w for w in caught if issubclass(w.category, InconsistentVersionWarning)]
                if version_warnings:
                    details = "; ".join(str(w.message) for w in version_warnings)
                    raise RuntimeError(f"artefacte creat amb una versió diferent de scikit-learn: {details}")
                out[name] = model
                status[name] = "loaded"
                continue
            except Exception as exc:
                load_error = exc

        can_fit_gaussian = name == "gaussian" and data_dir and Path(data_dir).exists()
        if can_fit_gaussian:
            try:
                from data import load_hourly
                hourly = load_hourly(data_dir)
                model = cls().fit(hourly)
                artifacts_dir.mkdir(parents=True, exist_ok=True)
                model.save(path)
                out[name] = model
                status[name] = "fitted_from_data" if load_error is None else "refitted_after_incompatible_artifact"
                if load_error is not None:
                    status[name] += f" ({type(load_error).__name__}: {load_error})"
            except Exception as fit_error:
                if load_error is not None:
                    status[name] = (f"artifact load failed ({type(load_error).__name__}: {load_error}); "
                                    f"retraining failed ({type(fit_error).__name__}: {fit_error})")
                else:
                    status[name] = f"fitting failed: {type(fit_error).__name__}: {fit_error}"
        elif load_error is not None:
            status[name] = f"artifact load failed: {type(load_error).__name__}: {load_error}"
        else:
            status[name] = f"missing artifact {path}"

    return out, status
