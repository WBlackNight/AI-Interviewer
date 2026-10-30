import assert from "node:assert/strict";
import { test } from "node:test";
import { exportReport } from "../lib/api";

test("export sends the resource header and downloads the complete attachment", async t => {
  const storage = Object.getOwnPropertyDescriptor(globalThis, "sessionStorage");
  const dom = Object.getOwnPropertyDescriptor(globalThis, "document");
  t.after(() => {
    if (storage) Object.defineProperty(globalThis, "sessionStorage", storage);
    else Reflect.deleteProperty(globalThis, "sessionStorage");
    if (dom) Object.defineProperty(globalThis, "document", dom);
    else Reflect.deleteProperty(globalThis, "document");
  });
  Object.defineProperty(globalThis, "sessionStorage", { configurable: true, value: { getItem: () => "synthetic-token" } });
  let clicked = 0, removed = 0;
  const anchor = { href: "", download: "", click() { clicked++; }, remove() { removed++; } };
  Object.defineProperty(globalThis, "document", { configurable: true, value: {
    createElement: () => anchor, body: { appendChild: () => {} },
  } });
  t.mock.method(globalThis, "fetch", async (url: string, init: RequestInit) => {
    assert.ok(url.endsWith("/api/interview/example/report/export?format=json"));
    assert.equal((init.headers as Record<string, string>)["X-Interview-Token"], "synthetic-token");
    assert.equal(init.cache, "no-store");
    return new Response('{"per_question":[{"answer_text":"完整回答"}]}');
  });
  t.mock.method(URL, "createObjectURL", (blob: Blob) => { assert.ok(blob.size > 0); return "blob:synthetic"; });
  const revoke = t.mock.method(URL, "revokeObjectURL", () => {});
  await exportReport("example", "json");
  assert.equal(clicked, 1); assert.equal(removed, 1);
  assert.equal(anchor.download, "interview-example.json");
  await new Promise(resolve => setTimeout(resolve, 1100));
  assert.equal(revoke.mock.calls.length, 1);
});

test("authorization failure is surfaced without generating a download", async t => {
  t.mock.method(globalThis, "fetch", async () => new Response('{"detail":"面试访问凭据无效"}', { status: 403 }));
  const create = t.mock.method(URL, "createObjectURL", () => { throw new Error("must not download"); });
  await assert.rejects(exportReport("example", "markdown"), /面试访问凭据无效/);
  assert.equal(create.mock.calls.length, 0);
});
