"""Tests for bashron.cron — 100% branch coverage."""

import subprocess
from unittest.mock import MagicMock, call, patch

import pytest

import bashron.store as store
import bashron.config as config
import bashron.cron as cron


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    config_dir = tmp_path / ".bashron"
    log_dir = config_dir / "logs"
    monkeypatch.setattr(store, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(store, "DB_FILE", config_dir / "scripts.json")
    monkeypatch.setattr(store, "LOG_DIR", log_dir)
    monkeypatch.setattr(config, "CONFIG_FILE", config_dir / "config.json")


def _add_job(tmp_path, name, run_at="09:00"):
    s = tmp_path / f"{name}.sh"
    s.touch()
    store.add(name, str(s), run_at)


# ---------------------------------------------------------------------------
# _bashron_bin
# ---------------------------------------------------------------------------

class TestBashronBin:
    def test_returns_path_when_found(self):
        with patch("shutil.which", return_value="/usr/local/bin/bashron"):
            assert cron._bashron_bin() == "/usr/local/bin/bashron"

    def test_raises_when_not_found(self):
        with patch("shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="not found in PATH"):
                cron._bashron_bin()


# ---------------------------------------------------------------------------
# _time_to_cron
# ---------------------------------------------------------------------------

class TestTimeToCron:
    def test_converts_hour_and_minute(self):
        assert cron._time_to_cron("09:30") == "30 9"

    def test_zero_pads_stripped(self):
        assert cron._time_to_cron("08:00") == "0 8"

    def test_midnight(self):
        assert cron._time_to_cron("00:00") == "0 0"


# ---------------------------------------------------------------------------
# _to_cron_schedule
# ---------------------------------------------------------------------------

class TestToCronSchedule:
    def test_daily_default(self):
        entry = {"run_at": "09:30", "frequency": "daily"}
        assert cron._to_cron_schedule(entry) == "30 9 * * *"

    def test_daily_missing_frequency_defaults_to_daily(self):
        entry = {"run_at": "08:00"}
        assert cron._to_cron_schedule(entry) == "0 8 * * *"

    def test_hourly(self):
        entry = {"run_at": "08:00", "frequency": "hourly"}
        assert cron._to_cron_schedule(entry) == "0 * * * *"

    def test_weekly_monday(self):
        entry = {"run_at": "09:00", "frequency": "weekly", "weekday": "monday"}
        assert cron._to_cron_schedule(entry) == "0 9 * * 1"

    def test_weekly_sunday(self):
        entry = {"run_at": "10:00", "frequency": "weekly", "weekday": "sunday"}
        assert cron._to_cron_schedule(entry) == "0 10 * * 0"

    def test_weekly_defaults_to_monday(self):
        entry = {"run_at": "09:00", "frequency": "weekly"}
        assert cron._to_cron_schedule(entry) == "0 9 * * 1"

    def test_monthly_day_1(self):
        entry = {"run_at": "08:00", "frequency": "monthly", "month_day": 1}
        assert cron._to_cron_schedule(entry) == "0 8 1 * *"

    def test_monthly_day_15(self):
        entry = {"run_at": "14:30", "frequency": "monthly", "month_day": 15}
        assert cron._to_cron_schedule(entry) == "30 14 15 * *"

    def test_monthly_defaults_to_day_1(self):
        entry = {"run_at": "08:00", "frequency": "monthly"}
        assert cron._to_cron_schedule(entry) == "0 8 1 * *"


# ---------------------------------------------------------------------------
# build_entries
# ---------------------------------------------------------------------------

def _add_job_with_freq(tmp_path, name, run_at="09:00", frequency="daily", weekday="monday", month_day=1):
    s = tmp_path / f"{name}.sh"
    s.touch()
    store.add(name, str(s), run_at, frequency=frequency, weekday=weekday, month_day=month_day)


class TestBuildEntries:
    def test_includes_block_markers(self, tmp_path):
        _add_job(tmp_path, "myjob", "09:00")
        entries = cron.build_entries(bashron_bin="/usr/bin/bashron")
        assert entries[0] == cron._BLOCK_START
        assert entries[-1] == cron._BLOCK_END

    def test_includes_job_entry(self, tmp_path):
        _add_job(tmp_path, "myjob", "09:00")
        entries = cron.build_entries(bashron_bin="/usr/bin/bashron")
        assert any("bashron run myjob" in e for e in entries)

    def test_includes_clean_logs_entry(self, tmp_path):
        _add_job(tmp_path, "myjob", "09:00")
        entries = cron.build_entries(bashron_bin="/usr/bin/bashron")
        assert any("clean-logs" in e for e in entries)

    def test_daily_cron_time_is_correct(self, tmp_path):
        _add_job(tmp_path, "myjob", "14:30")
        entries = cron.build_entries(bashron_bin="/b")
        job_line = next(e for e in entries if "run myjob" in e)
        assert job_line.startswith("30 14 * * *")

    def test_hourly_cron_schedule(self, tmp_path):
        _add_job_with_freq(tmp_path, "hj", frequency="hourly")
        entries = cron.build_entries(bashron_bin="/b")
        job_line = next(e for e in entries if "run hj" in e)
        assert job_line.startswith("0 * * * *")

    def test_weekly_cron_schedule(self, tmp_path):
        _add_job_with_freq(tmp_path, "wj", run_at="09:00", frequency="weekly", weekday="friday")
        entries = cron.build_entries(bashron_bin="/b")
        job_line = next(e for e in entries if "run wj" in e)
        assert job_line.startswith("0 9 * * 5")

    def test_monthly_cron_schedule(self, tmp_path):
        _add_job_with_freq(tmp_path, "mj", run_at="08:00", frequency="monthly", month_day=10)
        entries = cron.build_entries(bashron_bin="/b")
        job_line = next(e for e in entries if "run mj" in e)
        assert job_line.startswith("0 8 10 * *")

    def test_uses_configured_retention(self, tmp_path):
        _add_job(tmp_path, "j", "08:00")
        config.set_retention_days(21)
        entries = cron.build_entries(bashron_bin="/b")
        cleanup_line = next(e for e in entries if "clean-logs" in e)
        assert "--days 21" in cleanup_line

    def test_uses_which_when_bin_not_provided(self, tmp_path):
        _add_job(tmp_path, "j", "08:00")
        with patch("shutil.which", return_value="/auto/bashron"):
            entries = cron.build_entries()
        assert any("/auto/bashron" in e for e in entries)

    def test_multiple_jobs(self, tmp_path):
        for name, t in [("a", "01:00"), ("b", "02:00"), ("c", "03:00")]:
            _add_job(tmp_path, name, t)
        entries = cron.build_entries(bashron_bin="/b")
        job_lines = [e for e in entries if " run " in e]
        assert len(job_lines) == 3


# ---------------------------------------------------------------------------
# _read_crontab
# ---------------------------------------------------------------------------

class TestReadCrontab:
    def test_returns_stdout_on_success(self):
        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = "0 9 * * * /bin/backup\n"
        with patch("subprocess.run", return_value=mock):
            assert cron._read_crontab() == "0 9 * * * /bin/backup\n"

    def test_returns_empty_string_when_no_crontab(self):
        mock = MagicMock()
        mock.returncode = 1
        with patch("subprocess.run", return_value=mock):
            assert cron._read_crontab() == ""


# ---------------------------------------------------------------------------
# _write_crontab
# ---------------------------------------------------------------------------

class TestWriteCrontab:
    def test_calls_crontab_with_content(self):
        mock = MagicMock()
        mock.returncode = 0
        with patch("subprocess.run", return_value=mock) as mock_run:
            cron._write_crontab("some content\n")
        args, kwargs = mock_run.call_args
        assert args[0] == ["crontab", "-"]
        assert kwargs["input"] == "some content\n"

    def test_raises_on_failure(self):
        mock = MagicMock()
        mock.returncode = 1
        mock.stderr = "permission denied"
        with patch("subprocess.run", return_value=mock):
            with pytest.raises(RuntimeError, match="crontab write failed"):
                cron._write_crontab("bad\n")


# ---------------------------------------------------------------------------
# _strip_managed_block
# ---------------------------------------------------------------------------

class TestStripManagedBlock:
    def test_removes_block_between_markers(self):
        text = f"before\n{cron._BLOCK_START}\nmanaged line\n{cron._BLOCK_END}\nafter"
        result = cron._strip_managed_block(text)
        assert "managed line" not in result
        assert "before" in result
        assert "after" in result

    def test_no_markers_returns_unchanged(self):
        text = "line1\nline2\n"
        # join(splitlines()) drops the trailing newline — that's expected behaviour
        assert cron._strip_managed_block(text) == "line1\nline2"

    def test_strips_only_inside_block(self):
        text = f"keep\n{cron._BLOCK_START}\nremove\n{cron._BLOCK_END}\nkeep2"
        result = cron._strip_managed_block(text)
        assert result == "keep\nkeep2"


# ---------------------------------------------------------------------------
# is_supported
# ---------------------------------------------------------------------------

class TestIsSupported:
    def test_windows_not_supported(self):
        with patch("platform.system", return_value="Windows"):
            assert cron.is_supported() is False

    def test_linux_supported(self):
        with patch("platform.system", return_value="Linux"):
            assert cron.is_supported() is True

    def test_darwin_supported(self):
        with patch("platform.system", return_value="Darwin"):
            assert cron.is_supported() is True


# ---------------------------------------------------------------------------
# install
# ---------------------------------------------------------------------------

class TestInstall:
    def test_installs_into_empty_crontab(self, tmp_path):
        _add_job(tmp_path, "j", "09:00")
        read_mock = MagicMock(returncode=1)  # empty crontab
        write_mock = MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=[read_mock, write_mock]) as mock_run, \
             patch("shutil.which", return_value="/bin/bashron"):
            entries = cron.install()

        written = mock_run.call_args_list[1][1]["input"]
        assert cron._BLOCK_START in written
        assert "bashron run j" in written

    def test_replaces_existing_block(self, tmp_path):
        _add_job(tmp_path, "j", "09:00")
        old = f"other job\n{cron._BLOCK_START}\nold entry\n{cron._BLOCK_END}\n"
        read_mock = MagicMock(returncode=0, stdout=old)
        write_mock = MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=[read_mock, write_mock]) as mock_run, \
             patch("shutil.which", return_value="/bin/bashron"):
            cron.install()

        written = mock_run.call_args_list[1][1]["input"]
        assert "old entry" not in written
        assert "other job" in written

    def test_returns_entries(self, tmp_path):
        _add_job(tmp_path, "j", "09:00")
        read_mock = MagicMock(returncode=1)
        write_mock = MagicMock(returncode=0)
        with patch("subprocess.run", side_effect=[read_mock, write_mock]), \
             patch("shutil.which", return_value="/bin/bashron"):
            entries = cron.install()
        assert isinstance(entries, list)
        assert len(entries) > 0

    def test_accepts_custom_bin(self, tmp_path):
        _add_job(tmp_path, "j", "09:00")
        read_mock = MagicMock(returncode=1)
        write_mock = MagicMock(returncode=0)
        with patch("subprocess.run", side_effect=[read_mock, write_mock]) as mock_run:
            cron.install(bashron_bin="/custom/bashron")
        written = mock_run.call_args_list[1][1]["input"]
        assert "/custom/bashron" in written


