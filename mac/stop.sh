#!/usr/bin/env bash
# Stop the Mac app agent (it will start again at next login unless you uninstall) and free the port.
#   bash '/path/to/problem-tree/mac/stop.sh'
set -uo pipefail
LABEL=org.problem-tree.cockpit; PORT="${PORT:-8891}"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null && echo "agent stopped"
for pid in $(lsof -ti tcp:"$PORT" -sTCP:LISTEN 2>/dev/null); do kill "$pid" && echo "stopped pid $pid on :$PORT"; done
echo "start again: mac/launch.sh"
