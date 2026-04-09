# bashron TODO — Make It Go Viral & Actually Easy to Use

## Why This Document Exists

bashron has a great core: zero-config, named jobs, rich terminal output, daemon + cron dual-mode.
But right now it's invisible. Nobody will find it, and the few who do will hit friction before
they see the value. This TODO fixes both problems.

---

## TIER 1 — Shareability (makes it go viral)

### 1. `bashron init` — interactive onboarding wizard
**Why:** First impressions decide virality. A new user types `bashron` and sees a wall of help
text. Instead, `bashron init` should walk them through adding their first job in 30 seconds.
Screencasts of great CLIs always show an interactive wizard — it's the thing people screenshot
and share.

```
$ bashron init
? What should we call this job? › nightly-backup
? Path to your script? › ~/scripts/backup.sh
? What time should it run? (HH:MM) › 02:00
✓ Job added! Run `bashron start` to launch the daemon.
```

### 2. A beautiful `--demo` / `bashron demo` command
**Why:** The #1 way CLI tools spread on Twitter/Reddit is a terminal recording. A built-in demo
command that creates a fake job, runs it, and shows off the rich output lets anyone record and
share a perfect 10-second clip — no setup required.

### 3. ASCII art / banner on `bashron start`
**Why:** "Warrior-class" branding is in the description but invisible. A one-time startup
banner (suppressible with `--quiet`) gives the tool personality. People share personality.

### 4. `bashron export` / `bashron import`
**Why:** "Here's my bashron setup" is a sharing moment. Export jobs to a `bashronfile.json`
that others can `bashron import` to instantly replicate a workflow. Enables blog posts like
"My personal automation stack."

---

## TIER 2 — Ease of Use (reduces abandonment)

### 5. Auto-install as a background service (launchd / systemd)
**Why:** `bashron start` requires a terminal to stay open — that's a dealbreaker for real
daily use. The tool promises "warrior-class scheduling" but the daemon dies when you close
iTerm. Add `bashron service install` that registers a launchd plist (macOS) or systemd unit
(Linux) so it survives reboots.

```
$ bashron service install   # writes ~/.config/systemd/user/bashron.service
$ bashron service status
$ bashron service uninstall
```

### 6. `--every` flag: non-daily intervals
**Why:** Daily at HH:MM covers maybe 30% of real automation needs. People want
`--every 1h`, `--every 30m`, `--on monday,wednesday`. Without this, users hit a wall
immediately and switch to bare cron.

```
$ bashron add sync ~/scripts/sync.sh --every 30m
$ bashron add weekly-report ~/scripts/report.sh --on friday --at 09:00
```

### 7. `bashron status` — live dashboard
**Why:** After adding 3+ jobs, users need a single-pane view of what's scheduled, last run,
last exit code, next run time. `bashron list` shows config but not runtime state. A live
`status` command (refreshes every N seconds with `--watch`) makes the tool feel alive and
worth showing off.

| Name            | Next Run     | Last Run  | Exit |
|-----------------|-------------|-----------|------|
| nightly-backup  | 02:00 (8h)  | yesterday | 0    |
| sync            | in 12 min   | 4:47 PM   | 0    |

### 8. Script templates: `bashron new <name>`
**Why:** Many users know they want automation but don't have a script yet. `bashron new`
scaffolds a commented `.sh` template at `~/scripts/<name>.sh` and immediately adds it.
Reduces the distance from "I want to automate X" to "it's running."

### 9. Notify on failure (macOS notification / webhook)
**Why:** A job silently failing at 2 AM defeats the whole purpose. Add opt-in failure
notifications: macOS native notifications via `osascript`, and a `--webhook <url>` option
for Slack/Discord. This is the feature that makes users tell their team about bashron.

### 10. `bashron logs --follow` (tail -f equivalent)
**Why:** Developers debug by watching logs in real time. One missing flag (`--follow` / `-f`)
makes the whole experience feel unfinished. This is a 15-minute implementation.

---

## TIER 3 — Distribution & Discovery

### 11. Publish to PyPI + add a Homebrew tap
**Why:** `pip install bashron` works but `brew install bashron` is how CLI tools reach
developers who never use pip. A Homebrew tap (even self-hosted) unlocks a huge audience and
makes the tool feel "real."

### 12. A 60-second terminal recording in the README
**Why:** The README has code blocks but no visual. A GIF/SVG recording (use `vhs` or
`asciinema`) showing the full add → start → logs flow converts README visitors into users.
This is the single highest-ROI change for GitHub traffic.

### 13. Add GitHub topics: `automation`, `cron`, `cli`, `productivity`, `bash`
**Why:** GitHub topic search is a real discovery channel for CLI tools. Takes 30 seconds.

### 14. Post on Hacker News "Show HN" and r/commandline
**Why:** bashron is a genuine "I built this tool I use every day" story. Those communities
reward exactly this kind of focused, well-crafted CLI tool. A good Show HN post can drive
500–2000 GitHub stars in 48 hours.

---

## Quick Wins (< 1 hour each)

- [ ] `bashron logs <name> --follow` — tail log in real time
- [ ] `bashron list --json` — machine-readable output for scripting
- [ ] `bashron run --all` — run every job immediately (useful for testing)
- [ ] `bashron cron install` should confirm before overwriting existing crontab
- [ ] Warn if scheduled time has already passed today when adding a job
- [ ] `bashron --version` should also show Python version and platform

---

## Priority Order

1. `bashron service install` (launchd/systemd) — daemon is currently not production-usable
2. Terminal recording in README — biggest ROI for discovery
3. `--every` interval flag — unblocks the most common use cases beyond daily
4. `bashron init` wizard — onboarding is the make-or-break moment
5. Failure notifications — makes the tool trustworthy for real automation
