import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../assets/account-menu.js',import.meta.url),'utf8');
const node=()=>({textContent:'',hidden:false,attributes:{},setAttribute(k,v){this.attributes[k]=v;},removeAttribute(k){delete this[k];}});
const label=node(),image=node(),initial=node(),root={...node(),querySelector:q=>q==='img'?image:q==='[data-user-name]'?label:initial};
const session=letter=>({access_token:letter.repeat(64),account:{id:'c'.repeat(32),username:'user_'+letter},expires_at:'2099-01-01T00:00:00Z'});
let stored=JSON.stringify(session('a')),pending=[],revoked=[],events={},created=0;
vm.runInNewContext(source,{
  document:{querySelector:()=>root},sessionStorage:{getItem:()=>stored,removeItem:()=>{stored=null;}},
  fetch:(url,options)=>new Promise(resolve=>pending.push({url,options,resolve})),
  URL:{createObjectURL:()=>{created++;return 'blob:'+created;},revokeObjectURL:u=>revoked.push(u)},
  AbortSignal,Event,dispatchEvent:e=>events[e.type]?.(),addEventListener:(name,fn)=>{events[name]=fn;}
});
const tick=()=>new Promise(setImmediate);
const respond=(call,data)=>call.resolve({ok:true,json:async()=>data,blob:async()=>({type:'image/png'})});
const old=pending.shift();stored=JSON.stringify(session('b'));events['account:changed']();const current=pending.shift();
respond(old,{username:'PRIVATE_OLD',nickname:'PRIVATE_OLD',avatar_version:'x'});await tick();assert.equal(label.textContent,'登录 / 注册');assert.equal(pending.length,0);
respond(current,{username:'user_b',nickname:'新昵称',avatar_version:'x'});await tick();assert.equal(label.textContent,'新昵称');
const avatar=pending.shift();assert.equal(avatar.url,'/api/account/avatar');assert.equal(avatar.options.headers.Authorization,'Bearer '+'b'.repeat(64));
stored=null;events['account:changed']();respond(avatar,{});await tick();assert.equal(created,0);assert.equal(image.hidden,true);
stored=JSON.stringify(session('b'));events['account:changed']();respond(pending.shift(),{username:'user_b',nickname:'新昵称',avatar_version:'x'});await tick();respond(pending.shift(),{});await tick();assert.equal(image.src,'blob:1');
stored=null;events['account:changed']();assert.deepEqual(revoked,['blob:1']);assert.equal(label.textContent,'登录 / 注册');
console.log('Passed: nickname/avatar, authenticated image request, stale account/late avatar isolation, logout object-URL cleanup.');
