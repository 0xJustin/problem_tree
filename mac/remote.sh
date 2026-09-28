#!/usr/bin/env bash
# Run the cockpit ON THE CLUSTER (vault on local disk there) and forward it to this Mac.
#
#   bash '/path/to/problem-tree/mac/remote.sh'            # start + tunnel (Ctrl-C closes the tunnel)
#   bash '…/mac/remote.sh' status                                                           # is it running there?
#   bash '…/mac/remote.sh' restart                                                          # pick up code changes, then tunnel
#   bash '…/mac/remote.sh' stop
#   HOST=your.cluster.login.host bash '…/mac/remote.sh'    PORT=8890 bash '…/mac/remote.sh'
#
# No default host — set HOST or REMOTE_HOST to your cluster's login node. The remote server
# survives the tunnel closing. Forwards the cockpit port and the services pool 8892-8899
# (TensorBoard / observatory tabs).
set -uo pipefail
CMD="${1:-start}"
HOST="${HOST:-${REMOTE_HOST:-}}"; PORT="${PORT:-8891}"
[[ -n "$HOST" ]] || { echo "set HOST (or REMOTE_HOST) to your cluster's login node"; exit 1; }
REMOTE_TOOLS="${REMOTE_TOOLS:?set REMOTE_TOOLS to the problem-tree checkout path on the cluster}"
R="bash '$REMOTE_TOOLS/cockpit.sh'"

case "$CMD" in
  status)  exec ssh -o ConnectTimeout=10 "$HOST" "PORT=$PORT $R status" ;;
  stop)    exec ssh -o ConnectTimeout=10 "$HOST" "PORT=$PORT $R stop" ;;
  restart) ssh -o ConnectTimeout=10 "$HOST" "PORT=$PORT $R restart" || exit 1 ;;
  start)   ssh -o ConnectTimeout=10 "$HOST" "PORT=$PORT $R start" || exit 1 ;;
  *) sed -n 2,11p "$0"; exit 1 ;;
esac

if lsof -ti tcp:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "local port $PORT is in use (the Mac agent?). Stop it with mac/stop.sh, or use PORT=8890 $0"; exit 1
fi
echo "→ tunnel http://localhost:$PORT → $HOST  (Ctrl-C to close; the server keeps running)"
( sleep 2; curl -fs "http://localhost:$PORT/api/trees" >/dev/null 2>&1 && { echo "✓ http://localhost:$PORT"; command -v open >/dev/null && open "http://localhost:$PORT"; } ) &
FWD=(-L "$PORT:127.0.0.1:$PORT"); for p in $(seq 8892 8899); do [[ $p == "$PORT" ]] || FWD+=(-L "$p:127.0.0.1:$p"); done
exec ssh -N "${FWD[@]}" -o ServerAliveInterval=30 -o ServerAliveCountMax=3 "$HOST"
