from .base import (ScenarioGenerator, MeanModel, GenRequest, GenResult, VARS, H_MAX)   # noqa: F401
from .registry import REGISTRY, register, load_generators                                # noqa: F401
from . import gaussian_mc                                                                # noqa: F401  (registra "gaussian")
# from . import gbm_generator   # <- descomentar quan existeixi
