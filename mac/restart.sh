#!/usr/bin/env bash
# Restart the cockpit on this Mac, whichever way it is currently running.
#
#   bash '/path/to/problem-tree/mac/restart.sh'
#
# - launch agent loaded  -> kickstart it
# - plist present, not loaded -> bootstrap it (this is the state after a failed install step)
# - no plist -> tells you to run mac/install.sh
# Anything else listening on the port (a server started by hand) is stopped first, otherwise
# the agent's server cannot bind and launchd would keep retrying.
set -uo pipefail
LABEL=org.problem-tree.cockpit
PORT="${PORT:-8891}"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

# stop whatever holds the port
for pid in $(lsof -ti tcp:"$PORT" -sTCP:LISTEN 2>/dev/null); do
  echo "stopping pid $pid on :$PORT ($(ps -o comm= -p "$pid"))"; kill "$pid"
done

if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
  launchctl kickstart -k "$DOMAIN/$LABEL" && echo "kickstarted $LABEL"
elif [[ -f "$PLIST" ]]; then
  launchctl bootstrap "$DOMAIN" "$PLIST" && echo "bootstrapped $LABEL from $PLIST"
else
  echo "no $PLIST — run mac/install.sh first"; exit 1
fi

for i in $(seq 1 20); do curl -fs "http://localhost:$PORT/api/trees" >/dev/null 2>&1 && { echo "✓ up: http://localhost:$PORT"; exit 0; }; sleep 1; done
echo "not answering yet — last log lines:"; tail -n 5 "$HOME/Library/Logs/problem-tree.log" 2>/dev/null
