"""Tests for bashron.cli — 100% branch coverage."""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

import bashron.cli as cli
import bashron.store as store
import bashron.config as config
import bashron.runner as runner
from bashron.cli import app

runner_cli = CliRunner()


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    config_dir = tmp_path / ".bashron"
    log_dir = config_dir / "logs"
    monkeypatch.setattr(store, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(store, "DB_FILE", config_dir / "scripts.json")
    monkeypatch.setattr(store, "LOG_DIR", log_dir)
    monkeypatch.setattr(config, "CONFIG_FILE", config_dir / "config.json")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def make_script(tmp_path, name="test.sh"):
    s = tmp_path / name
    s.write_text("#!/bin/bash\necho hi\n")
    return s


# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------

class TestInternalHelpers:
    def test_demo_script_contains_core_flow(self):
        demo = cli._demo_script()
        assert "bashron add backup" in demo
        assert "bashron list" in demo
        assert "bashron run backup" in demo
        assert "bashron start --quiet" in demo

    def test_has_time_passed_today_true(self):
        now = datetime(2026, 4, 8, 15, 30)
        assert cli._has_time_passed_today("15:00", now=now) is True

    def test_has_time_passed_today_false(self):
        now = datetime(2026, 4, 8, 15, 30)
        assert cli._has_time_passed_today("16:00", now=now) is False

    def test_print_log_tail_returns_false_when_missing(self):
        assert cli._print_log_tail("missing", 10) is False

    def test_print_log_tail_returns_true_when_log_exists(self, tmp_path):
        log = store.log_path("job")
        log.write_text("a\nb\nc\n")
        assert cli._print_log_tail("job", 2) is True

    def test_follow_log_returns_immediately_when_log_missing(self):
        with patch("bashron.cli._print_log_tail", return_value=False):
            cli._follow_log("missing", 10)

    def test_follow_log_prints_new_content_and_stops(self, tmp_path):
        mock_log = MagicMock()
        mock_log.stat.side_effect = [MagicMock(st_size=6), MagicMock(st_size=12)]
        handle = MagicMock()
        handle.read.return_value = "extra\n"
        context = MagicMock()
        context.__enter__.return_value = handle
        context.__exit__.return_value = None
        mock_log.open.return_value = context
        with patch("bashron.cli._print_log_tail", return_value=True), \
             patch("bashron.cli.store.log_path", return_value=mock_log), \
             patch("bashron.cli.time.sleep", side_effect=KeyboardInterrupt):
            cli._follow_log("job", 10)
        handle.seek.assert_called_once_with(6)

    def test_follow_log_handles_truncated_file(self, tmp_path):
        mock_log = MagicMock()
        mock_log.stat.side_effect = [MagicMock(st_size=5), MagicMock(st_size=2)]
        handle = MagicMock()
        handle.read.return_value = ""
        context = MagicMock()
        context.__enter__.return_value = handle
        context.__exit__.return_value = None
        mock_log.open.return_value = context
        with patch("bashron.cli._print_log_tail", return_value=True), \
             patch("bashron.cli.store.log_path", return_value=mock_log), \
             patch("bashron.cli.time.sleep", side_effect=KeyboardInterrupt):
            cli._follow_log("job", 10)
        handle.seek.assert_called_once_with(0)

    def test_follow_log_handles_unchanged_file(self):
        mock_log = MagicMock()
        mock_log.stat.side_effect = [MagicMock(st_size=5), MagicMock(st_size=5)]
        with patch("bashron.cli._print_log_tail", return_value=True), \
             patch("bashron.cli.store.log_path", return_value=mock_log), \
             patch("bashron.cli.time.sleep", side_effect=KeyboardInterrupt):
            cli._follow_log("job", 10)
        mock_log.open.assert_not_called()

    def test_run_single_job_success(self, tmp_path):
        entry = {"name": "job", "path": str(make_script(tmp_path))}
        with patch("bashron.cli.runner.run_script", return_value=0):
            assert cli._run_single_job(entry) == 0

    def test_run_single_job_failure(self, tmp_path):
        entry = {"name": "job", "path": str(make_script(tmp_path))}
        with patch("bashron.cli.runner.run_script", return_value=2):
            assert cli._run_single_job(entry) == 2


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------

class TestDoctor:
    def _patch_all_pass(self, monkeypatch, tmp_path):
        """Patch everything so doctor sees a fully healthy system."""
        monkeypatch.setattr(store, "CONFIG_DIR", tmp_path / ".bashron")
        monkeypatch.setattr(store, "DB_FILE", tmp_path / ".bashron" / "scripts.json")
        monkeypatch.setattr(store, "LOG_DIR", tmp_path / ".bashron" / "logs")
        return {
            "bashron.cli.get_os": "Linux",
            "bashron.cli.is_supported_os": True,
            "bashron.cli.find_bash": "/bin/bash",
            "bashron.cli.python_version": "3.11.0",
        }

    def test_all_checks_pass(self, tmp_path, monkeypatch):
        monkeypatch.setattr(store, "CONFIG_DIR", tmp_path / ".bashron")
        monkeypatch.setattr(store, "DB_FILE", tmp_path / ".bashron" / "scripts.json")
        monkeypatch.setattr(store, "LOG_DIR", tmp_path / ".bashron" / "logs")
        with patch("bashron.cli.get_os", return_value="Linux"), \
             patch("bashron.cli.is_supported_os", return_value=True), \
             patch("bashron.cli.find_bash", return_value="/bin/bash"), \
             patch("bashron.cli.python_version", return_value="3.11.0"):
            result = runner_cli.invoke(app, ["doctor"])
        assert result.exit_code == 0
        assert "PASS" in result.output
        assert "ready" in result.output

    def test_unsupported_os_fails(self, tmp_path, monkeypatch):
        monkeypatch.setattr(store, "CONFIG_DIR", tmp_path / ".bashron")
        monkeypatch.setattr(store, "DB_FILE", tmp_path / ".bashron" / "scripts.json")
        monkeypatch.setattr(store, "LOG_DIR", tmp_path / ".bashron" / "logs")
        with patch("bashron.cli.get_os", return_value="FreeBSD"), \
             patch("bashron.cli.is_supported_os", return_value=False), \
             patch("bashron.cli.find_bash", return_value="/bin/bash"), \
             patch("bashron.cli.python_version", return_value="3.11.0"):
            result = runner_cli.invoke(app, ["doctor"])
        assert result.exit_code == 1
        assert "FAIL" in result.output

    def test_bash_missing_shows_hint_and_fails(self, tmp_path, monkeypatch):
        monkeypatch.setattr(store, "CONFIG_DIR", tmp_path / ".bashron")
        monkeypatch.setattr(store, "DB_FILE", tmp_path / ".bashron" / "scripts.json")
        monkeypatch.setattr(store, "LOG_DIR", tmp_path / ".bashron" / "logs")
        with patch("bashron.cli.get_os", return_value="Linux"), \
             patch("bashron.cli.is_supported_os", return_value=True), \
             patch("bashron.cli.find_bash", return_value=None), \
             patch("bashron.cli.python_version", return_value="3.11.0"), \
             patch("bashron.cli.bash_install_hint", return_value="Install bash hint"):
            result = runner_cli.invoke(app, ["doctor"])
        assert result.exit_code == 1
        assert "not found" in result.output
        assert "Install bash hint" in result.output

    def test_config_dir_not_writable_fails(self, tmp_path, monkeypatch):
        monkeypatch.setattr(store, "CONFIG_DIR", tmp_path / ".bashron")
        monkeypatch.setattr(store, "DB_FILE", tmp_path / ".bashron" / "scripts.json")
        monkeypatch.setattr(store, "LOG_DIR", tmp_path / ".bashron" / "logs")
        with patch("bashron.cli.get_os", return_value="Linux"), \
             patch("bashron.cli.is_supported_os", return_value=True), \
             patch("bashron.cli.find_bash", return_value="/bin/bash"), \
             patch("bashron.cli.python_version", return_value="3.11.0"), \
             patch("bashron.store._ensure_dirs", side_effect=OSError("Permission denied")):
            result = runner_cli.invoke(app, ["doctor"])
        assert result.exit_code == 1
        assert "Permission denied" in result.output


# ---------------------------------------------------------------------------
# --version
# ---------------------------------------------------------------------------

class TestMain:
    def test_no_args_shows_logo_and_help(self):
        result = runner_cli.invoke(app, [])
        assert result.exit_code == 0
        assert "warrior-class bash scheduling" in result.output
        assert "bashron" in result.output

    def test_subcommand_does_not_show_logo(self):
        result = runner_cli.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "warrior-class bash scheduling" not in result.output


class TestVersion:
    def test_prints_version(self):
        with patch("bashron.cli.python_version", return_value="3.13.0"), \
             patch("bashron.cli.get_os", return_value="Linux"):
            result = runner_cli.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "bashron" in result.output
        assert "3.13.0" in result.output
        assert "Linux" in result.output


# ---------------------------------------------------------------------------
# overview
# ---------------------------------------------------------------------------

class TestOverview:
    def test_prints_architecture_and_onboarding(self):
        result = runner_cli.invoke(app, ["overview"])
        assert result.exit_code == 0
        assert "bashron architecture" in result.output
        assert "new contributor path" in result.output
        assert "store.py" in result.output
        assert "runner.py" in result.output


# ---------------------------------------------------------------------------
# demo
# ---------------------------------------------------------------------------

class TestDemo:
    def test_prints_demo_and_recording_notes(self):
        result = runner_cli.invoke(app, ["demo"])
        assert result.exit_code == 0
        assert "bashron demo" in result.output
        assert "recording notes" in result.output
        assert "bashron add backup" in result.output
        assert "repo-stats" in result.output


# ---------------------------------------------------------------------------
# repo-stats
# ---------------------------------------------------------------------------

class TestRepoStats:
    def test_git_output_success(self):
        mock_result = MagicMock(returncode=0, stdout="main\n", stderr="")
        with patch("subprocess.run", return_value=mock_result):
            assert cli._git_output(["status"]) == "main"

    def test_git_output_failure(self):
        mock_result = MagicMock(returncode=1, stdout="", stderr="not a git repository")
        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="not a git repository"):
                cli._git_output(["status"])

    def test_repo_stats_shows_branch_and_commit_counts(self):
        with patch(
            "bashron.cli._git_output",
            side_effect=["feature/docs", "42", "5"],
        ):
            result = runner_cli.invoke(app, ["repo-stats"])
        assert result.exit_code == 0
        assert "feature/docs" in result.output
        assert "42" in result.output
        assert "5" in result.output

    def test_repo_stats_handles_missing_base_branch(self):
        with patch(
            "bashron.cli._git_output",
            side_effect=["feature/docs", "42", RuntimeError("unknown revision")],
        ):
            result = runner_cli.invoke(app, ["repo-stats", "--base", "develop"])
        assert result.exit_code == 0
        assert "unavailable" in result.output
        assert "develop" in result.output

    def test_repo_stats_fails_when_not_in_git_repo(self):
        with patch("bashron.cli._git_output", side_effect=RuntimeError("not a git repository")):
            result = runner_cli.invoke(app, ["repo-stats"])
        assert result.exit_code == 1
        assert "Git stats unavailable" in result.output


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------

