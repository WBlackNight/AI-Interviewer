import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../ui/pages/home.js',import.meta.url),'utf8').replace(/\/\* @module ([a-z]+\/[a-z]+) \*\//g, (_,name)=>readFileSync(new URL('../ui/modules/'+name+'.js',import.meta.url),'utf8'));
const start=source.indexOf('function accountCarousel()');
const end=source.indexOf('// 初始化：',start);
assert.ok(start>0&&end>start);
class Node {
  textContent='';disabled=false;children=[];events={};attributes={};
  addEventListener(n,fn){this.events[n]=fn;}
  replaceChildren(...nodes){this.children=nodes;}
  append(...nodes){this.children.push(...nodes);}
  setAttribute(name,value){this.attributes[name]=value;}
  removeAttribute(name){delete this.attributes[name];}
  contains(){return false;}
}
const nodes=new Map(),select=q=>{if(!nodes.has(q))nodes.set(q,new Node());return nodes.get(q);};
let account={access_token:'a'.repeat(64)},timer,resolve,visibility;
const motion={matches:false,addEventListener(n,fn){this.change=fn;}};
const compactHome={matches:false,addEventListener(n,fn){this.change=fn;}};
vm.runInNewContext(source.slice(start,end)+'\naccountCarousel();',{
  select,reducedMotion:motion,compactHome,readSession:()=>account,
  guardedFetch:()=>new Promise(r=>{resolve=r;}),
  document:{createElement:()=>new Node(),hidden:false,activeElement:null},
  IntersectionObserver:class { constructor(callback){visibility=callback;} observe(){} },
  performance:{now:()=>0},requestAnimationFrame:fn=>fn(1000),
  setInterval:(fn, delay)=>{assert.equal(delay, 4200);timer=fn;return 1;},clearInterval(){},addEventListener(){},AbortSignal
});
assert.equal(select('#carousel-finished').textContent,'0');
resolve({ok:true,json:async()=>({active:[{interview_id:'b'.repeat(32),position:'English',answer_count:1,status:'running'}],recent:[{interview_id:'c'.repeat(32),position:'Marketing',answer_count:2,status:'finished'}],interviews:{finished:4},tasks:{todo:2},notes_with_content:3})});
await new Promise(setImmediate);
assert.equal(select('#carousel-finished').textContent,'4');
assert.equal(select('#carousel-page').textContent,'1 / 2');
timer();assert.equal(select('#carousel-page').textContent,'1 / 2','Off-screen slides should not advance');
visibility([{isIntersecting:true}]);timer();assert.equal(select('#carousel-page').textContent,'2 / 2');
select('#carousel-prev').events.click();assert.equal(select('#carousel-slide').children[1].attributes['data-direction'],'previous');
select('#carousel-next').events.click();assert.equal(select('#carousel-page').textContent,'2 / 2');
assert.equal(select('#carousel-slide').children[1].attributes['data-direction'],'next');
motion.matches=true;timer();assert.equal(select('#carousel-page').textContent,'2 / 2');
account=null;timer();assert.equal(select('#carousel-page').textContent,'1 / 3');
assert.equal(select('#carousel-slide').children[1].children[1].textContent,'找到值得练习的下一题');
assert.equal(select('#carousel-finished').textContent,'0');
select('#carousel-next').events.click();assert.equal(select('#carousel-page').textContent,'2 / 3');
assert.equal(select('#carousel-slide').children[1].children[3].href,'/#start');
account={access_token:'d'.repeat(64)};timer();
account=null;timer();
resolve({ok:true,json:async()=>({active:[],recent:[],interviews:{finished:99},tasks:{todo:2},notes_with_content:3})});
await new Promise(setImmediate);
assert.equal(select('#carousel-finished').textContent,'0');
assert.equal(select('#carousel-page').textContent,'1 / 3');
console.log('Passed: fixed slides, account records, count completion, manual switch, reduced motion, logout reset, stale response isolation.');
