"""Agent loading with isolated sys.modules to avoid module name collisions.

Each agent folder (agents/estandar, agents/dificil) has its own `lp_model.py`
(and `features.py` / `forecaster_base.py`). Both agents do `import lp_model`,
so the generic names are bound to the right files only *while* the agent module
is being executed, and restored afterwards. Loaded classes are cached per mode.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import threading
from pathlib import Path

from app.agent_config import AGENTS, ENABLED_AGENTS, ROOT

MODE_SPECS = {
    mode: {"agent_file": (ROOT / spec["agent_file"]).resolve(),
           "prefix": spec.get("module_prefix", f"_{mode}")}
    for mode, spec in ENABLED_AGENTS.items()
}

# Helper modules an agent may import by their generic name
_HELPERS = ("lp_model", "features", "forecaster_base")

_cache: dict[str, type] = {}
_modules: dict[str, object] = {}
_lock = threading.Lock()


def _load_file(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_agent_module(mode: str):
    """Return the (cached) agent module for a mode."""
    if mode in _modules:
        return _modules[mode]
    with _lock:
        if mode in _modules:
            return _modules[mode]
        cfg = MODE_SPECS.get(mode)
        if cfg is None:
            raise ValueError(f"Agent '{mode}' is disabled or unknown. Available: {', '.join(MODE_SPECS)}")
        agent_file: Path = cfg["agent_file"]
        if not agent_file.exists():
            raise FileNotFoundError(f"Agent file not found: {agent_file}")
        folder = agent_file.parent
        saved = {h: sys.modules.get(h) for h in _HELPERS}
        try:
            for h in _HELPERS:
                sys.modules.pop(h, None)
            # load helpers under an isolated name and expose them under the generic one
            for h in _HELPERS:
                f = folder / f"{h}.py"
                if f.exists():
                    sys.modules[h] = _load_file(f"{cfg['prefix']}_{h}", f)
            mod = _load_file(f"{cfg['prefix']}_agent", agent_file)
        finally:
            for h, m in saved.items():
                if m is None:
                    sys.modules.pop(h, None)
                else:
                    sys.modules[h] = m
        _modules[mode] = mod
        _cache[mode] = mod.BatteryAgent
        return mod


def load_agent_class(mode: str):
    """Return the BatteryAgent class for a mode (instantiate it to get a fresh agent)."""
    if mode not in _cache:
        load_agent_module(mode)
    return _cache[mode]


def load_parametres(mode: str) -> dict:
    """Load parametres.json from the agent's directory."""
    if mode not in AGENTS:
        raise KeyError(f"Unknown agent mode: {mode}")
    param_file = (ROOT / AGENTS[mode]["agent_file"]).resolve().parent / "parametres.json"
    if param_file.exists():
        return json.loads(param_file.read_text())
    return {}
