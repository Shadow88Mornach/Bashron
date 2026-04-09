"""Tests for bashron.store — 100% branch coverage."""

import json
from pathlib import Path

import pytest

import bashron.store as store


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    """Redirect all store paths to a temp directory for every test."""
    config_dir = tmp_path / ".bashron"
    log_dir = config_dir / "logs"

    monkeypatch.setattr(store, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(store, "DB_FILE", config_dir / "scripts.json")
    monkeypatch.setattr(store, "LOG_DIR", log_dir)


# ---------------------------------------------------------------------------
# _ensure_dirs
# ---------------------------------------------------------------------------

class TestEnsureDirs:
    def test_creates_config_and_log_dirs(self):
        assert not store.CONFIG_DIR.exists()
        store._ensure_dirs()
        assert store.CONFIG_DIR.is_dir()
        assert store.LOG_DIR.is_dir()

    def test_idempotent_when_dirs_already_exist(self):
        store._ensure_dirs()
        store._ensure_dirs()  # should not raise
        assert store.CONFIG_DIR.is_dir()


# ---------------------------------------------------------------------------
# load
# ---------------------------------------------------------------------------

class TestLoad:
    def test_returns_empty_list_when_db_missing(self):
        assert store.load() == []

    def test_returns_data_from_existing_db(self):
        store._ensure_dirs()
        data = [{"name": "x", "path": "/tmp/x.sh", "run_at": "08:00"}]
        store.DB_FILE.write_text(json.dumps(data))
        assert store.load() == data


# ---------------------------------------------------------------------------
# save
# ---------------------------------------------------------------------------

class TestSave:
    def test_writes_json_to_db_file(self):
        data = [{"name": "job1", "path": "/tmp/a.sh", "run_at": "09:00"}]
        store.save(data)
        assert json.loads(store.DB_FILE.read_text()) == data

    def test_overwrites_existing_db(self):
        store.save([{"name": "old"}])
        store.save([{"name": "new"}])
        assert json.loads(store.DB_FILE.read_text()) == [{"name": "new"}]


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------

class TestAdd:
    def test_adds_entry_and_returns_it(self, tmp_path):
        script = tmp_path / "go.sh"
        script.touch()
        entry = store.add("myjob", str(script), "10:00")
        assert entry["name"] == "myjob"
        assert entry["run_at"] == "10:00"
        assert entry["path"] == str(script.resolve())

    def test_persists_to_disk(self, tmp_path):
        script = tmp_path / "go.sh"
        script.touch()
        store.add("myjob", str(script), "10:00")
        assert store.load()[0]["name"] == "myjob"

    def test_raises_on_duplicate_name(self, tmp_path):
        script = tmp_path / "go.sh"
        script.touch()
        store.add("dup", str(script), "10:00")
        with pytest.raises(ValueError, match="already exists"):
            store.add("dup", str(script), "11:00")

    def test_multiple_entries(self, tmp_path):
        for i in range(3):
            s = tmp_path / f"s{i}.sh"
            s.touch()
            store.add(f"job{i}", str(s), "00:00")
        assert len(store.load()) == 3

    def test_add_with_notify_true(self, tmp_path):
        script = tmp_path / "go.sh"
        script.touch()
        entry = store.add("notifyjob", str(script), "10:00", notify=True)
        assert entry["notify"] is True

    def test_add_with_webhook(self, tmp_path):
        script = tmp_path / "go.sh"
        script.touch()
        entry = store.add("webhookjob", str(script), "10:00", webhook="https://hooks.example.com")
        assert entry["webhook"] == "https://hooks.example.com"

    def test_add_defaults_notify_false_and_empty_webhook(self, tmp_path):
        script = tmp_path / "go.sh"
        script.touch()
        entry = store.add("defaultjob", str(script), "10:00")
        assert entry["notify"] is False
        assert entry["webhook"] == ""

    def test_add_with_frequency_weekly(self, tmp_path):
        script = tmp_path / "go.sh"
        script.touch()
        entry = store.add("weeklyjob", str(script), "09:00", frequency="weekly", weekday="friday")
        assert entry["frequency"] == "weekly"
        assert entry["weekday"] == "friday"

    def test_add_with_frequency_monthly(self, tmp_path):
        script = tmp_path / "go.sh"
        script.touch()
        entry = store.add("monthlyjob", str(script), "08:00", frequency="monthly", month_day=15)
        assert entry["frequency"] == "monthly"
        assert entry["month_day"] == 15

    def test_add_with_frequency_hourly(self, tmp_path):
        script = tmp_path / "go.sh"
        script.touch()
        entry = store.add("hourlyjob", str(script), "08:00", frequency="hourly")
        assert entry["frequency"] == "hourly"

    def test_add_defaults_frequency_daily(self, tmp_path):
        script = tmp_path / "go.sh"
        script.touch()
        entry = store.add("dailyjob", str(script), "10:00")
        assert entry["frequency"] == "daily"
        assert entry["weekday"] == "monday"
        assert entry["month_day"] == 1


# ---------------------------------------------------------------------------
# remove
# ---------------------------------------------------------------------------

class TestRemove:
    def test_removes_existing_entry(self, tmp_path):
        script = tmp_path / "s.sh"
        script.touch()
        store.add("todelete", str(script), "07:00")
        assert store.remove("todelete") is True
        assert store.load() == []

    def test_returns_false_for_missing_name(self):
        assert store.remove("ghost") is False

    def test_leaves_other_entries_intact(self, tmp_path):
        for name in ("keep", "gone"):
            s = tmp_path / f"{name}.sh"
            s.touch()
            store.add(name, str(s), "06:00")
        store.remove("gone")
        remaining = [e["name"] for e in store.load()]
        assert remaining == ["keep"]


# ---------------------------------------------------------------------------
# log_path
# ---------------------------------------------------------------------------

class TestLogPath:
    def test_returns_path_under_log_dir(self):
        p = store.log_path("myjob")
        assert p == store.LOG_DIR / "myjob.log"

    def test_ensures_dirs_created(self):
        assert not store.CONFIG_DIR.exists()
        store.log_path("x")
        assert store.LOG_DIR.is_dir()
