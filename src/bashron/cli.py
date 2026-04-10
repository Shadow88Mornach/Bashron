"""bashron CLI — warrior-class daily bash script scheduler."""

import json
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import schedule
import typer
from rich import box
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from . import __version__, cleaner, config, cron, runner, service, store
from .platform_utils import (
    bash_install_hint,
    find_bash,
    get_os,
    is_supported_os,
    python_version,
)

app = typer.Typer(
    name="bashron",
    help="[bold cyan]bashron[/] — warrior-class daily bash script scheduler.",
    rich_markup_mode="rich",
)
console = Console()

# Sub-app for `bashron config ...`
config_app = typer.Typer(help="View or update bashron configuration.", rich_markup_mode="rich")
app.add_typer(config_app, name="config")

# Sub-app for `bashron cron ...`
cron_app = typer.Typer(help="Manage system crontab entries for bashron jobs.", rich_markup_mode="rich")
app.add_typer(cron_app, name="cron")

# Sub-app for `bashron service ...`
service_app = typer.Typer(help="Manage bashron as a background service (launchd/systemd).", rich_markup_mode="rich")
app.add_typer(service_app, name="service")


def _version_callback(value: bool) -> None:
    if value:
        console.print(
            f"[bold cyan]bashron[/] v{__version__}  "
            f"| Python {python_version()}  "
            f"| {get_os()}"
        )
        raise typer.Exit()


_NATURAL_TIME_RE = re.compile(
    r"^\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm|AM|PM)?\s*$"
)


def _parse_time(value: str) -> str:
    """Normalize a human time string into ``HH:MM`` 24-hour format.

    Accepts ``9am``, ``9 AM``, ``3:30pm``, ``14:30``, ``09:00`` — so users
    never have to think about 24-hour format on the command line.
    Raises ``ValueError`` with a friendly message for anything else.
    """
    if value is None:
        raise ValueError("Time is required.")
    match = _NATURAL_TIME_RE.match(value)
    if not match:
        raise ValueError(
            f"Invalid time '{value}'. Try formats like 9am, 3:30pm, or 14:30."
        )
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    suffix = match.group(3)
    if suffix:
        suffix = suffix.lower()
        if not 1 <= hour <= 12:
            raise ValueError(
                f"Invalid time '{value}'. 12-hour clock expects hour 1-12."
            )
        if suffix == "am":
            hour = 0 if hour == 12 else hour
        else:  # pm
            hour = 12 if hour == 12 else hour + 12
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(
            f"Invalid time '{value}'. Hour must be 0-23 and minute 0-59."
        )
    return f"{hour:02d}:{minute:02d}"


def _has_time_passed_today(run_at: str, now: Optional[datetime] = None) -> bool:
    """Return True when an HH:MM time is earlier than the current local time."""
    current = now or datetime.now()
    scheduled = datetime.strptime(run_at, "%H:%M").time()
    return scheduled < current.time().replace(second=0, microsecond=0)


def _print_log_tail(name: str, lines: int) -> bool:
    """Print the last N lines of a log file. Returns False if no log exists."""
    log = store.log_path(name)
    if not log.exists():
        console.print(f"[dim]No log found for '{name}' yet.[/dim]")
        return False

    content = log.read_text()
    tail = content.splitlines()[-lines:]
    console.print(
        Panel(
            "\n".join(tail),
            title=f"[cyan]{name}[/] log (last {lines} lines)",
            border_style="dim",
        )
    )
    return True


def _follow_log(name: str, lines: int) -> None:
    """Tail a log file until interrupted."""
    if not _print_log_tail(name, lines):
        return

    log = store.log_path(name)
    last_size = log.stat().st_size
    console.print("[dim]Following log. Press Ctrl+C to stop.[/dim]")

    try:
        while True:
            current_size = log.stat().st_size
            if current_size < last_size:
                last_size = 0
            if current_size > last_size:
                with log.open() as handle:
                    handle.seek(last_size)
                    chunk = handle.read()
                if chunk:
                    console.print(chunk, end="")
                last_size = current_size
            time.sleep(1)
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped following log.[/dim]")


def _run_single_job(entry: dict) -> int:
    """Run one job entry and print the outcome."""
    name = entry["name"]
    console.print(f"[cyan]Running[/] [bold]{name}[/] → {entry['path']}")
    code = runner.run_script(entry)
    log = store.log_path(name)
    if code == 0:
        console.print(f"[green]Done.[/] Exit code: 0  |  Log: {log}")
    else:
        console.print(f"[red]Failed.[/] Exit code: {code}  |  Log: {log}")
    return code


_VALID_FREQUENCIES = {"hourly", "daily", "weekly", "monthly"}
_WEEKDAYS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
_WEEKDAY_DOW = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def _run_if_month_day(entry: dict, month_day: int, now: Optional[datetime] = None) -> None:
    """Run a job only when today matches the scheduled day of month."""
    current = now or datetime.now()
    if current.day == month_day:
        runner.run_script(entry)


