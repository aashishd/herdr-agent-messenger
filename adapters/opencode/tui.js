import { execFile } from "node:child_process";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";


const execFileAsync = promisify(execFile);
const ROOT = fileURLToPath(new URL("../../", import.meta.url));

async function invoke(argumentsText) {
  const { stdout } = await execFileAsync(
    "python3",
    [`${ROOT}scripts/harness_command.py`, "--arguments", argumentsText],
    { env: process.env, timeout: 200_000 },
  );
  return JSON.parse(stdout);
}

async function handle(api, argumentsText) {
  let outcome;
  try {
    outcome = await invoke(argumentsText);
  } catch (error) {
    api.ui.toast({ variant: "error", message: error.message || "Messenger failed." });
    return;
  }

  if (outcome.kind === "cancelled") return;
  if (outcome.kind === "draft") {
    const route = api.route.current;
    const sessionID = route.name === "session" ? route.params.sessionID : undefined;
    if (!sessionID) {
      api.ui.toast({ variant: "error", message: "Open a session before requesting an agent draft." });
      return;
    }
    await api.client.session.promptAsync({
      sessionID,
      parts: [{ type: "text", text: outcome.context }],
    });
    return;
  }

  api.ui.toast({
    variant: outcome.kind === "failure" ? "error" : "info",
    message: outcome.display,
  });
}

const plugin = {
  id: "herdr-agent-messenger",
  tui: async (api) => {
    if (process.env.HERDR_ENV !== "1") return;

    api.keymap.registerLayer({
      commands: [
        {
          name: "herdr-agent-messenger.open",
          title: "Messenger",
          category: "Plugin",
          namespace: "palette",
          slashName: "msg",
          run: () => handle(api, ""),
        },
        {
          name: "herdr-agent-messenger.whoami",
          title: "Messenger: show call-sign",
          category: "Plugin",
          namespace: "palette",
          slashName: "msg-whoami",
          run: () => handle(api, "whoami"),
        },
      ],
    });
  },
};

export default plugin;
