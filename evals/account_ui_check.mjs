/* Login return destinations are explicit, same-origin application routes. */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../ui/pages/account.js',import.meta.url),'utf8');
const start=source.indexOf('function safeReturn('), end=source.indexOf('const returnPath',start);
const safeReturn=vm.runInNewContext(source.slice(start,end)+'\nsafeReturn',{
  URL,location:{origin:'http://localhost:3000'}
});
for(const value of ['https://outside.example/','//outside.example/','/\\outside.example/','javascript:alert(1)','/account','/api/auth/logout','/%2Foutside.example','/missing']) assert.equal(safeReturn(value),'',value);
for(const value of ['/','/#start','/catalog?position=marketing','/history','/interview/'+'a'.repeat(32)+'?mode=realtime']) assert.equal(safeReturn(value),value);
assert.equal(safeReturn('/catalog/?position=marketing#topics'), '/catalog?position=marketing#topics');
console.log('Passed: safe login return routes, outside origins/unknown paths/auth endpoints rejected.');

const controls = new Map();
const find = id => {
  if (!controls.has(id)) controls.set(id, {
    addEventListener(event, callback) { this[event] = callback; },
    showModal() { this.open = true; },
    close() { this.open = false; }
  });
  return controls.get(id);
};
let requests = 0;
const logoutStart = source.indexOf("  const logoutDialog =");
const logoutEnd = source.indexOf("  const dialog =", logoutStart);
vm.runInNewContext(source.slice(logoutStart, logoutEnd), {
  find, busy: false, account: {}, selectedFile: null,
  notify() {}, setBusy() {}, render() {}, clearSession() {}, loadAvatar() {}, dispatchEvent() {}, Event,
  crop: { clear() {} },
  async request(path, options) {
    assert.equal(path, '/auth/logout');
    assert.equal(options.method, 'POST');
    requests++;
  }
});
find('#account-logout').click();
assert.equal(find('#account-logout-dialog').open, true);
find('#account-logout-cancel').click();
assert.equal(find('#account-logout-dialog').open, false);
assert.equal(requests, 0);
find('#account-logout').click();
await find('#account-logout-form').submit({ preventDefault() {} });
assert.equal(requests, 1);
assert.equal(find('#account-logout-dialog').open, false);
