#!/usr/bin/env bash
# bashron macOS popup example
#
# Pops up a native macOS dialog with a button, auto-dismissing after 30
# seconds so you never end up with a forgotten prompt blocking your screen.
#
# Try it once, right now:
#   chmod +x examples/hello-popup.sh
#   examples/hello-popup.sh
#
# Schedule it with bashron:
#   bashron add hello-popup examples/hello-popup.sh --at 9am
#   bashron run hello-popup        # trigger it immediately
#   bashron rm hello-popup         # delete the scheduled job
#
# Requires: macOS (uses osascript). On Linux, replace the osascript block
# with `notify-send "bashron" "Hello!"` or similar.

set -euo pipefail

# Guard against running on non-macOS systems so the scheduled job logs a
# clear message instead of crashing with "osascript: command not found".
if [[ "$(uname)" != "Darwin" ]]; then
    echo "hello-popup.sh only works on macOS — current OS: $(uname)"
    exit 0
fi

TITLE="bashron"
MESSAGE="Hello from bashron! This popup will auto-dismiss in 30 seconds."

# `display dialog` — modal popup with an OK button.
# `giving up after 30` — auto-dismiss after 30 seconds if untouched.
# `with icon note` — the little info icon on the left.
osascript <<EOF
tell application "System Events"
    activate
    display dialog "$MESSAGE" ¬
        with title "$TITLE" ¬
        buttons {"Dismiss"} ¬
        default button "Dismiss" ¬
        with icon note ¬
        giving up after 30
end tell
EOF

echo "[$(date)] hello-popup shown and dismissed."
