"""Generate and manage crontab entries for bashron jobs."""

import platform
import shutil
import subprocess
from . import store
from .config import get_retention_days

# Marker so we can find and remove bashron-managed lines
_BLOCK_START = "# >>> bashron managed >>>"
_BLOCK_END = "# <<< bashron managed <<<"


def _bashron_bin() -> str:
    """Return the absolute path to the bashron executable."""
    found = shutil.which("bashron")
    if found:
        return found
    raise RuntimeError(
        "bashron executable not found in PATH. "
        "Activate your venv or install bashron globally first."
    )


_WEEKDAY_CRON = {
    "monday": 1, "tuesday": 2, "wednesday": 3, "thursday": 4,
    "friday": 5, "saturday": 6, "sunday": 0,
}


def _time_to_cron(run_at: str) -> str:
    """Convert 'HH:MM' to cron 'MIN HOUR' fields."""
    hour, minute = run_at.split(":")
    return f"{int(minute)} {int(hour)}"


def _to_cron_schedule(entry: dict) -> str:
    """Return the full cron time fields (5 fields) for a job entry."""
    freq = entry.get("frequency", "daily")
    hm = _time_to_cron(entry.get("run_at", "08:00"))

    if freq == "hourly":
        return "0 * * * *"
    if freq == "weekly":
        dow = _WEEKDAY_CRON.get(entry.get("weekday", "monday"), 1)
        return f"{hm} * * {dow}"
    if freq == "monthly":
        month_day = entry.get("month_day", 1)
        return f"{hm} {month_day} * *"
    # daily (default)
    return f"{hm} * * *"


def build_entries(bashron_bin: str = None) -> list[str]:
    """
    Build crontab lines for all scheduled jobs plus the daily log-cleanup.

    Returns a list of strings (without trailing newlines).
    """
    if bashron_bin is None:
        bashron_bin = _bashron_bin()

    scripts = store.load()
    retention = get_retention_days()
    lines = [_BLOCK_START]

    for s in scripts:
        cron_schedule = _to_cron_schedule(s)
        lines.append(f"{cron_schedule} {bashron_bin} run {s['name']}")

    # Daily log cleanup at midnight
    lines.append(f"0 0 * * * {bashron_bin} clean-logs --days {retention}")
    lines.append(_BLOCK_END)
    return lines


def _read_crontab() -> str:
    """Return the current user crontab as a string (empty string if none)."""
    result = subprocess.run(
        ["crontab", "-l"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout
    # 'crontab -l' exits 1 when there is no crontab yet — treat as empty
    return ""


def _write_crontab(content: str) -> None:
    """Write content as the user's crontab."""
    proc = subprocess.run(
        ["crontab", "-"],
        input=content,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"crontab write failed: {proc.stderr.strip()}")


def _strip_managed_block(crontab: str) -> str:
    """Remove any existing bashron-managed block from a crontab string."""
    lines = crontab.splitlines()
    result = []
    inside = False
    for line in lines:
        if line.strip() == _BLOCK_START:
            inside = True
            continue
        if line.strip() == _BLOCK_END:
            inside = False
            continue
        if not inside:
            result.append(line)
    return "\n".join(result)


def is_supported() -> bool:
    """Return True if the platform supports crontab (not Windows)."""
    return platform.system() != "Windows"


def install(bashron_bin: str = None) -> list[str]:
    """
    Install bashron jobs into the user's crontab.

    Replaces any existing bashron block. Returns the list of installed lines.
    """
    entries = build_entries(bashron_bin)
    existing = _read_crontab()
    clean = _strip_managed_block(existing).rstrip("\n")
    new_block = "\n".join(entries)
    new_crontab = f"{clean}\n{new_block}\n" if clean else f"{new_block}\n"
    _write_crontab(new_crontab)
    return entries


def uninstall() -> bool:
    """
    Remove the bashron-managed block from the user's crontab.

    Returns True if a block was found and removed, False if nothing was there.
    """
    existing = _read_crontab()
    if _BLOCK_START not in existing:
        return False
    cleaned = _strip_managed_block(existing).strip()
    _write_crontab(cleaned + "\n" if cleaned else "")
    return True
