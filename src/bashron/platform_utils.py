"""Cross-platform helpers: OS detection and bash discovery."""

import platform
import shutil
import sys
from pathlib import Path
from typing import Optional

# Ordered list of Windows-specific bash candidates (Git Bash, WSL, Cygwin)
_WINDOWS_BASH_CANDIDATES = [
    Path("C:/Program Files/Git/bin/bash.exe"),
    Path("C:/Program Files (x86)/Git/bin/bash.exe"),
    Path("C:/Windows/System32/bash.exe"),       # WSL
    Path("C:/cygwin64/bin/bash.exe"),
    Path("C:/cygwin/bin/bash.exe"),
]


def get_os() -> str:
    """Return 'Windows', 'Linux', or 'Darwin'."""
    return platform.system()


def is_supported_os() -> bool:
    """Return True for Windows, Linux, and macOS."""
    return get_os() in {"Windows", "Linux", "Darwin"}


def find_bash() -> Optional[str]:
    """
    Locate the bash executable.

    Search order:
      1. PATH (works on Linux/macOS and Windows with Git Bash in PATH)
      2. Known Windows install locations (Git Bash, WSL, Cygwin)
    Returns the absolute path string, or None if not found.
    """
    found = shutil.which("bash")
    if found:
        return found

    if get_os() == "Windows":
        for candidate in _WINDOWS_BASH_CANDIDATES:
            if candidate.exists():
                return str(candidate)

    return None


def bash_install_hint() -> str:
    """Return a human-readable hint for installing bash on the current OS."""
    os_name = get_os()
    if os_name == "Windows":
        return (
            "bash not found. Install one of:\n"
            "  • Git for Windows  https://git-scm.com/download/win  (adds Git Bash)\n"
            "  • WSL              run: wsl --install  in PowerShell (Admin)\n"
            "  • Cygwin           https://www.cygwin.com"
        )
    if os_name == "Linux":
        return "bash not found. Install it with: sudo apt install bash  (or your distro's package manager)"
    # Darwin
    return "bash not found. Install Homebrew then run: brew install bash"


def python_version() -> str:
    """Return the current Python version string."""
    return sys.version.split()[0]
