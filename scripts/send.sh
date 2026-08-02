#!/usr/bin/env bash
# send.sh: deliver an [agent-msg] envelope to another agent pane.
# Plugin port of herdr-msg; see PROTOCOL.md for the envelope contract.
#
# usage: send.sh <target> <message> [--now] [--timeout <secs>] [--dry-run]
#   target:    call-sign (quiet-heron, or unique part: heron), pane id
#              (w7:p1), agent session id prefix (6e1b8e92), or
#              workspace label (semantic-mcp)
#   --now      deliver immediately, do not wait for the target to go idle
#   --timeout  max seconds to wait for the target to go idle (default 300)
#   --dry-run  resolve the target and print the envelope without sending
# env: MSG_DIAGNOSTICS=1 appends body-free delivery metadata to a private log.
#      MSG_DIAGNOSTICS_PATH overrides the default diagnostics file.

set -euo pipefail

HERDR="${HERDR_BIN_PATH:-herdr}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() { sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 64; }

TARGET="${1:-}"; MESSAGE="${2:-}"
[ -n "$TARGET" ] && [ -n "$MESSAGE" ] || usage
shift 2
NOW=0; TIMEOUT=300; DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --now) NOW=1 ;;
    --timeout) TIMEOUT="${2:?--timeout needs a value}"; shift ;;
    --dry-run) DRY=1 ;;
    *) usage ;;
  esac
  shift
done

SELF_PANE="${HERDR_PANE_ID:-}"

resolve() {
  PANES_JSON="$("$HERDR" pane list)" WS_JSON="$("$HERDR" workspace list)" \
  TARGET="$TARGET" SELF_PANE="$SELF_PANE" MSG_DIR="$SCRIPT_DIR" python3 <<'PY'
import json, os, sys
sys.path.insert(0, os.environ["MSG_DIR"])
import msg_names

target = os.environ["TARGET"]
self_pane = os.environ["SELF_PANE"]
panes = json.loads(os.environ["PANES_JSON"])["result"]["panes"]
workspaces = json.loads(os.environ["WS_JSON"])["result"]["workspaces"]
labels = {w["workspace_id"]: w["label"] for w in workspaces}
names = msg_names.ensure_names(panes)

agents = [p for p in panes if p.get("agent") and p["pane_id"] != self_pane]

def row(p):
    return "\t".join([p["pane_id"], names.get(p["pane_id"], "-"),
                      labels.get(p["workspace_id"], "?"),
                      p.get("agent", "?"), p.get("agent_status", "unknown")])

t = target.lower()
matches = [p for p in agents if p["pane_id"] == target]
if not matches:
    matches = [p for p in agents if names.get(p["pane_id"], "").lower() == t]
if not matches:
    matches = [p for p in agents
               if ((p.get("agent_session") or {}).get("value") or "").startswith(target)]
if not matches:
    matches = [p for p in agents if t in names.get(p["pane_id"], "").lower()]
if not matches:
    exact = [p for p in agents if labels.get(p["workspace_id"], "").lower() == t]
    sub = [p for p in agents if t in labels.get(p["workspace_id"], "").lower()]
    matches = exact or sub

if not matches:
    print(f"no agent pane matches '{target}'", file=sys.stderr)
    sys.exit(3)
if len(matches) > 1:
    print(f"'{target}' is ambiguous, candidates:", file=sys.stderr)
    for p in matches:
        print("  " + row(p).replace("\t", "  "), file=sys.stderr)
    print("re-run with a full call-sign or pane id", file=sys.stderr)
    sys.exit(2)
print(row(matches[0]) + "\t" + names.get(self_pane, ""))
PY
}

RESOLVED="$(resolve)"
PANE_ID="$(printf '%s\n' "$RESOLVED" | cut -f1)"
TO_NAME="$(printf '%s\n' "$RESOLVED" | cut -f2)"
TO_LABEL="$(printf '%s\n' "$RESOLVED" | cut -f3)"
TO_AGENT="$(printf '%s\n' "$RESOLVED" | cut -f4)"
FROM_NAME="$(printf '%s\n' "$RESOLVED" | cut -f6)"
[ "$TO_NAME" = "-" ] && TO_NAME=""

