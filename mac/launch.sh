#!/usr/bin/env bash
# Start the Mac app (launchd agent) if it is not running and open the cockpit in the browser.
#   bash '/path/to/problem-tree/mac/launch.sh'
set -uo pipefail
LABEL=org.problem-tree.cockpit; PORT="${PORT:-8891}"; PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"; DOMAIN="gui/$(id -u)"
if ! curl -fs "http://localhost:$PORT/api/trees" >/dev/null 2>&1; then
  if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then launchctl kickstart "$DOMAIN/$LABEL"
  elif [[ -f "$PLIST" ]]; then launchctl bootstrap "$DOMAIN" "$PLIST"
  else echo "not installed — run mac/install.sh first"; exit 1; fi
  for _ in $(seq 1 30); do curl -fs "http://localhost:$PORT/api/trees" >/dev/null 2>&1 && break; sleep 1; done
fi
curl -fs "http://localhost:$PORT/api/trees" >/dev/null 2>&1 && { echo "✓ http://localhost:$PORT"; open "http://localhost:$PORT"; } || { echo "not answering — log:"; tail -n 8 "$HOME/Library/Logs/problem-tree.log"; exit 1; }
