"""Log retention: delete log files older than N days."""

from datetime import datetime, timezone

from . import store
from .config import get_retention_days


def clean_logs(retention_days: int = None) -> list[str]:
    """
    Delete log files whose last modification time exceeds retention_days.

    Args:
        retention_days: Override retention period. Uses configured value when None.

    Returns:
        List of deleted log file names (without path).
    """
    if retention_days is None:
        retention_days = get_retention_days()

    store._ensure_dirs()
    now = datetime.now(tz=timezone.utc)
    deleted = []

    for log_file in store.LOG_DIR.glob("*.log"):
        mtime = datetime.fromtimestamp(log_file.stat().st_mtime, tz=timezone.utc)
        age_days = (now - mtime).days
        if age_days >= retention_days:
            log_file.unlink()
            deleted.append(log_file.name)

    return deleted
