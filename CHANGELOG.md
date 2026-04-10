# Changelog

All notable changes to bashron are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/shadowmornachAsia/Bashron/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/shadowmornachAsia/Bashron/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/shadowmornachAsia/Bashron/releases/tag/v0.1.0
