#!/usr/bin/env bash
# Remove everything mac/install.sh put on this Mac. Touches nothing on the mount.
set -uo pipefail
LABEL=org.problem-tree.cockpit
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
rm -rf "$HOME/Library/Application Support/problem-tree" "$HOME/Library/Caches/problem-tree" "$HOME/Applications/Problem Tree.app"
echo "removed launch agent, venv, config, cache and Dock app (log left at ~/Library/Logs/problem-tree.log)"