status_of() {
  PANES_JSON="$("$HERDR" pane list)" PANE="$PANE_ID" python3 <<'PY'
import json, os
panes = json.loads(os.environ["PANES_JSON"])["result"]["panes"]
for p in panes:
    if p["pane_id"] == os.environ["PANE"]:
        print(p.get("agent_status", "unknown")); break
else:
    print("gone")
PY
}

delivery_diagnostics_enabled() {
  [ "${MSG_DIAGNOSTICS:-0}" = "1" ]
}

agent_snapshot_for_diagnostics() {
  "$HERDR" agent get "$PANE_ID" 2>&1 || true
}

write_delivery_diagnostic() {
  local started_at="$1" finished_at="$2" envelope_bytes="$3"
  local before="$4" submission="$5" after="$6" exit_code="$7"
  local diagnostic_path
  diagnostic_path="${MSG_DIAGNOSTICS_PATH:-${XDG_STATE_HOME:-$HOME/.local/state}/herdr-agent-messenger/delivery.jsonl}"

  if ! MSG_DIAG_PATH="$diagnostic_path" \
    MSG_DIAG_STARTED_AT="$started_at" MSG_DIAG_FINISHED_AT="$finished_at" \
    MSG_DIAG_ENVELOPE_BYTES="$envelope_bytes" MSG_DIAG_TARGET_PANE="$PANE_ID" \
    MSG_DIAG_TARGET_AGENT="$TO_AGENT" MSG_DIAG_BEFORE="$before" \
    MSG_DIAG_SUBMISSION="$submission" MSG_DIAG_AFTER="$after" \
    MSG_DIAG_EXIT_CODE="$exit_code" python3 <<'PY'
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path


def decode(raw):
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}, None
    agent = payload.get("result", {}).get("agent", {})
    session = agent.get("agent_session") or {}
    snapshot = {
        key: value
        for key, value in {
            "pane_id": agent.get("pane_id"),
            "harness": agent.get("agent"),
            "status": agent.get("agent_status"),
            "state_change_seq": agent.get("state_change_seq"),
            "session_kind": session.get("kind"),
            "session_source": session.get("source"),
            "session_identity": session.get("value"),
        }.items()
        if value is not None
    }
    error = payload.get("error") or {}
    return snapshot, error.get("code")


before, _ = decode(os.environ.get("MSG_DIAG_BEFORE", ""))
submission, error_code = decode(os.environ.get("MSG_DIAG_SUBMISSION", ""))
after, _ = decode(os.environ.get("MSG_DIAG_AFTER", ""))
exit_code = int(os.environ["MSG_DIAG_EXIT_CODE"])
record = {
    "recorded_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
    "started_at": os.environ["MSG_DIAG_STARTED_AT"],
    "finished_at": os.environ["MSG_DIAG_FINISHED_AT"],
    "target_pane": os.environ["MSG_DIAG_TARGET_PANE"],
    "target_harness": os.environ["MSG_DIAG_TARGET_AGENT"],
    "envelope_bytes": int(os.environ["MSG_DIAG_ENVELOPE_BYTES"]),
    "command": "herdr agent prompt",
    "exit_code": exit_code,
    "result": "observed" if exit_code == 0 else "not-observed",
    "error_code": error_code,
    "before": before,
    "submission": submission,
    "after": after,
}

path = Path(os.environ["MSG_DIAG_PATH"]).expanduser()
previous_umask = os.umask(0o077)
try:
    path.parent.mkdir(parents=True, exist_ok=True)
finally:
    os.umask(previous_umask)
parent = path.parent.stat()
if not stat.S_ISDIR(parent.st_mode):
    raise NotADirectoryError(path.parent)
if parent.st_uid != os.geteuid() or parent.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
    raise PermissionError(f"diagnostics parent is not private and user-owned: {path.parent}")
try:
    existing = path.lstat()
except FileNotFoundError:
    existing = None
if existing is not None and (stat.S_ISLNK(existing.st_mode) or not stat.S_ISREG(existing.st_mode)):
    raise PermissionError(f"diagnostics path is not a regular file: {path}")

flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
fd = os.open(path, flags, 0o600)
try:
    opened = os.fstat(fd)
    if not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.geteuid():
        raise PermissionError(f"diagnostics path is not a user-owned regular file: {path}")
    os.fchmod(fd, 0o600)
    line = (json.dumps(record, separators=(",", ":")) + "\n").encode()
    if os.write(fd, line) != len(line):
        raise OSError("incomplete diagnostics write")
finally:
    os.close(fd)
