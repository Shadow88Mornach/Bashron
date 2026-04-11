# Changelog

All notable changes to bashron are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.2] - 2026-04-11

### Added
- `examples/hello-popup.sh` — macOS dialog demo. Pops up a native `osascript`
  dialog every `INTERVAL_SECONDS` (default 10) and polls `bashron list --json`
  each iteration, so running `bashron remove <name>` cleanly stops the loop
  with no Ctrl+C or stray background processes. Refuses to start until a
  matching job is scheduled, so the user always has a stop handle.
- `.github/workflows/release.yml` — tag-triggered release workflow that
  builds with `uv`, validates with `twine check`, and publishes to PyPI via
  trusted publishing (OIDC). No API tokens stored anywhere.
- `.github/workflows/ci.yml` — runs the full test suite on Python 3.9–3.13
  for every push and pull request.
- `RELEASING.md` — maintainer guide for the one-time PyPI trusted-publisher
  setup and the new three-command release flow.

## [0.1.1] - 2026-04-11

### Added
- `authors` field in `pyproject.toml` so PyPI displays the maintainer.

### Changed
- Version bumped from `0.1.0` to `0.1.1` — first version published through
  the GitHub Actions + PyPI trusted publishing workflow.

## [0.1.0] - 2026-04-10

### Added
- Natural-language time parsing. `--at 9am`, `--at 3:30pm`, and `--at 14:30`
  all work everywhere a time is accepted.
- `bashron` with no subcommand now shows a welcome panel on empty stores or
  the live status dashboard when jobs are scheduled.
- `bashron status --watch` — live auto-refreshing dashboard powered by Rich.
- `bashron add --explain` — dry-run preview that prints the schedule in plain
  English without persisting anything.
- Command aliases `ls`, `rm`, `ps` for list/remove/status.
- Full `bashron service install` support for macOS launchd and Linux systemd.
- `bashron export` / `bashron import` for sharing job configurations.

### Fixed
- Banner rendering bug where `[/]` leaked as literal text in the welcome
  panel because Rich parsed `\[` as an escaped literal.

[Unreleased]: https://github.com/shadowmornachAsia/Bashron/compare/v0.1.2...HEAD
[0.1.2]: https://github.com/shadowmornachAsia/Bashron/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/shadowmornachAsia/Bashron/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/shadowmornachAsia/Bashron/releases/tag/v0.1.0
