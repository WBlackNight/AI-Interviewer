/* npm start uses the same Python entry and local environment as the root launcher. */
import { existsSync } from "node:fs";
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const local = path.join(
  root,
  "backend/.venv",
  process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
);
const child = spawn(
  existsSync(local) ? local : "python",
  [
    path.join(root, "tools/project.py"),
    "serve",
    "--port",
    process.env.PORT || "3000",
    ...process.argv.slice(2),
  ],
  { cwd: root, stdio: "inherit", windowsHide: true },
);
child.on("error", () => {
  console.error(
    "Python backend could not start. Install backend/requirements.txt in backend/.venv.",
  );
  process.exitCode = 1;
});
child.on("exit", (code) => {
  process.exitCode = code ?? 1;
});
for (const signal of ["SIGINT", "SIGTERM"])
  process.on(signal, () => child.kill(signal));
