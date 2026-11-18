import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';

const geometry = vm.runInNewContext(readFileSync(new URL('../ui/shared/petposition.js',import.meta.url),'utf8')+'\n({petPosition,petPanel})');
for(const [width,height] of [[1280,720],[390,844],[320,360]]){
  for(const saved of [null,{x:-9,y:20},{x:NaN,y:1},{x:.5,y:.5}]){
    const p=geometry.petPosition(saved,width,height,76),r=geometry.petPanel(p,width,height);
    assert.ok(p.x>=12&&p.x+76<=width); assert.ok(p.y>=p.minY&&p.y+92<=height);
    assert.ok(r.left>=12&&r.top>=12&&r.left+r.width<=width&&r.top+r.height<=height);
  }
}
class Element{
  constructor(tag){this.tagName=tag;this.children=[];this.style={};this.attrs={};this.events={};this.hidden=false;const classes=new Set();this.classList={add:v=>classes.add(v),remove:v=>classes.delete(v),toggle:(v,on)=>on?classes.add(v):classes.delete(v)};}
  append(...items){this.children.push(...items);} replaceChildren(...items){this.children=items;}
  setAttribute(k,v){this.attrs[k]=v;} addEventListener(k,fn){(this.events[k]||=[]).push(fn);} setPointerCapture(){} focus(){this.focused=true;} remove(){}
  fire(type,extra={}){for(const fn of this.events[type]||[])fn({button:0,pointerId:1,clientX:0,clientY:0,preventDefault(){},...extra});}
}
const body=new Element('body'),head=new Element('head'),values=new Map(),motionWindow={};
for(const saved of [{x:0,y:.5},{x:1,y:.5}]){
  const p=geometry.petPosition(saved,1280,720),r=geometry.petPanel(p,1280,720);
  assert.ok(r.left>=p.x+88 || r.left+r.width<=p.x-12,'desktop chat must not cover its companion');
}
function byId(id,node=body){if(node.id===id)return node;for(const child of node.children){const found=byId(id,child);if(found)return found;}return null;}
vm.runInNewContext(readFileSync(new URL('../assets/qing-pet.js',import.meta.url),'utf8'),{
  document:{body,head,documentElement:{clientWidth:1280},createElement:t=>new Element(t),createElementNS:(_,t)=>new Element(t),getElementById:byId},
  window:motionWindow,innerWidth:1280,innerHeight:720,location:{pathname:'/catalog'},localStorage:{getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,v)},addEventListener(){},URL,Promise,Math,JSON
});
const host=byId('qing-pet'),button=host.children[0],panel=byId('qing-widget-panel');
assert.equal(head.children.length,0,'closed launcher must not load React or request chat');
button.fire('pointerdown',{clientX:1100,clientY:600});button.fire('pointermove',{clientX:100,clientY:300});button.fire('pointerup');button.fire('click');
assert.equal(panel.hidden,true,'drag must not accidentally open chat');assert.equal(head.children.length,0);
assert.ok(values.has('qing:pet-position:v1')); assert.equal(Object.keys(JSON.parse(values.get('qing:pet-position:v1'))).sort().join(','),'x,y');
button.fire('pointerdown');button.fire('pointerup');button.fire('click');
assert.equal(panel.hidden,false);assert.equal(head.children.length,1);assert.match(head.children[0].src,/^\/assets\/qing-widget\.js\?v=[a-f0-9]{12}$/);
button.fire('click');assert.equal(panel.hidden,true);
button.fire('click');assert.equal(head.children.length,1,'reopening reuses the mounted chat');
button.fire('keydown',{key:'Escape'});assert.equal(panel.hidden,true);
const left=host.style.left;button.fire('keydown',{key:'ArrowRight'});assert.notEqual(host.style.left,left);
const animations=[];
motionWindow.matchMedia=()=>({matches:false});
panel.animate=()=>{
  let finish,reject;const finished=new Promise((yes,no)=>{finish=yes;reject=no;});
  const animation={finished,finish,cancel(){reject(new Error('cancelled'));}};animations.push(animation);return animation;
};
button.fire('click');button.fire('click');
assert.equal(panel.hidden,false,'exit remains visible while animating');assert.equal(panel.inert,true,'closing content cannot receive input');
button.fire('click');await Promise.resolve();
assert.equal(panel.hidden,false,'quick reopen cancels stale exit');assert.equal(panel.inert,false);
button.fire('click');animations.at(-1).finish();await Promise.resolve();
assert.equal(panel.hidden,true,'completed exit hides the panel');
motionWindow.matchMedia=()=>({matches:true});
const count=animations.length;button.fire('click');button.fire('click');
assert.equal(panel.hidden,true);assert.equal(animations.length,count,'reduced motion closes immediately');
console.log('Passed: responsive bounds, drag/click separation, position-only storage, lazy loading, reuse, keyboard controls and interruptible/reduced exit motion.');
