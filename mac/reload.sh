#!/usr/bin/env bash
# Reload the Mac app after a code change (same as restart.sh), then reopen the page.
#   bash '/path/to/problem-tree/mac/reload.sh'
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$HERE/restart.sh" && open "http://localhost:${PORT:-8891}"
