import assert from "node:assert/strict";
import { test } from "node:test";
import { canCancelInterview, isInterviewTerminal, snapshotStatus } from "../lib/interview-status";
import { cancelInterview } from "../lib/api";

test("cancelled records are terminal and cannot offer a continue or second cancellation", () => {
  for (const status of ["finished", "cancelled"]) {
    assert.ok(isInterviewTerminal(status)); assert.equal(canCancelInterview(status), false);
  }
  for (const status of ["created", "running"]) {
    assert.equal(isInterviewTerminal(status), false); assert.ok(canCancelInterview(status));
  }
});

test("cancelled snapshots remain distinct from successfully finished interviews", () => {
  assert.equal(snapshotStatus({ finished: true, cancelled: true, state: "cancelled" }), "cancelled");
  assert.equal(snapshotStatus({ finished: true, state: "cancelled" }), "cancelled");
  assert.equal(snapshotStatus({ finished: true, state: "finished" }), "finished");
  assert.equal(snapshotStatus({ finished: false, state: "questioning" }), "active");
});

test("cancellation uses the resource header and does not send or invent scores", async t => {
  const original = Object.getOwnPropertyDescriptor(globalThis, "sessionStorage");
  Object.defineProperty(globalThis, "sessionStorage", { configurable: true, value: { getItem: () => "synthetic-token" } });
  t.after(() => original ? Object.defineProperty(globalThis, "sessionStorage", original) : Reflect.deleteProperty(globalThis, "sessionStorage"));
  t.mock.method(globalThis, "fetch", async (url: string, init: RequestInit) => {
    assert.ok(url.endsWith("/api/interview/sample/cancel")); assert.equal(init.method, "POST");
    assert.equal((init.headers as Record<string, string>)["X-Interview-Token"], "synthetic-token");
    assert.equal(init.body, undefined);
    return new Response('{"interview_id":"sample","status":"cancelled","changed":true,"version":2,"report_url":"/report/sample"}');
  });
  assert.equal((await cancelInterview("sample")).status, "cancelled");
});

test("a conflict is surfaced so the user can refresh and retry instead of showing success", async t => {
  t.mock.method(globalThis, "fetch", async () => new Response('{"detail":"面试已更新，请重试取消"}', { status: 409 }));
  await assert.rejects(cancelInterview("sample"), /请重试取消/);
});
