#!/usr/bin/env bash
# install.sh: copy a durable plugin payload, then wire the PATH shim and
# harness adapters to that payload. Idempotent.
# usage: install.sh [--uninstall]

set -euo pipefail

SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${MSG_BIN_DIR:-$HOME/.local/bin}"
CLAUDE_CMDS="$HOME/.claude/commands"
PI_EXTENSIONS="$HOME/.pi/agent/extensions"
MARKETPLACE="herdr-agent-messenger-local"
PLUGIN_SELECTOR="herdr-agent-messenger@$MARKETPLACE"
DATA_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/herdr-agent-messenger"
PAYLOAD_ROOT="$DATA_ROOT/plugin"
PAYLOAD_MARKER=".herdr-agent-messenger-payload"
PAYLOAD_STATE_RECORD=".herdr-agent-messenger-install-state"
INSTALL_STATE="${XDG_STATE_HOME:-$HOME/.local/state}/herdr-agent-messenger/install"

set_owner_paths() {
  PAYLOAD_OWNER="$INSTALL_STATE/payload-root"
  MSG_OWNER="$INSTALL_STATE/msg-source"
  CLAUDE_COMMAND_OWNER="$INSTALL_STATE/claude-command-source"
  PI_EXTENSION_OWNER="$INSTALL_STATE/pi-extension-source"
  OPENCODE_SKILL_OWNER="$INSTALL_STATE/opencode-skill-source"
  OPENCODE_PLUGIN_OWNER="$INSTALL_STATE/opencode-plugin-source"
  CLAUDE_MARKETPLACE_OWNER="$INSTALL_STATE/claude-marketplace"
  CLAUDE_MARKETPLACE_SOURCE="$INSTALL_STATE/claude-marketplace-source"
  CLAUDE_PLUGIN_OWNER="$INSTALL_STATE/claude-plugin"
  CODEX_MARKETPLACE_OWNER="$INSTALL_STATE/codex-marketplace"
  CODEX_MARKETPLACE_SOURCE="$INSTALL_STATE/codex-marketplace-source"
  CODEX_PLUGIN_OWNER="$INSTALL_STATE/codex-plugin"
}

set_owner_paths

recorded_source() {
  [ -f "$1" ] && head -n 1 "$1" || true
}

if [ "${1:-}" = "--uninstall" ]; then
  if [ -f "$SOURCE_ROOT/$PAYLOAD_MARKER" ] && [ -f "$SOURCE_ROOT/$PAYLOAD_STATE_RECORD" ]; then
    RECORDED_INSTALL_STATE="$(recorded_source "$SOURCE_ROOT/$PAYLOAD_STATE_RECORD")"
    if [ -n "$RECORDED_INSTALL_STATE" ]; then
      INSTALL_STATE="$RECORDED_INSTALL_STATE"
      set_owner_paths
    fi
  fi
  RECORDED_PAYLOAD="$(recorded_source "$PAYLOAD_OWNER")"
  if [ -n "$RECORDED_PAYLOAD" ] && [ -f "$RECORDED_PAYLOAD/$PAYLOAD_MARKER" ]; then
    PAYLOAD_ROOT="$RECORDED_PAYLOAD"
    DATA_ROOT="$(dirname "$PAYLOAD_ROOT")"
  elif [ -f "$SOURCE_ROOT/$PAYLOAD_MARKER" ]; then
    PAYLOAD_ROOT="$SOURCE_ROOT"
    DATA_ROOT="$(dirname "$PAYLOAD_ROOT")"
  fi
  if [ -f "$PAYLOAD_ROOT/$PAYLOAD_MARKER" ]; then
    ROOT="$(cd "$PAYLOAD_ROOT" && pwd)"
  else
    ROOT="$SOURCE_ROOT"
  fi
else
  ROOT="$(python3 "$SOURCE_ROOT/scripts/install_payload.py" "$SOURCE_ROOT" "$PAYLOAD_ROOT")"
  mkdir -p "$INSTALL_STATE"
  INSTALL_STATE="$(cd "$INSTALL_STATE" && pwd)"
  set_owner_paths
  printf '%s\n' "$ROOT" > "$PAYLOAD_OWNER"
  printf '%s\n' "$INSTALL_STATE" > "$ROOT/$PAYLOAD_STATE_RECORD"
  echo "installed durable payload at $ROOT"
fi

OPENCODE_SOURCE="$ROOT/adapters/opencode/tui.js"
OPENCODE_SKILL_SOURCE="$ROOT/skills/msg"
OPENCODE_SKILL_DEST="$HOME/.config/opencode/skills/msg"

