import test from 'node:test';
import assert from 'node:assert/strict';
import {readRoute,routeSearch,listPath,trendPoints,exportPath} from '../admin/state';
import {adminRequest} from '../admin/api';

test('admin routes normalize unsafe filters and preserve supported search and pagination',()=>{
  const route=readRoute('?view=questions&q=教学&position=education&difficulty=mid&kind=knowledge&page=2&limit=20&days=30');
  assert.deepEqual(readRoute('?'+routeSearch(route)),route);
  assert.equal(new URL('http://localhost'+listPath(route)).searchParams.get('offset'),'20');
  const bad=readRoute('?view=<script>&position=../../&status=anything&page=-1&limit=999&days=999');
  assert.equal(bad.view,'overview');assert.equal(bad.position,'');assert.equal(bad.page,1);assert.equal(bad.limit,10);assert.equal(bad.days,14);
});
test('admin review, audit, dates and export preserve supported filters only',()=>{
  const route=readRoute('?view=questions&review=needs_revision&sort=difficulty&page=2&limit=20&position=education');
  assert.deepEqual(readRoute('?'+routeSearch(route)),route);
  const url=new URL(exportPath(route),'http://localhost');
  assert.equal(url.searchParams.get('review'),'needs_revision');assert.equal(url.searchParams.get('sort'),'difficulty');
  assert.equal(url.searchParams.has('offset'),false);assert.equal(url.searchParams.has('limit'),false);
  const audit=readRoute('?view=audit&action=data_export&outcome=succeeded&start=2026-02-30&end=2026-11-17&sort=name');
  assert.equal(audit.start,'');assert.equal(audit.end,'2026-11-17');assert.equal(audit.sort,'default');
  assert.ok(listPath(audit).includes('action=data_export'));
});
test('admin lists send only filters supported by the selected resource',()=>{
  const route=readRoute('?view=accounts&position=education&status=running&bound=bound&q=abc');
  const url=new URL('http://localhost'+listPath(route));
  assert.equal(url.pathname,'/api/admin/accounts');assert.equal(url.searchParams.has('position'),false);assert.equal(url.searchParams.get('bound'),'bound');
});
test('admin chart geometry handles empty or zero data without NaN or overflow',()=>{
  assert.deepEqual(trendPoints([]),[]);
  for(const [x,y] of trendPoints([0,0,0])){assert.ok(Number.isFinite(x)&&Number.isFinite(y));assert.equal(y,184);}
  assert.equal(trendPoints([1,2,4]).at(-1)?.[1],20);
  assert.ok(trendPoints([1],560,164,6)[0][1] > trendPoints([6],560,164,6)[0][1], 'both series must share the same vertical scale');
});
test('admin transport discards responses when the account changes during body reading',async()=>{
  const originalFetch=globalThis.fetch;const originalStorage=globalThis.sessionStorage;
  let token='a'.repeat(64);
  Object.defineProperty(globalThis,'sessionStorage',{configurable:true,value:{getItem:()=>JSON.stringify({access_token:token,account:{id:'b'.repeat(32),username:'test'},expires_at:'2099-01-01'})}});
  globalThis.fetch=async()=>({ok:true,json:async()=>{token='c'.repeat(64);return {private:true};}} as Response);
  try{await assert.rejects(adminRequest('/api/admin/overview','a'.repeat(64),new AbortController().signal),/账户已变化/);}
  finally{globalThis.fetch=originalFetch;Object.defineProperty(globalThis,'sessionStorage',{configurable:true,value:originalStorage});}
});
