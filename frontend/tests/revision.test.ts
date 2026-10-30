import assert from "node:assert/strict";
import { test } from "node:test";
import { addRevisionTasks, createRevisionPractice, getRevisionTasks, updateRevisionTask, scheduleRevisionTask } from "../lib/api";

test("adding revision tasks sends no client-selected themes, scores or completion state", async t => {
  t.mock.method(globalThis, "fetch", async (url: string, init: RequestInit) => {
    assert.match(url, /\/api\/account\/interviews\/source-id\/revision-tasks$/);
    assert.equal(init.method, "POST"); assert.equal(init.body, undefined); assert.equal(init.cache, "no-store");
    return new Response('{"items":[],"added":0,"existing":2}');
  });
  assert.equal((await addRevisionTasks("source-id")).existing, 2);
});

test("task practice delegates scope to the server and preserves a reused session response", async t => {
  t.mock.method(globalThis, "fetch", async (url: string, init: RequestInit) => {
    assert.match(url, /\/revision-tasks\/task-id\/practice$/);
    assert.equal(init.method, "POST"); assert.equal(init.body, undefined);
    return new Response('{"interview_id":"active-id","revision_task_id":"task-id","reused":true,"account_owned":true,"access_token":null}');
  });
  const result = await createRevisionPractice("task-id");
  assert.equal(result.interview_id, "active-id"); assert.equal(result.reused, true); assert.equal(result.access_token, null);
});

test("an unavailable task topic surfaces an error without fabricating a general interview", async t => {
  t.mock.method(globalThis, "fetch", async () => new Response('{"detail":"任务主题当前没有可用知识题"}', { status: 422 }));
  await assert.rejects(createRevisionPractice("task-id"), /任务主题当前没有可用知识题/);
});

test("task filters preserve all-status queries, encode positions and request page bounds", async t => {
  const queries: URLSearchParams[] = [];
  t.mock.method(globalThis, "fetch", async (url: string) => {
    queries.push(new URL(url).searchParams);
    return new Response('{"items":[],"total":0,"offset":20,"limit":20,"has_more":false}');
  });
  await getRevisionTasks(undefined, "A&B", 20);
  await getRevisionTasks("done", "python_backend");
  assert.equal(queries[0].get("status"), null); assert.equal(queries[0].get("position"), "A&B");
  assert.equal(queries[0].get("offset"), "20"); assert.equal(queries[0].get("limit"), "20");
  assert.equal(queries[1].get("status"), "done");
});

test("completion updates only manual status without rewriting scores", async t => {
  t.mock.method(globalThis, "fetch", async (url: string, init: RequestInit) => {
    assert.match(url, /\/revision-tasks\/task-id$/); assert.equal(init.method, "PATCH");
    assert.deepEqual(JSON.parse(init.body as string), { status: "done" });
    return new Response('{"id":"task-id","status":"done"}');
  });
  assert.equal((await updateRevisionTask("task-id", "done")).status, "done");
});

test("expired or unowned task access surfaces the server failure", async t => {
  t.mock.method(globalThis, "fetch", async () => new Response('{"detail":"请先登录"}', { status: 401 }));
  await assert.rejects(getRevisionTasks(), /请先登录/);
  await assert.rejects(addRevisionTasks("source-id"), /请先登录/);
  await assert.rejects(updateRevisionTask("task-id", "todo"), /请先登录/);
});

test("date filtering survives pagination and combines with manual state and position", async t => {
  t.mock.method(globalThis, "fetch", async (url: string) => {
    const query = new URL(url).searchParams;
    assert.equal(query.get("due"), "overdue"); assert.equal(query.get("offset"), "20");
    assert.equal(query.get("status"), "todo"); assert.equal(query.get("position"), "python_backend");
    return new Response('{"items":[],"today":"2026-10-24","timezone":"Asia/Shanghai"}');
  });
  assert.equal((await getRevisionTasks("todo", "python_backend", 20, "overdue")).today, "2026-10-24");
});

test("rescheduling preserves calendar strings without timezone conversion and clearing uses explicit null", async t => {
  const payloads: unknown[] = [];
  t.mock.method(globalThis, "fetch", async (_url: string, init: RequestInit) => {
    assert.equal(init.method, "PATCH");
    const payload = JSON.parse(init.body as string); payloads.push(payload);
    return new Response(JSON.stringify({ id: "task-id", status: "done", ...payload }));
  });
  assert.equal((await scheduleRevisionTask("task-id", "2026-10-24")).status, "done");
  assert.equal((await scheduleRevisionTask("task-id", null)).due_date, null);
  assert.deepEqual(payloads, [{ due_date: "2026-10-24" }, { due_date: null }]);
});

test("a rejected calendar change surfaces the validation error", async t => {
  t.mock.method(globalThis, "fetch", async () => new Response('{"detail":"日期无效"}', { status: 422 }));
  await assert.rejects(scheduleRevisionTask("task-id", "2026-02-30"), /日期无效/);
});
