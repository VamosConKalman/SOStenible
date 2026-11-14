"""pytest -q   (dades sintètiques, no cal tenir els CSV)"""
import os, sys, tempfile
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def synth(days=90, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-01", periods=24 * days, freq="h")
    h = idx.hour.values
    sol = np.clip(120 * np.sin((h - 6) / 12 * np.pi), 0, None) * rng.uniform(.6, 1.1, len(idx))
    dem = 1000 + 300 * np.sin((h - 8) / 24 * 2 * np.pi) - 200 * (idx.dayofweek.values >= 5) + rng.normal(0, 60, len(idx))
    price = 0.14 + 0.05 * np.sin((h - 14) / 24 * 2 * np.pi) + rng.normal(0, .01, len(idx))
    co2 = 0.08 + 0.02 * np.sin((h - 14) / 24 * 2 * np.pi) + rng.normal(0, .004, len(idx))
    return pd.DataFrame({"dem": dem, "sol": sol, "price": price, "co2": co2}, index=idx)


def test_generate_and_reduce():
    from generators.gaussian_mc import GaussianMCGenerator
    from generators import GenRequest
    from reduction import reduce_paths
    g = GaussianMCGenerator().fit(synth())
    req = GenRequest(timestamp=pd.Timestamp("2026-02-10 17:00"), price_forecast=np.full(24, .15), co2_forecast=np.full(24, .08),
                     last_dem=1100., last_sol=20., n_paths=300, seed=1)
    r = g.generate(req)
    assert r.paths["dem"].shape == (300, 24) and r.paths["sol"].shape == (300, 24)
    assert (r.paths["sol"] >= 0).all() and abs(r.prob.sum() - 1) < 1e-9
    red = reduce_paths(r.paths, k=5)
    assert red["paths"]["dem"].shape == (5, 24) and abs(red["prob"].sum() - 1) < 1e-9


def test_api():
    from fastapi.testclient import TestClient
    from generators.gaussian_mc import GaussianMCGenerator
    d = tempfile.mkdtemp()
    GaussianMCGenerator().fit(synth()).save(Path(d) / "gaussian.joblib")
    os.environ["ARTIFACTS_DIR"] = d
    import importlib, config, api
    importlib.reload(config); importlib.reload(api)
    body = {"timestamp": "2026-02-10T17:00:00", "price_forecast": [.15] * 24, "co2_forecast": [.08] * 24,
            "last_dem_kw": 1100, "last_sol_kw": 20, "n_paths": 200, "reduce": {"k": 4}}
    with TestClient(api.app) as c:
        assert c.get("/health").json()["generators_loaded"] == ["gaussian"]
        r = c.post("/generate", json=body)
        assert r.status_code == 200, r.text
        j = r.json()
        assert len(j["timestamps"]) == 24 and len(j["paths"]["dem"]) == 200 and len(j["reduced"]["prob"]) == 4
        assert c.post("/generate", json={**body, "generator": "nope"}).status_code == 404
        assert c.post("/generate", json={**body, "co2_forecast": [.08] * 5}).status_code == 422


def test_loader_recovers_from_incompatible_artifact(tmp_path, monkeypatch):
    from generators.registry import load_generators
    import data

    artifacts = tmp_path / "artifacts"
    train = tmp_path / "train"
    artifacts.mkdir()
    train.mkdir()
    # Simula un joblib trencat/incompatible que ja existeix.
    (artifacts / "gaussian.joblib").write_bytes(b"not-a-valid-joblib")
    monkeypatch.setattr(data, "load_hourly", lambda _: synth(days=90, seed=12))

    loaded, status = load_generators(artifacts, train)
    assert "gaussian" in loaded
    assert status["gaussian"].startswith("refitted_after_incompatible_artifact")
    assert (artifacts / "gaussian.joblib").stat().st_size > 1000
