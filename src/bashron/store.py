"""Persistent JSON store for scheduled scripts."""

import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".bashron"
DB_FILE = CONFIG_DIR / "scripts.json"
LOG_DIR = CONFIG_DIR / "logs"


def _ensure_dirs() -> None:
    CONFIG_DIR.mkdir(exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)


def load() -> list[dict]:
    _ensure_dirs()
    if not DB_FILE.exists():
        return []
    with DB_FILE.open() as f:
        return json.load(f)


def save(scripts: list[dict]) -> None:
    _ensure_dirs()
    with DB_FILE.open("w") as f:
        json.dump(scripts, f, indent=2)


def add(
    name: str,
    path: str,
    run_at: str,
    frequency: str = "daily",
    weekday: str = "monday",
    month_day: int = 1,
    notify: bool = False,
    webhook: str = "",
) -> dict:
    scripts = load()
    for s in scripts:
        if s["name"] == name:
            raise ValueError(f"Script '{name}' already exists. Use a different name.")
    entry = {
        "name": name,
        "path": str(Path(path).expanduser().resolve()),
        "run_at": run_at,
        "frequency": frequency,
        "weekday": weekday,
        "month_day": month_day,
        "notify": notify,
        "webhook": webhook,
    }
    scripts.append(entry)
    save(scripts)
    return entry


def remove(name: str) -> bool:
    scripts = load()
    new = [s for s in scripts if s["name"] != name]
    if len(new) == len(scripts):
        return False
    save(new)
    return True


def log_path(name: str) -> Path:
    _ensure_dirs()
    return LOG_DIR / f"{name}.log"
