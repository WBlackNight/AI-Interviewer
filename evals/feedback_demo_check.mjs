import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

class Node {
  constructor() { this.events={}; this.attributes={}; this.children=[]; this.dataset={}; this.hidden=true; }
  addEventListener(name, fn) { this.events[name]=fn; }
  append(...nodes) { this.children.push(...nodes); }
  setAttribute(name,value) { this.attributes[name]=value; }
  getAttribute(name) { return this.attributes[name]; }
  closest() { return root; }
  contains(target) { return target===this; }
  focus() { this.focused=true; }
}
const events={}, timers=new Map(), storage=new Map(), body=new Node(); let sequence=0;
const setTimer=(fn,ms)=>{timers.set(++sequence,{fn,ms});return sequence;};
const environment={document:{body,createElement:()=>new Node()},
  addEventListener:(name,fn)=>{events[name]=fn;},setTimeout:setTimer,clearTimeout:id=>timers.delete(id),
  sessionStorage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)},Date};
vm.runInNewContext(readFileSync(new URL('../ui/shared/feedback.js',import.meta.url),'utf8'),environment);
const box=body.children[0], [message,close]=box.children;
events['app:notice']({detail:{message:'保存成功',type:'success'}});
assert.equal(message.textContent,'保存成功');assert.equal(box.attributes.role,'status');
assert.equal([...timers.values()][0].ms,2000);
events['app:notice']({detail:{message:'保存失败',type:'error'}});
assert.equal(timers.size,1);assert.equal(box.attributes.role,'alert');assert.equal(message.textContent,'保存失败');
[...timers.values()][0].fn();assert.equal(box.hidden,true);assert.equal(message.textContent,'');
storage.set('ui:notice',JSON.stringify({message:'登录成功',expires:Date.now()+1000}));events.pageshow();
assert.equal(message.textContent,'登录成功');assert.equal(storage.has('ui:notice'),false);
events['account:changed']();assert.equal(box.hidden,true);
storage.set('ui:notice',JSON.stringify({message:'过期提示',expires:0}));events.pageshow();assert.equal(box.hidden,true);
events['app:notice']({detail:{message:'完成'}});close.events.click();assert.equal(timers.size,0);

const source=readFileSync(new URL('../ui/modules/home/demonstration.js',import.meta.url),'utf8');
const a=source.indexOf('  function demoTabs('), b=source.indexOf('\n  function questionDemo',a);
const root=new Node(), tabs=[0,1,2].map(index=>{const node=new Node();node.setAttribute('aria-controls','panel-'+index);return node;});
const panels=[new Node(),new Node(),new Node()], motion={matches:false,addEventListener(name,fn){this.changed=fn;}};
let observe, changed=-1;
const document={hidden:false,addEventListener(name,fn){this[name]=fn;}};
const compactHome={matches:false,addEventListener(name,fn){this.changed=fn;}};
vm.runInNewContext(source.slice(a,b)+'\ndemoTabs(tabs,{autoPlay:true,onChange:index=>changed(index)});',{
  tabs,select:selector=>panels[Number(selector.slice(-1))],changed:index=>{changed=index;},
  IntersectionObserver:class{constructor(fn){observe=fn;}observe(){}}, document,reducedMotion:motion,compactHome,
  setTimeout:setTimer,clearTimeout:id=>timers.delete(id),addEventListener:(name,fn)=>{events[name]=fn;}
});
assert.equal(timers.size,0,'offscreen demonstrations do not schedule work');
observe([{isIntersecting:true}]);assert.equal([...timers.values()][0].ms,4800);
compactHome.matches=true;compactHome.changed();assert.equal(timers.size,0);
compactHome.matches=false;compactHome.changed();assert.equal(timers.size,1);
const advance=()=>{const active=[...timers.values()];timers.clear();active.forEach(timer=>timer.fn());};
advance();assert.equal(changed,1);assert.equal(panels[0].hidden,true);assert.equal(panels[1].hidden,false);
root.events.mouseenter();assert.equal(timers.size,0);root.events.mouseleave();assert.equal(timers.size,1);
document.hidden=true;document.visibilitychange();assert.equal(timers.size,0);
document.hidden=false;document.visibilitychange();motion.matches=true;motion.changed();assert.equal(timers.size,0);
tabs[2].events.click();assert.equal(changed,2,'manual selection remains available with reduced motion');
motion.matches=false;motion.changed();root.events.focusin();assert.equal(timers.size,0);
root.events.focusout({relatedTarget:null});assert.equal(timers.size,1);
events.pagehide();assert.equal(timers.size,0);events.pageshow();assert.equal(timers.size,1);
observe([{isIntersecting:false}]);assert.equal(timers.size,0);
console.log('Passed: 2s success/error notices, replacement/dismissal, route restoration, stale notices, demo visibility/hover/focus/reduced-motion/BFCache cleanup.');