class TestAdd:
    def test_add_success(self, tmp_path):
        s = make_script(tmp_path)
        with patch("bashron.cli._has_time_passed_today", return_value=False):
            result = runner_cli.invoke(app, ["add", "myjob", str(s), "--at", "09:00"])
        assert result.exit_code == 0
        assert "Job added" in result.output
        assert "myjob" in result.output
        assert "bashron run myjob" in result.output

    def test_add_file_not_found(self, tmp_path):
        result = runner_cli.invoke(app, ["add", "myjob", "/nonexistent/path.sh"])
        assert result.exit_code == 1
        assert "File not found" in result.output

    def test_add_non_sh_extension_shows_warning(self, tmp_path):
        s = tmp_path / "script.txt"
        s.write_text("echo hi")
        with patch("bashron.cli._has_time_passed_today", return_value=False):
            result = runner_cli.invoke(app, ["add", "myjob", str(s)])
        assert "Warning" in result.output
        assert result.exit_code == 0

    def test_add_duplicate_name_fails(self, tmp_path):
        s = make_script(tmp_path)
        with patch("bashron.cli._has_time_passed_today", return_value=False):
            runner_cli.invoke(app, ["add", "dup", str(s)])
            result = runner_cli.invoke(app, ["add", "dup", str(s)])
        assert result.exit_code == 1
        assert "Error" in result.output

    def test_add_default_time_is_0800(self, tmp_path):
        s = make_script(tmp_path)
        with patch("bashron.cli._has_time_passed_today", return_value=False):
            runner_cli.invoke(app, ["add", "myjob", str(s)])
        assert store.load()[0]["run_at"] == "08:00"

    def test_add_no_warning_when_time_not_passed(self, tmp_path):
        s = make_script(tmp_path)
        with patch("bashron.cli._has_time_passed_today", return_value=False):
            result = runner_cli.invoke(app, ["add", "futurejob", str(s), "--at", "23:00"])
        assert result.exit_code == 0
        assert "First run will be tomorrow" not in result.output

    def test_add_warns_when_time_has_passed_today(self, tmp_path):
        s = make_script(tmp_path)
        with patch("bashron.cli._has_time_passed_today", return_value=True):
            result = runner_cli.invoke(app, ["add", "latejob", str(s), "--at", "01:00"])
        assert result.exit_code == 0
        assert "First run will be tomorrow" in result.output

    def test_add_invalid_time_fails(self, tmp_path):
        s = make_script(tmp_path)
        with patch("bashron.cli._has_time_passed_today", side_effect=ValueError("bad time")):
            result = runner_cli.invoke(app, ["add", "badtime", str(s), "--at", "25:00"])
        assert result.exit_code == 1
        assert "Invalid time" in result.output


