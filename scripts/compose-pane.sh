#!/usr/bin/env bash
# compose-pane.sh: runs inside the pane-scoped Messenger board split.
# Reads its work order from $MSG_WORKDIR (injected by the caller
# via `herdr pane split --env`): list (targets), self (caller's
# call-sign), optional intent marker. Writes back: target, mode, text,
# outcome, done. Exits when finished; the caller closes the pane.

set -euo pipefail

WORK="${MSG_WORKDIR:?MSG_WORKDIR not set (open this pane via compose.sh)}"
LIST="$WORK/list"
SELF="$(cat "$WORK/self" 2>/dev/null || true)"
CANCEL_ARMED="$WORK/cancel-armed"
DRAFT_REQUEST="$WORK/draft-request"

finish() {
  printf '%s\n' "$1" > "$WORK/outcome"
  touch "$WORK/done"
  trap - EXIT
  exit 0
}

failed() {
  [ -f "$WORK/done" ] || {
    printf '%s\n' failure > "$WORK/outcome"
    touch "$WORK/done"
  }
}
trap failed EXIT

write_headers() {
  local base="$1" normal="$2" armed="$3"
  printf '%s\n' "$base" > "$normal"
  printf '%s\nPress Escape again to cancel\n' "$base" > "$armed"
}

run_picker() {
  local normal="$WORK/pick-header" armed="$WORK/pick-header-armed"
  local header='pick the agent to message · enter: select · s: search · esc: cancel'
  [ -n "$SELF" ] && header="you are: $SELF
$header"
  write_headers "$header" "$normal" "$armed"
  rm -f "$CANCEL_ARMED"

  fzf --delimiter '\t' --with-nth 2 --reverse --info=inline \
    --prompt 'search> ' \
    --header "$(cat "$normal")" \
    --bind "esc:transform:[[ -f '$CANCEL_ARMED' ]] && echo abort || { touch '$CANCEL_ARMED'; echo \"disable-search+change-prompt(nav [s: search, esc: cancel]> )+transform-header(cat '$armed')\"; }" \
    --bind "change:execute-silent(rm -f '$CANCEL_ARMED')+transform-header(cat '$normal')" \
    --bind "focus:execute-silent(rm -f '$CANCEL_ARMED')+transform-header(cat '$normal')" \
    --bind "up:execute-silent(rm -f '$CANCEL_ARMED')+transform-header(cat '$normal')+up" \
    --bind "down:execute-silent(rm -f '$CANCEL_ARMED')+transform-header(cat '$normal')+down" \
    --bind "left:execute-silent(rm -f '$CANCEL_ARMED')+transform-header(cat '$normal')+backward-char" \
    --bind "right:execute-silent(rm -f '$CANCEL_ARMED')+transform-header(cat '$normal')+forward-char" \
    --bind "home:execute-silent(rm -f '$CANCEL_ARMED')+transform-header(cat '$normal')+beginning-of-line" \
    --bind "end:execute-silent(rm -f '$CANCEL_ARMED')+transform-header(cat '$normal')+end-of-line" \
    --bind "s:transform:[[ \"\$FZF_PROMPT\" = \"search> \" ]] && echo 'put(s)' || { rm -f '$CANCEL_ARMED'; echo \"enable-search+change-prompt(search> )+transform-header(cat '$normal')\"; }" \
    --bind 'ctrl-c:ignore,ctrl-g:ignore,ctrl-q:ignore' \
    < "$LIST"
}

run_message_entry() {
  local target_label="$1" normal="$WORK/message-header" armed="$WORK/message-header-armed"
  local validation="" query="" out rc text

  while true; do
    local header="to: $target_label"
    [ -n "$SELF" ] && header="you are: $SELF
$header"
    header="$header
ENTER: send your text exactly as typed
TAB: give your agent instructions to write and send the message
ESC: cancel"
    [ -n "$validation" ] && header="$header
$validation"
    write_headers "$header" "$normal" "$armed"
    rm -f "$CANCEL_ARMED" "$DRAFT_REQUEST"

    set +e
    out="$(fzf --disabled --print-query --reverse --info=hidden \
      --query "$query" \
      --prompt 'message or instructions> ' \
      --header "$(cat "$normal")" \
      --bind 'enter:accept-or-print-query' \
      --bind "tab:execute-silent(touch '$DRAFT_REQUEST')+accept-or-print-query" \
      --bind "esc:transform:[[ -f '$CANCEL_ARMED' ]] && echo abort || { touch '$CANCEL_ARMED'; echo \"transform-header(cat '$armed')\"; }" \
      --bind "change:execute-silent(rm -f '$CANCEL_ARMED')+transform-header(cat '$normal')" \
      --bind "up:execute-silent(rm -f '$CANCEL_ARMED')+transform-header(cat '$normal')+up" \
      --bind "down:execute-silent(rm -f '$CANCEL_ARMED')+transform-header(cat '$normal')+down" \
      --bind "left:execute-silent(rm -f '$CANCEL_ARMED')+transform-header(cat '$normal')+backward-char" \
      --bind "right:execute-silent(rm -f '$CANCEL_ARMED')+transform-header(cat '$normal')+forward-char" \
      --bind "home:execute-silent(rm -f '$CANCEL_ARMED')+transform-header(cat '$normal')+beginning-of-line" \
      --bind "end:execute-silent(rm -f '$CANCEL_ARMED')+transform-header(cat '$normal')+end-of-line" \
      --bind 'ctrl-c:ignore,ctrl-g:ignore,ctrl-q:ignore' \
      < /dev/null)"
    rc=$?
    set -e

    [ "$rc" -eq 130 ] && finish cancelled
    [ "$rc" -eq 0 ] || finish failure

    text="$(printf '%s\n' "$out" | sed -n 1p)"
    if [ -z "${text//[[:space:]]/}" ]; then
      query="$text"
      validation='Message required'
      continue
    fi

    printf '%s\n' "$text" > "$WORK/text"
    if [ -f "$DRAFT_REQUEST" ]; then
      printf '%s\n' draft > "$WORK/mode"
    else
      printf '%s\n' direct > "$WORK/mode"
    fi
    finish submitted
  done
}

set +e
sel="$(run_picker)"
rc=$?
set -e
[ "$rc" -eq 130 ] && finish cancelled
[ "$rc" -eq 0 ] || finish failure
printf '%s\n' "$sel" > "$WORK/target"

[ -f "$WORK/intent" ] && finish submitted

tlabel="$(printf '%s\n' "$sel" | cut -f2)"
run_message_entry "$tlabel"
