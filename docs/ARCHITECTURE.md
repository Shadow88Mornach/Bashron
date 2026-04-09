# Architecture

This diagram is the fastest way for a new contributor to understand how `bashron` is wired.

```mermaid
flowchart TD
    U[User / Shell] --> CLI[cli.py]

    CLI --> STORE[store.py]
    CLI --> RUNNER[runner.py]
    CLI --> CONFIG[config.py]
    CLI --> CRON[cron.py]
    CLI --> PLATFORM[platform_utils.py]

    CONFIG --> CLEANER[cleaner.py]
    RUNNER --> LOGS[(~/.bashron/logs)]
    STORE --> DB[(~/.bashron/scripts.json)]
    CONFIG --> CFG[(~/.bashron/config.json)]
    CRON --> SYS[system crontab]

    CLI --> START[start daemon loop]
    START --> RUNNER
    START --> CLEANER
```

## Reading Order

1. `src/bashron/cli.py`
2. `src/bashron/store.py`
3. `src/bashron/runner.py`
4. `src/bashron/config.py`
5. `src/bashron/cleaner.py`
6. `src/bashron/cron.py`
7. `src/bashron/platform_utils.py`
8. `src/bashron/service.py`
