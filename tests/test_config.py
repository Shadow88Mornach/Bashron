"""Tests for bashron.config — 100% branch coverage."""

import json

import pytest

import bashron.store as store
import bashron.config as config


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    config_dir = tmp_path / ".bashron"
    log_dir = config_dir / "logs"
    monkeypatch.setattr(store, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(store, "DB_FILE", config_dir / "scripts.json")
    monkeypatch.setattr(store, "LOG_DIR", log_dir)
    monkeypatch.setattr(config, "CONFIG_FILE", config_dir / "config.json")


class TestLoadRaw:
    def test_returns_empty_dict_when_file_missing(self):
        assert config._load_raw() == {}

    def test_returns_data_when_file_exists(self, tmp_path):
        config.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        config.CONFIG_FILE.write_text(json.dumps({"log_retention_days": 14}))
        assert config._load_raw() == {"log_retention_days": 14}


class TestSaveRaw:
    def test_writes_json_file(self):
        config._save_raw({"log_retention_days": 3})
        assert json.loads(config.CONFIG_FILE.read_text()) == {"log_retention_days": 3}


class TestGet:
    def test_returns_default_when_key_missing(self):
        assert config.get("log_retention_days", 99) == 99

    def test_returns_value_when_key_exists(self):
        config.set("log_retention_days", 10)
        assert config.get("log_retention_days") == 10

    def test_returns_none_default_when_not_specified(self):
        assert config.get("nonexistent") is None


class TestSet:
    def test_sets_new_key(self):
        config.set("foo", "bar")
        assert config.get("foo") == "bar"

    def test_overwrites_existing_key(self):
        config.set("log_retention_days", 5)
        config.set("log_retention_days", 20)
        assert config.get("log_retention_days") == 20


class TestAllSettings:
    def test_returns_default_when_no_config(self):
        settings = config.all_settings()
        assert settings == {"log_retention_days": config.DEFAULT_RETENTION_DAYS}

    def test_returns_configured_value(self):
        config.set_retention_days(30)
        assert config.all_settings()["log_retention_days"] == 30


class TestGetRetentionDays:
    def test_returns_default_when_not_set(self):
        assert config.get_retention_days() == config.DEFAULT_RETENTION_DAYS

    def test_returns_configured_value(self):
        config.set_retention_days(14)
        assert config.get_retention_days() == 14


class TestSetRetentionDays:
    def test_sets_valid_value(self):
        config.set_retention_days(30)
        assert config.get_retention_days() == 30

    def test_allows_minimum_of_1(self):
        config.set_retention_days(1)
        assert config.get_retention_days() == 1

    def test_raises_for_zero(self):
        with pytest.raises(ValueError, match="at least 1"):
            config.set_retention_days(0)

    def test_raises_for_negative(self):
        with pytest.raises(ValueError, match="at least 1"):
            config.set_retention_days(-5)
