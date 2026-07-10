#!/usr/bin/env bash
# whoami.sh: print this pane's call-sign (assigning one if new).
# usage: whoami.sh [pane_id]   (defaults to $HERDR_PANE_ID)

set -euo pipefail

HERDR="${HERDR_BIN_PATH:-herdr}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

[ "${HERDR_ENV:-}" = "1" ] || { echo "not inside herdr" >&2; exit 64; }
PANE="${1:-${HERDR_PANE_ID:-}}"
[ -n "$PANE" ] || { echo "no pane id (HERDR_PANE_ID unset and none given)" >&2; exit 64; }

PANES_JSON="$("$HERDR" pane list)" python3 "$SCRIPT_DIR/msg_names.py" whoami "$PANE"
