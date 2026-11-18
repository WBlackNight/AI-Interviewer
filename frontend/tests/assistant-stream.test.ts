import assert from 'node:assert/strict';
import { test, TestContext } from 'node:test';
import { parseFrame, streamChat } from '../assistant/transport';
import { ChatEvent, safeLink } from '../assistant/types';

function storage(t: TestContext) {
  const original = Object.getOwnPropertyDescriptor(globalThis, 'sessionStorage');
  const values = new Map<string, string>();
  Object.defineProperty(globalThis, 'sessionStorage', { configurable: true, value: { getItem: (key: string) => values.get(key) || null } });
  t.after(() => original ? Object.defineProperty(globalThis, 'sessionStorage', original) : Reflect.deleteProperty(globalThis, 'sessionStorage'));
  return values;
}
function response(parts: Uint8Array[]) {
  return new Response(new ReadableStream({ start(controller) { parts.forEach(part => controller.enqueue(part)); controller.close(); } }),
    { headers: { 'content-type': 'text/event-stream' } });
}
const encode = (text: string) => new TextEncoder().encode(text);

test('SSE parser accepts data frames and rejects malformed or unknown events', () => {
  assert.equal(parseFrame(': keepalive'), null);
  assert.deepEqual(parseFrame('data: {"type":"stage","label":"正在检索"}'), { type: 'stage', label: '正在检索' });
  for (const frame of ['data: {"type":"execute"}', 'data: {"type":"delta","text":{}}', 'data: {"type":"done","version":-1}']) {
    assert.throws(() => parseFrame(frame));
  }
});

test('UTF-8 deltas split across packets and CRLF frames preserve full text', async t => {
  storage(t);
  const bytes = encode('data: {"type":"delta","text":"你好小青"}\r\n\r\ndata: {"type":"done","version":1}\r\n\r\n');
  t.mock.method(globalThis, 'fetch', async () => response(Array.from(bytes, byte => new Uint8Array([byte]))));
  const events: ChatEvent[] = [];
  await streamChat('/api/assistant/demo', {}, '', new AbortController().signal, event => events.push(event));
  assert.deepEqual(events, [{ type: 'delta', text: '你好小青' }, { type: 'done', version: 1 }]);
});

test('a grounding revision replaces provisional content with bounded learning guidance', async t => {
  storage(t);
  t.mock.method(globalThis, 'fetch', async () => response([encode('data: {"type":"delta","text":"临时片段"}\n\ndata: {"type":"revision","text":"依据中的学习指引","reason":"已切换"}\n\ndata: {"type":"done","version":1}\n\n')]));
  let shown = '';
  await streamChat('/api/assistant/demo', {}, '', new AbortController().signal, event => {
    if (event.type === 'delta') shown += event.text;
    if (event.type === 'revision') shown = event.text;
  });
  assert.equal(shown, '依据中的学习指引');
  assert.throws(() => parseFrame('data: {"type":"revision","text":"x","reason":{}}'));
});

test('truncated streams and explicit server errors are retryable failures', async t => {
  storage(t);
  for (const text of ['data: {"type":"delta","text":"未完成"}\n\n', 'data: {"type":"error","message":"请重试"}\n\n']) {
    t.mock.method(globalThis, 'fetch', async () => response([encode(text)]));
    await assert.rejects(streamChat('/api/assistant/demo', {}, '', new AbortController().signal, () => {}));
    t.mock.restoreAll();
  }
});

test('account changes prevent old identity content from being rendered', async t => {
  const values = storage(t);
  const identity = { access_token: 'a'.repeat(64), account: { id: 'b'.repeat(32), username: 'demo' }, expires_at: '2099-01-01T00:00:00Z' };
  values.set('account:session', JSON.stringify(identity));
  t.mock.method(globalThis, 'fetch', async () => { values.clear(); return response([encode('data: {"type":"delta","text":"private"}\n\n')]); });
  const rendered: ChatEvent[] = [];
  await assert.rejects(streamChat('/api/assistant/conversations/x/turns', {}, identity.access_token, new AbortController().signal, value => rendered.push(value)), /账户已变化/);
  assert.deepEqual(rendered, []);
});

test('caller cancellation prevents late content from appearing', async t => {
  storage(t);
  const controller = new AbortController();
  t.mock.method(globalThis, 'fetch', async () => { controller.abort(); return response([encode('data: {"type":"done","version":0}\n\n')]); });
  await assert.rejects(streamChat('/api/assistant/demo', {}, '', controller.signal, () => assert.fail('must not render')), { name: 'AbortError' });
});

test('assistant action links stay within the allowed application routes', () => {
  for (const link of ['https://evil.test', '//evil.test', 'javascript:alert(1)', '/account/delete', '/report/not-an-id']) assert.equal(safeLink(link), '/guide');
  assert.equal(safeLink('/catalog?position=java_backend'), '/catalog?position=java_backend');
  assert.equal(safeLink('/?position=java_backend#start'), '/?position=java_backend#start');
});
