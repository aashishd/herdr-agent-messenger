# Usage

Intent: help people install Herdr Agent Messenger and coordinate live agents
across Claude Code, pi, Codex, and OpenCode.

## Before you start

You need:

- Herdr 0.7.1 or newer on macOS or Linux
- Bash, Python 3, and `fzf`
- At least two live agent panes on the same Herdr server
- `~/.local/bin` on `PATH` for the `msg` shell command

Install `fzf` with your package manager, for example `brew install fzf` on
macOS.

## Install from GitHub

```sh
herdr plugin install aashishd/herdr-agent-messenger
```

Herdr displays a trust preview before running the repository's setup command.
The setup command installs the `msg` PATH link and configures only the supported
harnesses it detects. Restart each configured harness so it loads the adapter.

In a new Claude Code or Codex session, open `/hooks`, review the Messenger hook,
and trust it. The hook keeps cancellation and identity lookup out of model
context and starts an agent turn only for an agent-drafted message.

For local development instead:

```sh
git clone https://github.com/aashishd/herdr-agent-messenger.git
cd herdr-agent-messenger
herdr plugin link .
./install.sh
```

`./install.sh` is safe to repeat and preserves unrelated files.

## Harness commands

| Harness | Messenger board | Identity | Notes |
|---|---|---|---|
| Claude Code | `/msg` | `/msg whoami` | Trust the plugin hook in a new session. Claude may prefix identity with hook-stop UI text. |
| pi | `/msg` | `/msg whoami` | Commands appear only while pi runs inside Herdr. |
| Codex | `$herdr-agent-messenger:msg` | `$herdr-agent-messenger:msg whoami` | Trust the plugin hook in a new thread. Codex may prefix identity with blocked-hook UI text. |
| OpenCode | `/msg` | `/msg-whoami` | OpenCode currently requires a separate identity command. |

Commands are hidden outside Herdr when the harness allows it. Otherwise they
return an availability error without opening the Messenger board.

## Send from the Messenger board

1. Open Messenger with the command for the current harness.
2. Search for and select another live agent by call-sign, workspace, harness,
   status, or pane identity.
3. Enter either the exact message or instructions for your current agent.
4. Press Enter for a direct send, or Tab for an agent-drafted send.

The board opens below the current pane and uses about 35 percent of that pane.
Press Escape twice consecutively to cancel. The first press displays a
confirmation, and any other interaction resets it. A completed cancellation is
local and silent.

### Direct send with Enter

Enter sends your text exactly as typed. Messenger adds the sender, receiver,
trust boundary, and reply command around it.

Example text:

```text
Please review scripts/send.sh for quoting issues and reply with file and line references.
```

### Agent-drafted send with Tab

Tab treats the text as instructions for the current agent. The agent turns
those instructions into a self-contained, single-line message, sends it to the
selected target, and reports what it sent.

Example instructions:

```text
Share the relevant protocol documentation, current implementation status, and the next verification step so this agent can continue the work.
```

If you open Messenger with an intent, Messenger asks only for the target and
then gives the intent to the current agent. OpenCode does not currently expose
this argument form through its local slash command.

## Tell your agent to coordinate

You do not have to open the Messenger board yourself. Ask the current agent to
frame and send the message:

```text
Use Messenger to share the relevant documentation and next steps with the agent named quiet-heron, so it can continue the work. Include the repository, branch, exact paths, and what response I need.
```

The agent should compose a standalone message and run:

```sh
msg quiet-heron '<self-contained message>'
```

This is useful for handing off documentation, asking for a review, delegating a
bounded investigation, or requesting test results. The receiving agent cannot
see this conversation, so a useful message includes all necessary paths, URLs,
identifiers, constraints, and the expected reply.

## Use the shell command

```sh
msg whoami
msg <call-sign> '<message>'
msg compose
```

Useful variants:

```sh
msg quiet-heron 'Review PROTOCOL.md and reply with any compatibility risk.'
msg quiet-heron 'Run the focused tests and reply with the exact failures.' --timeout 300
msg quiet-heron 'This is urgent and may interrupt your current turn.' --now
msg quiet-heron 'Preview only.' --dry-run
msg compose 'Summarize the current docs and ask the selected agent to review them.'
```

Use `--now` only when you intentionally want to skip the normal wait for the
target to become idle. A dry run resolves the target and prints the envelope
without sending it.

Messenger resolves targets in this order: exact pane identity, exact call-sign,
agent-session prefix, call-sign substring, exact workspace label, then
workspace-label substring. An ambiguous selector is rejected instead of
guessed.

## Receiving and replying

The receiver gets one line beginning with `[agent-msg]`. It names the sender,
states that the source is another AI agent, and includes a ready-to-run reply
command. A reply is optional unless the message explicitly asks for one.

Ordinary non-gated collaboration and Messenger replies are permitted by the
enabled Messenger policy. Protected actions still require the receiving human
to approve or reject them through the harness's native approval flow.

## Update

Herdr v1 refreshes a GitHub-managed plugin by reinstalling it:

```sh
herdr plugin install aashishd/herdr-agent-messenger
```

Restart configured harnesses after the update. For a linked checkout, pull the
changes and rerun `./install.sh`.

## Uninstall

Remove the harness wiring before Herdr removes its managed checkout. If `msg`
is the installed symlink:

```sh
PLUGIN_ROOT="$(cd "$(dirname "$(readlink "$(command -v msg)")")/.." && pwd)"
"$PLUGIN_ROOT/install.sh" --uninstall
herdr plugin uninstall herdr-agent-messenger
```

Uninstall removes only wiring owned by this checkout. The compatibility
call-sign registry at `~/.local/state/herdr-messenger/` remains so uninstall
does not delete unrelated or historical local state.

## Troubleshooting

- No command appears: restart the harness after setup and confirm it is running
  inside a Herdr pane.
- No targets appear: start another supported agent in the same Herdr server.
- `msg` is not found: add `~/.local/bin` to `PATH`, then restart the shell or
  harness.
- Claude Code or Codex does not intercept Messenger locally: review and trust
  the installed hook from `/hooks`, then start a fresh session or thread.
- The board reports that `fzf` is missing: install `fzf` with the system package
  manager.
