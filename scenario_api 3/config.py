"""Configuració per variables d'entorn (pensat per a Docker)."""
import os
from pathlib import Path

ARTIFACTS_DIR = Path(os.getenv("ARTIFACTS_DIR", "artifacts"))   # models ajustats (.joblib) + avaluacions (.json)
DATA_DIR = Path(os.getenv("DATA_DIR", "data/train"))            # CSV oficials (només per ajustar)
MAX_PATHS = int(os.getenv("MAX_PATHS", "20000"))                # límit de trajectòries per petició
DEFAULT_HORIZON = int(os.getenv("DEFAULT_HORIZON", "24"))       # hores a simular (t .. t+H-1)
