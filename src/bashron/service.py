"""Manage bashron as a background service (launchd on macOS, systemd on Linux)."""

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from .platform_utils import get_os


def _launchd_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / "com.bashron.plist"


def _systemd_unit_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / "bashron.service"


def _bashron_bin() -> str:
    """Return the bashron executable, falling back to python -m invocation."""
    found = shutil.which("bashron")
    if found:
        return found
    return f"{sys.executable} -m bashron.cli"


def _launchd_plist(bashron_bin: str) -> str:
    log = Path.home() / ".bashron" / "service.log"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"\n'
        '    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        "<dict>\n"
        "    <key>Label</key>\n"
        "    <string>com.bashron</string>\n"
        "    <key>ProgramArguments</key>\n"
        "    <array>\n"
        f"        <string>{bashron_bin}</string>\n"
        "        <string>start</string>\n"
        "        <string>--quiet</string>\n"
        "    </array>\n"
        "    <key>RunAtLoad</key>\n"
        "    <true/>\n"
        "    <key>KeepAlive</key>\n"
        "    <true/>\n"
        "    <key>StandardOutPath</key>\n"
        f"    <string>{log}</string>\n"
        "    <key>StandardErrorPath</key>\n"
        f"    <string>{log}</string>\n"
        "</dict>\n"
        "</plist>"
    )


def _systemd_unit(bashron_bin: str) -> str:
    return (
        "[Unit]\n"
        "Description=bashron \u2014 warrior-class bash script scheduler\n"
        "After=network.target\n"
        "\n"
        "[Service]\n"
        f"ExecStart={bashron_bin} start --quiet\n"
        "Restart=always\n"
        "RestartSec=10\n"
        "\n"
        "[Install]\n"
        "WantedBy=default.target"
    )


def is_supported() -> bool:
    """Return True on macOS and Linux."""
    return get_os() in {"Darwin", "Linux"}


def install() -> str:
    """Install bashron as a background service. Returns the service file path."""
    os_name = get_os()
    bashron_bin = _bashron_bin()

    if os_name == "Darwin":
        plist_path = _launchd_plist_path()
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        plist_path.write_text(_launchd_plist(bashron_bin))
        subprocess.run(["launchctl", "load", str(plist_path)], check=False)
        return str(plist_path)

    if os_name == "Linux":
        unit_path = _systemd_unit_path()
        unit_path.parent.mkdir(parents=True, exist_ok=True)
        unit_path.write_text(_systemd_unit(bashron_bin))
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
        subprocess.run(["systemctl", "--user", "enable", "--now", "bashron"], check=False)
        return str(unit_path)

    raise RuntimeError(f"Service management is not supported on {os_name}.")


def uninstall() -> bool:
    """Remove the service. Returns True if something was removed."""
    os_name = get_os()

    if os_name == "Darwin":
        plist_path = _launchd_plist_path()
        if plist_path.exists():
            subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
            plist_path.unlink()
            return True
        return False

    if os_name == "Linux":
        unit_path = _systemd_unit_path()
        if unit_path.exists():
            subprocess.run(["systemctl", "--user", "disable", "--now", "bashron"], check=False)
            unit_path.unlink()
            return True
        return False

    return False


def get_status() -> Optional[str]:
    """Return service status string, or None if not installed."""
    os_name = get_os()

    if os_name == "Darwin":
        if not _launchd_plist_path().exists():
            return None
        result = subprocess.run(
            ["launchctl", "list", "com.bashron"],
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() or result.stderr.strip()

    if os_name == "Linux":
        if not _systemd_unit_path().exists():
            return None
        result = subprocess.run(
            ["systemctl", "--user", "status", "bashron"],
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() or result.stderr.strip()

    return None
