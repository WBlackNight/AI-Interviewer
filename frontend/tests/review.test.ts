import assert from "node:assert/strict";
import { test } from "node:test";
import { getAccountReview } from "../lib/api";
import { originLabel, originVersions } from "../lib/score-origin";

test("historical unknown origins are not relabeled from a configured model", () => {
  assert.equal(originLabel(), "来源未记录");
  assert.equal(originVersions({ source: "unknown", model: "current-model" }), "历史来源与版本未记录");
  assert.equal(originLabel({ source: "unrecognized" }), "来源未记录");
});

test("cache and fallback labels explain how the score was produced", () => {
  assert.match(originLabel({ source: "llm", cached: true }), /缓存命中，本轮未调用评分模型/);
  assert.match(originLabel({ source: "heuristic_fallback" }), /模型失败后规则回退/);
  assert.match(originLabel({ source: "heuristic", sandbox_applied: true }), /含客观判题合分/);
  assert.match(originVersions({ source: "heuristic_fallback", model: "fake-model", config_version: "cfg", fallback_reason: "timeout" }), /fake-model.*cfg.*timeout/);
});

test("review queries encode position/theme and preserve session pagination", async t => {
  t.mock.method(globalThis, "fetch", async (url: string, init: RequestInit) => {
    const query = new URL(url).searchParams;
    assert.equal(query.get("position"), "python_backend");
    assert.equal(query.get("theme"), "Web与数据&事务");
    assert.equal(query.get("offset"), "20"); assert.equal(query.get("limit"), "20");
    assert.equal(init.cache, "no-store");
    return new Response('{"items":[],"total":20,"offset":20,"limit":20,"has_more":false}');
  });
  assert.equal((await getAccountReview("python_backend", "Web与数据&事务", 20)).offset, 20);
});

test("unauthorized review does not fabricate an empty successful history", async t => {
  t.mock.method(globalThis, "fetch", async () => new Response('{"detail":"请先登录"}', { status: 401 }));
  await assert.rejects(getAccountReview(), /请先登录/);
});
