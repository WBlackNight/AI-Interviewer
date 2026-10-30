/* 用真实原生脚本验证恢复协议；DOM/连接替身只提供脚本使用的浏览器边界。 */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const script = fs.readFileSync(path.join(root, 'assets/interview.js'), 'utf8');
const html = fs.readFileSync(path.join(root, 'interview.html'), 'utf8');
const interviewId = 'a'.repeat(32);
const grant = 'b'.repeat(64);
const turnId = '1'.repeat(32);
const pendingKey = `interview:${interviewId}:pending`;
const question = (turn = turnId) => ({ type: 'question', id: 'main', turn_id: turn, theme: 'MySQL', content: 'Question', seq: 1, version: 1 });
const snapshot = (extra = {}) => ({ type: 'snapshot', version: 1, state: 'questioning', finished: false, current_question: question(), events: [question()], ...extra });
const submission = (extra = {}) => ({ type: 'answer', message_id: 'saved-message', turn_id: turnId, version: 1, text: 'Original answer', ...extra });

class Element {
  constructor() { this.children = []; this.dataset = {}; this.listeners = {}; this.value = ''; this.hidden = false; this.disabled = false; this.text = ''; }
  set textContent(value) { this.text = String(value ?? ''); this.children = []; }
  get textContent() { return this.text + this.children.map(node => node.textContent).join(''); }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; this.text = ''; }
  setAttribute(key, value) { this[key] = value; }
  addEventListener(name, callback) { (this.listeners[name] ||= []).push(callback); }
  async fire(name, properties = {}) { for (const callback of this.listeners[name] || []) await callback({ preventDefault() {}, ...properties }); }
  requestSubmit() { return this.fire('submit'); }
  showModal() { this.open = true; }
  close() { this.open = false; }
  querySelector(name) { return this.parts?.[name]; }
}

function harness({ pending, token = grant } = {}) {
  const nodes = new Map([...html.matchAll(/id="studio-([^"]+)"/g)].map(match => [match[1], new Element()]));
  const copyTag = html.match(/<div id="studio-copy"[^>]+>/)[0];
  for (const match of copyTag.matchAll(/data-([a-z_-]+)="([^"]*)"/g)) {
    nodes.get('copy').dataset[match[1].replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())] = match[2];
  }
  const dimensions = ['技术深度', '表达逻辑', '岗位匹配'].map(label => {
    const node = new Element(); node.dataset.dimension = label; node.parts = { strong: new Element(), meter: new Element() }; return node;
  });
  const storage = new Map();
  if (token) storage.set(`interview:${interviewId}:token`, token);
  if (pending !== undefined) storage.set(pendingKey, typeof pending === 'string' ? pending : JSON.stringify(pending));
  const sockets = [], timers = new Map(), events = {}, requests = [];
  let timerId = 0, messageId = 0;
  class Socket {
    static OPEN = 1;
    constructor(url, protocols) { this.url = url; this.protocols = protocols; this.sent = []; this.readyState = 0; sockets.push(this); }
    send(value) { this.sent.push(JSON.parse(value)); }
    open() { this.readyState = 1; this.onopen?.(); }
    receive(value) { this.onmessage?.({ data: JSON.stringify(value) }); }
    close(code = 1000) { this.readyState = 3; this.onclose?.({ code }); }
  }
  vm.runInNewContext(script, {
    document: { querySelector: selector => nodes.get(selector.replace('#studio-', '')), querySelectorAll: () => dimensions,
      createElement: () => new Element(), body: { dataset: { wsBase: '' } } },
    location: { pathname: `/interview/${interviewId}`, origin: 'http://localhost:3000' },
    sessionStorage: { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key) },
    WebSocket: Socket, URL, TextEncoder, AbortController, Date,
    crypto: { randomUUID: () => `message-${++messageId}` },
    setTimeout: (callback, delay) => { timers.set(++timerId, { callback, delay }); return timerId; }, clearTimeout: id => timers.delete(id),
    addEventListener: (name, callback) => { events[name] = callback; },
    fetch: async (url, options) => { requests.push({ url, options }); return { ok: true, json: async () => ({ status: 'cancelled' }) }; },
  });
  return { nodes, sockets, timers, storage, events, requests, get ws() { return sockets.at(-1); },
    async answer(text = 'Draft answer') { nodes.get('answer').value = text; await nodes.get('answer').fire('input'); },
    async submit() { await nodes.get('form').fire('submit'); },
    connect(data = snapshot()) { this.ws.open(); this.ws.receive(data); },
    nextTimer() { const [id, timer] = [...timers].sort((a, b) => a[1].delay - b[1].delay)[0]; timers.delete(id); timer.callback(); return timer.delay; } };
}