is_messenger_root() {
  local candidate="$1"
  if [ "$candidate" = "$ROOT" ] || [ "$candidate" = "$SOURCE_ROOT" ]; then
    return 0
  fi
  case "$candidate" in
    */herdr/plugins/.tmp-install-*/checkout) return 0 ;;
  esac
  [ -f "$candidate/herdr-plugin.toml" ] &&
    grep -q '^id = "herdr-agent-messenger"$' "$candidate/herdr-plugin.toml"
}

messenger_root_for_source() {
  local source="$1" suffix="$2" candidate
  case "$source" in
    */"$suffix") candidate="${source%/$suffix}" ;;
    *) return 1 ;;
  esac
  is_messenger_root "$candidate" || return 1
  printf '%s' "$candidate"
}

adopt_legacy_link() {
  local destination="$1" suffix="$2" owner="$3" current root
  [ -f "$owner" ] && return 0
  [ -L "$destination" ] || return 0
  current="$(readlink "$destination")"
  root="$(messenger_root_for_source "$current" "$suffix" || true)"
  [ -n "$root" ] || return 0
  mkdir -p "$(dirname "$owner")"
  printf '%s\n' "$current" > "$owner"
}

link_recorded() {
  local source="$1" destination="$2" owner="$3" current="" recorded=""
  mkdir -p "$(dirname "$destination")"
  if [ -L "$destination" ]; then
    current="$(readlink "$destination")"
    recorded="$(recorded_source "$owner")"
    if [ "$current" != "$source" ] && [ "$current" != "$recorded" ]; then
      echo "skip $destination (symlink points elsewhere; remove it first)" >&2
      return
    fi
  elif [ -e "$destination" ]; then
    echo "skip $destination (exists and is not a symlink; remove it first)" >&2
    return
  fi
  ln -sfn "$source" "$destination"
  mkdir -p "$(dirname "$owner")"
  printf '%s\n' "$source" > "$owner"
  echo "linked $destination -> $source"
}

unlink_recorded() {
  local source="$1" destination="$2" owner="$3" current="" recorded=""
  recorded="$(recorded_source "$owner")"
  if [ -L "$destination" ]; then
    current="$(readlink "$destination")"
    if [ "$current" = "$source" ] || { [ -n "$recorded" ] && [ "$current" = "$recorded" ]; }; then
      rm "$destination"
      echo "removed $destination"
    fi
  fi
  rm -f "$owner"
}

previous_opencode_source() {
  local source root
  source="$(recorded_source "$OPENCODE_PLUGIN_OWNER")"
  if [ -n "$source" ]; then
    printf '%s' "$source"
    return
  fi
  source="$(recorded_source "$OPENCODE_SKILL_OWNER")"
  if [ -z "$source" ] && [ -L "$OPENCODE_SKILL_DEST" ]; then
    source="$(readlink "$OPENCODE_SKILL_DEST")"
  fi
  root="$(messenger_root_for_source "$source" "skills/msg" || true)"
  if [ -n "$root" ]; then
    printf '%s/adapters/opencode/tui.js' "$root"
  fi
  return 0
}

