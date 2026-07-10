#!/usr/bin/env python3
"""Call-sign registry for herdr-agent-messenger.

Every live agent pane gets a two-word call-sign (adjective-noun, e.g.
'quiet-heron') for the lifetime of the pane. Names live in a registry
file under XDG state, never in pane labels, so nothing renders in the
herdr UI; they surface in the compose picker, envelopes, and `msg
whoami`.

Assignment is deterministic from (pane_id, terminal_id): concurrent
assigners compute identical names, so registry write races are
harmless (atomic replace, identical content). A pane that closes is
pruned on the next call and its name returns to the pool.

CLI (PANES_JSON env required, from `herdr pane list`):
  msg_names.py map            'pane_id<TAB>name' for live agent panes
  msg_names.py whoami <pane>  the call-sign of one pane
"""
import hashlib
import json
import os
import sys

ADJECTIVES = [
    "amber", "bold", "brave", "brisk", "calm", "civil", "clear", "cobalt",
    "coral", "crisp", "deft", "dusky", "eager", "fleet", "frank", "gentle",
    "glad", "golden", "hardy", "hazel", "humble", "ivory", "jade", "keen",
    "kind", "lively", "lucid", "lunar", "mellow", "merry", "misty", "noble",
    "olive", "opal", "pale", "proud", "quick", "quiet", "rosy", "royal",
    "sage", "sharp", "silent", "silver", "sleek", "solar", "steady", "swift",
]

NOUNS = [
    "badger", "bison", "brook", "canyon", "comet", "condor", "coyote",
    "crane", "creek", "delta", "dune", "eagle", "ember", "falcon", "fern",
    "finch", "fjord", "fox", "gecko", "glacier", "grove", "gull", "harbor",
    "hawk", "heron", "ibis", "iris", "island", "jaguar", "kestrel", "kite",
    "lagoon", "lark", "lemur", "lotus", "lynx", "maple", "marmot", "marten",
    "meadow", "mesa", "moth", "newt", "oriole", "osprey", "otter", "owl",
    "panda", "pebble", "pelican", "pine", "plover", "prairie", "puffin",
    "quail", "raven", "reef", "ridge", "river", "robin", "sparrow",
    "summit", "swan", "wren",
]


def state_file():
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    # Preserve the pre-rename location so existing live-pane call-signs survive.
    return os.path.join(base, "herdr-messenger", "names.tsv")


def load_registry():
    reg = {}
    try:
        with open(state_file()) as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) == 3:
                    reg[(parts[0], parts[1])] = parts[2]
    except FileNotFoundError:
        pass
    return reg


def save_registry(reg):
    path = state_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w") as f:
        for (pane, term), name in sorted(reg.items()):
            f.write(f"{pane}\t{term}\t{name}\n")
    os.replace(tmp, path)


def candidates(key):
    total = len(ADJECTIVES) * len(NOUNS)
    start = int(hashlib.sha1(key.encode()).hexdigest(), 16) % total
    for i in range(total):
        idx = (start + i) % total
        yield f"{ADJECTIVES[idx % len(ADJECTIVES)]}-{NOUNS[idx // len(ADJECTIVES)]}"


def ensure_names(panes):
    """Return {pane_id: call-sign} for agent panes, assigning missing ones."""
    agents = sorted((p for p in panes if p.get("agent")), key=lambda p: p["pane_id"])
    reg = load_registry()
    live = {(p["pane_id"], p.get("terminal_id", "")) for p in agents}
    pruned = {k: v for k, v in reg.items() if k in live}
    used = set(pruned.values())
    out, changed = {}, len(pruned) != len(reg)
    for p in agents:
        key = (p["pane_id"], p.get("terminal_id", ""))
        name = pruned.get(key)
        if not name:
            name = next(c for c in candidates("|".join(key)) if c not in used)
            pruned[key] = name
            used.add(name)
            changed = True
        out[p["pane_id"]] = name
    if changed:
        save_registry(pruned)
    return out


def main():
    panes = json.loads(os.environ["PANES_JSON"])["result"]["panes"]
    names = ensure_names(panes)
    cmd = sys.argv[1] if len(sys.argv) > 1 else "map"
    if cmd == "map":
        for pid, name in sorted(names.items()):
            print(f"{pid}\t{name}")
    elif cmd == "whoami":
        pane = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("HERDR_PANE_ID", "")
        name = names.get(pane)
        if not name:
            print(f"pane '{pane}' is not a live agent pane", file=sys.stderr)
            sys.exit(3)
        print(name)
    else:
        print(f"unknown command '{cmd}' (map|whoami)", file=sys.stderr)
        sys.exit(64)


if __name__ == "__main__":
    main()
