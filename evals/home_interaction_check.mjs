/* Exercise source functions with a controlled animation clock and tab events. */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../ui/pages/home.js',import.meta.url),'utf8');
const extract=name=>{
  const start=source.indexOf('  function '+name+'('),end=source.indexOf('\n  function ',start+5);
  assert.ok(start>0&&end>start);return source.slice(start,end);
};
class Node {
  constructor(){this.dataset={};this.events={};this.attributes={};this.hidden=false;this.textContent='';}
  addEventListener(key,fn){this.events[key]=fn;}
  setAttribute(key,value){this.attributes[key]=value;}
  getAttribute(key){return this.attributes[key];}
  focus(){this.focused=true;}
}
const nodes=[6,120,3,2].map(target=>{const n=new Node();n.dataset.count=String(target);return n;});
let callback,clock=0,id=0;const frames=new Map(),motion={matches:false,addEventListener(key,fn){this.change=fn;}};
vm.runInNewContext(extract('homepageCounts')+'\nhomepageCounts();',{
  selectAll:()=>nodes,reducedMotion:motion,window:{IntersectionObserver:true},
  IntersectionObserver:class {constructor(fn){callback=fn;}observe(){}unobserve(){}disconnect(){}},
  performance:{now:()=>clock},requestAnimationFrame:fn=>{frames.set(++id,fn);return id;},cancelAnimationFrame:id=>frames.delete(id),addEventListener(){}
});
assert.ok(nodes.every(n=>n.textContent==='0'));
callback(nodes.map(target=>({target,isIntersecting:true})));
function advance(time){clock=time;const pending=[...frames.values()];frames.clear();pending.forEach(fn=>fn(time));}
advance(400);assert.ok(+nodes[1].textContent>0&&+nodes[1].textContent<120);
advance(1200);assert.deepEqual(nodes.map(n=>+n.textContent),[6,120,3,2]);
motion.matches=true;motion.change();assert.equal(frames.size,0);
nodes.forEach(n=>{n.textContent='0';});
vm.runInNewContext(extract('homepageCounts')+'\nhomepageCounts();',{
  selectAll:()=>nodes,reducedMotion:motion,cancelAnimationFrame(){},addEventListener(){}
});
assert.deepEqual(nodes.map(n=>+n.textContent),[6,120,3,2],'Reduced motion renders final values immediately');
const tabs=[0,1,2].map(i=>{const n=new Node();n.setAttribute('aria-controls','hero-panel-'+i);return n;});
const all=new Map();const select=q=>{if(!all.has(q))all.set(q,new Node());return all.get(q);};
vm.runInNewContext(extract('heroDemo')+'\nheroDemo();',{selectAll:()=>tabs,select});
tabs[1].events.click();assert.equal(tabs[1].getAttribute('aria-selected'),'true');assert.equal(select('#hero-panel-0').hidden,true);assert.equal(select('#hero-panel-1').hidden,false);
tabs[1].events.keydown({key:'ArrowDown',preventDefault(){}});assert.equal(tabs[2].focused,true);assert.equal(select('#hero-panel-2').hidden,false);
tabs[2].events.keydown({key:'Home',preventDefault(){}});assert.equal(tabs[0].focused,true);assert.equal(select('#hero-panel-0').hidden,false);
console.log('Passed: zero start, intermediate/final counts, reduced-motion cleanup, hero clicks and keyboard navigation.');
