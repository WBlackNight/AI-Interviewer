import assert from "node:assert/strict";
import { test, type TestContext } from "node:test";
import { clearAccountSession, getAccountSession, saveAccountSession } from "../lib/account";
import { getAccess, getAnonymousAccess } from "../lib/access";
import { authenticate, claimInterview, createInterview, getAccountHistory, logoutAccount } from "../lib/api";

const session = { account: { id: "a".repeat(32), username: "demo_user" }, access_token: "b".repeat(64), expires_at: "2099-01-01T00:00:00Z" };

function storage(t: TestContext) {
  const data = new Map<string, string>();
  const original = Object.getOwnPropertyDescriptor(globalThis, "sessionStorage");
  Object.defineProperty(globalThis, "sessionStorage", { configurable: true, value: {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => data.set(key, value),
    removeItem: (key: string) => data.delete(key),
  } });
  t.after(() => original ? Object.defineProperty(globalThis, "sessionStorage", original) : Reflect.deleteProperty(globalThis, "sessionStorage"));
  return data;
}

test("account sessions expire and malformed or blocked storage does not grant access", t => {
  const data = storage(t);
  assert.equal(getAccountSession(), null);
  saveAccountSession(session);
  assert.deepEqual(getAccountSession(), session);
  data.set("account:session", "{bad json");
  assert.equal(getAccountSession(), null);
  saveAccountSession({ ...session, expires_at: "2000-01-01T00:00:00Z" });
  assert.equal(getAccountSession(), null);
  clearAccountSession(); assert.equal(data.size, 0);
  t.mock.method(sessionStorage, "getItem", () => { throw new Error("storage unavailable"); });
  assert.equal(getAccountSession(), null);
});

test("resource reads use the active account while claim reads the original anonymous proof", t => {
  const data = storage(t);
  data.set("interview:old:token", "anonymous-token");
  saveAccountSession(session);
  assert.equal(getAccess("interview", "old"), session.access_token);
  assert.equal(getAnonymousAccess("interview", "old"), "anonymous-token");
  clearAccountSession();
  assert.equal(getAccess("interview", "old"), "anonymous-token");
});

test("login stores only the response session and sends credentials only in the POST body", async t => {
  const data = storage(t);
  t.mock.method(globalThis, "fetch", async (url: string, init: RequestInit) => {
    assert.ok(url.endsWith("/api/auth/login")); assert.ok(!url.includes("synthetic-password"));
    assert.deepEqual(JSON.parse(init.body as string), { username: "demo_user", password: "synthetic-password" });
    assert.equal(init.cache, "no-store");
    return new Response(JSON.stringify(session));
  });
  await authenticate("login", "demo_user", "synthetic-password");
  assert.deepEqual(getAccountSession(), session);
  assert.ok([...data.values()].every(value => !value.includes("synthetic-password")));
});

test("claim requires both account authorization and anonymous proof, then forgets only that proof", async t => {
  const data = storage(t);
  saveAccountSession(session); data.set("interview:old:token", "c".repeat(64));
  data.set("interview:other:token", "d".repeat(64));
  t.mock.method(globalThis, "fetch", async (url: string, init: RequestInit) => {
    assert.ok(url.endsWith("/api/account/interviews/old/claim"));
    assert.equal((init.headers as Record<string, string>).Authorization, `Bearer ${session.access_token}`);
    assert.deepEqual(JSON.parse(init.body as string), { access_token: "c".repeat(64) });
    return new Response('{"claimed":true}');
  });
  await claimInterview("old");
  assert.equal(getAnonymousAccess("interview", "old"), null);
  assert.equal(getAnonymousAccess("interview", "other"), "d".repeat(64));
});

test("failed claim preserves the anonymous credential", async t => {
  const data = storage(t); saveAccountSession(session);
  data.set("interview:old:token", "c".repeat(64));
  t.mock.method(globalThis, "fetch", async () => new Response('{"detail":"无法认领该面试"}', { status: 403 }));
  await assert.rejects(claimInterview("old"), /无法认领/);
  assert.equal(getAnonymousAccess("interview", "old"), "c".repeat(64));
});

test("owned creations send account authorization and do not save a null anonymous token", async t => {
  const data = storage(t); saveAccountSession(session);
  t.mock.method(globalThis, "fetch", async (_url: string, init: RequestInit) => {
    assert.equal((init.headers as Record<string, string>).Authorization, `Bearer ${session.access_token}`);
    return new Response('{"interview_id":"owned","access_token":null,"account_owned":true,"plan":[]}');
  });
  assert.ok((await createInterview({ position: "python_backend", difficulty: "mid" })).account_owned);
  assert.equal(data.has("interview:owned:token"), false);
});

test("history uses account pagination; failed logout keeps local access until revocation succeeds", async t => {
  storage(t); saveAccountSession(session);
  t.mock.method(globalThis, "fetch", async (url: string) => {
    if (url.includes("/account/interviews")) {
      assert.ok(url.endsWith("offset=20&limit=20"));
      return new Response('{"items":[],"total":20,"offset":20,"limit":20,"has_more":false}');
    }
    return new Response('{"detail":"网络服务暂不可用"}', { status: 503 });
  });
  assert.equal((await getAccountHistory(20)).offset, 20);
  await assert.rejects(logoutAccount(), /暂不可用/);
  assert.ok(getAccountSession());
  t.mock.method(globalThis, "fetch", async () => new Response('{"logged_out":true}'));
  await logoutAccount(); assert.equal(getAccountSession(), null);
});
