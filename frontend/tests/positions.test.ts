import assert from "node:assert/strict";
import { test } from "node:test";
import { getPositions } from "../lib/api";

test("position choices and labels come from the server without a Java-only fallback", async t => {
  t.mock.method(globalThis, "fetch", async (url: string, init: RequestInit) => {
    assert.ok(url.endsWith('/api/positions')); assert.equal(init.cache, 'no-store');
    return new Response(JSON.stringify({ positions: [{ id:'custom', display_name:'自定义岗位', roots:['基础'], question_count:2 }] }));
  });
  const data = await getPositions();
  assert.equal(data.positions[0].display_name, '自定义岗位');
  assert.equal(data.positions[0].id, 'custom');
});
test("empty and failed catalogs do not invent available positions", async t => {
  t.mock.method(globalThis, 'fetch', async () => new Response('{"positions":[]}'));
  assert.deepEqual((await getPositions()).positions, []);
  t.mock.method(globalThis, 'fetch', async () => new Response('{"detail":"服务暂不可用"}', {status:503}));
  await assert.rejects(getPositions(), /服务暂不可用/);
});
