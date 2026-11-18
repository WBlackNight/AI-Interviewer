import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const intentSource = readFileSync(new URL('../ui/shared/practiceintent.js', import.meta.url), 'utf8');
const intent = vm.runInNewContext(intentSource + '\n({readPracticeIntent,practiceIntentQuery})', { URLSearchParams });
const roles = { java: { themes: ['MySQL', 'Redis'] }, english: { themes: ['Introduction'] } };
const selected = intent.readPracticeIntent('?position=java&theme=Redis&theme=Redis&theme=INVALID&duration=5&difficulty=hard&resume=PRIVATE', roles);
assert.deepEqual(JSON.parse(JSON.stringify(selected)), { position: 'java', themes: ['Redis'], duration: '5', difficulty: 'hard', mode: 'topic' });
const address = intent.practiceIntentQuery(selected).toString();
assert.ok(!address.includes('PRIVATE') && !address.includes('INVALID'));
assert.equal(intent.readPracticeIntent('?position=UNKNOWN&duration=999&difficulty=oops', roles).position, 'java');
assert.equal(intent.readPracticeIntent('?position=english&theme=MySQL', roles).themes.length, 0);

const httpSource = readFileSync(new URL('../ui/shared/http.js', import.meta.url), 'utf8');
let identity = { access_token: 'synthetic-a' }, calls = [], pending;
const request = vm.runInNewContext(httpSource + '\nrequestJSON', {
  readSession: () => identity, AbortController, setTimeout, clearTimeout, TypeError,
  fetch: async (url, options) => { calls.push({ url, options }); return pending(options); }
});
pending = async () => ({ ok: true, json: async () => ({ ok: 1 }) });
assert.equal((await request('/api/account/dashboard', { auth: true })).ok, 1);
assert.equal(calls[0].options.headers.Authorization, 'Bearer synthetic-a');
let release;
pending = async () => ({ ok: true, json: () => new Promise(resolve => { release = resolve; }) });
const old = request('/api/account/dashboard', { auth: true });
await new Promise(setImmediate); identity = { access_token: 'synthetic-b' }; release({ private: 'OLD' });
await assert.rejects(old, error => error.status === 401);
pending = async () => ({ ok: false, status: 503, json: async () => ({ detail: '请稍后重试' }) });
const before = calls.length;
await assert.rejects(request('/api/action', { method: 'POST' }), /请稍后重试/);
assert.equal(calls.length, before + 1, 'writes are never retried automatically');
identity = null;
await assert.rejects(request('/api/private', { auth: true }), error => error.status === 401);
assert.equal(calls.length, before + 1, 'missing identity fails before sending');
pending = options => new Promise((resolve, reject) => options.signal.addEventListener('abort', () =>
  reject(Object.assign(new Error('cancelled'), { name: 'AbortError' }))));
const cancelled = new AbortController();
const active = request('/api/preview', { signal: cancelled.signal });
cancelled.abort();
await assert.rejects(active, error => error.name === 'AbortError');
await assert.rejects(request('/api/preview', { timeout: 1 }), error => error.code === 'TIMEOUT');
console.log('Passed: whitelisted practice URLs, private-data exclusion, authenticated transport, late account isolation, no write retries, cancellation and timeout cleanup.');
