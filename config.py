from __future__ import annotations

import os
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        if key and value:
            os.environ[key] = value


_load_env_file(BASE_DIR / ".env.local")
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = BASE_DIR / "cache"
RAW_CACHE_DIR = CACHE_DIR / "raw"
SUMMARY_CACHE_DIR = CACHE_DIR / "summaries"
PROMPTS_DIR = BASE_DIR / "prompts"
USER_SETTINGS_FILE = DATA_DIR / "user_settings.json"

# Ensure directories exist at import time
for directory in (DATA_DIR, RAW_CACHE_DIR / "blogs", RAW_CACHE_DIR / "youtube", SUMMARY_CACHE_DIR, PROMPTS_DIR):
    directory.mkdir(parents=True, exist_ok=True)

CONTENT_INDEX_FILE = DATA_DIR / "content_index.json"
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Default cache configuration values
CACHE_TTL_HOURS = float(os.getenv("CACHE_TTL_HOURS", 12))
MAX_BLOG_ARTICLES_PER_SOURCE = int(os.getenv("MAX_BLOG_ARTICLES_PER_SOURCE", 5))


def get_user_settings() -> dict:
    if not USER_SETTINGS_FILE.exists():
        return {}
    try:
        return json.loads(USER_SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
