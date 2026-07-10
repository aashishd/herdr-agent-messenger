#!/usr/bin/env bash
# compose.sh: caller-side compose flow for Messenger.
# Splits the invoking pane for the Messenger board (target picker + message
# box), waits for the user's input there, then either delivers directly (ENTER) or
# reports a DRAFT-REQUEST (TAB) for the calling agent to fulfil.
# usage: compose.sh [intent]
#   with a non-empty intent argument only target selection runs; the
#   result is a DRAFT-REQUEST carrying that intent.
# env: MSG_DRY=1 makes direct mode use send.sh --dry-run.
# All user outcomes (sent, draft, cancelled, not-sent) exit 0; nonzero
# is reserved for environment errors.

set -euo pipefail

HERDR="${HERDR_BIN_PATH:-herdr}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

[ "${HERDR_ENV:-}" = "1" ] || { echo "not inside herdr" >&2; exit 64; }
command -v fzf >/dev/null || { echo "fzf not installed (brew install fzf)" >&2; exit 64; }

INTENT="${1:-}"
[ "$INTENT" = '$ARGUMENTS' ] && INTENT=""

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

PANES_JSON="$("$HERDR" pane list)" WS_JSON="$("$HERDR" workspace list)" \
SELF_PANE="${HERDR_PANE_ID:-}" WORK="$WORK" MSG_DIR="$SCRIPT_DIR" python3 <<'PY' > "$WORK/list"
import json, os, sys
sys.path.insert(0, os.environ["MSG_DIR"])
import msg_names
panes = json.loads(os.environ["PANES_JSON"])["result"]["panes"]
ws = json.loads(os.environ["WS_JSON"])["result"]["workspaces"]
labels = {w["workspace_id"]: w["label"] for w in ws}
names = msg_names.ensure_names(panes)
self_pane = os.environ["SELF_PANE"]
if self_pane in names:
    label = next((labels.get(p["workspace_id"], "?") for p in panes
                  if p["pane_id"] == self_pane), "?")
    with open(os.path.join(os.environ["WORK"], "self"), "w") as f:
        f.write(f"{names[self_pane]} · {label}\n")
for p in panes:
    if not p.get("agent") or p["pane_id"] == self_pane:
        continue
    label = labels.get(p["workspace_id"], "?")
    display = (f"{names[p['pane_id']]} · {label} · {p['agent']}"
               f" · {p.get('agent_status', 'unknown')} · {p['pane_id']}")
    print(f"{p['pane_id']}\t{display}")
PY

[ -s "$WORK/list" ] || { echo "NO-TARGETS"; exit 0; }
[ -n "$INTENT" ] && touch "$WORK/intent"
SELF_DESC="$(cat "$WORK/self" 2>/dev/null || true)"

CURRENT_PANE="${HERDR_PANE_ID:?HERDR_PANE_ID not set}"
OPEN_JSON="$("$HERDR" pane split "$CURRENT_PANE" --direction down --ratio 0.35 \
  --env "MSG_WORKDIR=$WORK" --env "MSG_BOARD_SCRIPT=$SCRIPT_DIR/compose-pane.sh" --focus)"
BOARD_PANE="$(printf '%s' "$OPEN_JSON" | python3 -c '
import sys, json
r = json.load(sys.stdin).get("result", {})
pane = r.get("pane") or r
print(pane.get("pane_id", ""))' 2>/dev/null || true)"
[ -n "$BOARD_PANE" ] || { echo "BOARD-FAILURE"; exit 0; }

sleep 0.3
if ! "$HERDR" pane run "$BOARD_PANE" 'bash "$MSG_BOARD_SCRIPT"; exit'; then
  "$HERDR" pane close "$BOARD_PANE" 2>/dev/null || true
  echo "BOARD-FAILURE"
  exit 0
fi

steps=0
while [ ! -f "$WORK/done" ] && [ "$steps" -lt 340 ]; do sleep 0.5; steps=$((steps + 1)); done
"$HERDR" pane close "$BOARD_PANE" 2>/dev/null || true

[ -f "$WORK/done" ] || { echo "TIMEOUT"; exit 0; }
OUTCOME="$(cat "$WORK/outcome" 2>/dev/null || true)"
[ "$OUTCOME" = "cancelled" ] && { echo "CANCELLED"; exit 0; }
[ "$OUTCOME" = "submitted" ] || { echo "BOARD-FAILURE"; exit 0; }
[ -s "$WORK/target" ] || { echo "BOARD-FAILURE"; exit 0; }

TARGET_LINE="$(cat "$WORK/target")"
PANE_ID="$(printf '%s\n' "$TARGET_LINE" | cut -f1)"
TARGET_DESC="$(printf '%s\n' "$TARGET_LINE" | cut -f2)"

if [ -n "$INTENT" ]; then
  printf 'DRAFT-REQUEST\nfrom: %s\ntarget: %s\nintent: %s\n' "$SELF_DESC" "$TARGET_DESC" "$INTENT"
  exit 0
fi

[ -s "$WORK/mode" ] || { echo "BOARD-FAILURE"; exit 0; }
MODE="$(cat "$WORK/mode")"
TEXT="$(cat "$WORK/text" 2>/dev/null || true)"
[ -n "$TEXT" ] || { echo "BOARD-FAILURE"; exit 0; }

if [ "$MODE" = "draft" ]; then
  printf 'DRAFT-REQUEST\nfrom: %s\ntarget: %s\nintent: %s\n' "$SELF_DESC" "$TARGET_DESC" "$TEXT"
  exit 0
fi

DRY_FLAG=""
[ "${MSG_DRY:-}" = "1" ] && DRY_FLAG="--dry-run"
if OUT="$(bash "$SCRIPT_DIR/send.sh" "$PANE_ID" "$TEXT" --timeout 90 $DRY_FLAG 2>&1)"; then
  printf 'SENT-DIRECT%s\nfrom: %s\ntarget: %s\ntext: %s\ndelivery: %s\n' \
    "${DRY_FLAG:+ (dry-run)}" "$SELF_DESC" "$TARGET_DESC" "$TEXT" "$OUT"
else
  printf 'NOT-SENT\ntarget: %s\ntext: %s\nerror: %s\n' "$TARGET_DESC" "$TEXT" "$OUT"
fi
