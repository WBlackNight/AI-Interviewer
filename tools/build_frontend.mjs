/* Vite production entries, with hashes checked by the same-origin Python build. */
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const requireFrontend = createRequire(path.join(root, "frontend/package.json"));
const { build } = await import(
  pathToFileURL(requireFrontend.resolve("vite")).href
);
const { default: react } = await import(
  pathToFileURL(requireFrontend.resolve("@vitejs/plugin-react")).href
);
const hash = (data) => crypto.createHash("sha256").update(data).digest("hex");
const entries = {
  assistant: "assistant/entry.tsx",
  studio: "studio/entry.tsx",
  widget: "widget/entry.tsx",
  admin: "admin/entry.tsx",
};
const requested = process.argv[2];
if (requested && !Object.hasOwn(entries, requested))
  throw new Error("Unknown frontend entry");
function sourceFiles(directory) {
  return fs
    .readdirSync(path.join(root, directory), { withFileTypes: true })
    .flatMap((item) =>
      item.isDirectory()
        ? sourceFiles(directory + "/" + item.name)
        : /\.tsx?$/.test(item.name)
          ? [directory + "/" + item.name]
          : [],
    );
}
const inputs = [
  "tools/build_frontend.mjs",
  "frontend/vite.config.mjs",
  "frontend/package.json",
  "frontend/package-lock.json",
  "frontend/tsconfig.json",
  "frontend/tsconfig.web.json",
  ...[
    "frontend/assistant",
    "frontend/studio",
    "frontend/shared",
    "frontend/lib",
    "frontend/widget",
    "frontend/admin",
  ].flatMap(sourceFiles),
].sort();
for (const [name, entry] of Object.entries(entries)) {
  if (requested && requested !== name) continue;
  const results = await build({
    root: path.join(root, "frontend"),
    configFile: false,
    plugins: [react()],
    logLevel: "warn",
    define: { "process.env.NODE_ENV": '"production"' },
    build: {
      write: false,
      target: "es2020",
      minify: true,
      sourcemap: false,
      lib: {
        entry: path.join(root, "frontend", entry),
        name: "Qingzhan" + name,
        formats: ["iife"],
        fileName: () => name + ".js",
      },
    },
  });
  const outputs = (Array.isArray(results) ? results : [results]).flatMap(
    (result) => result.output,
  );
  const bundle = outputs.find((item) => item.type === "chunk");
  if (!bundle || outputs.length !== 1)
    throw new Error("Expected one self-contained entry");
  const bytes = Buffer.from(bundle.code),
    output = path.join(root, "ui/compiled");
  fs.mkdirSync(output, { recursive: true });
  fs.writeFileSync(path.join(output, name + ".js"), bytes);
  fs.writeFileSync(
    path.join(output, name + ".json"),
    JSON.stringify(
      {
        builder: "vite",
        files: Object.fromEntries(
          inputs.map((file) => [
            file,
            hash(
              fs
                .readFileSync(path.join(root, file), "utf8")
                .replace(/\r\n?/g, "\n"),
            ),
          ]),
        ),
        sha256: hash(bytes),
        bytes: bytes.length,
      },
      null,
      2,
    ) + "\n",
  );
  console.log(`${name}: Vite + React, ${bytes.length} bytes`);
}
