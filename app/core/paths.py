from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

DATA_DIR = PROJECT_ROOT / "data"
JOBS_DIR = DATA_DIR / "jobs"
# Uploads land here while being size-checked, before a job id exists.
TMP_DIR = DATA_DIR / "tmp"

CONFIG_DIR = PROJECT_ROOT / "config"
# Your list, which is gitignored, and the checked-in default it starts from.
MODELS_FILE = CONFIG_DIR / "models.toml"
MODELS_DEFAULT_FILE = CONFIG_DIR / "model_default.toml"