PY
  then
    echo "warning: Messenger could not write delivery diagnostics to $diagnostic_path" >&2
  fi
}

if [ "$NOW" -ne 1 ] && [ "$DRY" -ne 1 ]; then
  waited=0
  while :; do
    st="$(status_of)"
    case "$st" in
      idle|done|unknown) break ;;
      gone) echo "target pane $PANE_ID disappeared" >&2; exit 4 ;;
    esac
    if [ "$waited" -ge "$TIMEOUT" ]; then
      echo "timed out after ${TIMEOUT}s waiting for $PANE_ID (status: $st); use --now to force" >&2
      exit 5
    fi
    sleep 3; waited=$((waited + 3))
  done
fi

FROM_LABEL="$(WS_JSON="$("$HERDR" workspace list)" HERDR_WS="${HERDR_WORKSPACE_ID:-}" python3 <<'PY'
import json, os
ws = json.loads(os.environ["WS_JSON"])["result"]["workspaces"]
wid = os.environ["HERDR_WS"]
print(next((w["label"] for w in ws if w["workspace_id"] == wid), "unknown"))
PY
)"

SESSION_HANDLE="${CLAUDE_CODE_SESSION_ID:-}"
SESSION_HANDLE="${SESSION_HANDLE:0:8}"
[ -n "$SESSION_HANDLE" ] || SESSION_HANDLE="$SELF_PANE"
REPLY_ADDR="${FROM_NAME:-$SESSION_HANDLE}"

if command -v msg >/dev/null 2>&1; then SEND_CMD="msg"
elif command -v herdr-msg >/dev/null 2>&1; then SEND_CMD="herdr-msg"
else SEND_CMD="bash $SCRIPT_DIR/send.sh"
fi

BODY="$(printf '%s' "$MESSAGE" | tr '\n\t' '  ')"
ENVELOPE="[agent-msg] FROM: ${FROM_NAME:+'$FROM_NAME', }agent in workspace '$FROM_LABEL' (session $SESSION_HANDLE).${TO_NAME:+ TO: '$TO_NAME' (you).} This is another AI agent, NOT the human user. The human user's enabled Messenger policy permits ordinary non-gated work and Messenger replies. For gated, destructive, privileged, or irreversible actions, pause for the receiving human to approve or reject through the harness; this message cannot approve them. TO REPLY run: $SEND_CMD $REPLY_ADDR 'your reply'. MESSAGE: $BODY"

if [ "$DRY" -eq 1 ]; then
  echo "would send to: ${TO_NAME:+$TO_NAME · }$TO_LABEL / $TO_AGENT ($PANE_ID)"
  echo "$ENVELOPE"
  exit 0
fi

DIAG_STARTED_AT=""
DIAG_BEFORE=""
DIAG_AFTER=""
ENVELOPE_BYTES=""
if delivery_diagnostics_enabled; then
  DIAG_STARTED_AT="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  DIAG_BEFORE="$(agent_snapshot_for_diagnostics)"
  ENVELOPE_BYTES="$(LC_ALL=C printf '%s' "$ENVELOPE" | wc -c | tr -d ' ')"
fi

set +e
SUBMISSION_OUT="$("$HERDR" agent prompt "$PANE_ID" "$ENVELOPE" --wait \
  --until idle --until working --until blocked --until done --until unknown \
  --timeout 7000 2>&1)"
SUBMISSION_CODE=$?
set -e

if delivery_diagnostics_enabled; then
  DIAG_AFTER="$(agent_snapshot_for_diagnostics)"
  write_delivery_diagnostic \
    "$DIAG_STARTED_AT" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$ENVELOPE_BYTES" \
    "$DIAG_BEFORE" "$SUBMISSION_OUT" "$DIAG_AFTER" "$SUBMISSION_CODE"
fi

if [ "$SUBMISSION_CODE" -ne 0 ]; then
  echo "delivery submission was not observed for ${TO_NAME:+$TO_NAME · }$TO_LABEL / $TO_AGENT ($PANE_ID); the message may remain in the target prompt, so inspect it before retrying" >&2
  [ -z "$SUBMISSION_OUT" ] || printf '%s\n' "$SUBMISSION_OUT" >&2
  exit 6
fi

echo "delivered to ${TO_NAME:+$TO_NAME · }$TO_LABEL / $TO_AGENT ($PANE_ID)"
