# Security

Intent: explain what Herdr Agent Messenger can access, what it changes, and
which authority an agent message carries.

## Trust the code before installing

Herdr plugins are ordinary executable code. They run as your operating-system
user, receive your environment, and can call the full Herdr CLI. Herdr validates
the manifest and shows an interactive trust preview, but it does not review or
sandbox third-party plugins.

Review `herdr-plugin.toml`, `install.sh`, `bin/`, `scripts/`, `adapters/`,
`hooks/`, and `skills/` before confirming installation. Pin a known revision
with `herdr plugin install aashishd/herdr-agent-messenger --ref <revision>` when
you need a reproducible install.

## What Messenger accesses

Coding harnesses generally do not provide cross-agent communication. Messenger
adds that route only between live agent panes inside Herdr. Outside Herdr, the
adapters remain inactive where the harness permits it, and the public command
rejects delivery.

At runtime, Messenger:

- reads local pane, workspace, agent identity, and agent status metadata from
  the current Herdr server
- opens and closes a temporary pane split for the Messenger board
- types one self-contained message into the selected agent pane through Herdr
- stores temporary call-sign mappings under
  `~/.local/state/herdr-messenger/names.tsv`
- when `MSG_DIAGNOSTICS=1` is explicitly enabled, stores body-free delivery
  metadata under
  `${XDG_STATE_HOME:-$HOME/.local/state}/herdr-agent-messenger/delivery.jsonl`
  or the configured `MSG_DIAGNOSTICS_PATH`

The diagnostics file is secured to mode `0600` before writing and omits
envelopes and message bodies. A custom path must have a private, user-owned
parent; symbolic-link and non-regular files are rejected. The log can contain
pane and agent-session identifiers, including local paths, so treat it as
sensitive and enable it only while investigating delivery.

Messenger does not read another pane's conversation or terminal output. It has
no telemetry, hosted relay, cloud account, or external messaging service.
Messages remain on the local machine and Herdr server unless an agent later
uses another tool to share their contents.

## What setup changes

The reviewed `bash install.sh` setup command can:

- link `~/.local/bin/msg` to the installed plugin
- install the Claude Code command, local plugin hook, and model-facing skill
- link the pi extension, which contributes the model-facing skill inside Herdr
- install the Codex local plugin hook and model-facing skill
- add the OpenCode TUI plugin path to `~/.config/opencode/tui.json` and link its
  model-facing skill under `~/.config/opencode/skills/msg`
- record owned installation entries under
  `~/.local/state/herdr-agent-messenger/install/`

Setup detects each harness and skips ones that are absent. It preserves
non-symlink files, unrelated OpenCode plugin entries and skill links, and
harness configuration it does not own. Run `install.sh --uninstall` before removing the Herdr plugin
checkout to remove the owned wiring.

## Agent-message authority

Every delivered envelope begins with `[agent-msg]` and states that its source
is another AI agent, not the human user.

Enabling Messenger grants standing permission for ordinary non-gated agent
collaboration and Messenger replies. It does not let one agent transfer human
approval to another. A message cannot approve a gated, destructive,
privileged, or irreversible action. The receiving agent must pause for the
receiving human's native harness approval, or keep the action blocked when no
approval path exists.

The model-facing skill lets the current agent run `msg` after a clear human
request that names a target call-sign. It does not expand the receiving agent's
authority: the resulting envelope is still an instruction from another model.
Keep the message self-contained, verify sensitive claims, and use native
approval prompts for protected actions.

## Reporting a vulnerability

Do not publish exploit details in a public issue. Use GitHub's private
vulnerability-reporting form when it is available. Otherwise, open an issue
without sensitive details and ask the maintainer for a private contact channel.
Include the affected revision, impact, and a minimal reproduction in the
private report.