def _parse_log_status(name: str) -> tuple:
    """Return (last_run_str, exit_code_str) parsed from the job's log file."""
    log = store.log_path(name)
    if not log.exists():
        return "never", "\u2014"
    content = log.read_text()
    lines = content.splitlines()
    last_run = "unknown"
    exit_code = "\u2014"
    for line in reversed(lines):
        if last_run == "unknown" and "] Running:" in line:
            last_run = line[1:line.index("]")]
        if exit_code == "\u2014" and "Exit code:" in line:
            exit_code = line.split("Exit code:")[-1].strip()
        if last_run != "unknown" and exit_code != "\u2014":
            break
    if last_run == "unknown":
        last_run = "never"
    return last_run, exit_code


def _next_run_str(entry: dict, now: datetime) -> str:
    """Return a human-readable string for the next scheduled run time."""
    from datetime import timedelta
    freq = entry.get("frequency", "daily")
    run_at = entry.get("run_at", "08:00")
    h, m = map(int, run_at.split(":"))

    if freq == "hourly":
        next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        mins = int((next_hour - now).total_seconds()) // 60
        return f"every hour (in {mins}m)"

    if freq == "weekly":
        weekday = entry.get("weekday", "monday")
        target_dow = _WEEKDAY_DOW.get(weekday, 0)
        days_ahead = (target_dow - now.weekday()) % 7
        scheduled = now.replace(hour=h, minute=m, second=0, microsecond=0) + timedelta(days=days_ahead)
        if scheduled <= now:
            scheduled += timedelta(days=7)
        delta = scheduled - now
        return f"{weekday} {run_at} (in {delta.days}d {delta.seconds // 3600}h)"

    if freq == "monthly":
        month_day = entry.get("month_day", 1)
        scheduled = now.replace(day=month_day, hour=h, minute=m, second=0, microsecond=0)
        if scheduled <= now:
            if now.month == 12:
                scheduled = now.replace(year=now.year + 1, month=1, day=month_day, hour=h, minute=m, second=0, microsecond=0)
            else:
                scheduled = now.replace(month=now.month + 1, day=month_day, hour=h, minute=m, second=0, microsecond=0)
        return f"day {month_day} of month {run_at} (in {(scheduled - now).days}d)"

    # daily (default)
    scheduled_today = now.replace(hour=h, minute=m, second=0, microsecond=0)
    delta = (scheduled_today - now) if scheduled_today > now else (scheduled_today + timedelta(days=1) - now)
    hours, remainder = divmod(int(delta.total_seconds()), 3600)
    mins = remainder // 60
    if hours > 0:
        return f"daily {run_at} (in {hours}h {mins}m)"
    return f"daily {run_at} (in {mins}m)"


def _startup_banner() -> str:
    """Return the startup banner shown when the daemon begins."""
    lines = [
        r"[bold cyan] _               _                    [/]",
        r"[bold bright_cyan]| |__   __ _ ___| |__  _ __ ___  _ __ [/]",
        # Close the tag BEFORE the trailing backslash — otherwise Rich parses
        # the `\[` as an escaped literal `[` and the `[/]` leaks as text.
        r"[bold blue]| '_ \ / _` / __| '_ \| '__/ _ \| '_ [/bold blue]" + "\\",
        r"[bold bright_blue]| |_) | (_| \__ \ | | | | | (_) | | | |[/]",
        r"[bold magenta]|_.__/ \__,_|___/_| |_|_|  \___/|_| |_|[/]",
        "",
        r"[bold yellow]  ⚔  warrior-class bash scheduling  ⚔[/]",
    ]
    return "\n".join(lines)


def _demo_script() -> str:
    """Return a deterministic demo transcript for walkthroughs and recordings."""
    return """[bold cyan]$ bashron add backup ~/scripts/backup.sh --at 02:00[/]
[green]Added[/] backup and scheduled it for 02:00 daily.

[bold cyan]$ bashron list[/]
backup   02:00   ~/scripts/backup.sh

[bold cyan]$ bashron run backup[/]
[cyan]Running[/] [bold]backup[/] -> ~/scripts/backup.sh
[green]Done.[/] Exit code: 0

[bold cyan]$ bashron logs backup --lines 3[/]
Starting backup
Sync complete
Exit code: 0

[bold cyan]$ bashron start --quiet[/]
[bold]bashron daemon started[/]
backup scheduled at 02:00
log-cleanup scheduled at 00:00"""


