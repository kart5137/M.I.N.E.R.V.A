from __future__ import annotations

import os
from pathlib import Path

# Repo root: pipeline/src/ei_pipeline/config.py → parents[3]
ROOT = Path(os.environ.get("EI_ROOT", Path(__file__).resolve().parents[3]))
RAW_DIR = ROOT / "data" / "raw"
PROFILE_DIR = ROOT / "data" / "profiles"

USER_AGENT = "minerva-pipeline/0.1 (public-health research project)"
