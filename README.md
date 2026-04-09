# bashron

> Warrior-class daily bash script scheduler for your terminal.

```
$ bashron add backup ~/scripts/backup.sh --at 02:00
$ bashron start
```

## Install

```bash
pip install bashron
# or with uv
uv tool install bashron
```

## Quickstart — verify it works

After installing, run this to confirm everything is working:

```bash
# 1. Check your system is ready
bashron doctor

# 2. Download the hello-world example script
curl -O https://raw.githubusercontent.com/yourusername/bashron/main/examples/hello.sh
chmod +x hello.sh

# 3. Add it as a job and run it immediately
bashron add hello ./hello.sh
bashron run hello

# 4. Check the output
bashron logs hello
```

You should see:
```
Hello from bashron!
bashron is installed and working.
Script ran at: <current date/time>
```

Clean up when done:
```bash
bashron remove hello
```

## Test all features

If you want to exercise every command after installing:

```bash
# Interactive wizard — guided job setup
bashron init

# Scaffold a new script and schedule it in one step
bashron new my-task --dir ~/scripts --at 09:00

# Live dashboard — next run, last run, exit code
bashron status

# Export your jobs to share or back up
bashron export ~/my-jobs.json

# Import jobs on another machine (merges by default)
bashron import ~/my-jobs.json

# Import and replace everything
bashron import ~/my-jobs.json --overwrite

# Get notified on failure (macOS desktop notification)
bashron add my-task ~/scripts/my-task.sh --notify

# Post to Slack/Discord on failure
bashron add my-task ~/scripts/my-task.sh --webhook https://hooks.slack.com/...

# Run as a persistent background service (survives reboots)
bashron service install   # registers with launchd (macOS) or systemd (Linux)
bashron service status
bashron service uninstall
```

## Commands

| Command | Description |
|---|---|
| `bashron init` | Interactive wizard to add your first job |
| `bashron new <name>` | Scaffold a bash script and schedule it immediately |
| `bashron add <name> <script.sh>` | Schedule a local script (daily at 08:00 by default) |
| `bashron add <name> <https://...>` | Download a script from a URL and schedule it |
| `bashron add ... --every hourly` | Run every hour |
| `bashron add ... --every daily --at HH:MM` | Run daily at a specific time |
| `bashron add ... --every weekly --on monday --at HH:MM` | Run every week on a given day |
| `bashron add ... --every monthly --on 1 --at HH:MM` | Run on a specific day of every month (1–28) |
| `bashron add ... --notify` | Enable macOS desktop notification on failure |
| `bashron add ... --webhook <url>` | POST to Slack/Discord on failure |
| `bashron list` | List all scheduled jobs |
| `bashron list --json` | List all scheduled jobs as JSON |
| `bashron status` | Live dashboard: next run, last run, exit code |
| `bashron run <name>` | Run a job immediately |
| `bashron run --all` | Run every job immediately |
| `bashron logs <name>` | View job logs |
| `bashron logs <name> --follow` | Follow a job log in real time |
| `bashron remove <name>` | Remove a scheduled job |
| `bashron export [file]` | Export jobs to JSON (stdout if no file given) |
| `bashron import <file>` | Import jobs from JSON (merges by default) |
| `bashron start` | Start the daemon (keeps running) |
| `bashron service install` | Install as a background service (launchd/systemd) |
| `bashron service status` | Show background service status |
| `bashron service uninstall` | Remove the background service |
| `bashron doctor` | Check system is ready to run bashron |
| `bashron overview` | Show a visual architecture map for contributors |
| `bashron demo` | Show a colored sample workflow for onboarding or recordings |

## Examples

```bash
# Run every hour
bashron add sync ~/scripts/sync.sh --every hourly

# Run daily at a specific time
bashron add backup ~/scripts/backup.sh --every daily --at 03:00

# Download a script from the internet and run it weekly on Friday
bashron add report https://example.com/report.sh --every weekly --on friday --at 09:00

# Run on the 1st of every month
bashron add billing ~/scripts/billing.sh --every monthly --on 1 --at 08:00

# Run it once right now to test
bashron run backup

# Check the log
bashron logs backup

# Live dashboard showing schedule, last run, and exit code
bashron status

# Start the scheduler daemon
bashron start
```

| Path | What's stored there |
|---|---|
| `~/.bashron/logs/<name>.log` | Output logs for each job |
| `~/.bashron/scripts/<name>.sh` | Scripts downloaded from URLs |
| `~/.bashron/scripts.json` | Job database |

## New Contributor Start Here

Run the built-in overview first:

```bash
bashron overview
bashron demo
```

Then read the code in this order:

1. `src/bashron/cli.py`
2. `src/bashron/store.py`
3. `src/bashron/runner.py`
4. `src/bashron/config.py`
5. `src/bashron/cleaner.py`
6. `src/bashron/cron.py`

There is also a Mermaid version in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Architecture

```text
User CLI
  |
  v
cli.py
  |
  +--> store.py ---------> scripts.json / ~/.bashron/logs
  |
  +--> runner.py --------> bash subprocess + log output
  |
  +--> config.py --------> config.json
  |        |
  |        +--> cleaner.py
  |
  +--> cron.py ----------> crontab preview/install/uninstall
  |
  +--> platform_utils.py -> OS/bash/python detection
```

## PR And Commit Counting

This repository currently has no Git metadata in the local workspace, so contributor and PR metrics cannot be generated from inside the repo alone.

If the project is in a git checkout, you can now run:

```bash
bashron repo-stats
bashron repo-stats --base develop
```

If you want PR commit counts on GitHub, the simplest command is:

```bash
gh pr view <number> --json commits
```

Or with plain git for a branch comparison:

```bash
git rev-list --count origin/main..HEAD
```