def _git_output(args: list[str]) -> str:
    """Run a git command and return stripped stdout."""
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def _welcome_panel() -> Panel:
    """Return the empty-state welcome shown when the user has no jobs yet."""
    body = (
        f"{_startup_banner()}\n\n"
        "[bold]No jobs yet — let's fix that in 30 seconds.[/]\n\n"
        "  [bold cyan]1.[/] [bold]bashron init[/]              [dim]guided wizard[/]\n"
        "  [bold cyan]2.[/] [bold]bashron new my-task[/]       [dim]scaffold a script[/]\n"
        "  [bold cyan]3.[/] [bold]bashron add <name> <file>[/] [dim]schedule an existing script[/]\n\n"
        "[dim]Tip:[/] times are friendly — [bold]--at 9am[/], [bold]--at 3:30pm[/], [bold]--at 14:30[/] all work."
    )
    return Panel(body, border_style="cyan", title="[bold]welcome to bashron[/]")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Optional[bool] = typer.Option(
        None, "--version", "-v", callback=_version_callback, is_eager=True, help="Show version."
    ),
) -> None:
    if ctx.invoked_subcommand is None:
        scripts = store.load()
        if not scripts:
            console.print(_welcome_panel())
        else:
            console.print(_render_status(scripts, datetime.now()))
            console.print(
                "[dim]Commands:[/] [bold]add[/] · [bold]run[/] · [bold]logs[/] · "
                "[bold]status --watch[/] · [bold]service install[/]  "
                "([dim]full help:[/] [bold]bashron --help[/])"
            )


@app.command()
def overview() -> None:
    """Show a visual architecture overview for contributors."""
    architecture = """[bold cyan]CLI[/] [dim](Typer commands)[/]
  [green]add/list/run/logs/start/cron[/]
        |
        v
[bold yellow]store.py[/] [dim]persistent job database + log paths[/]
        |
        +--> [bold magenta]runner.py[/] [dim]executes bash scripts, writes logs[/]
        |
        +--> [bold blue]config.py[/] [dim]retention settings[/]
        |        |
        |        +--> [bold white]cleaner.py[/] [dim]deletes old logs[/]
        |
        +--> [bold red]cron.py[/] [dim]renders/install crontab entries[/]

[bold green]platform_utils.py[/] supports doctor/version/runtime checks.
"""
    onboarding = """1. Read [bold]README.md[/] for the user workflow.
2. Start at [bold]src/bashron/cli.py[/] to see command entry points.
3. Follow calls into [bold]store.py[/], [bold]runner.py[/], and [bold]cron.py[/].
4. Run [bold]PYTHONPATH=src pytest[/] before changing behavior.
"""
    console.print(Panel.fit(architecture, title="[bold]bashron architecture[/]", border_style="cyan"))
    console.print(Panel.fit(onboarding, title="[bold]new contributor path[/]", border_style="green"))


@app.command()
def demo() -> None:
    """Show a polished fake workflow for onboarding and recordings."""
    tips = """Use this when you need a fast repo tour:
- [bold]overview[/] explains the code layout
- [bold]repo-stats[/] shows branch and commit counts in a real git checkout
- [bold]start --quiet[/] is best for screenshots after setup"""
    console.print(Panel.fit(_demo_script(), title="[bold]bashron demo[/]", border_style="magenta"))
    console.print(Panel.fit(tips, title="[bold]recording notes[/]", border_style="yellow"))


@app.command(name="repo-stats")
def repo_stats(
    base: str = typer.Option("main", "--base", help="Base branch to compare against for ahead count."),
) -> None:
    """Show simple git-based repository stats for contributors."""
    try:
        branch = _git_output(["rev-parse", "--abbrev-ref", "HEAD"])
        total_commits = int(_git_output(["rev-list", "--count", "HEAD"]))
    except RuntimeError as exc:
        console.print(f"[yellow]Git stats unavailable:[/] {exc}")
        raise typer.Exit(1)

    ahead_output = None
    try:
        ahead_output = _git_output(["rev-list", "--count", f"{base}..HEAD"])
    except RuntimeError:
        ahead_output = None

    table = Table(box=box.ROUNDED, header_style="bold cyan", show_lines=True)
    table.add_column("Metric")
    table.add_column("Value", style="yellow")
    table.add_row("Current branch", branch)
    table.add_row("Total commits on HEAD", str(total_commits))
    if ahead_output is not None:
        table.add_row(f"Commits ahead of {base}", ahead_output)
    else:
        table.add_row(f"Commits ahead of {base}", "unavailable")

    console.print(table)


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------

@app.command()
def doctor() -> None:
    """Check your system is ready to run bashron (OS, bash, config dir)."""
    checks = []
    all_ok = True

    os_name = get_os()
    if is_supported_os():
        checks.append(("[green]PASS[/]", "Operating system", f"{os_name} (supported)"))
    else:
        checks.append(("[red]FAIL[/]", "Operating system", f"{os_name} (unsupported)"))
        all_ok = False

    checks.append(("[green]PASS[/]", "Python version", python_version()))

    bash_path = find_bash()
    if bash_path:
        checks.append(("[green]PASS[/]", "bash executable", bash_path))
    else:
        checks.append(("[red]FAIL[/]", "bash executable", "not found"))
        all_ok = False

    try:
        store._ensure_dirs()
        test_file = store.CONFIG_DIR / ".write_test"
        test_file.write_text("ok")
        test_file.unlink()
        checks.append(("[green]PASS[/]", "Config dir writable", str(store.CONFIG_DIR)))
    except OSError as exc:
        checks.append(("[red]FAIL[/]", "Config dir writable", str(exc)))
        all_ok = False

    table = Table(box=box.ROUNDED, header_style="bold cyan", show_lines=True)
    table.add_column("Status", justify="center")
    table.add_column("Check")
    table.add_column("Detail", style="dim")
    for status, check, detail in checks:
        table.add_row(status, check, detail)

    console.print(table)

    if not bash_path:
        console.print(f"\n[yellow]{bash_install_hint()}[/yellow]")

    if all_ok:
        console.print(Panel("[bold green]All checks passed — bashron is ready![/]", border_style="green"))
    else:
        console.print(Panel("[bold red]Some checks failed. Fix the issues above before using bashron.[/]", border_style="red"))
        raise typer.Exit(1)


