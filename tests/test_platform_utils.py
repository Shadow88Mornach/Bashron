"""Tests for bashron.platform_utils — 100% branch coverage."""

from pathlib import Path
from unittest.mock import patch

import bashron.platform_utils as pu


class TestGetOs:
    def test_returns_platform_system(self):
        with patch("platform.system", return_value="Linux"):
            assert pu.get_os() == "Linux"


class TestIsSupportedOs:
    def test_windows_supported(self):
        with patch("bashron.platform_utils.get_os", return_value="Windows"):
            assert pu.is_supported_os() is True

    def test_linux_supported(self):
        with patch("bashron.platform_utils.get_os", return_value="Linux"):
            assert pu.is_supported_os() is True

    def test_darwin_supported(self):
        with patch("bashron.platform_utils.get_os", return_value="Darwin"):
            assert pu.is_supported_os() is True

    def test_unknown_os_not_supported(self):
        with patch("bashron.platform_utils.get_os", return_value="FreeBSD"):
            assert pu.is_supported_os() is False


class TestFindBash:
    def test_returns_path_when_found_in_path(self):
        with patch("shutil.which", return_value="/bin/bash"):
            assert pu.find_bash() == "/bin/bash"

    def test_returns_none_on_non_windows_when_not_in_path(self):
        with patch("shutil.which", return_value=None), \
             patch("bashron.platform_utils.get_os", return_value="Linux"):
            assert pu.find_bash() is None

    def test_windows_falls_back_to_candidate_files(self, tmp_path):
        fake_bash = tmp_path / "bash.exe"
        fake_bash.touch()

        fake_candidates = [tmp_path / "missing.exe", fake_bash]
        with patch("shutil.which", return_value=None), \
             patch("bashron.platform_utils.get_os", return_value="Windows"), \
             patch("bashron.platform_utils._WINDOWS_BASH_CANDIDATES", fake_candidates):
            result = pu.find_bash()
        assert result == str(fake_bash)

    def test_windows_returns_none_when_no_candidate_exists(self, tmp_path):
        fake_candidates = [tmp_path / "nope1.exe", tmp_path / "nope2.exe"]
        with patch("shutil.which", return_value=None), \
             patch("bashron.platform_utils.get_os", return_value="Windows"), \
             patch("bashron.platform_utils._WINDOWS_BASH_CANDIDATES", fake_candidates):
            assert pu.find_bash() is None


class TestBashInstallHint:
    def test_windows_hint(self):
        with patch("bashron.platform_utils.get_os", return_value="Windows"):
            hint = pu.bash_install_hint()
        assert "Git for Windows" in hint
        assert "WSL" in hint
        assert "Cygwin" in hint

    def test_linux_hint(self):
        with patch("bashron.platform_utils.get_os", return_value="Linux"):
            hint = pu.bash_install_hint()
        assert "apt install bash" in hint

    def test_darwin_hint(self):
        with patch("bashron.platform_utils.get_os", return_value="Darwin"):
            hint = pu.bash_install_hint()
        assert "brew install bash" in hint


class TestPythonVersion:
    def test_returns_string(self):
        version = pu.python_version()
        assert isinstance(version, str)
        # e.g. "3.11.4"
        parts = version.split(".")
        assert len(parts) >= 2
        assert parts[0].isdigit()
