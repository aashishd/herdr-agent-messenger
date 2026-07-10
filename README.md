# Herdr Agent Messenger

Send focused, self-contained messages between AI agents running in live
[Herdr](https://herdr.dev) panes. One agent can coordinate work with another
across Claude Code, pi, Codex, and OpenCode without sharing either agent's full
conversation.

Each live agent pane gets a temporary call-sign such as `quiet-heron`. Use the
Messenger board, tell your current agent what to send, or address another agent
directly from the shell.

## Install

Requirements: Herdr 0.7.1 or newer, Bash, Python 3, and
[fzf](https://github.com/junegunn/fzf) on macOS or Linux.

```sh
herdr plugin install aashishd/herdr-agent-messenger
```

Herdr shows the repository and the `bash install.sh` setup command before you
confirm. Setup adds the `msg` command and configures adapters only for supported
harnesses already present on the machine. Restart those harnesses after setup.
Claude Code and Codex also ask you to review and trust the Messenger hook in a
new session.

## Use Messenger

| Harness | Open Messenger | Show this pane's call-sign |
|---|---|---|
| Claude Code | `/msg` | `/msg whoami` |
| pi | `/msg` | `/msg whoami` |
| Codex | `$herdr-agent-messenger:msg` | `$herdr-agent-messenger:msg whoami` |
| OpenCode | `/msg` | `/msg-whoami` |

In the Messenger board, select a target and enter text:

- Press Enter to send the text exactly as written.
- Press Tab to ask your current agent to turn the text into a self-contained
  message and send it.
- Press Escape twice consecutively to cancel without involving the agent.

You can also ask your agent naturally:

> Use Messenger to share the relevant documentation and next steps with the
> agent named `quiet-heron`, so it can continue the work.

The current agent frames a self-contained message and sends it with `msg`.
Include paths, URLs, repository details, and the expected next action because
the receiving agent cannot see the sender's conversation.

For direct shell use:

```sh
msg whoami
msg quiet-heron 'Read docs/USAGE.md, then continue the adapter test and reply with the result.'
msg compose
```

See [Usage](docs/USAGE.md) for installation variants, examples, updates,
uninstall steps, and harness limitations.

## Trust and security

Herdr plugins run as your operating-system user and are not sandboxed. Review
the manifest and scripts before installing. Messenger reads local Herdr pane
metadata, writes local adapter and call-sign state, and can type a message into
the selected agent pane. It does not provide an external messaging service or
send telemetry.

An `[agent-msg]` message is from another AI agent, not from the human user.
Enabling Messenger permits ordinary non-gated collaboration and replies, but a
message can never approve a gated, destructive, privileged, or irreversible
action. Such actions must pause for the receiving human's native harness
approval or remain blocked.

Read [Security](SECURITY.md) for the complete access and authority model, and
[Protocol](PROTOCOL.md) for the wire format.

## Current limits

- Sender and receiver must be live on the same machine and Herdr server.
- Messages are single-line and have no delivery acknowledgement or threading.
- Call-signs last only for the lifetime of an agent pane.
- Claude Code and Codex may show harness-owned hook status text around local
  identity results.
- OpenCode uses `/msg-whoami` because its local command callback does not expose
  slash-command arguments.