_SCRIPT_TEMPLATE = """\
#!/usr/bin/env bash
# {name} \u2014 created by bashron new
# Schedule: daily at {at}

set -euo pipefail

echo "[$( date )] {name} running..."

# TODO: add your commands here

echo "[$( date )] {name} done."
"""


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

@app.command()
def init() -> None:
    """Interactive wizard to schedule your first script in under 30 seconds."""
    console.print(Panel(
        "[bold cyan]Welcome to bashron![/]\nLet's schedule your first script.",
        border_style="cyan",
    ))
    name = typer.prompt("? What should we call this job?")
    path_str = typer.prompt("? Path to your script?")
    at_raw = typer.prompt("? What time should it run? (e.g. 9am, 3:30pm, 14:30)", default="08:00")

    script_path = Path(path_str).expanduser().resolve()
    if not script_path.exists():
        console.print(f"[red]Error:[/] File not found: {script_path}")
        raise typer.Exit(1)

    try:
        at = _parse_time(at_raw)
    except ValueError as exc:
        console.print(f"[red]Error:[/] {exc}")
        raise typer.Exit(1)

    if _has_time_passed_today(at):
        console.print(f"[yellow]Note:[/] {at} has already passed today. First run will be tomorrow.")

    try:
        store.add(name, str(script_path), at)
    except ValueError as exc:
        console.print(f"[red]Error:[/] {exc}")
        raise typer.Exit(1)

    console.print(Panel(
        f"[bold green]Job added![/]\n"
        f"[cyan]{name}[/] will run daily at [yellow]{at}[/]\n\n"
        f"Run [bold]bashron start[/] to launch the daemon.",
        border_style="green",
    ))


# ---------------------------------------------------------------------------
# new
# ---------------------------------------------------------------------------

