#!/usr/bin/env bash
# Install the problem-tree cockpit as an always-on background app on this Mac.
#
#   bash '/path/to/problem-tree/mac/install.sh'
#
# What it does (all on the Mac's own disk except the code, which stays on the mount so
# updates are picked up on restart):
#   ~/Library/Application Support/problem-tree/.venv     Python 3.13 + fastapi etc. (via uv)
#   ~/Library/Application Support/problem-tree/config.yaml   Mac paths + path_map to the cluster
#   ~/Library/Application Support/problem-tree/run.sh    waits for the volume, then serves
#   ~/Library/LaunchAgents/org.problem-tree.cockpit.plist   starts at login, restarts on exit
#   ~/Applications/Problem Tree.app                      Dock icon that opens http://localhost:8891
#
# Override with env vars: MOUNT, REMOTE_HOME, PORT, SSH_HOST (login node; enables the TensorBoard /
# observatory buttons — needs key-based ssh). Re-run any time; it is idempotent.
# Uninstall: mac/uninstall.sh
set -euo pipefail

TOOLS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"        # this checkout (on the mount)
MOUNT="${MOUNT:?set MOUNT=/Volumes/YOUR_SHARE\$/YOU, the cluster home as mounted on this Mac}"
REMOTE_HOME="${REMOTE_HOME:?set REMOTE_HOME=/path/on/the/cluster, the same directory over there}"
SSH_HOST="${SSH_HOST:-}"                                        # login node for TensorBoard / observatory (unset to disable)
PORT="${PORT:-8891}"
LABEL=org.problem-tree.cockpit
APP="$HOME/Library/Application Support/problem-tree"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
VAULT="$MOUNT/brain"

[[ -d "$VAULT" ]] || { echo "vault not found at $VAULT — mount the volume first (or set MOUNT=…)"; exit 1; }
mkdir -p "$APP" "$HOME/Library/Logs" "$HOME/Library/LaunchAgents" "$HOME/Library/Caches/problem-tree" "$HOME/Applications"

echo "→ python environment (uv)"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
uv venv --python 3.13 "$APP/.venv" -q
uv pip install -q --python "$APP/.venv/bin/python" fastapi "uvicorn[standard]" pyyaml markdown

echo "→ config"
cat > "$APP/config.yaml" <<EOF
# problem-tree cockpit, Mac configuration (written by mac/install.sh; edit freely)
vault: "$VAULT"
tree_globs:
  - 02-Projects/*/problems
  - 02-Projects/*/*/problems
session_roots:            # cluster logs via the mount, plus any local pi / Claude sessions
  - "$MOUNT/.pi/agent/sessions"
  - "$MOUNT/.claude/projects"
  - ~/.pi/agent/sessions
  - ~/.claude/projects
session_cache: ~/Library/Caches/problem-tree/sessions.json
# repos: your-repo: https://github.com/you/your-repo   (used to link fix:/before:/after: entries)
# default_repo: your-repo
path_map:
  "$MOUNT": "$REMOTE_HOME"
tree_ttl: 5
note_index_ttl: 120
note_index_skip: [media]
experiment_globs: ["02-Projects/*/*/experiments"]
run_media: "../media/single/{run_id}"
EOF
if [[ -n "$SSH_HOST" ]]; then
cat >> "$APP/config.yaml" <<EOF
services:                 # run cluster-side over ssh, forwarded to this Mac (needs key-based ssh to ssh_host)
  ssh_host: $SSH_HOST
  port_pool: [8892, 8899]
  # repo_roots: your-repo: $REMOTE_HOME/path/to/your-repo   (cluster-side paths for the observatory/TensorBoard buttons)
  # tensorboard: $REMOTE_HOME/path/to/tensorboard
  # observatory: {script: ..., spec: ..., bundle_subdir: ..., queue: ..., walltime: ..., mode: ...}
EOF
fi
# figure tiers + stage order: copy the cluster config's scheme so both hosts agree
"$APP/.venv/bin/python" - "$TOOLS/config.yaml" "$APP/config.yaml" <<'PY'
import sys, yaml
src = yaml.safe_load(open(sys.argv[1]))
with open(sys.argv[2], "a") as dst:
    dst.write("\n" + yaml.safe_dump({k: src[k] for k in ("figure_tiers", "stage_order") if k in src}, sort_keys=False, allow_unicode=True))
PY

echo "→ run.sh"
cat > "$APP/run.sh" <<EOF
#!/usr/bin/env bash
# Started by launchd. Waits until the volume is mounted, then serves the cockpit.
VAULT=$(printf '%q' "$VAULT")
TOOLS=$(printf '%q' "$TOOLS")
APP=$(printf '%q' "$APP")
until [[ -f "\$TOOLS/serve.py" ]]; do sleep 20; done
exec "\$APP/.venv/bin/python" "\$TOOLS/serve.py" --config "\$APP/config.yaml" --port $PORT
EOF
chmod +x "$APP/run.sh"

echo "→ launch agent ($LABEL)"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$APP/run.sh</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>15</integer>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/problem-tree.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/problem-tree.log</string>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>/usr/bin:/bin:/usr/sbin:/sbin:$HOME/.local/bin</string></dict>
</dict></plist>
EOF
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
for pid in $(lsof -ti tcp:"$PORT" -sTCP:LISTEN 2>/dev/null); do echo "  stopping pid $pid already on :$PORT"; kill "$pid"; done
if launchctl bootstrap "gui/$(id -u)" "$PLIST"; then echo "  loaded $LABEL"; else echo "  !! launchctl bootstrap failed — run mac/restart.sh after fixing the message above"; fi

echo "→ Dock app"
rm -rf "$HOME/Applications/Problem Tree.app"
osacompile -o "$HOME/Applications/Problem Tree.app" -e "open location \"http://localhost:$PORT\"" >/dev/null

for i in $(seq 1 20); do curl -fs "http://localhost:$PORT/api/trees" >/dev/null 2>&1 && break; sleep 1; done
if curl -fs "http://localhost:$PORT/api/trees" >/dev/null 2>&1; then
  echo "✓ cockpit is up: http://localhost:$PORT"
else
  echo "… server not answering yet; check ~/Library/Logs/problem-tree.log"
fi
cat <<EOF

Done. It starts at login and restarts itself; log: ~/Library/Logs/problem-tree.log
  • everyday:  mac/launch.sh (start + open)   mac/reload.sh (after code changes)   mac/stop.sh
  • cluster-hosted instead:  mac/remote.sh [start|status|restart|stop]   (set HOST to your cluster login node)
  • ~/Applications/Problem Tree.app  — Dock icon, opens the cockpit in your browser
  • nicer: open http://localhost:$PORT in Safari → File → Add to Dock (own window, own icon)
    or Chrome → ⋮ → Save and share → Create shortcut → "Open as window"
  • restart after a code change:  bash "$TOOLS/mac/restart.sh"
  • stop:  launchctl bootout gui/\$(id -u)/$LABEL
EOF
