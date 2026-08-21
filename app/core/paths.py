from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

DATA_DIR = PROJECT_ROOT / "data"
JOBS_DIR = DATA_DIR / "jobs"

CONFIG_DIR = PROJECT_ROOT / "config"
MODELS_FILE = CONFIG_DIR / "models.toml"
