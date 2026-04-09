"""Tests for bashron.cleaner — 100% branch coverage."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

import bashron.store as store
import bashron.config as config
import bashron.cleaner as cleaner


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    config_dir = tmp_path / ".bashron"
    log_dir = config_dir / "logs"
    monkeypatch.setattr(store, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(store, "DB_FILE", config_dir / "scripts.json")
    monkeypatch.setattr(store, "LOG_DIR", log_dir)
    monkeypatch.setattr(config, "CONFIG_FILE", config_dir / "config.json")


def _make_log(name: str, age_days: float) -> None:
    """Create a log file and set its mtime to age_days in the past."""
    store._ensure_dirs()
    log = store.LOG_DIR / f"{name}.log"
    log.write_text(f"log content for {name}")
    past = datetime.now(tz=timezone.utc) - timedelta(days=age_days)
    import os, time
    ts = past.timestamp()
    os.utime(log, (ts, ts))


class TestCleanLogs:
    def test_deletes_logs_older_than_retention(self):
        _make_log("old-job", age_days=8)
        deleted = cleaner.clean_logs(retention_days=7)
        assert "old-job.log" in deleted
        assert not (store.LOG_DIR / "old-job.log").exists()

    def test_keeps_logs_within_retention(self):
        _make_log("fresh-job", age_days=3)
        deleted = cleaner.clean_logs(retention_days=7)
        assert deleted == []
        assert (store.LOG_DIR / "fresh-job.log").exists()

    def test_log_exactly_at_retention_boundary_is_deleted(self):
        _make_log("boundary-job", age_days=7)
        deleted = cleaner.clean_logs(retention_days=7)
        assert "boundary-job.log" in deleted

    def test_returns_empty_list_when_no_logs(self):
        store._ensure_dirs()
        deleted = cleaner.clean_logs(retention_days=7)
        assert deleted == []

    def test_deletes_only_old_files_mixed(self):
        _make_log("old", age_days=10)
        _make_log("new", age_days=2)
        deleted = cleaner.clean_logs(retention_days=7)
        assert deleted == ["old.log"]
        assert (store.LOG_DIR / "new.log").exists()

    def test_uses_configured_retention_when_days_is_none(self):
        config.set_retention_days(5)
        _make_log("mid-age", age_days=6)
        deleted = cleaner.clean_logs()  # no override → uses config (5)
        assert "mid-age.log" in deleted

    def test_override_days_ignores_config(self):
        config.set_retention_days(1)  # config says delete after 1 day
        _make_log("safe", age_days=3)
        # override to 30 days → should NOT delete
        deleted = cleaner.clean_logs(retention_days=30)
        assert deleted == []
        assert (store.LOG_DIR / "safe.log").exists()

    def test_multiple_old_logs_all_deleted(self):
        for name in ("a", "b", "c"):
            _make_log(name, age_days=15)
        deleted = cleaner.clean_logs(retention_days=7)
        assert sorted(deleted) == ["a.log", "b.log", "c.log"]
