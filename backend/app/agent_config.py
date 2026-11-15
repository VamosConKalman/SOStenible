"""Central registry for enabled demo agents and their battery parameters."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "agents.json"

def _load() -> dict[str, Any]:
    with CONFIG_PATH.open(encoding="utf-8") as f:
        config = json.load(f)
    agents = config.get("agents")
    if not isinstance(agents, dict) or not agents:
        raise ValueError("config/agents.json needs a non-empty agents object")
    for key, spec in agents.items():
        for field in ("enabled", "label", "description", "agent_file", "battery"):
            if field not in spec:
                raise ValueError(f"Agent {key} misses {field}")
        path = (ROOT / spec["agent_file"]).resolve()
        if ROOT.resolve() not in path.parents:
            raise ValueError(f"Agent path escapes repository: {key}")
    enabled = [k for k,v in agents.items() if v["enabled"]]
    if not enabled:
        raise ValueError("At least one agent must be enabled")
    return config

CONFIG = _load()
AGENTS = CONFIG["agents"]
ENABLED_AGENTS = {k:v for k,v in AGENTS.items() if v["enabled"]}
DEFAULT_MODE = CONFIG.get("default_mode")
if DEFAULT_MODE not in ENABLED_AGENTS:
    DEFAULT_MODE = next(iter(ENABLED_AGENTS))

def public_agent_catalog() -> dict[str, Any]:
    return {
        "default_mode": DEFAULT_MODE,
        "agents": [{
            "id": key, "label": spec["label"], "description": spec["description"],
            "score_reference": spec.get("score_reference"),
            "capacity_kwh": spec["battery"]["capacity_kwh"],
            "power_kw": spec["battery"]["power_kw"],
            "forecast_horizon": spec["battery"]["forecast_horizon"],
        } for key,spec in ENABLED_AGENTS.items()]
    }
