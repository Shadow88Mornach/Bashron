"""Execute a bash script and append output to its log file."""

import json as _json
import platform
import subprocess
import urllib.request
from datetime import datetime

from . import store
from .platform_utils import find_bash


def _notify_failure(name: str, exit_code: int) -> None:
    """Send a desktop notification on failure (macOS only)."""
    if platform.system() != "Darwin":
        return
    msg = f'display notification "Exit code: {exit_code}" with title "bashron: {name} failed"'
    subprocess.run(["osascript", "-e", msg], capture_output=True)


def _send_webhook(url: str, name: str, exit_code: int) -> None:
    """POST a failure notification to a webhook URL (Slack/Discord compatible)."""
    payload = _json.dumps({"text": f"bashron: *{name}* failed with exit code {exit_code}"}).encode()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


def run_script(entry: dict) -> int:
    """Run a script entry and log stdout/stderr. Returns exit code."""
    bash = find_bash()
    if bash is None:
        log = store.log_path(entry["name"])
        with log.open("a") as lf:
            lf.write("ERROR: bash executable not found on this system.\n")
        return 127  # POSIX "command not found"

    log = store.log_path(entry["name"])
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    script_path = entry["path"]

    with log.open("a") as lf:
        lf.write(f"\n{'='*60}\n[{timestamp}] Running: {script_path}\n{'='*60}\n")
        result = subprocess.run(
            [bash, script_path],
            stdout=lf,
            stderr=lf,
            text=True,
        )
        lf.write(f"[{timestamp}] Exit code: {result.returncode}\n")

    if result.returncode != 0:
        if entry.get("notify"):
            _notify_failure(entry["name"], result.returncode)
        webhook = entry.get("webhook")
        if webhook:
            _send_webhook(webhook, entry["name"], result.returncode)

    return result.returncode