@app.command(name="new")
def new_script(
    name: str = typer.Argument(..., help="Name for the new job and script file."),
    scripts_dir: str = typer.Option("~/scripts", "--dir", help="Directory to scaffold the script in."),
    at: str = typer.Option("08:00", "--at", help="Daily run time — e.g. 9am, 3:30pm, or 14:30."),
) -> None:
    """Scaffold a new bash script and schedule it immediately."""
    try:
        at = _parse_time(at)
    except ValueError as exc:
        console.print(f"[red]Error:[/] {exc}")
        raise typer.Exit(1)

    out_dir = Path(scripts_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    script_file = out_dir / f"{name}.sh"

    if script_file.exists():
        console.print(f"[yellow]Note:[/] {script_file} already exists \u2014 skipping creation.")
    else:
        script_file.write_text(_SCRIPT_TEMPLATE.format(name=name, at=at))
        script_file.chmod(0o755)
        console.print(f"[green]Created[/] {script_file}")

    try:
        store.add(name, str(script_file), at)
    except ValueError as exc:
        console.print(f"[red]Error:[/] {exc}")
        raise typer.Exit(1)

    console.print(Panel(
        f"[bold green]Ready![/] [cyan]{name}[/] scheduled at [yellow]{at}[/] daily.\n\n"
        f"Edit: [dim]{script_file}[/dim]\n"
        f"Run now: [bold]bashron run {name}[/bold]",
        border_style="green",
    ))


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

def _render_status(scripts: list[dict], now: datetime) -> Table:
    """Build the Rich table used by both `status` and the bare-command view."""
    table = Table(
        box=box.ROUNDED,
        header_style="bold cyan",
        show_lines=True,
        title=f"[bold cyan]bashron[/]  [dim]·[/] {len(scripts)} job(s)  "
              f"[dim]·[/] {now.strftime('%Y-%m-%d %H:%M:%S')}",
    )
    table.add_column("Name", style="cyan")
    table.add_column("Next Run", style="yellow")
    table.add_column("Last Run", style="dim")
    table.add_column("Exit", justify="center")

    for s in scripts:
        last_run, exit_code_str = _parse_log_status(s["name"])
        next_run = _next_run_str(s, now)
        if exit_code_str == "0":
            exit_col = "[green]0[/green]"
        elif exit_code_str == "\u2014":
            exit_col = "[dim]\u2014[/dim]"
        else:
            exit_col = f"[red]{exit_code_str}[/red]"
        table.add_row(s["name"], next_run, last_run, exit_col)

    return table


def _watch_status(interval: float, iterations: Optional[int] = None) -> None:
    """Refresh the status dashboard in place until Ctrl+C (or `iterations` ticks)."""
    step = 0
    try:
        with Live(
            _render_status(store.load(), datetime.now()),
            console=console,
            refresh_per_second=4,
            screen=False,
        ) as live:
            while iterations is None or step < iterations:
                time.sleep(interval)
                live.update(_render_status(store.load(), datetime.now()))
                step += 1
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped watching.[/dim]")


@app.command()
def status(
    watch: bool = typer.Option(False, "--watch", "-w", help="Refresh the dashboard every few seconds (Ctrl+C to stop)."),
    interval: float = typer.Option(2.0, "--interval", help="Refresh interval in seconds when using --watch."),
) -> None:
    """Show scheduled jobs with last run time, exit code, and next run."""
    scripts = store.load()
    if not scripts:
        console.print(_welcome_panel())
        return

    if watch:
        _watch_status(interval)
        return

    console.print(_render_status(scripts, datetime.now()))


# ---------------------------------------------------------------------------
# export / import
# ---------------------------------------------------------------------------

@app.command(name="export")
def export_jobs(
    output: Optional[str] = typer.Argument(None, help="Output file path (omit to print to stdout)."),
) -> None:
    """Export all scheduled jobs to JSON (bashronfile.json)."""
    scripts = store.load()
    data = json.dumps(scripts, indent=2)
    if output:
        Path(output).write_text(data)
        console.print(f"[green]Exported[/] {len(scripts)} job(s) to [cyan]{output}[/]")
    else:
        console.print(data)


@app.command(name="import")
def import_jobs(
    source: str = typer.Argument(..., help="Path to bashronfile.json."),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace all existing jobs instead of merging."),
) -> None:
    """Import jobs from a bashronfile.json (merges with existing by default)."""
    path = Path(source)
    if not path.exists():
        console.print(f"[red]Error:[/] File not found: {path}")
        raise typer.Exit(1)
    try:
        imported = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        console.print(f"[red]Error:[/] Invalid JSON: {exc}")
        raise typer.Exit(1)
    if not isinstance(imported, list):
        console.print("[red]Error:[/] Expected a JSON array of jobs.")
        raise typer.Exit(1)

    if overwrite:
        store.save(imported)
        console.print(f"[green]Imported[/] {len(imported)} job(s) (replaced all existing).")
        return

    existing = store.load()
    existing_names = {s["name"] for s in existing}
    added, skipped = 0, 0
    for job in imported:
        if job["name"] in existing_names:
            skipped += 1
        else:
            existing.append(job)
            existing_names.add(job["name"])
            added += 1
    store.save(existing)
    console.print(f"[green]Imported[/] {added} job(s). [yellow]Skipped[/] {skipped} duplicate(s).")


# ---------------------------------------------------------------------------
# add / remove / list
# ---------------------------------------------------------------------------

def _is_url(path: str) -> bool:
    """Return True if path looks like an http(s) URL."""
    return path.startswith("http://") or path.startswith("https://")


def _download_script(url: str, name: str) -> Path:
    """Download a script from a URL into ~/.bashron/scripts/<name>.sh and return its path."""
    import urllib.error
    import urllib.request

    scripts_dir = store.CONFIG_DIR / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    dest = scripts_dir / f"{name}.sh"

    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            dest.write_bytes(response.read())
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Download failed: {exc}") from exc

    dest.chmod(0o755)
    return dest


@app.command()
def add(
    name: str = typer.Argument(..., help="Unique name for this script job."),
    path: str = typer.Argument(..., help="Path to the .sh script file, or an https:// URL to download it."),
    at: str = typer.Option("08:00", "--at", "-t", help="Run time — e.g. 9am, 3:30pm, 14:30. Ignored for --every hourly."),
    every: str = typer.Option("daily", "--every", help="Frequency: hourly, daily, weekly, monthly."),
    on: str = typer.Option("", "--on", help="Weekday for weekly (e.g. monday) or day of month for monthly (1-28)."),
    notify: bool = typer.Option(False, "--notify", help="Send a desktop notification on failure (macOS only)."),
    webhook: str = typer.Option("", "--webhook", help="Webhook URL to POST on failure (Slack/Discord)."),
    explain: bool = typer.Option(False, "--explain", help="Preview the schedule in plain English without saving."),
) -> None:
    """Add a bash script on a schedule. Path can be a local file or a URL."""
    # Resolve script path
    if _is_url(path):
        if explain:
            script_path = Path(f"[will download] {path}")
        else:
            console.print(f"[cyan]Downloading[/] {path}")
            try:
                script_path = _download_script(path, name)
            except RuntimeError as exc:
                console.print(f"[red]Error:[/] {exc}")
                raise typer.Exit(1)
            console.print(f"[green]Saved[/] {script_path}")
    else:
        script_path = Path(path).expanduser().resolve()
        if not script_path.exists():
            console.print(f"[red]Error:[/] File not found: {script_path}")
            raise typer.Exit(1)

    if not script_path.suffix == ".sh":
        console.print("[yellow]Warning:[/] File does not have a .sh extension. Proceeding anyway.")

    # Validate frequency
    freq = every.lower()
    if freq not in _VALID_FREQUENCIES:
        console.print(f"[red]Error:[/] Invalid frequency '{every}'. Choose: hourly, daily, weekly, monthly.")
        raise typer.Exit(1)

    # Parse --on based on frequency
    weekday = "monday"
    month_day = 1
    if freq == "weekly":
        day_str = on.lower() if on else "monday"
        if day_str not in _WEEKDAYS:
            console.print(
                f"[red]Error:[/] Invalid weekday '{day_str}'. "
                "Use: monday, tuesday, wednesday, thursday, friday, saturday, sunday."
            )
            raise typer.Exit(1)
        weekday = day_str
    elif freq == "monthly":
        day_str = on if on else "1"
        try:
            month_day = int(day_str)
            if not 1 <= month_day <= 28:
                raise ValueError
        except ValueError:
            console.print("[red]Error:[/] --on must be a day number between 1 and 28 for monthly frequency.")
            raise typer.Exit(1)

    # Normalize run time (skip for hourly — no specific time needed)
    if freq != "hourly":
        try:
            at = _parse_time(at)
        except ValueError as exc:
            console.print(f"[red]Error:[/] {exc}")
            raise typer.Exit(1)
        if _has_time_passed_today(at):
            console.print(f"[yellow]Warning:[/] {at} has already passed today. First run will be tomorrow.")

    # --explain: show the human-readable preview and bail without writing
    if explain:
        preview_entry = {
            "name": name,
            "path": str(script_path),
            "run_at": at,
            "frequency": freq,
            "weekday": weekday,
            "month_day": month_day,
        }
        next_run = _next_run_str(preview_entry, datetime.now())
        console.print(
            Panel(
                f"[bold]Dry run — nothing was saved.[/]\n\n"
                f"  [dim]name    [/dim] [cyan]{name}[/]\n"
                f"  [dim]script  [/dim] {script_path}\n"
                f"  [dim]when    [/dim] [yellow]{next_run}[/]\n\n"
                f"Run again without [bold]--explain[/] to actually schedule it.",
                title="[bold cyan]bashron[/] preview",
                border_style="cyan",
            )
        )
        return

    try:
        entry = store.add(
            name, str(script_path), at,
            frequency=freq, weekday=weekday, month_day=month_day,
            notify=notify, webhook=webhook,
        )
    except ValueError as e:
        console.print(f"[red]Error:[/] {e}")
        raise typer.Exit(1)

    schedule_desc = {
        "hourly": "every hour",
        "daily": f"daily at {at}",
        "weekly": f"every {weekday} at {at}",
        "monthly": f"day {month_day} of every month at {at}",
    }[freq]

    extras = []
    if notify:
        extras.append("[dim]notify on failure:[/dim] [green]on[/green]")
    if webhook:
        extras.append("[dim]webhook:[/dim] [green]on[/green]")
    extras_line = ("  " + "  ".join(extras)) if extras else ""

    console.print(
        Panel(
            f"[bold green]✓ Job added![/]\n\n"
            f"  [dim]name    [/dim] [cyan]{name}[/]\n"
            f"  [dim]script  [/dim] {entry['path']}\n"
            f"  [dim]schedule[/dim] [yellow]{schedule_desc}[/]\n"
            f"  [dim]log     [/dim] {store.log_path(name)}"
            + (f"\n{extras_line}" if extras_line else "")
            + f"\n\n"
            f"  Run now : [bold]bashron run {name}[/bold]\n"
            f"  Daemon  : [bold]bashron start[/bold]",
            title="[bold]bashron[/]",
            border_style="green",
        )
    )


@app.command()
def remove(
    name: str = typer.Argument(..., help="Name of the job to remove."),
) -> None:
    """Remove a scheduled script by name."""
    if store.remove(name):
        console.print(f"[green]Removed[/] job [cyan]{name}[/].")
    else:
        console.print(f"[red]Error:[/] No job named '{name}' found.")
        raise typer.Exit(1)


@app.command(name="list")
def list_jobs(
    as_json: bool = typer.Option(False, "--json", help="Output jobs as JSON."),
) -> None:
    """List all scheduled scripts."""
    scripts = store.load()
    if as_json:
        payload = [
            {**script, "log": str(store.log_path(script["name"]))}
            for script in scripts
        ]
        console.print_json(json.dumps(payload))
        return
    if not scripts:
        console.print(_welcome_panel())
        return

    table = Table(box=box.ROUNDED, header_style="bold cyan", show_lines=True)
    table.add_column("Name", style="cyan")
    table.add_column("Run At", style="yellow")
    table.add_column("Script Path", style="white")
    table.add_column("Log", style="dim")

    for s in scripts:
        log = store.log_path(s["name"])
        table.add_row(s["name"], s["run_at"], s["path"], str(log))

    console.print(table)


# ---------------------------------------------------------------------------
# run / logs
# ---------------------------------------------------------------------------

@app.command()
def run(
    name: Optional[str] = typer.Argument(None, help="Name of the job to run immediately."),
    run_all: bool = typer.Option(False, "--all", help="Run every scheduled job immediately."),
) -> None:
    """Run a scheduled script right now (ignores time)."""
    scripts = store.load()
    if run_all and name is not None:
        console.print("[red]Error:[/] Provide either a job name or --all, not both.")
        raise typer.Exit(1)
    if run_all:
        if not scripts:
            console.print("[red]Error:[/] No jobs scheduled.")
            raise typer.Exit(1)
        exit_code = 0
        for entry in scripts:
            code = _run_single_job(entry)
            if code != 0:
                exit_code = code
        if exit_code != 0:
            raise typer.Exit(exit_code)
        return
    if name is None:
        console.print("[red]Error:[/] Provide a job name or use --all.")
        raise typer.Exit(1)

    entry = next((s for s in scripts if s["name"] == name), None)
    if not entry:
        console.print(f"[red]Error:[/] No job named '{name}' found.")
        raise typer.Exit(1)

    code = _run_single_job(entry)
    if code != 0:
        raise typer.Exit(code)


@app.command()
def logs(
    name: str = typer.Argument(..., help="Name of the job to view logs for."),
    lines: int = typer.Option(50, "--lines", "-n", help="Number of tail lines to show."),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow the log like tail -f."),
) -> None:
    """View the last N lines of a job's log."""
    if follow:
        _follow_log(name, lines)
        return
    _print_log_tail(name, lines)


# ---------------------------------------------------------------------------
# clean-logs
# ---------------------------------------------------------------------------

@app.command(name="clean-logs")
def clean_logs_cmd(
    days: Optional[int] = typer.Option(None, "--days", "-d", help="Override retention days for this run."),
) -> None:
    """Delete log files older than the configured retention period (default 7 days)."""
    retention = days if days is not None else config.get_retention_days()
    deleted = cleaner.clean_logs(retention)

    if deleted:
        for name in deleted:
            console.print(f"[yellow]Deleted[/] {name}")
        console.print(f"\n[green]Cleaned {len(deleted)} log file(s)[/] older than [bold]{retention}[/] day(s).")
    else:
        console.print(f"[dim]No logs older than {retention} day(s) found.[/dim]")


# ---------------------------------------------------------------------------
# config sub-commands
# ---------------------------------------------------------------------------

@config_app.callback(invoke_without_command=True)
def config_default(ctx: typer.Context) -> None:
    """View or update bashron configuration."""
    if ctx.invoked_subcommand is None:
        settings = config.all_settings()
        table = Table(box=box.ROUNDED, header_style="bold cyan", show_lines=True)
        table.add_column("Setting")
        table.add_column("Value", style="yellow")
        for key, value in settings.items():
            table.add_row(key, str(value))
        console.print(table)


@config_app.command(name="set-retention")
def config_set_retention(
    days: int = typer.Argument(..., help="Number of days to retain log files."),
) -> None:
    """Set how many days to keep log files before auto-cleanup."""
    try:
        config.set_retention_days(days)
        console.print(f"[green]Retention set to[/] [bold]{days}[/] day(s).")
    except ValueError as e:
        console.print(f"[red]Error:[/] {e}")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# start (daemon)
# ---------------------------------------------------------------------------

@app.command()
def start(
    quiet: bool = typer.Option(False, "--quiet", help="Suppress the startup banner."),
) -> None:
    """Start the bashron daemon — runs all jobs on their daily schedule."""
    scripts = store.load()
    if not scripts:
        console.print("[yellow]No scripts scheduled. Add some with [bold]bashron add[/].[/yellow]")
        raise typer.Exit()

    retention = config.get_retention_days()

    if not quiet:
        console.print(Panel.fit(_startup_banner(), border_style="cyan"))

    console.print(Panel(
        f"[bold cyan]bashron daemon started[/]\n"
        f"Log retention: [yellow]{retention}[/] day(s)  |  Press [bold]Ctrl+C[/] to stop.",
        border_style="cyan",
    ))

    for s in scripts:
        freq = s.get("frequency", "daily")
        if freq == "hourly":
            schedule.every().hour.do(runner.run_script, s)
            console.print(f"  [green]+[/] [cyan]{s['name']}[/] scheduled [yellow]every hour[/]")
        elif freq == "weekly":
            weekday = s.get("weekday", "monday")
            getattr(schedule.every(), weekday).at(s["run_at"]).do(runner.run_script, s)
            console.print(f"  [green]+[/] [cyan]{s['name']}[/] scheduled [yellow]every {weekday} at {s['run_at']}[/]")
        elif freq == "monthly":
            month_day = s.get("month_day", 1)
            schedule.every().day.at(s["run_at"]).do(_run_if_month_day, s, month_day)
            console.print(f"  [green]+[/] [cyan]{s['name']}[/] scheduled [yellow]day {month_day} of month at {s['run_at']}[/]")
        else:
            schedule.every().day.at(s["run_at"]).do(runner.run_script, s)
            console.print(f"  [green]+[/] [cyan]{s['name']}[/] scheduled [yellow]daily at {s['run_at']}[/]")

    # Daily log cleanup at midnight
    schedule.every().day.at("00:00").do(cleaner.clean_logs)
    console.print(f"  [green]+[/] [dim]log-cleanup[/] scheduled at [yellow]00:00[/] (retention: {retention}d)")

    console.print()
    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        console.print("\n[dim]bashron daemon stopped.[/dim]")


# ---------------------------------------------------------------------------
# cron sub-commands
# ---------------------------------------------------------------------------

def _cron_platform_guard() -> None:
    """Exit with a message on Windows where crontab is not available."""
    if not cron.is_supported():
        console.print("[red]Error:[/] crontab is not supported on Windows. Use Task Scheduler instead.")
        raise typer.Exit(1)


@cron_app.callback(invoke_without_command=True)
def cron_default(ctx: typer.Context) -> None:
    """Manage system crontab entries for bashron jobs."""
    if ctx.invoked_subcommand is None:
        ctx.get_help()


@cron_app.command(name="show")
def cron_show() -> None:
    """Preview the crontab entries bashron would install (dry run)."""
    _cron_platform_guard()
    scripts = store.load()
    if not scripts:
        console.print("[dim]No jobs scheduled. Use [bold]bashron add[/] first.[/dim]")
        return
    try:
        entries = cron.build_entries()
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        raise typer.Exit(1)

    console.print(Panel(
        "\n".join(entries),
        title="[cyan]crontab preview[/]",
        border_style="cyan",
    ))


@cron_app.command(name="install")
def cron_install() -> None:
    """Install all bashron jobs into the system crontab."""
    _cron_platform_guard()
    scripts = store.load()
    if not scripts:
        console.print("[dim]No jobs scheduled. Use [bold]bashron add[/] first.[/dim]")
        return
    existing = cron._read_crontab().strip()
    if existing and not typer.confirm("Existing crontab detected. Overwrite with updated bashron entries?"):
        console.print("[yellow]Aborted.[/yellow]")
        raise typer.Exit(1)
    try:
        entries = cron.install()
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        raise typer.Exit(1)

    for line in entries:
        if line.startswith("#"):
            console.print(f"[dim]{line}[/dim]")
        else:
            console.print(f"  [green]+[/] {line}")
    console.print(Panel("[bold green]Crontab updated successfully.[/]", border_style="green"))


@cron_app.command(name="uninstall")
def cron_uninstall() -> None:
    """Remove all bashron-managed entries from the system crontab."""
    _cron_platform_guard()
    if cron.uninstall():
        console.print("[green]Removed[/] bashron entries from crontab.")
    else:
        console.print("[dim]No bashron entries found in crontab.[/dim]")


# ---------------------------------------------------------------------------
# service sub-commands
# ---------------------------------------------------------------------------

def _service_platform_guard() -> None:
    """Exit with a message on unsupported platforms."""
    if not service.is_supported():
        console.print("[red]Error:[/] Service management is only supported on macOS and Linux.")
        raise typer.Exit(1)


@service_app.callback(invoke_without_command=True)
def service_default(ctx: typer.Context) -> None:
    """Manage bashron as a background service (launchd/systemd)."""
    if ctx.invoked_subcommand is None:
        ctx.get_help()


@service_app.command(name="install")
def service_install() -> None:
    """Install bashron as a background service that starts on login/boot."""
    _service_platform_guard()
    try:
        path = service.install()
        console.print(Panel(
            f"[bold green]Service installed![/]\n{path}\n\n"
            "bashron will start automatically on login.",
            border_style="green",
        ))
    except RuntimeError as exc:
        console.print(f"[red]Error:[/] {exc}")
        raise typer.Exit(1)


@service_app.command(name="status")
def service_status() -> None:
    """Show the current status of the bashron background service."""
    _service_platform_guard()
    status_text = service.get_status()
    if status_text is None:
        console.print("[yellow]Service is not installed. Run [bold]bashron service install[/] first.[/yellow]")
    else:
        console.print(Panel(
            status_text or "running",
            title="[cyan]bashron service status[/]",
            border_style="cyan",
        ))


@service_app.command(name="uninstall")
def service_uninstall() -> None:
    """Remove the bashron background service."""
    _service_platform_guard()
    if service.uninstall():
        console.print("[green]Service uninstalled.[/]")
    else:
        console.print("[dim]No service found.[/dim]")


# ---------------------------------------------------------------------------
# command aliases — free muscle-memory for unix / docker / git users
# ---------------------------------------------------------------------------

app.command(name="ls", help="Alias for [bold]list[/].")(list_jobs)
app.command(name="rm", help="Alias for [bold]remove[/].")(remove)
app.command(name="ps", help="Alias for [bold]status[/].")(status)