if [ "${1:-}" = "--uninstall" ]; then
  PREVIOUS_OPENCODE_SOURCE="$(previous_opencode_source)"
  adopt_legacy_link "$BIN_DIR/msg" "bin/msg" "$MSG_OWNER"
  adopt_legacy_link "$CLAUDE_CMDS/msg.md" "adapters/claude-code/commands/msg.md" "$CLAUDE_COMMAND_OWNER"
  adopt_legacy_link "$PI_EXTENSIONS/herdr-agent-messenger.ts" "adapters/pi/index.ts" "$PI_EXTENSION_OWNER"
  adopt_legacy_link "$OPENCODE_SKILL_DEST" "skills/msg" "$OPENCODE_SKILL_OWNER"

  unlink_recorded "$ROOT/bin/msg" "$BIN_DIR/msg" "$MSG_OWNER"
  unlink_recorded "$ROOT/adapters/claude-code/commands/msg.md" "$CLAUDE_CMDS/msg.md" "$CLAUDE_COMMAND_OWNER"
  unlink_recorded "$ROOT/adapters/pi/index.ts" "$PI_EXTENSIONS/herdr-agent-messenger.ts" "$PI_EXTENSION_OWNER"
  unlink_recorded "$OPENCODE_SKILL_SOURCE" "$OPENCODE_SKILL_DEST" "$OPENCODE_SKILL_OWNER"

  if command -v claude >/dev/null; then
    if [ -f "$CLAUDE_PLUGIN_OWNER" ]; then
      claude plugin uninstall "$PLUGIN_SELECTOR" --scope user --keep-data -y >/dev/null 2>&1 || true
      rm -f "$CLAUDE_PLUGIN_OWNER"
    fi
    if [ -f "$CLAUDE_MARKETPLACE_OWNER" ]; then
      claude plugin marketplace remove "$MARKETPLACE" --scope user >/dev/null 2>&1 || true
      rm -f "$CLAUDE_MARKETPLACE_OWNER" "$CLAUDE_MARKETPLACE_SOURCE"
    fi
  elif [ -f "$CLAUDE_PLUGIN_OWNER" ] || [ -f "$CLAUDE_MARKETPLACE_OWNER" ]; then
    echo "Claude Code not detected; retained adapter ownership state" >&2
  fi

  if command -v codex >/dev/null; then
    if [ -f "$CODEX_PLUGIN_OWNER" ]; then
      codex plugin remove "$PLUGIN_SELECTOR" --json >/dev/null 2>&1 || true
      rm -f "$CODEX_PLUGIN_OWNER"
    fi
    if [ -f "$CODEX_MARKETPLACE_OWNER" ]; then
      codex plugin marketplace remove "$MARKETPLACE" --json >/dev/null 2>&1 || true
      rm -f "$CODEX_MARKETPLACE_OWNER" "$CODEX_MARKETPLACE_SOURCE"
    fi
  elif [ -f "$CODEX_PLUGIN_OWNER" ] || [ -f "$CODEX_MARKETPLACE_OWNER" ]; then
    echo "Codex not detected; retained adapter ownership state" >&2
  fi

  if [ -f "$HOME/.config/opencode/tui.json" ]; then
    if [ -n "$PREVIOUS_OPENCODE_SOURCE" ]; then
      python3 "$ROOT/scripts/opencode_plugin_config.py" uninstall "$PREVIOUS_OPENCODE_SOURCE" || true
    fi
    if [ "$PREVIOUS_OPENCODE_SOURCE" != "$OPENCODE_SOURCE" ]; then
      python3 "$ROOT/scripts/opencode_plugin_config.py" uninstall "$OPENCODE_SOURCE" || true
    fi
  fi
  rm -f "$OPENCODE_PLUGIN_OWNER"

  echo "note: compatibility call-sign registry (~/.local/state/herdr-messenger/) left in place"
  if [ -f "$PAYLOAD_ROOT/$PAYLOAD_MARKER" ]; then
    rm -rf "$PAYLOAD_ROOT"
    rmdir "$DATA_ROOT" 2>/dev/null || true
    echo "removed durable payload $PAYLOAD_ROOT"
  fi
  rm -f "$PAYLOAD_OWNER"
  rmdir "$INSTALL_STATE" 2>/dev/null || true
  rmdir "$(dirname "$INSTALL_STATE")" 2>/dev/null || true
  exit 0
fi

PREVIOUS_OPENCODE_SOURCE="$(previous_opencode_source)"
adopt_legacy_link "$BIN_DIR/msg" "bin/msg" "$MSG_OWNER"
adopt_legacy_link "$CLAUDE_CMDS/msg.md" "adapters/claude-code/commands/msg.md" "$CLAUDE_COMMAND_OWNER"
adopt_legacy_link "$PI_EXTENSIONS/herdr-agent-messenger.ts" "adapters/pi/index.ts" "$PI_EXTENSION_OWNER"
adopt_legacy_link "$OPENCODE_SKILL_DEST" "skills/msg" "$OPENCODE_SKILL_OWNER"

link_recorded "$ROOT/bin/msg" "$BIN_DIR/msg" "$MSG_OWNER"
if command -v claude >/dev/null && [ -d "$HOME/.claude" ]; then
  link_recorded "$ROOT/adapters/claude-code/commands/msg.md" "$CLAUDE_CMDS/msg.md" "$CLAUDE_COMMAND_OWNER"
  mkdir -p "$INSTALL_STATE"
  CLAUDE_MARKETPLACE_WAS_OURS=no
  CLAUDE_PLUGIN_WAS_OURS=no
  CLAUDE_REGISTERED_SOURCE="$(recorded_source "$CLAUDE_MARKETPLACE_SOURCE")"
  if [ -f "$CLAUDE_MARKETPLACE_OWNER" ]; then
    CLAUDE_MARKETPLACE_WAS_OURS=yes
  fi
  if [ -f "$CLAUDE_PLUGIN_OWNER" ]; then
    CLAUDE_PLUGIN_WAS_OURS=yes
  fi
  if [ "$CLAUDE_MARKETPLACE_WAS_OURS" = yes ] && [ "$CLAUDE_REGISTERED_SOURCE" != "$ROOT" ]; then
    if [ "$CLAUDE_PLUGIN_WAS_OURS" = yes ]; then
      claude plugin uninstall "$PLUGIN_SELECTOR" --scope user --keep-data -y >/dev/null 2>&1 || true
      rm -f "$CLAUDE_PLUGIN_OWNER"
    fi
    claude plugin marketplace remove "$MARKETPLACE" --scope user >/dev/null 2>&1 || true
    rm -f "$CLAUDE_MARKETPLACE_OWNER" "$CLAUDE_MARKETPLACE_SOURCE"
  fi
  CLAUDE_MARKETPLACE_PRESENT="$( (claude plugin marketplace list --json 2>/dev/null || true) | python3 -c '