# ---------------------------------------------------------------------------
# remove
# ---------------------------------------------------------------------------

class TestRemove:
    def test_remove_existing_job(self, tmp_path):
        s = make_script(tmp_path)
        runner_cli.invoke(app, ["add", "todelete", str(s)])
        result = runner_cli.invoke(app, ["remove", "todelete"])
        assert result.exit_code == 0
        assert "Removed" in result.output

    def test_remove_missing_job_fails(self):
        result = runner_cli.invoke(app, ["remove", "ghost"])
        assert result.exit_code == 1
        assert "Error" in result.output


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

class TestList:
    def test_list_empty(self):
        result = runner_cli.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "No scripts scheduled" in result.output

    def test_list_json_empty(self):
        result = runner_cli.invoke(app, ["list", "--json"])
        assert result.exit_code == 0
        assert "[]" in result.output

    def test_list_shows_jobs(self, tmp_path):
        s = make_script(tmp_path)
        runner_cli.invoke(app, ["add", "showme", str(s), "--at", "07:30"])
        result = runner_cli.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "showme" in result.output
        assert "07:30" in result.output

    def test_list_json_shows_jobs(self, tmp_path):
        s = make_script(tmp_path)
        runner_cli.invoke(app, ["add", "showme", str(s), "--at", "07:30"])
        result = runner_cli.invoke(app, ["list", "--json"])
        assert result.exit_code == 0
        assert '"name": "showme"' in result.output
        assert '"run_at": "07:30"' in result.output
        assert '"log":' in result.output


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

class TestRun:
    def test_run_requires_name_or_all(self):
        result = runner_cli.invoke(app, ["run"])
        assert result.exit_code == 1
        assert "Provide a job name or use --all" in result.output

    def test_run_missing_job_fails(self):
        result = runner_cli.invoke(app, ["run", "ghost"])
        assert result.exit_code == 1
        assert "Error" in result.output

    def test_run_success(self, tmp_path):
        s = make_script(tmp_path)
        runner_cli.invoke(app, ["add", "runjob", str(s)])
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("bashron.runner.find_bash", return_value="/bin/bash"), \
             patch("subprocess.run", return_value=mock_result):
            result = runner_cli.invoke(app, ["run", "runjob"])
        assert result.exit_code == 0
        assert "Done" in result.output

    def test_run_failure_exits_with_code(self, tmp_path):
        s = make_script(tmp_path)
        runner_cli.invoke(app, ["add", "failjob", str(s)])
        mock_result = MagicMock()
        mock_result.returncode = 2
        with patch("bashron.runner.find_bash", return_value="/bin/bash"), \
             patch("subprocess.run", return_value=mock_result):
            result = runner_cli.invoke(app, ["run", "failjob"])
        assert result.exit_code == 2
        assert "Failed" in result.output

    def test_run_all_requires_no_name(self):
        result = runner_cli.invoke(app, ["run", "job", "--all"])
        assert result.exit_code == 1
        assert "either a job name or --all" in result.output

    def test_run_all_fails_when_no_jobs(self):
        result = runner_cli.invoke(app, ["run", "--all"])
        assert result.exit_code == 1
        assert "No jobs scheduled" in result.output

    def test_run_all_runs_every_job(self, tmp_path):
        first = make_script(tmp_path, "first.sh")
        second = make_script(tmp_path, "second.sh")
        runner_cli.invoke(app, ["add", "first", str(first)])
        runner_cli.invoke(app, ["add", "second", str(second)])
        with patch("bashron.cli._run_single_job", side_effect=[0, 0]) as mock_run:
            result = runner_cli.invoke(app, ["run", "--all"])
        assert result.exit_code == 0
        assert mock_run.call_count == 2

    def test_run_all_returns_last_nonzero_exit_code(self, tmp_path):
        first = make_script(tmp_path, "first.sh")
        second = make_script(tmp_path, "second.sh")
        runner_cli.invoke(app, ["add", "first", str(first)])
        runner_cli.invoke(app, ["add", "second", str(second)])
        with patch("bashron.cli._run_single_job", side_effect=[0, 3]):
            result = runner_cli.invoke(app, ["run", "--all"])
        assert result.exit_code == 3


# ---------------------------------------------------------------------------
# logs
# ---------------------------------------------------------------------------

class TestLogs:
    def test_logs_no_log_file(self, tmp_path):
        result = runner_cli.invoke(app, ["logs", "nolog"])
        assert result.exit_code == 0
        assert "No log found" in result.output

    def test_logs_shows_tail(self, tmp_path):
        s = make_script(tmp_path)
        runner_cli.invoke(app, ["add", "logjob", str(s)])
        log = store.log_path("logjob")
        log.write_text("\n".join(f"line{i}" for i in range(100)))
        result = runner_cli.invoke(app, ["logs", "logjob", "--lines", "10"])
        assert result.exit_code == 0
        assert "line99" in result.output
        assert "line90" in result.output

    def test_logs_default_50_lines(self, tmp_path):
        s = make_script(tmp_path)
        runner_cli.invoke(app, ["add", "logjob2", str(s)])
        log = store.log_path("logjob2")
        log.write_text("\n".join(f"line{i}" for i in range(200)))
        result = runner_cli.invoke(app, ["logs", "logjob2"])
        assert result.exit_code == 0
        assert "last 50 lines" in result.output

    def test_logs_follow_uses_follow_helper(self):
        with patch("bashron.cli._follow_log") as mock_follow:
            result = runner_cli.invoke(app, ["logs", "logjob", "--follow", "--lines", "5"])
        assert result.exit_code == 0
        mock_follow.assert_called_once_with("logjob", 5)


# ---------------------------------------------------------------------------
# start
# ---------------------------------------------------------------------------

