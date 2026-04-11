#!/usr/bin/env bash
# bashron macOS popup loop example
#
# Pops up a native macOS dialog every few seconds until you remove the
# matching bashron job. Each popup auto-dismisses after INTERVAL_SECONDS
# so a forgotten prompt never ends up blocking your screen.
#
# --- Quickstart ---
#
#   # 1. Schedule it (any --at value — the schedule isn't the point; the
#   #    name is what this script polls to know when to stop).
#   bashron add hello-popup "$PWD/examples/hello-popup.sh" --at 9am
#
#   # 2. Start the loop in the background.
#   "$PWD/examples/hello-popup.sh" &
#
#   # 3. Popups now fire every 10 seconds. In the same (or another)
#   #    terminal, stop them any time with:
#   bashron remove hello-popup
#
# --- How it stops ---
#
# Every iteration, the script asks bashron whether its own job name still
# exists (`bashron list --json`). The moment you run `bashron remove
# hello-popup`, the next check returns false and the loop exits cleanly.
#
# --- Environment overrides ---
#
#   JOB_NAME=my-popup ./hello-popup.sh          # use a different job name
#   INTERVAL_SECONDS=5 ./hello-popup.sh         # 5-second cadence
#
# --- Platform ---
#
# macOS only — uses AppleScript via osascript. On Linux, replace the
# osascript block with `notify-send "bashron" "Hello!"` or similar.

set -euo pipefail

JOB_NAME="${JOB_NAME:-hello-popup}"
INTERVAL_SECONDS="${INTERVAL_SECONDS:-10}"

still_scheduled() {
    # Ask bashron (not the raw JSON file) so we stay decoupled from the
    # on-disk storage layout. The exact-match quoting ("name": "X") means
    # we won't false-positive on a prefix like "hello-popup-2".
    bashron list --json 2>/dev/null \
        | grep -q "\"name\": *\"${JOB_NAME}\""
}

# Platform guard — fail loud but non-fatal on non-Darwin so a scheduled
# run on Linux logs a useful message instead of crashing the daemon.
if [[ "$(uname)" != "Darwin" ]]; then
    echo "hello-popup.sh only works on macOS — current OS: $(uname)"
    exit 0
fi

# Require the job to exist before we start, otherwise the user has no
# handle to stop us with.
if ! still_scheduled; then
    cat <<EOF
hello-popup needs a bashron job named '${JOB_NAME}' before it can run,
so that 'bashron remove ${JOB_NAME}' has something to delete.

Schedule it first:
    bashron add ${JOB_NAME} "\$PWD/examples/hello-popup.sh" --at 9am

Then relaunch this script:
    "\$PWD/examples/hello-popup.sh" &

Stop the loop anytime with:
    bashron remove ${JOB_NAME}
EOF
    exit 1
fi

echo "[$(date)] ${JOB_NAME} loop started. Stop with: bashron remove ${JOB_NAME}"

while still_scheduled; do
    # `|| true` — if the user clicks the red close button instead of
    # Dismiss, osascript returns non-zero; we don't want that to crash
    # the loop, we want the next iteration's still_scheduled check to
    # decide whether to continue.
    osascript <<OSA || true
tell application "System Events"
    activate
    display dialog "Hello from bashron! Auto-dismissing in ${INTERVAL_SECONDS}s. Run 'bashron remove ${JOB_NAME}' to stop the loop." ¬
        with title "bashron" ¬
        buttons {"Dismiss"} ¬
        default button "Dismiss" ¬
        with icon note ¬
        giving up after ${INTERVAL_SECONDS}
end tell
OSA
    # Tiny breather so clicking Dismiss doesn't immediately re-fire with
    # no perceptible gap between popups.
    sleep 1
done

echo "[$(date)] '${JOB_NAME}' was removed from bashron — loop stopped."