import json, sys
try:
    rows = json.load(sys.stdin)
except Exception:
    print("unknown")
    raise SystemExit
print("yes" if any(row.get("name") == "herdr-agent-messenger-local" for row in rows) else "no")')"
  CLAUDE_PLUGIN_PRESENT="$( (claude plugin list --json 2>/dev/null || true) | python3 -c '
import json, sys
try:
    rows = json.load(sys.stdin)
except Exception:
    print("unknown")
    raise SystemExit
print("yes" if any(row.get("id") == "herdr-agent-messenger@herdr-agent-messenger-local" and row.get("scope") == "user" for row in rows) else "no")')"
  if claude plugin marketplace add "$ROOT/" --scope user >/dev/null; then
    if [ "$CLAUDE_MARKETPLACE_WAS_OURS" = yes ] || [ "$CLAUDE_MARKETPLACE_PRESENT" = no ]; then
      touch "$CLAUDE_MARKETPLACE_OWNER"
      printf '%s\n' "$ROOT" > "$CLAUDE_MARKETPLACE_SOURCE"
    fi
    CLAUDE_PLUGIN_READY=no
    if [ "$CLAUDE_PLUGIN_PRESENT" = yes ] || {
      [ "$CLAUDE_PLUGIN_WAS_OURS" = yes ] && [ "$CLAUDE_REGISTERED_SOURCE" = "$ROOT" ];
    }; then
      if claude plugin update "$PLUGIN_SELECTOR" --scope user >/dev/null; then
        CLAUDE_PLUGIN_READY=yes
      fi
    elif claude plugin install "$PLUGIN_SELECTOR" --scope user >/dev/null; then
      CLAUDE_PLUGIN_READY=yes
    fi
    if [ "$CLAUDE_PLUGIN_READY" = yes ]; then
      if [ "$CLAUDE_PLUGIN_WAS_OURS" = yes ] || [ "$CLAUDE_PLUGIN_PRESENT" = no ]; then
        touch "$CLAUDE_PLUGIN_OWNER"
      fi
      echo "installed Claude Code adapter ($PLUGIN_SELECTOR)"
      echo "note: review and trust its hook with /hooks in a new Claude Code session"
    else
      if [ "$CLAUDE_PLUGIN_WAS_OURS" = yes ]; then
        touch "$CLAUDE_PLUGIN_OWNER"
      fi
      echo "Claude Code adapter installation failed; see claude plugin output" >&2
    fi
  else
    if [ "$CLAUDE_MARKETPLACE_WAS_OURS" = yes ]; then
      touch "$CLAUDE_MARKETPLACE_OWNER"
      printf '%s\n' "$ROOT" > "$CLAUDE_MARKETPLACE_SOURCE"
    fi
    if [ "$CLAUDE_PLUGIN_WAS_OURS" = yes ]; then
      touch "$CLAUDE_PLUGIN_OWNER"
    fi
    echo "Claude Code marketplace installation failed; see claude plugin output" >&2
  fi
else
  echo "Claude Code not detected; skipped adapter"
fi

if command -v pi >/dev/null && [ -d "$HOME/.pi/agent" ]; then
  link_recorded "$ROOT/adapters/pi/index.ts" "$PI_EXTENSIONS/herdr-agent-messenger.ts" "$PI_EXTENSION_OWNER"
else
  echo "pi not detected; skipped adapter"
fi

