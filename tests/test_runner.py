"""Tests for bashron.runner — 100% branch coverage."""

from unittest.mock import MagicMock, patch

import pytest

import bashron.store as store
import bashron.runner as runner


# ---------------------------------------------------------------------------
# _notify_failure
# ---------------------------------------------------------------------------

class TestNotifyFailure:
    def test_calls_osascript_on_darwin(self):
        with patch("bashron.runner.platform.system", return_value="Darwin"), \
             patch("bashron.runner.subprocess.run") as mock_run:
            runner._notify_failure("myjob", 1)
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "osascript"
        assert "myjob" in cmd[2]

    def test_does_nothing_on_non_darwin(self):
        with patch("bashron.runner.platform.system", return_value="Linux"), \
             patch("bashron.runner.subprocess.run") as mock_run:
            runner._notify_failure("myjob", 1)
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# _send_webhook
# ---------------------------------------------------------------------------

class TestSendWebhook:
    def test_sends_post_request(self):
        mock_response = MagicMock()
        with patch("bashron.runner.urllib.request.urlopen", return_value=mock_response) as mock_open:
            runner._send_webhook("https://hooks.example.com/test", "myjob", 1)
        mock_open.assert_called_once()

    def test_silently_ignores_network_errors(self):
        with patch("bashron.runner.urllib.request.urlopen", side_effect=Exception("network error")):
            # Must not raise
            runner._send_webhook("https://hooks.example.com/test", "myjob", 1)


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    config_dir = tmp_path / ".bashron"
    log_dir = config_dir / "logs"
    monkeypatch.setattr(store, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(store, "DB_FILE", config_dir / "scripts.json")
    monkeypatch.setattr(store, "LOG_DIR", log_dir)


class TestRunScript:
    def _entry(self, tmp_path, name="job"):
        script = tmp_path / f"{name}.sh"
        script.write_text("#!/bin/bash\necho hello\n")
        return {"name": name, "path": str(script)}

    # -- bash not found branch -------------------------------------------------

    def test_returns_127_when_bash_not_found(self, tmp_path):
        entry = self._entry(tmp_path)
        with patch("bashron.runner.find_bash", return_value=None):
            code = runner.run_script(entry)
        assert code == 127

    def test_writes_error_to_log_when_bash_not_found(self, tmp_path):
        entry = self._entry(tmp_path)
        with patch("bashron.runner.find_bash", return_value=None):
            runner.run_script(entry)
        log = store.log_path(entry["name"])
        assert "bash executable not found" in log.read_text()

    # -- normal execution branches ---------------------------------------------

    def test_returns_zero_on_success(self, tmp_path):
        entry = self._entry(tmp_path)
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("bashron.runner.find_bash", return_value="/bin/bash"), \
             patch("subprocess.run", return_value=mock_result) as mock_run:
            code = runner.run_script(entry)
        assert code == 0
        mock_run.assert_called_once()

    def test_returns_nonzero_on_failure(self, tmp_path):
        entry = self._entry(tmp_path)
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch("bashron.runner.find_bash", return_value="/bin/bash"), \
             patch("subprocess.run", return_value=mock_result):
            code = runner.run_script(entry)
        assert code == 1

    def test_log_file_is_written(self, tmp_path):
        entry = self._entry(tmp_path)
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("bashron.runner.find_bash", return_value="/bin/bash"), \
             patch("subprocess.run", return_value=mock_result):
            runner.run_script(entry)
        log = store.log_path(entry["name"])
        assert log.exists()
        content = log.read_text()
        assert "Running:" in content
        assert "Exit code: 0" in content

    def test_log_appends_on_multiple_runs(self, tmp_path):
        entry = self._entry(tmp_path)
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("bashron.runner.find_bash", return_value="/bin/bash"), \
             patch("subprocess.run", return_value=mock_result):
            runner.run_script(entry)
            runner.run_script(entry)
        content = store.log_path(entry["name"]).read_text()
        assert content.count("Running:") == 2

    def test_subprocess_called_with_found_bash_and_script_path(self, tmp_path):
        entry = self._entry(tmp_path)
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("bashron.runner.find_bash", return_value="/usr/local/bin/bash"), \
             patch("subprocess.run", return_value=mock_result) as mock_run:
            runner.run_script(entry)
        args, kwargs = mock_run.call_args
        assert args[0] == ["/usr/local/bin/bash", entry["path"]]
        assert kwargs["text"] is True


# ---------------------------------------------------------------------------
# run_script — notification integration
# ---------------------------------------------------------------------------

class TestRunScriptNotifications:
    def _entry(self, tmp_path, name="job", notify=False, webhook=""):
        script = tmp_path / f"{name}.sh"
        script.write_text("#!/bin/bash\necho hello\n")
        return {"name": name, "path": str(script), "notify": notify, "webhook": webhook}

    def test_notifies_on_failure_when_notify_true(self, tmp_path):
        entry = self._entry(tmp_path, notify=True)
        mock_result = MagicMock(returncode=1)
        with patch("bashron.runner.find_bash", return_value="/bin/bash"), \
             patch("subprocess.run", return_value=mock_result), \
             patch("bashron.runner._notify_failure") as mock_notify:
            runner.run_script(entry)
        mock_notify.assert_called_once_with("job", 1)

    def test_no_notify_on_success_even_when_notify_true(self, tmp_path):
        entry = self._entry(tmp_path, notify=True)
        mock_result = MagicMock(returncode=0)
        with patch("bashron.runner.find_bash", return_value="/bin/bash"), \
             patch("subprocess.run", return_value=mock_result), \
             patch("bashron.runner._notify_failure") as mock_notify:
            runner.run_script(entry)
        mock_notify.assert_not_called()

    def test_no_notify_when_notify_is_false(self, tmp_path):
        entry = self._entry(tmp_path, notify=False)
        mock_result = MagicMock(returncode=1)
        with patch("bashron.runner.find_bash", return_value="/bin/bash"), \
             patch("subprocess.run", return_value=mock_result), \
             patch("bashron.runner._notify_failure") as mock_notify:
            runner.run_script(entry)
        mock_notify.assert_not_called()

    def test_sends_webhook_on_failure(self, tmp_path):
        entry = self._entry(tmp_path, webhook="https://hooks.example.com")
        mock_result = MagicMock(returncode=1)
        with patch("bashron.runner.find_bash", return_value="/bin/bash"), \
             patch("subprocess.run", return_value=mock_result), \
             patch("bashron.runner._send_webhook") as mock_webhook:
            runner.run_script(entry)
        mock_webhook.assert_called_once_with("https://hooks.example.com", "job", 1)

    def test_no_webhook_on_success(self, tmp_path):
        entry = self._entry(tmp_path, webhook="https://hooks.example.com")
        mock_result = MagicMock(returncode=0)
        with patch("bashron.runner.find_bash", return_value="/bin/bash"), \
             patch("subprocess.run", return_value=mock_result), \
             patch("bashron.runner._send_webhook") as mock_webhook:
            runner.run_script(entry)
        mock_webhook.assert_not_called()

    def test_no_webhook_when_webhook_not_configured(self, tmp_path):
        entry = self._entry(tmp_path, webhook="")
        mock_result = MagicMock(returncode=1)
        with patch("bashron.runner.find_bash", return_value="/bin/bash"), \
             patch("subprocess.run", return_value=mock_result), \
             patch("bashron.runner._send_webhook") as mock_webhook:
            runner.run_script(entry)
        mock_webhook.assert_not_called()
