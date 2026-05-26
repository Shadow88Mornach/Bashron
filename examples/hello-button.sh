#!/usr/bin/env bash
# Show a native macOS dialog with a single "hello" button.
#
# Usage:
#   ./examples/hello-button.sh

set -euo pipefail

if [[ "$(uname)" != "Darwin" ]]; then
    echo "hello-button.sh only works on macOS — current OS: $(uname)"
    exit 0
fi

osascript <<'OSA'
tell application "System Events"
    activate
    display dialog "" with title "bashron" buttons {"hello"} default button "hello"
end tell
OSA
