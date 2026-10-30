/* Shared-source regressions: real functions, deferred bodies, no network/devices. */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
const source = ['session', 'element', 'token', 'fetch'].map(name =>
  readFileSync(new URL('../ui/shared/' + name + '.js', import.meta.url), 'utf8')).join('\n');
let stored = null, requests = 0, fetchResult;
const anon = 'c'.repeat(64);
const valid = (letter = 'a') => ({ access_token: letter.repeat(64), account: { id: 'd'.repeat(32), username: 'demo' }, expires_at: '2099-01-01T00:00:00Z' });
const core = vm.runInNewContext(source + '\n({readSession,createNode,interviewToken,guardedFetch})', {
  sessionStorage: { getItem: key => key === 'account:session' ? stored : anon },
  document: { createElement: tag => ({ tag, textContent: '', className: '' }) },
  fetch: async (...args) => { requests++; return fetchResult(...args); }
});
stored = JSON.stringify(valid());
assert.equal(core.readSession().access_token, 'a'.repeat(64));
assert.equal(core.interviewToken('test'), 'a'.repeat(64));
for (const invalid of [null, '{', JSON.stringify({...valid(), expires_at: '2000-01-01'}),
  JSON.stringify({...valid(), account: { id: 'invalid', username: 'demo' }}),
  JSON.stringify({...valid(), access_token: 'invalid'}), JSON.stringify({...valid(), account: {id:'d'.repeat(32)}})]) {
  stored = invalid; assert.equal(core.readSession(), null);
  assert.equal(core.interviewToken('test'), anon);
}
stored = JSON.stringify(valid());
const text = '<img src=x onerror=alert(1)>';
assert.equal(core.createNode('p', text, 'message').textContent, text);
let resolveBody;
fetchResult = async () => ({ ok: true, status: 200, json: () => new Promise(r => { resolveBody = r; }) });
const response = await core.guardedFetch('/private', { method: 'GET' });
const body = response.json();
stored = JSON.stringify(valid('b')); resolveBody({ private: 'old account' });
await assert.rejects(body, e => e.status === 401);
assert.equal(requests, 1);
// A write whose result becomes uncertain is sent exactly once.
stored = JSON.stringify(valid()); requests = 0;
fetchResult = async (_, options) => {
  assert.equal(options.method, 'POST');
  stored = null;
  return { ok: true, status: 200, json: async () => ({ id: 'created' }) };
};
await assert.rejects((await core.guardedFetch('/write', {method:'POST'})).json(), e => e.status === 401);
assert.equal(requests, 1);
// Existing HTTP status and caller cancellation signal remain available.
const signal = new AbortController().signal;
fetchResult = async (_, options) => {
  assert.equal(options.signal, signal);
  return { ok: false, status: 409, json: async () => ({detail:'version conflict'}) };
};
const conflict = await core.guardedFetch('/conflict', {signal});
assert.equal(conflict.status, 409);
assert.equal((await conflict.json()).detail, 'version conflict');
console.log('Passed: session schema/expiry, anonymous credentials, safe DOM, deferred identity change, no write retry, HTTP status and cancellation.');
