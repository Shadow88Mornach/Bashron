"""Tests for bashron.service — 100% branch coverage."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import bashron.service as service


class TestHelpers:
    def test_launchd_plist_path_name(self):
        assert service._launchd_plist_path().name == "com.bashron.plist"

    def test_systemd_unit_path_name(self):
        assert service._systemd_unit_path().name == "bashron.service"

    def test_bashron_bin_uses_which_when_found(self):
        with patch("bashron.service.shutil.which", return_value="/usr/local/bin/bashron"):
            assert service._bashron_bin() == "/usr/local/bin/bashron"

    def test_bashron_bin_falls_back_to_python(self):
        with patch("bashron.service.shutil.which", return_value=None), \
             patch("bashron.service.sys.executable", "/usr/bin/python3"):
            result = service._bashron_bin()
        assert result == "/usr/bin/python3 -m bashron.cli"

    def test_launchd_plist_contains_label_and_bin(self):
        plist = service._launchd_plist("/usr/bin/bashron")
        assert "com.bashron" in plist
        assert "/usr/bin/bashron" in plist
        assert "start" in plist

    def test_systemd_unit_contains_exec_and_description(self):
        unit = service._systemd_unit("/usr/bin/bashron")
        assert "/usr/bin/bashron start --quiet" in unit
        assert "Description=" in unit
        assert "WantedBy=default.target" in unit


class TestIsSupported:
    def test_darwin_is_supported(self):
        with patch("bashron.service.get_os", return_value="Darwin"):
            assert service.is_supported() is True

    def test_linux_is_supported(self):
        with patch("bashron.service.get_os", return_value="Linux"):
            assert service.is_supported() is True

    def test_windows_is_not_supported(self):
        with patch("bashron.service.get_os", return_value="Windows"):
            assert service.is_supported() is False


class TestInstall:
    def test_darwin_writes_plist_and_calls_launchctl(self, tmp_path):
        plist_path = tmp_path / "com.bashron.plist"
        with patch("bashron.service.get_os", return_value="Darwin"), \
             patch("bashron.service._launchd_plist_path", return_value=plist_path), \
             patch("bashron.service._bashron_bin", return_value="/bin/bashron"), \
             patch("subprocess.run") as mock_run:
            result = service.install()
        assert result == str(plist_path)
        assert plist_path.exists()
        assert "com.bashron" in plist_path.read_text()
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0][0] == "launchctl"

    def test_linux_writes_unit_and_calls_systemctl(self, tmp_path):
        unit_path = tmp_path / "bashron.service"
        with patch("bashron.service.get_os", return_value="Linux"), \
             patch("bashron.service._systemd_unit_path", return_value=unit_path), \
             patch("bashron.service._bashron_bin", return_value="/bin/bashron"), \
             patch("subprocess.run") as mock_run:
            result = service.install()
        assert result == str(unit_path)
        assert unit_path.exists()
        assert mock_run.call_count == 2

    def test_unsupported_os_raises_runtime_error(self):
        with patch("bashron.service.get_os", return_value="FreeBSD"), \
             patch("bashron.service._bashron_bin", return_value="/bin/bashron"):
            with pytest.raises(RuntimeError, match="not supported"):
                service.install()


class TestUninstall:
    def test_darwin_uninstalls_existing_plist(self, tmp_path):
        plist_path = tmp_path / "com.bashron.plist"
        plist_path.write_text("plist content")
        with patch("bashron.service.get_os", return_value="Darwin"), \
             patch("bashron.service._launchd_plist_path", return_value=plist_path), \
             patch("subprocess.run") as mock_run:
            result = service.uninstall()
        assert result is True
        assert not plist_path.exists()
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0][0] == "launchctl"

    def test_darwin_returns_false_when_plist_missing(self, tmp_path):
        plist_path = tmp_path / "com.bashron.plist"
        with patch("bashron.service.get_os", return_value="Darwin"), \
             patch("bashron.service._launchd_plist_path", return_value=plist_path):
            result = service.uninstall()
        assert result is False

    def test_linux_uninstalls_existing_unit(self, tmp_path):
        unit_path = tmp_path / "bashron.service"
        unit_path.write_text("unit content")
        with patch("bashron.service.get_os", return_value="Linux"), \
             patch("bashron.service._systemd_unit_path", return_value=unit_path), \
             patch("subprocess.run") as mock_run:
            result = service.uninstall()
        assert result is True
        assert not unit_path.exists()
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0][0] == "systemctl"

    def test_linux_returns_false_when_unit_missing(self, tmp_path):
        unit_path = tmp_path / "bashron.service"
        with patch("bashron.service.get_os", return_value="Linux"), \
             patch("bashron.service._systemd_unit_path", return_value=unit_path):
            result = service.uninstall()
        assert result is False

    def test_other_os_returns_false(self):
        with patch("bashron.service.get_os", return_value="Windows"):
            result = service.uninstall()
        assert result is False


class TestGetStatus:
    def test_darwin_not_installed_returns_none(self, tmp_path):
        plist_path = tmp_path / "com.bashron.plist"
        with patch("bashron.service.get_os", return_value="Darwin"), \
             patch("bashron.service._launchd_plist_path", return_value=plist_path):
            result = service.get_status()
        assert result is None

    def test_darwin_installed_returns_stdout(self, tmp_path):
        plist_path = tmp_path / "com.bashron.plist"
        plist_path.write_text("plist")
        mock_result = MagicMock(stdout="running\n", stderr="")
        with patch("bashron.service.get_os", return_value="Darwin"), \
             patch("bashron.service._launchd_plist_path", return_value=plist_path), \
             patch("subprocess.run", return_value=mock_result):
            result = service.get_status()
        assert result == "running"

    def test_darwin_installed_returns_stderr_when_stdout_empty(self, tmp_path):
        plist_path = tmp_path / "com.bashron.plist"
        plist_path.write_text("plist")
        mock_result = MagicMock(stdout="", stderr="not loaded")
        with patch("bashron.service.get_os", return_value="Darwin"), \
             patch("bashron.service._launchd_plist_path", return_value=plist_path), \
             patch("subprocess.run", return_value=mock_result):
            result = service.get_status()
        assert result == "not loaded"

    def test_linux_not_installed_returns_none(self, tmp_path):
        unit_path = tmp_path / "bashron.service"
        with patch("bashron.service.get_os", return_value="Linux"), \
             patch("bashron.service._systemd_unit_path", return_value=unit_path):
            result = service.get_status()
        assert result is None

    def test_linux_installed_returns_stdout(self, tmp_path):
        unit_path = tmp_path / "bashron.service"
        unit_path.write_text("unit")
        mock_result = MagicMock(stdout="active (running)\n", stderr="")
        with patch("bashron.service.get_os", return_value="Linux"), \
             patch("bashron.service._systemd_unit_path", return_value=unit_path), \
             patch("subprocess.run", return_value=mock_result):
            result = service.get_status()
        assert result == "active (running)"

    def test_linux_installed_returns_stderr_when_stdout_empty(self, tmp_path):
        unit_path = tmp_path / "bashron.service"
        unit_path.write_text("unit")
        mock_result = MagicMock(stdout="", stderr="inactive")
        with patch("bashron.service.get_os", return_value="Linux"), \
             patch("bashron.service._systemd_unit_path", return_value=unit_path), \
             patch("subprocess.run", return_value=mock_result):
            result = service.get_status()
        assert result == "inactive"

    def test_other_os_returns_none(self):
        with patch("bashron.service.get_os", return_value="Windows"):
            result = service.get_status()
        assert result is None