class TestStart:
    def test_start_with_no_scripts_exits(self):
        result = runner_cli.invoke(app, ["start"])
        assert result.exit_code == 0
        assert "No scripts scheduled" in result.output

    def test_start_registers_jobs_and_stops_on_keyboard_interrupt(self, tmp_path):
        s = make_script(tmp_path)
        runner_cli.invoke(app, ["add", "daemon-job", str(s), "--at", "03:00"])

        with patch("bashron.cli.schedule") as mock_schedule, \
             patch("bashron.cli.time.sleep", side_effect=KeyboardInterrupt):
            mock_schedule.every.return_value.day.at.return_value.do.return_value = None
            mock_schedule.run_pending.return_value = None
            result = runner_cli.invoke(app, ["start"])

        assert result.exit_code == 0
        assert "daemon started" in result.output
        assert "daemon-job" in result.output
        assert "log-cleanup" in result.output
        assert "daemon stopped" in result.output
        assert "warrior-class bash scheduling" in result.output

    def test_start_shows_configured_retention(self, tmp_path):
        s = make_script(tmp_path)
        runner_cli.invoke(app, ["add", "job", str(s), "--at", "01:00"])
        config.set_retention_days(14)

        with patch("bashron.cli.schedule") as mock_schedule, \
             patch("bashron.cli.time.sleep", side_effect=KeyboardInterrupt):
            mock_schedule.every.return_value.day.at.return_value.do.return_value = None
            mock_schedule.run_pending.return_value = None
            result = runner_cli.invoke(app, ["start"])

        assert "14" in result.output

    def test_start_schedules_hourly_job(self, tmp_path):
        s = make_script(tmp_path)
        runner_cli.invoke(app, ["add", "hjob", str(s), "--every", "hourly"])
        with patch("bashron.cli.schedule") as mock_schedule, \
             patch("bashron.cli.time.sleep", side_effect=KeyboardInterrupt):
            mock_schedule.every.return_value.hour.do.return_value = None
            mock_schedule.every.return_value.day.at.return_value.do.return_value = None
            mock_schedule.run_pending.return_value = None
            result = runner_cli.invoke(app, ["start", "--quiet"])
        assert result.exit_code == 0
        assert "every hour" in result.output

    def test_start_schedules_weekly_job(self, tmp_path):
        s = make_script(tmp_path)
        with patch("bashron.cli._has_time_passed_today", return_value=False):
            runner_cli.invoke(app, ["add", "wjob", str(s), "--every", "weekly", "--on", "friday"])
        with patch("bashron.cli.schedule") as mock_schedule, \
             patch("bashron.cli.time.sleep", side_effect=KeyboardInterrupt):
            mock_schedule.every.return_value.friday.at.return_value.do.return_value = None
            mock_schedule.every.return_value.day.at.return_value.do.return_value = None
            mock_schedule.run_pending.return_value = None
            result = runner_cli.invoke(app, ["start", "--quiet"])
        assert result.exit_code == 0
        assert "friday" in result.output

    def test_start_schedules_monthly_job(self, tmp_path):
        s = make_script(tmp_path)
        with patch("bashron.cli._has_time_passed_today", return_value=False):
            runner_cli.invoke(app, ["add", "mjob", str(s), "--every", "monthly", "--on", "5"])
        with patch("bashron.cli.schedule") as mock_schedule, \
             patch("bashron.cli.time.sleep", side_effect=KeyboardInterrupt):
            mock_schedule.every.return_value.day.at.return_value.do.return_value = None
            mock_schedule.run_pending.return_value = None
            result = runner_cli.invoke(app, ["start", "--quiet"])
        assert result.exit_code == 0
        assert "day 5 of month" in result.output

    def test_start_quiet_suppresses_banner(self, tmp_path):
        s = make_script(tmp_path)
        runner_cli.invoke(app, ["add", "job", str(s), "--at", "01:00"])

        with patch("bashron.cli.schedule") as mock_schedule, \
             patch("bashron.cli.time.sleep", side_effect=KeyboardInterrupt):
            mock_schedule.every.return_value.day.at.return_value.do.return_value = None
            mock_schedule.run_pending.return_value = None
            result = runner_cli.invoke(app, ["start", "--quiet"])

        assert result.exit_code == 0
        assert "warrior-class bash scheduling" not in result.output


# ---------------------------------------------------------------------------
# clean-logs
# ---------------------------------------------------------------------------

class TestCleanLogs:
    def test_no_old_logs(self):
        result = runner_cli.invoke(app, ["clean-logs"])
        assert result.exit_code == 0
        assert "No logs older" in result.output

    def test_deletes_old_logs(self):
        with patch("bashron.cli.cleaner.clean_logs", return_value=["stale.log"]):
            result = runner_cli.invoke(app, ["clean-logs"])
        assert result.exit_code == 0
        assert "stale.log" in result.output

    def test_uses_override_days(self):
        with patch("bashron.cli.cleaner.clean_logs", return_value=[]) as mock_clean:
            runner_cli.invoke(app, ["clean-logs", "--days", "3"])
        mock_clean.assert_called_once_with(3)

    def test_uses_configured_retention_when_no_override(self):
        config.set_retention_days(14)
        with patch("bashron.cli.cleaner.clean_logs", return_value=[]) as mock_clean:
            runner_cli.invoke(app, ["clean-logs"])
        mock_clean.assert_called_once_with(14)

    def test_shows_each_deleted_file(self):
        with patch("bashron.cli.cleaner.clean_logs", return_value=["a.log", "b.log"]):
            result = runner_cli.invoke(app, ["clean-logs"])
        assert "a.log" in result.output
        assert "b.log" in result.output
        assert "2 log file(s)" in result.output


# ---------------------------------------------------------------------------
# config sub-commands
# ---------------------------------------------------------------------------

class TestConfigCmd:
    def test_config_default_shows_settings(self):
        result = runner_cli.invoke(app, ["config"])
        assert result.exit_code == 0
        assert "log_retention_days" in result.output

    def test_config_set_retention_valid(self):
        result = runner_cli.invoke(app, ["config", "set-retention", "21"])
        assert result.exit_code == 0
        assert "21" in result.output
        assert config.get_retention_days() == 21

    def test_config_set_retention_invalid_fails(self):
        result = runner_cli.invoke(app, ["config", "set-retention", "0"])
        assert result.exit_code == 1
        assert "Error" in result.output


# ---------------------------------------------------------------------------
# cron sub-commands
# ---------------------------------------------------------------------------

class TestCronShow:
    def test_show_no_jobs(self):
        with patch("bashron.cli.cron.is_supported", return_value=True):
            result = runner_cli.invoke(app, ["cron", "show"])
        assert result.exit_code == 0
        assert "No jobs scheduled" in result.output

    def test_show_previews_entries(self, tmp_path):
        s = make_script(tmp_path)
        runner_cli.invoke(app, ["add", "preview-job", str(s), "--at", "07:00"])
        with patch("bashron.cli.cron.is_supported", return_value=True), \
             patch("bashron.cron.shutil.which", return_value="/bin/bashron"):
            result = runner_cli.invoke(app, ["cron", "show"])
        assert result.exit_code == 0
        assert "preview-job" in result.output

    def test_show_runtime_error_fails(self, tmp_path):
        s = make_script(tmp_path)
        runner_cli.invoke(app, ["add", "j", str(s)])
        with patch("bashron.cli.cron.is_supported", return_value=True), \
             patch("bashron.cli.cron.build_entries", side_effect=RuntimeError("no bin")):
            result = runner_cli.invoke(app, ["cron", "show"])
        assert result.exit_code == 1
        assert "Error" in result.output

    def test_show_windows_fails(self):
        with patch("bashron.cli.cron.is_supported", return_value=False):
            result = runner_cli.invoke(app, ["cron", "show"])
        assert result.exit_code == 1
        assert "Windows" in result.output


