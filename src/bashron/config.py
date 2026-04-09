"""Persistent configuration store for bashron settings."""

import json
from typing import Any

from . import store

CONFIG_FILE = store.CONFIG_DIR / "config.json"
DEFAULT_RETENTION_DAYS = 7


def _load_raw() -> dict:
    store._ensure_dirs()
    if not CONFIG_FILE.exists():
        return {}
    with CONFIG_FILE.open() as f:
        return json.load(f)


def _save_raw(cfg: dict) -> None:
    store._ensure_dirs()
    with CONFIG_FILE.open("w") as f:
        json.dump(cfg, f, indent=2)


def get(key: str, default: Any = None) -> Any:
    return _load_raw().get(key, default)


def set(key: str, value: Any) -> None:  # noqa: A001
    cfg = _load_raw()
    cfg[key] = value
    _save_raw(cfg)


def all_settings() -> dict:
    """Return all settings merged with defaults."""
    return {"log_retention_days": get("log_retention_days", DEFAULT_RETENTION_DAYS)}


def get_retention_days() -> int:
    return int(get("log_retention_days", DEFAULT_RETENTION_DAYS))


def set_retention_days(days: int) -> None:
    if days < 1:
        raise ValueError("Retention must be at least 1 day.")
    set("log_retention_days", days)
