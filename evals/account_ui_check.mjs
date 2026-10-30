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
console.log('Passed: safe login return routes, outside origins/unknown paths/auth endpoints rejected.');