test('credentials use subprotocols; a missing grant does not open a socket', () => {
  const app = harness(); app.connect();
  assert.equal(app.ws.url, `ws://localhost:3000/ws/interview/${interviewId}`);
  assert.equal(app.ws.protocols.join('|'), `interview|${grant}`);
  assert.equal(app.ws.sent[0].type, 'start');
  assert.equal(harness({ token: null }).sockets.length, 0);
});

test('explicit submit is single-flight and acknowledgement waits for next question', async () => {
  const app = harness(); app.connect(); await app.answer(); await app.submit(); await app.submit();
  assert.equal(app.ws.sent.filter(item => item.type === 'answer').length, 1);
  const sent = app.ws.sent.at(-1);
  assert.equal(JSON.parse(app.storage.get(pendingKey)).message_id, sent.message_id);
  app.ws.receive({ type: 'answer_ack', turn_id: turnId, message_id: sent.message_id, answer_text: 'Draft answer', seq: 2, version: 2 });
  assert.equal(app.nodes.get('submit').disabled, true);
  app.ws.receive({ ...question('2'.repeat(32)), seq: 3, version: 2 });
  await app.answer('Next answer'); assert.equal(app.nodes.get('submit').disabled, false);
});

test('restored pending answer resends the exact message only for matching turn and version', () => {
  const saved = submission(); const app = harness({ pending: saved }); app.connect();
  assert.equal(JSON.stringify(app.ws.sent.at(-1)), JSON.stringify(saved));
  assert.equal(app.nodes.get('submit').disabled, true);
});

test('committed snapshot clears pending without resubmission and deduplicates history', () => {
  const saved = submission(); const app = harness({ pending: saved });
  const ack = { type: 'answer_ack', turn_id: turnId, message_id: saved.message_id, answer_text: saved.text, seq: 2 };
  const score = { type: 'score', turn_id: turnId, score: 6, dimensions: {}, evidence: 'Evidence', seq: 3 };
  app.connect(snapshot({ version: 2, events: [question(), ack, score], current_question: question('2'.repeat(32)) }));
  assert.equal(app.ws.sent.length, 1); assert.equal(app.storage.has(pendingKey), false);
  app.ws.receive(score); assert.equal(app.nodes.get('saved-count').textContent, '1 轮');
});

test('stale pending stays read-only and is never reused for a new question', () => {
  const app = harness({ pending: submission({ code: 'private old code' }) });
  app.connect(snapshot({ version: 2, current_question: question('2'.repeat(32)) }));
  assert.equal(app.ws.sent.length, 1); assert.equal(app.storage.has(pendingKey), false);
  assert.equal(app.nodes.get('answer').value, '');
  assert.match(app.nodes.get('recovery-copy').textContent, /private old code/);
});

test('new question preserves unsubmitted draft; committed draft is not mislabelled as unsent', async () => {
  const app = harness(); app.connect(); await app.answer('Unsubmitted');
  app.ws.receive(snapshot({ version: 2, current_question: question('2'.repeat(32)) }));
  assert.equal(app.nodes.get('recovery-copy').textContent, 'Unsubmitted');
  const second = harness(); second.connect(); await second.answer('Submitted'); await second.submit();
  const sent = second.ws.sent.at(-1);
  second.nodes.get('recovery').hidden = true;
  second.ws.receive(snapshot({ version: 2, current_question: question('2'.repeat(32)), events: [question(),
    { type: 'answer_ack', turn_id: turnId, message_id: sent.message_id, answer_text: sent.text, seq: 2 }] }));
  assert.equal(second.nodes.get('recovery').hidden, true);
});