class TestCronInstall:
    def test_install_no_jobs(self):
        with patch("bashron.cli.cron.is_supported", return_value=True):
            result = runner_cli.invoke(app, ["cron", "install"])
        assert result.exit_code == 0
        assert "No jobs scheduled" in result.output

    def test_install_success(self, tmp_path):
        s = make_script(tmp_path)
        runner_cli.invoke(app, ["add", "inst-job", str(s), "--at", "06:00"])
        with patch("bashron.cli.cron.is_supported", return_value=True), \
             patch("bashron.cli.cron._read_crontab", return_value=""), \
             patch("bashron.cli.cron.install", return_value=[
                 "# >>> bashron managed >>>",
                 "0 6 * * * /bin/bashron run inst-job",
                 "# <<< bashron managed <<<",
             ]):
            result = runner_cli.invoke(app, ["cron", "install"])
        assert result.exit_code == 0
        assert "inst-job" in result.output
        assert "Crontab updated" in result.output

    def test_install_runtime_error_fails(self, tmp_path):
        s = make_script(tmp_path)
        runner_cli.invoke(app, ["add", "j", str(s)])
        with patch("bashron.cli.cron.is_supported", return_value=True), \
             patch("bashron.cli.cron._read_crontab", return_value=""), \
             patch("bashron.cli.cron.install", side_effect=RuntimeError("write failed")):
            result = runner_cli.invoke(app, ["cron", "install"])
        assert result.exit_code == 1
        assert "Error" in result.output

    def test_install_windows_fails(self):
        with patch("bashron.cli.cron.is_supported", return_value=False):
            result = runner_cli.invoke(app, ["cron", "install"])
        assert result.exit_code == 1

    def test_install_confirms_before_overwriting_existing_crontab(self, tmp_path):
        s = make_script(tmp_path)
        runner_cli.invoke(app, ["add", "inst-job", str(s)])
        with patch("bashron.cli.cron.is_supported", return_value=True), \
             patch("bashron.cli.cron._read_crontab", return_value="0 1 * * * echo hi\n"), \
             patch("typer.confirm", return_value=True) as mock_confirm, \
             patch("bashron.cli.cron.install", return_value=[]):
            result = runner_cli.invoke(app, ["cron", "install"])
        assert result.exit_code == 0
        mock_confirm.assert_called_once()

    def test_install_abort_when_confirmation_rejected(self, tmp_path):
        s = make_script(tmp_path)
        runner_cli.invoke(app, ["add", "inst-job", str(s)])
        with patch("bashron.cli.cron.is_supported", return_value=True), \
             patch("bashron.cli.cron._read_crontab", return_value="0 1 * * * echo hi\n"), \
             patch("typer.confirm", return_value=False), \
             patch("bashron.cli.cron.install") as mock_install:
            result = runner_cli.invoke(app, ["cron", "install"])
        assert result.exit_code == 1
        assert "Aborted" in result.output
        mock_install.assert_not_called()


class TestCronUninstall:
    def test_uninstall_found(self):
        with patch("bashron.cli.cron.is_supported", return_value=True), \
             patch("bashron.cli.cron.uninstall", return_value=True):
            result = runner_cli.invoke(app, ["cron", "uninstall"])
        assert result.exit_code == 0
        assert "Removed" in result.output

    def test_uninstall_nothing_found(self):
        with patch("bashron.cli.cron.is_supported", return_value=True), \
             patch("bashron.cli.cron.uninstall", return_value=False):
            result = runner_cli.invoke(app, ["cron", "uninstall"])
        assert result.exit_code == 0
        assert "No bashron entries" in result.output

    def test_uninstall_windows_fails(self):
        with patch("bashron.cli.cron.is_supported", return_value=False):
            result = runner_cli.invoke(app, ["cron", "uninstall"])
        assert result.exit_code == 1


class TestCronDefault:
    def test_cron_no_subcommand_shows_help(self):
        result = runner_cli.invoke(app, ["cron"])
        assert result.exit_code == 0
        assert "show" in result.output or "install" in result.output


# ---------------------------------------------------------------------------
# add — notify / webhook options
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# _is_url / _download_script helpers
# ---------------------------------------------------------------------------

class TestIsUrl:
    def test_https_is_url(self):
        assert cli._is_url("https://example.com/script.sh") is True

    def test_http_is_url(self):
        assert cli._is_url("http://example.com/script.sh") is True

    def test_local_path_is_not_url(self):
        assert cli._is_url("/home/user/script.sh") is False

    def test_tilde_path_is_not_url(self):
        assert cli._is_url("~/scripts/script.sh") is False


