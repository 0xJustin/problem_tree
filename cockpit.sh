#!/usr/bin/env bash
# The cockpit on the cluster (vault on local disk). One process, one pidfile, one log.
#
#   cockpit.sh                 foreground (Ctrl-C stops)
#   cockpit.sh start           background; no-op if already answering
#   cockpit.sh stop
#   cockpit.sh restart         pick up code changes
#   cockpit.sh status
#   cockpit.sh logs            tail -f the log
#   PORT=8892 cockpit.sh start
#
# From the Mac, reach it with mac/remote.sh (tunnel; set HOST/REMOTE_HOST to your cluster login node).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PORT:-8891}"
PID=/tmp/problem-tree-cockpit-$USER.pid
LOG=/tmp/problem-tree-cockpit-$USER.log
PY="$HERE/.venv/bin/python"

up() { curl -fs "http://127.0.0.1:$PORT/api/trees" >/dev/null 2>&1; }
pid_alive() { [[ -f $PID ]] && kill -0 "$(cat "$PID")" 2>/dev/null; }

start() {
  if up; then echo "already up: http://127.0.0.1:$PORT/ ($(hostname))"; return; fi
  nohup "$PY" "$HERE/serve.py" --port "$PORT" >"$LOG" 2>&1 &
  echo $! >"$PID"
  for _ in $(seq 1 30); do up && { echo "cockpit up: http://127.0.0.1:$PORT/  host $(hostname)  pid $(cat "$PID")  log $LOG"; return; }; sleep 1; done
  echo "not answering after 30 s; log:"; tail -n 20 "$LOG"; exit 1
}
stop() {
  if pid_alive; then kill "$(cat "$PID")" && echo "stopped pid $(cat "$PID")"; rm -f "$PID"; fi
  # anything else holding the port (a hand-started server)
  for p in $(ss -ltnp 2>/dev/null | grep -oP ":$PORT .*?pid=\K[0-9]+" | sort -u); do kill "$p" 2>/dev/null && echo "stopped pid $p on :$PORT"; done
}
status() {
  if up; then echo "up: http://127.0.0.1:$PORT/ on $(hostname)$(pid_alive && echo "  pid $(cat "$PID")")"; else echo "down"; fi
  [[ -f $LOG ]] && { echo "--- last log lines ($LOG) ---"; tail -n 5 "$LOG"; }
}

case "${1:-fg}" in
  start|-d) start ;;
  stop) stop ;;
  restart) stop; sleep 1; start ;;
  status) status ;;
  logs) tail -n 40 -f "$LOG" ;;
  fg) exec "$PY" "$HERE/serve.py" --port "$PORT" ;;
  *) sed -n 2,12p "$0"; exit 1 ;;
esac