if command -v codex >/dev/null && [ -d "$HOME/.codex" ]; then
  mkdir -p "$INSTALL_STATE"
  CODEX_MARKETPLACE_WAS_OURS=no
  CODEX_PLUGIN_WAS_OURS=no
  CODEX_REGISTERED_SOURCE="$(recorded_source "$CODEX_MARKETPLACE_SOURCE")"
  if [ -f "$CODEX_MARKETPLACE_OWNER" ]; then
    CODEX_MARKETPLACE_WAS_OURS=yes
  fi
  if [ -f "$CODEX_PLUGIN_OWNER" ]; then
    CODEX_PLUGIN_WAS_OURS=yes
  fi
  if [ "$CODEX_MARKETPLACE_WAS_OURS" = yes ] && [ "$CODEX_REGISTERED_SOURCE" != "$ROOT" ]; then
    if [ "$CODEX_PLUGIN_WAS_OURS" = yes ]; then
      codex plugin remove "$PLUGIN_SELECTOR" --json >/dev/null 2>&1 || true
      rm -f "$CODEX_PLUGIN_OWNER"
    fi
    codex plugin marketplace remove "$MARKETPLACE" --json >/dev/null 2>&1 || true
    rm -f "$CODEX_MARKETPLACE_OWNER" "$CODEX_MARKETPLACE_SOURCE"
  fi
  CODEX_MARKETPLACE_PRESENT="$( (codex plugin marketplace list --json 2>/dev/null || true) | python3 -c '
import json, sys
try:
    rows = json.load(sys.stdin).get("marketplaces", [])
except Exception:
    print("unknown")
    raise SystemExit
print("yes" if any(row.get("name") == "herdr-agent-messenger-local" for row in rows) else "no")')"
  CODEX_PLUGIN_PRESENT="$( (codex plugin list --json 2>/dev/null || true) | python3 -c '
import json, sys
try:
    rows = json.load(sys.stdin).get("installed", [])
except Exception:
    print("unknown")
    raise SystemExit
print("yes" if any(row.get("pluginId") == "herdr-agent-messenger@herdr-agent-messenger-local" for row in rows) else "no")')"
  if codex plugin marketplace add "$ROOT" --json >/dev/null; then
    if [ "$CODEX_MARKETPLACE_WAS_OURS" = yes ] || [ "$CODEX_MARKETPLACE_PRESENT" = no ]; then
      touch "$CODEX_MARKETPLACE_OWNER"
      printf '%s\n' "$ROOT" > "$CODEX_MARKETPLACE_SOURCE"
    fi
    if codex plugin add "$PLUGIN_SELECTOR" --json >/dev/null; then
      if [ "$CODEX_PLUGIN_WAS_OURS" = yes ] || [ "$CODEX_PLUGIN_PRESENT" = no ]; then
        touch "$CODEX_PLUGIN_OWNER"
      fi
      echo "installed Codex adapter ($PLUGIN_SELECTOR)"
      echo "note: review and trust its hook with /hooks in a new Codex session"
    else
      if [ "$CODEX_PLUGIN_WAS_OURS" = yes ]; then
        touch "$CODEX_PLUGIN_OWNER"
      fi
      echo "Codex adapter installation failed; see codex plugin output" >&2
    fi
  else
    if [ "$CODEX_MARKETPLACE_WAS_OURS" = yes ]; then
      touch "$CODEX_MARKETPLACE_OWNER"
      printf '%s\n' "$ROOT" > "$CODEX_MARKETPLACE_SOURCE"
    fi
    if [ "$CODEX_PLUGIN_WAS_OURS" = yes ]; then
      touch "$CODEX_PLUGIN_OWNER"
    fi
    echo "Codex marketplace installation failed; see codex plugin output" >&2
  fi
else
  echo "Codex not detected; skipped adapter"
fi

if command -v opencode >/dev/null && [ -d "$HOME/.config/opencode" ]; then
  if [ -n "$PREVIOUS_OPENCODE_SOURCE" ] && [ "$PREVIOUS_OPENCODE_SOURCE" != "$OPENCODE_SOURCE" ]; then
    python3 "$ROOT/scripts/opencode_plugin_config.py" uninstall "$PREVIOUS_OPENCODE_SOURCE" || true
  fi
  link_recorded "$OPENCODE_SKILL_SOURCE" "$OPENCODE_SKILL_DEST" "$OPENCODE_SKILL_OWNER"
  if python3 "$ROOT/scripts/opencode_plugin_config.py" install "$OPENCODE_SOURCE"; then
    printf '%s\n' "$OPENCODE_SOURCE" > "$OPENCODE_PLUGIN_OWNER"
    echo "installed OpenCode adapter (/msg, /msg-whoami, and agent skill)"
  else
    echo "OpenCode TUI adapter installation failed; tui.json was preserved" >&2
  fi
else
  echo "OpenCode not detected; skipped adapter"
fi

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "note: $BIN_DIR is not on PATH" ;;
esac
echo "note: Messenger permits ordinary non-gated agent work and replies"
echo "note: protected actions still require the receiving human's native harness approval"
