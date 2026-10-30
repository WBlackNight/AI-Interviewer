import assert from "node:assert/strict";
import { test, type TestContext } from "node:test";
import { createInterview, createWeakPractice } from "../lib/api";

function installStorage(t: TestContext, value: object) {
  const original = Object.getOwnPropertyDescriptor(globalThis, "sessionStorage");
  Object.defineProperty(globalThis, "sessionStorage", { configurable: true, value });
  t.after(() => {
    if (original) Object.defineProperty(globalThis, "sessionStorage", original);
    else Reflect.deleteProperty(globalThis, "sessionStorage");
  });
}

test("topic practice sends only the explicit scope and saves its independent credential", async t => {
  const saved = new Map<string, string>();
  installStorage(t, {
    getItem: (key: string) => saved.get(key) ?? null,
    setItem: (key: string, value: string) => saved.set(key, value),
  });
  t.mock.method(globalThis, "fetch", async (url: string, init: RequestInit) => {
    assert.ok(url.endsWith("/api/interview")); assert.equal(init.method, "POST");
    assert.deepEqual(JSON.parse(init.body as string), { position: "python_backend", difficulty: "hard", themes: ["Python基础"] });
    return new Response(JSON.stringify({ interview_id: "new", access_token: "new-token", plan: [] }));
  });
  await createInterview({ position: "python_backend", difficulty: "hard", themes: ["Python基础"] });
  assert.ok([...saved.values()].includes("new-token"));
});

test("weak retry authorizes the source and stores a separate credential without overwriting it", async t => {
  const saved = new Map<string, string>([["interview:source:token", "source-token"]]);
  installStorage(t, {
    getItem: (key: string) => saved.get(key) ?? null,
    setItem: (key: string, value: string) => saved.set(key, value),
  });
  t.mock.method(globalThis, "fetch", async (url: string, init: RequestInit) => {
    assert.ok(url.endsWith("/api/interview/source/practice")); assert.equal(init.method, "POST");
    assert.equal((init.headers as Record<string, string>)["X-Interview-Token"], "source-token");
    assert.equal(init.body, undefined); // 主题由服务端报告决定。
    return new Response(JSON.stringify({ interview_id: "retry", access_token: "retry-token", plan: [] }));
  });
  const retry = await createWeakPractice("source");
  assert.equal(retry.interview_id, "retry");
  assert.equal(saved.get("interview:retry:token"), "retry-token");
  assert.equal(saved.get("interview:source:token"), "source-token");
});

test("unfinished or unauthorized sources expose the server error without saving new access", async t => {
  let writes = 0;
  installStorage(t, { getItem: () => "source-token", setItem: () => { writes++; } });
  t.mock.method(globalThis, "fetch", async () => new Response('{"detail":"请完成本场面试后再复练薄弱主题"}', { status: 409 }));
  await assert.rejects(createWeakPractice("source"), /请完成本场/);
  assert.equal(writes, 0);
});
