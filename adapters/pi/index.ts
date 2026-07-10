import { realpathSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";


type Outcome = {
  kind: string;
  display: string;
  context: string;
  detail: string;
};

const ROOT = resolve(dirname(realpathSync(fileURLToPath(import.meta.url))), "../..");

export default function messenger(pi: ExtensionAPI) {
  if (process.env.HERDR_ENV !== "1") return;

  pi.on("resources_discover", () => ({
    skillPaths: [resolve(ROOT, "skills/msg/SKILL.md")],
  }));

  pi.registerCommand("msg", {
    description: "Message another agent session in herdr",
    handler: async (args, ctx) => {
      const completed = await pi.exec(
        "python3",
        [resolve(ROOT, "scripts/harness_command.py"), "--arguments", args],
        { timeout: 200_000 },
      );

      if (completed.code !== 0) {
        ctx.ui.notify(completed.stderr.trim() || "Messenger failed.", "error");
        return;
      }

      const outcome = JSON.parse(completed.stdout) as Outcome;
      if (outcome.kind === "cancelled") return;
      if (outcome.kind === "draft") {
        pi.sendUserMessage(outcome.context);
        return;
      }

      const level = outcome.kind === "failure" ? "error" : "info";
      ctx.ui.notify(outcome.display, level);
    },
  });
}
