#!/usr/bin/env bash
# install.sh: wire herdr-agent-messenger into this machine, including the PATH
# shim and harness adapters. Symlinks back into the plugin checkout, so updates
# apply without re-running. Idempotent.
# usage: install.sh [--uninstall]

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${MSG_BIN_DIR:-$HOME/.local/bin}"
CLAUDE_CMDS="$HOME/.claude/commands"
PI_EXTENSIONS="$HOME/.pi/agent/extensions"
MARKETPLACE="herdr-agent-messenger-local"
PLUGIN_SELECTOR="herdr-agent-messenger@$MARKETPLACE"
OPENCODE_SOURCE="$ROOT/adapters/opencode/tui.js"
INSTALL_STATE="${XDG_STATE_HOME:-$HOME/.local/state}/herdr-agent-messenger/install"

link() {
  mkdir -p "$(dirname "$2")"
  if [ -e "$2" ] && [ ! -L "$2" ]; then
    echo "skip $2 (exists and is not a symlink; remove it first)" >&2
    return
  fi
  ln -sfn "$1" "$2"
  echo "linked $2 -> $1"
}

unlink_ours() {
  if [ -L "$2" ] && [ "$(readlink "$2")" = "$1" ]; then
    rm "$2"
    echo "removed $2"
  fi
}

if [ "${1:-}" = "--uninstall" ]; then
  unlink_ours "$ROOT/bin/msg" "$BIN_DIR/msg"
  unlink_ours "$ROOT/adapters/claude-code/commands/msg.md" "$CLAUDE_CMDS/msg.md"
  unlink_ours "$ROOT/adapters/pi/index.ts" "$PI_EXTENSIONS/herdr-agent-messenger.ts"
  if command -v claude >/dev/null && [ -f "$INSTALL_STATE/claude-plugin" ]; then
    claude plugin uninstall "$PLUGIN_SELECTOR" --scope user --keep-data -y >/dev/null 2>&1 || true
  fi
  if command -v claude >/dev/null && [ -f "$INSTALL_STATE/claude-marketplace" ]; then
    claude plugin marketplace remove "$MARKETPLACE" --scope user >/dev/null 2>&1 || true
  fi
  if command -v codex >/dev/null && [ -f "$INSTALL_STATE/codex-plugin" ]; then
    codex plugin remove "$PLUGIN_SELECTOR" --json >/dev/null 2>&1 || true
  fi
  if command -v codex >/dev/null && [ -f "$INSTALL_STATE/codex-marketplace" ]; then
    codex plugin marketplace remove "$MARKETPLACE" --json >/dev/null 2>&1 || true
  fi
  if [ -f "$HOME/.config/opencode/tui.json" ]; then
    python3 "$ROOT/scripts/opencode_plugin_config.py" uninstall "$OPENCODE_SOURCE" || true
  fi
  rm -f "$INSTALL_STATE/claude-plugin" "$INSTALL_STATE/claude-marketplace" \
    "$INSTALL_STATE/codex-plugin" "$INSTALL_STATE/codex-marketplace"
  echo "note: compatibility call-sign registry (~/.local/state/herdr-messenger/) left in place"
  exit 0
fi

link "$ROOT/bin/msg" "$BIN_DIR/msg"
if command -v claude >/dev/null && [ -d "$HOME/.claude" ]; then
  link "$ROOT/adapters/claude-code/commands/msg.md" "$CLAUDE_CMDS/msg.md"
  mkdir -p "$INSTALL_STATE"
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
  if claude plugin marketplace add "$ROOT/" --scope user >/dev/null &&
     claude plugin install "$PLUGIN_SELECTOR" --scope user >/dev/null; then
    [ "$CLAUDE_MARKETPLACE_PRESENT" = "no" ] && touch "$INSTALL_STATE/claude-marketplace"
    [ "$CLAUDE_PLUGIN_PRESENT" = "no" ] && touch "$INSTALL_STATE/claude-plugin"
    echo "installed Claude Code adapter ($PLUGIN_SELECTOR)"
    echo "note: review and trust its hook with /hooks in a new Claude Code session"
  else
    echo "Claude Code adapter installation failed; see claude plugin output" >&2
  fi
else
  echo "Claude Code not detected; skipped adapter"
fi
if command -v pi >/dev/null && [ -d "$HOME/.pi/agent" ]; then
  link "$ROOT/adapters/pi/index.ts" "$PI_EXTENSIONS/herdr-agent-messenger.ts"
else
  echo "pi not detected; skipped adapter"
fi
if command -v codex >/dev/null && [ -d "$HOME/.codex" ]; then
  mkdir -p "$INSTALL_STATE"
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
  if codex plugin marketplace add "$ROOT" --json >/dev/null &&
     codex plugin add "$PLUGIN_SELECTOR" --json >/dev/null; then
    [ "$CODEX_MARKETPLACE_PRESENT" = "no" ] && touch "$INSTALL_STATE/codex-marketplace"
    [ "$CODEX_PLUGIN_PRESENT" = "no" ] && touch "$INSTALL_STATE/codex-plugin"
    echo "installed Codex adapter ($PLUGIN_SELECTOR)"
    echo "note: review and trust its hook with /hooks in a new Codex session"
  else
    echo "Codex adapter installation failed; see codex plugin output" >&2
  fi
else
  echo "Codex not detected; skipped adapter"
fi
if command -v opencode >/dev/null && [ -d "$HOME/.config/opencode" ]; then
  if python3 "$ROOT/scripts/opencode_plugin_config.py" install "$OPENCODE_SOURCE"; then
    echo "installed OpenCode adapter (/msg and /msg-whoami)"
  else
    echo "OpenCode adapter installation failed; tui.json was preserved" >&2
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