class TestDownloadScript:
    def test_downloads_and_saves_script(self):
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = b"#!/bin/bash\necho hi\n"
            dest = cli._download_script("https://example.com/hi.sh", "hi")
        assert dest.read_bytes() == b"#!/bin/bash\necho hi\n"
        assert oct(dest.stat().st_mode)[-3:] == "755"

    def test_raises_runtime_error_on_network_failure(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
            with pytest.raises(RuntimeError, match="Download failed"):
                cli._download_script("https://example.com/hi.sh", "hi")


# ---------------------------------------------------------------------------
# add — URL download
# ---------------------------------------------------------------------------

class TestAddUrl:
    def test_add_downloads_script_from_url(self, tmp_path):
        saved = tmp_path / "remote.sh"
        with patch("bashron.cli._download_script", return_value=saved), \
             patch("bashron.cli._has_time_passed_today", return_value=False):
            result = runner_cli.invoke(
                app, ["add", "remote", "https://example.com/remote.sh", "--at", "08:00"]
            )
        assert result.exit_code == 0
        assert "Downloading" in result.output
        assert "Saved" in result.output
        assert "Job added" in result.output

    def test_add_url_download_failure_exits(self):
        with patch("bashron.cli._is_url", return_value=True), \
             patch("bashron.cli._download_script", side_effect=RuntimeError("Download failed: timeout")):
            result = runner_cli.invoke(app, ["add", "remote", "https://example.com/remote.sh"])
        assert result.exit_code == 1
        assert "Error" in result.output


class TestAddFrequency:
    def test_add_hourly(self, tmp_path):
        s = make_script(tmp_path)
        result = runner_cli.invoke(app, ["add", "hj", str(s), "--every", "hourly"])
        assert result.exit_code == 0
        assert "every hour" in result.output
        assert store.load()[0]["frequency"] == "hourly"

    def test_add_daily_explicit(self, tmp_path):
        s = make_script(tmp_path)
        with patch("bashron.cli._has_time_passed_today", return_value=False):
            result = runner_cli.invoke(app, ["add", "dj", str(s), "--every", "daily", "--at", "09:00"])
        assert result.exit_code == 0
        assert "daily at 09:00" in result.output

    def test_add_weekly_default_monday(self, tmp_path):
        s = make_script(tmp_path)
        with patch("bashron.cli._has_time_passed_today", return_value=False):
            result = runner_cli.invoke(app, ["add", "wj", str(s), "--every", "weekly"])
        assert result.exit_code == 0
        assert "every monday" in result.output
        assert store.load()[0]["weekday"] == "monday"

    def test_add_weekly_custom_day(self, tmp_path):
        s = make_script(tmp_path)
        with patch("bashron.cli._has_time_passed_today", return_value=False):
            result = runner_cli.invoke(app, ["add", "wj", str(s), "--every", "weekly", "--on", "friday"])
        assert result.exit_code == 0
        assert store.load()[0]["weekday"] == "friday"

    def test_add_weekly_invalid_day_fails(self, tmp_path):
        s = make_script(tmp_path)
        result = runner_cli.invoke(app, ["add", "wj", str(s), "--every", "weekly", "--on", "funday"])
        assert result.exit_code == 1
        assert "Invalid weekday" in result.output

    def test_add_monthly_default_day_1(self, tmp_path):
        s = make_script(tmp_path)
        with patch("bashron.cli._has_time_passed_today", return_value=False):
            result = runner_cli.invoke(app, ["add", "mj", str(s), "--every", "monthly"])
        assert result.exit_code == 0
        assert "day 1 of every month" in result.output
        assert store.load()[0]["month_day"] == 1

    def test_add_monthly_custom_day(self, tmp_path):
        s = make_script(tmp_path)
        with patch("bashron.cli._has_time_passed_today", return_value=False):
            result = runner_cli.invoke(app, ["add", "mj", str(s), "--every", "monthly", "--on", "15"])
        assert result.exit_code == 0
        assert store.load()[0]["month_day"] == 15

    def test_add_monthly_invalid_day_zero_fails(self, tmp_path):
        s = make_script(tmp_path)
        result = runner_cli.invoke(app, ["add", "mj", str(s), "--every", "monthly", "--on", "0"])
        assert result.exit_code == 1
        assert "1 and 28" in result.output

    def test_add_monthly_invalid_day_29_fails(self, tmp_path):
        s = make_script(tmp_path)
        result = runner_cli.invoke(app, ["add", "mj", str(s), "--every", "monthly", "--on", "29"])
        assert result.exit_code == 1
        assert "1 and 28" in result.output

    def test_add_monthly_invalid_day_string_fails(self, tmp_path):
        s = make_script(tmp_path)
        result = runner_cli.invoke(app, ["add", "mj", str(s), "--every", "monthly", "--on", "abc"])
        assert result.exit_code == 1
        assert "1 and 28" in result.output

    def test_add_invalid_frequency_fails(self, tmp_path):
        s = make_script(tmp_path)
        result = runner_cli.invoke(app, ["add", "xj", str(s), "--every", "sometimes"])
        assert result.exit_code == 1
        assert "Invalid frequency" in result.output

    def test_add_hourly_skips_time_validation(self, tmp_path):
        s = make_script(tmp_path)
        # No _has_time_passed_today mock needed — hourly skips it entirely
        result = runner_cli.invoke(app, ["add", "hj", str(s), "--every", "hourly"])
        assert result.exit_code == 0


class TestAddNotifications:
    def test_add_with_notify_flag_stores_true(self, tmp_path):
        s = make_script(tmp_path)
        with patch("bashron.cli._has_time_passed_today", return_value=False):
            result = runner_cli.invoke(app, ["add", "notifyjob", str(s), "--notify"])
        assert result.exit_code == 0
        assert store.load()[0]["notify"] is True
        assert "notify on failure" in result.output

    def test_add_with_webhook_stores_url(self, tmp_path):
        s = make_script(tmp_path)
        with patch("bashron.cli._has_time_passed_today", return_value=False):
            result = runner_cli.invoke(
                app, ["add", "whjob", str(s), "--webhook", "https://hooks.example.com"]
            )
        assert result.exit_code == 0
        assert store.load()[0]["webhook"] == "https://hooks.example.com"
        assert "webhook" in result.output


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

class TestInit:
    def test_init_success(self, tmp_path):
        s = make_script(tmp_path)
        with patch("bashron.cli._has_time_passed_today", return_value=False):
            result = runner_cli.invoke(app, ["init"], input=f"myjob\n{s}\n08:00\n")
        assert result.exit_code == 0
        assert "Job added" in result.output

    def test_init_file_not_found(self):
        result = runner_cli.invoke(app, ["init"], input="myjob\n/nonexistent/path.sh\n08:00\n")
        assert result.exit_code == 1
        assert "File not found" in result.output

    def test_init_invalid_time(self, tmp_path):
        s = make_script(tmp_path)
        with patch("bashron.cli._has_time_passed_today", side_effect=ValueError("bad time")):
            result = runner_cli.invoke(app, ["init"], input=f"myjob\n{s}\n25:00\n")
        assert result.exit_code == 1
        assert "Invalid time" in result.output

    def test_init_duplicate_name_fails(self, tmp_path):
        s = make_script(tmp_path)
        with patch("bashron.cli._has_time_passed_today", return_value=False):
            runner_cli.invoke(app, ["init"], input=f"myjob\n{s}\n08:00\n")
            result = runner_cli.invoke(app, ["init"], input=f"myjob\n{s}\n08:00\n")
        assert result.exit_code == 1
        assert "Error" in result.output

    def test_init_shows_note_when_time_passed(self, tmp_path):
        s = make_script(tmp_path)
        with patch("bashron.cli._has_time_passed_today", return_value=True):
            result = runner_cli.invoke(app, ["init"], input=f"myjob\n{s}\n01:00\n")
        assert result.exit_code == 0
        assert "tomorrow" in result.output


# ---------------------------------------------------------------------------
# new
# ---------------------------------------------------------------------------

class TestNew:
    def test_new_creates_script_and_schedules_job(self, tmp_path):
        result = runner_cli.invoke(app, ["new", "myjob", "--dir", str(tmp_path), "--at", "09:00"])
        assert result.exit_code == 0
        assert "Created" in result.output
        assert "Ready" in result.output
        assert (tmp_path / "myjob.sh").exists()
        assert store.load()[0]["name"] == "myjob"

    def test_new_skips_creation_when_script_exists(self, tmp_path):
        existing = tmp_path / "myjob.sh"
        existing.write_text("#!/bin/bash\necho existing\n")
        result = runner_cli.invoke(app, ["new", "myjob", "--dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "already exists" in result.output
        assert existing.read_text() == "#!/bin/bash\necho existing\n"

    def test_new_duplicate_name_fails(self, tmp_path):
        runner_cli.invoke(app, ["new", "myjob", "--dir", str(tmp_path)])
        result = runner_cli.invoke(app, ["new", "myjob", "--dir", str(tmp_path)])
        assert result.exit_code == 1
        assert "Error" in result.output


# ---------------------------------------------------------------------------
# status (job dashboard)
# ---------------------------------------------------------------------------

class TestStatusCmd:
    def test_status_no_jobs(self):
        result = runner_cli.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "No scripts scheduled" in result.output

    def test_status_shows_job_never_run(self, tmp_path):
        s = make_script(tmp_path)
        runner_cli.invoke(app, ["add", "myjob", str(s), "--at", "08:00"])
        result = runner_cli.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "myjob" in result.output
        assert "never" in result.output

    def test_status_shows_last_run_and_exit_zero(self, tmp_path):
        s = make_script(tmp_path)
        runner_cli.invoke(app, ["add", "myjob", str(s), "--at", "08:00"])
        log = store.log_path("myjob")
        log.write_text(
            "[2026-04-09 10:00:00] Running: /tmp/myjob.sh\n"
            "hello\n"
            "[2026-04-09 10:00:01] Exit code: 0\n"
        )
        result = runner_cli.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "2026-04-09 10:00:00" in result.output

    def test_status_shows_failed_exit_code(self, tmp_path):
        s = make_script(tmp_path)
        runner_cli.invoke(app, ["add", "myjob", str(s), "--at", "08:00"])
        log = store.log_path("myjob")
        log.write_text(
            "[2026-04-09 10:00:00] Running: /tmp/myjob.sh\n"
            "[2026-04-09 10:00:01] Exit code: 2\n"
        )
        result = runner_cli.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "2" in result.output


# ---------------------------------------------------------------------------
# _parse_log_status / _next_run_str helpers
# ---------------------------------------------------------------------------

class TestParseLogStatus:
    def test_returns_never_when_no_log(self):
        last_run, exit_code = cli._parse_log_status("missing")
        assert last_run == "never"
        assert exit_code == "\u2014"

    def test_parses_timestamp_and_exit_code(self):
        log = store.log_path("job")
        log.write_text(
            "[2026-04-09 09:00:00] Running: /tmp/job.sh\n"
            "output\n"
            "[2026-04-09 09:00:01] Exit code: 0\n"
            "[2026-04-09 10:00:00] Running: /tmp/job.sh\n"
            "output2\n"
        )
        last_run, exit_code = cli._parse_log_status("job")
        assert last_run == "2026-04-09 10:00:00"
        assert exit_code == "0"

    def test_returns_never_when_log_has_no_running_line(self):
        log = store.log_path("job")
        log.write_text("some output without a Running line\n")
        last_run, exit_code = cli._parse_log_status("job")
        assert last_run == "never"
        assert exit_code == "\u2014"


class TestRunIfMonthDay:
    def test_runs_when_day_matches(self):
        entry = {"name": "job", "path": "/tmp/job.sh"}
        now = datetime(2026, 4, 1, 10, 0, 0)
        with patch("bashron.cli.runner.run_script") as mock_run:
            cli._run_if_month_day(entry, 1, now=now)
        mock_run.assert_called_once_with(entry)

    def test_does_not_run_when_day_does_not_match(self):
        entry = {"name": "job", "path": "/tmp/job.sh"}
        now = datetime(2026, 4, 9, 10, 0, 0)
        with patch("bashron.cli.runner.run_script") as mock_run:
            cli._run_if_month_day(entry, 1, now=now)
        mock_run.assert_not_called()


class TestNextRunStr:
    def test_daily_returns_hours_and_minutes_when_future_today(self):
        now = datetime(2026, 4, 9, 10, 0, 0)
        entry = {"run_at": "15:00", "frequency": "daily"}
        result = cli._next_run_str(entry, now)
        assert "15:00" in result
        assert "in 5h" in result

    def test_daily_returns_only_minutes_when_less_than_one_hour(self):
        now = datetime(2026, 4, 9, 10, 0, 0)
        entry = {"run_at": "10:30", "frequency": "daily"}
        result = cli._next_run_str(entry, now)
        assert "in 30m" in result
        assert "h" not in result.split("in")[1]

    def test_daily_wraps_to_next_day_when_time_passed(self):
        now = datetime(2026, 4, 9, 10, 0, 0)
        entry = {"run_at": "08:00", "frequency": "daily"}
        result = cli._next_run_str(entry, now)
        assert "08:00" in result
        assert "in" in result

    def test_daily_defaults_when_frequency_missing(self):
        now = datetime(2026, 4, 9, 10, 0, 0)
        entry = {"run_at": "15:00"}
        result = cli._next_run_str(entry, now)
        assert "15:00" in result

    def test_hourly_shows_minutes_until_next_hour(self):
        now = datetime(2026, 4, 9, 10, 15, 0)
        entry = {"run_at": "08:00", "frequency": "hourly"}
        result = cli._next_run_str(entry, now)
        assert "every hour" in result
        assert "in 45m" in result

    def test_weekly_shows_days_and_hours(self):
        # Monday 2026-04-13; now is Thursday 2026-04-09
        now = datetime(2026, 4, 9, 10, 0, 0)  # Thursday
        entry = {"run_at": "09:00", "frequency": "weekly", "weekday": "monday"}
        result = cli._next_run_str(entry, now)
        assert "monday" in result
        assert "in" in result

    def test_weekly_wraps_when_scheduled_time_passed_same_day(self):
        # now is Monday 10:00, scheduled Monday 08:00 — already passed → next Monday
        now = datetime(2026, 4, 13, 10, 0, 0)  # Monday
        entry = {"run_at": "08:00", "frequency": "weekly", "weekday": "monday"}
        result = cli._next_run_str(entry, now)
        assert "monday" in result
        assert "7d" in result or "6d" in result  # at least 6 days away

    def test_monthly_shows_days_until_next_occurrence(self):
        now = datetime(2026, 4, 9, 10, 0, 0)
        entry = {"run_at": "08:00", "frequency": "monthly", "month_day": 20}
        result = cli._next_run_str(entry, now)
        assert "day 20" in result
        assert "in" in result

    def test_monthly_wraps_to_next_month_when_day_passed(self):
        now = datetime(2026, 4, 9, 10, 0, 0)
        entry = {"run_at": "08:00", "frequency": "monthly", "month_day": 1}
        result = cli._next_run_str(entry, now)
        assert "day 1" in result
        assert "in" in result

    def test_monthly_wraps_to_next_year_in_december(self):
        now = datetime(2026, 12, 15, 10, 0, 0)
        entry = {"run_at": "08:00", "frequency": "monthly", "month_day": 1}
        result = cli._next_run_str(entry, now)
        assert "day 1" in result


# ---------------------------------------------------------------------------
# export / import
# ---------------------------------------------------------------------------

class TestExport:
    def test_export_prints_to_stdout_when_no_output_arg(self, tmp_path):
        s = make_script(tmp_path)
        runner_cli.invoke(app, ["add", "job1", str(s), "--at", "08:00"])
        result = runner_cli.invoke(app, ["export"])
        assert result.exit_code == 0
        assert '"name": "job1"' in result.output

    def test_export_writes_to_file_when_output_arg_given(self, tmp_path):
        s = make_script(tmp_path)
        runner_cli.invoke(app, ["add", "job1", str(s), "--at", "08:00"])
        out = tmp_path / "export.json"
        result = runner_cli.invoke(app, ["export", str(out)])
        assert result.exit_code == 0
        assert "Exported" in result.output
        assert out.exists()
        import json
        data = json.loads(out.read_text())
        assert data[0]["name"] == "job1"

    def test_export_empty_store_prints_empty_list(self):
        result = runner_cli.invoke(app, ["export"])
        assert result.exit_code == 0
        assert "[]" in result.output


class TestImportJobs:
    def test_import_merges_new_jobs(self, tmp_path):
        import json
        source = tmp_path / "bashronfile.json"
        source.write_text(json.dumps([
            {"name": "imported", "path": "/tmp/x.sh", "run_at": "09:00"}
        ]))
        result = runner_cli.invoke(app, ["import", str(source)])
        assert result.exit_code == 0
        assert "Imported" in result.output
        assert store.load()[0]["name"] == "imported"

    def test_import_skips_duplicates(self, tmp_path):
        import json
        s = make_script(tmp_path)
        runner_cli.invoke(app, ["add", "dup", str(s), "--at", "08:00"])
        source = tmp_path / "bashronfile.json"
        source.write_text(json.dumps([{"name": "dup", "path": str(s), "run_at": "08:00"}]))
        result = runner_cli.invoke(app, ["import", str(source)])
        assert result.exit_code == 0
        assert "Skipped" in result.output
        assert "1 duplicate" in result.output

    def test_import_overwrite_replaces_all_existing(self, tmp_path):
        import json
        s = make_script(tmp_path)
        runner_cli.invoke(app, ["add", "old", str(s), "--at", "07:00"])
        source = tmp_path / "bashronfile.json"
        source.write_text(json.dumps([{"name": "new", "path": str(s), "run_at": "09:00"}]))
        result = runner_cli.invoke(app, ["import", str(source), "--overwrite"])
        assert result.exit_code == 0
        assert "replaced" in result.output.lower()
        jobs = store.load()
        assert len(jobs) == 1
        assert jobs[0]["name"] == "new"

    def test_import_file_not_found(self):
        result = runner_cli.invoke(app, ["import", "/nonexistent/file.json"])
        assert result.exit_code == 1
        assert "File not found" in result.output

    def test_import_invalid_json_fails(self, tmp_path):
        source = tmp_path / "bad.json"
        source.write_text("not valid json {{")
        result = runner_cli.invoke(app, ["import", str(source)])
        assert result.exit_code == 1
        assert "Invalid JSON" in result.output

    def test_import_non_list_json_fails(self, tmp_path):
        import json
        source = tmp_path / "bad.json"
        source.write_text(json.dumps({"name": "job"}))
        result = runner_cli.invoke(app, ["import", str(source)])
        assert result.exit_code == 1
        assert "JSON array" in result.output


# ---------------------------------------------------------------------------
# service sub-commands
# ---------------------------------------------------------------------------

class TestServiceInstall:
    def test_install_success(self):
        with patch("bashron.cli.service.is_supported", return_value=True), \
             patch("bashron.cli.service.install", return_value="/path/to/com.bashron.plist"):
            result = runner_cli.invoke(app, ["service", "install"])
        assert result.exit_code == 0
        assert "installed" in result.output.lower()
        assert "/path/to/com.bashron.plist" in result.output

    def test_install_runtime_error(self):
        with patch("bashron.cli.service.is_supported", return_value=True), \
             patch("bashron.cli.service.install", side_effect=RuntimeError("failed")):
            result = runner_cli.invoke(app, ["service", "install"])
        assert result.exit_code == 1
        assert "Error" in result.output

    def test_install_unsupported_os_fails(self):
        with patch("bashron.cli.service.is_supported", return_value=False):
            result = runner_cli.invoke(app, ["service", "install"])
        assert result.exit_code == 1
        assert "only supported" in result.output


class TestServiceStatus:
    def test_status_not_installed(self):
        with patch("bashron.cli.service.is_supported", return_value=True), \
             patch("bashron.cli.service.get_status", return_value=None):
            result = runner_cli.invoke(app, ["service", "status"])
        assert result.exit_code == 0
        assert "not installed" in result.output.lower()

    def test_status_installed_with_output(self):
        with patch("bashron.cli.service.is_supported", return_value=True), \
             patch("bashron.cli.service.get_status", return_value="active (running)"):
            result = runner_cli.invoke(app, ["service", "status"])
        assert result.exit_code == 0
        assert "active (running)" in result.output

    def test_status_installed_empty_output_shows_running(self):
        with patch("bashron.cli.service.is_supported", return_value=True), \
             patch("bashron.cli.service.get_status", return_value=""):
            result = runner_cli.invoke(app, ["service", "status"])
        assert result.exit_code == 0
        assert "running" in result.output

    def test_status_unsupported_os_fails(self):
        with patch("bashron.cli.service.is_supported", return_value=False):
            result = runner_cli.invoke(app, ["service", "status"])
        assert result.exit_code == 1


class TestServiceUninstall:
    def test_uninstall_found(self):
        with patch("bashron.cli.service.is_supported", return_value=True), \
             patch("bashron.cli.service.uninstall", return_value=True):
            result = runner_cli.invoke(app, ["service", "uninstall"])
        assert result.exit_code == 0
        assert "uninstalled" in result.output.lower()

    def test_uninstall_not_found(self):
        with patch("bashron.cli.service.is_supported", return_value=True), \
             patch("bashron.cli.service.uninstall", return_value=False):
            result = runner_cli.invoke(app, ["service", "uninstall"])
        assert result.exit_code == 0
        assert "No service" in result.output

    def test_uninstall_unsupported_os_fails(self):
        with patch("bashron.cli.service.is_supported", return_value=False):
            result = runner_cli.invoke(app, ["service", "uninstall"])
        assert result.exit_code == 1


class TestServiceDefault:
    def test_no_subcommand_shows_help(self):
        result = runner_cli.invoke(app, ["service"])
        assert result.exit_code == 0
        assert "install" in result.output or "status" in result.output