test('IME and plain Enter do not submit; explicit keyboard shortcut submits once', async () => {
  const app = harness(); app.connect(); await app.answer();
  await app.nodes.get('answer').fire('keydown', { key: 'Enter', ctrlKey: true, isComposing: true });
  await app.nodes.get('answer').fire('keydown', { key: 'Enter', ctrlKey: true, keyCode: 229 });
  await app.nodes.get('answer').fire('keydown', { key: 'Enter' });
  assert.equal(app.ws.sent.length, 1);
  await app.nodes.get('answer').fire('keydown', { key: 'Enter', ctrlKey: true });
  assert.equal(app.ws.sent.length, 2);
});

test('retryable failure keeps editable text and does not silently retry a write', async () => {
  const app = harness(); app.connect(); await app.answer('Keep this'); await app.submit();
  app.ws.receive({ type: 'error', code: 'processing_failed', retryable: true, detail: 'Try again' });
  assert.equal(app.nodes.get('answer').value, 'Keep this');
  assert.equal(app.nodes.get('answer').disabled, false); assert.equal(app.ws.sent.length, 2);
  const resumed = harness({ pending: submission() }); resumed.connect();
  resumed.ws.receive({ type: 'error', code: 'processing_failed', retryable: true });
  assert.equal(resumed.nodes.get('recovery-copy').textContent, 'Original answer');
  assert.equal(resumed.storage.has(pendingKey), false);
});

test('reconnect backoff is bounded; authorization rejection stops reconnecting', () => {
  const app = harness(); const delays = [];
  for (let index = 0; index < 6; index++) { app.ws.close(1006); delays.push(app.nextTimer()); }
  app.ws.close(1006);
  assert.deepEqual(delays, [1000, 2000, 4000, 8000, 10000, 10000]); assert.equal(app.timers.size, 0);
  const rejected = harness(); rejected.ws.close(4403);
  assert.equal(rejected.timers.size, 0); assert.equal(rejected.nodes.get('workspace').hidden, true);
  assert.equal(rejected.nodes.get('access').hidden, false);
});

test('corrupt pending data and oversized UTF-8 code are not sent', async () => {
  for (const pending of ['{invalid', submission({ version: -1 }), submission({ text: 'x'.repeat(20001) })]) {
    const app = harness({ pending }); app.connect(); assert.equal(app.ws.sent.length, 1);
  }
  const app = harness(); app.connect(snapshot({ current_question: { ...question(), is_coding: true } }));
  app.nodes.get('code').value = '中'.repeat(6000); await app.submit(); assert.equal(app.ws.sent.length, 1);
});

test('pagehide closes own socket and cancels reconnect; pageshow restores via snapshot', () => {
  const app = harness(); app.ws.close(1006); app.events.pagehide(); assert.equal(app.timers.size, 0);
  app.events.pageshow({ persisted: true }); assert.equal(app.sockets.length, 2);
});

test('cancellation dialog withdraws without write; confirmed cancellation keeps draft read-only', async () => {
  const app = harness(); app.connect(); await app.answer('Never upload on cancel');
  await app.nodes.get('cancel').fire('click'); await app.nodes.get('confirm-back').fire('click');
  assert.equal(app.requests.length, 0);
  await app.nodes.get('cancel').fire('click'); await app.nodes.get('confirm-submit').fire('click');
  assert.equal(app.requests.length, 1); assert.equal(app.requests[0].options.method, 'POST');
  assert.equal(app.nodes.get('terminal').hidden, false); assert.match(app.nodes.get('recovery-copy').textContent, /Never upload/);
});