# ---------------------------------------------------------------------------
# uninstall
# ---------------------------------------------------------------------------

class TestUninstall:
    def test_removes_block_and_returns_true(self):
        existing = f"keep\n{cron._BLOCK_START}\nmanaged\n{cron._BLOCK_END}\n"
        read_mock = MagicMock(returncode=0, stdout=existing)
        write_mock = MagicMock(returncode=0)
        with patch("subprocess.run", side_effect=[read_mock, write_mock]) as mock_run:
            result = cron.uninstall()
        assert result is True
        written = mock_run.call_args_list[1][1]["input"]
        assert "managed" not in written
        assert "keep" in written

    def test_returns_false_when_no_block(self):
        read_mock = MagicMock(returncode=0, stdout="other line\n")
        with patch("subprocess.run", return_value=read_mock):
            result = cron.uninstall()
        assert result is False

    def test_writes_empty_crontab_when_only_block_existed(self):
        existing = f"{cron._BLOCK_START}\nmanaged\n{cron._BLOCK_END}\n"
        read_mock = MagicMock(returncode=0, stdout=existing)
        write_mock = MagicMock(returncode=0)
        with patch("subprocess.run", side_effect=[read_mock, write_mock]) as mock_run:
            cron.uninstall()
        written = mock_run.call_args_list[1][1]["input"]
        assert written == ""
