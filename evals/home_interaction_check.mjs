/* Exercise source functions with a controlled animation clock and tab events. */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../ui/pages/home.js',import.meta.url),'utf8').replace(/\/\* @module ([a-z]+\/[a-z]+) \*\//g, (_,name)=>readFileSync(new URL('../ui/modules/'+name+'.js',import.meta.url),'utf8'));
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
vm.runInNewContext(extract('demoTabs') + extract('heroDemo') + '\nheroDemo();',{selectAll:()=>tabs,select});
tabs[1].events.click();assert.equal(tabs[1].getAttribute('aria-selected'),'true');assert.equal(select('#hero-panel-0').hidden,true);assert.equal(select('#hero-panel-1').hidden,false);
assert.equal(select('#hero-panel-1').getAttribute('data-direction'),'next');
tabs[1].events.keydown({key:'ArrowDown',preventDefault(){}});assert.equal(tabs[2].focused,true);assert.equal(select('#hero-panel-2').hidden,false);
tabs[2].events.keydown({key:'Home',preventDefault(){}});assert.equal(tabs[0].focused,true);assert.equal(select('#hero-panel-0').hidden,false);
assert.equal(select('#hero-panel-0').getAttribute('data-direction'),'previous');
console.log('Passed: zero start, intermediate/final counts, reduced-motion cleanup, hero clicks and keyboard navigation.');

const fields = new Map();
const field = key => {
  if (!fields.has(key)) fields.set(key, new Node());
  return fields.get(key);
};
const form = field('#practice-form');
const modal = field('#preview-dialog');
modal.showModal = () => { modal.open = true; };
modal.close = () => { modal.open = false; };
form.querySelector = () => field('submit');
form.elements = { mode: { value: 'general' } };
field('#position').value = 'java_backend';
field('#difficulty').selectedOptions = [{ textContent: '标准' }];
field('#practice-duration').selectedOptions = [{ textContent: '自动安排' }];
field('#resume-pdf').files = [];
field('#resume-text').value = '合成项目经验';
field('#theme-options').replaceChildren = () => {};
let identity = null;
const intentSource=readFileSync(new URL('../ui/shared/practiceintent.js',import.meta.url),'utf8');
vm.runInNewContext(intentSource + extract('practiceForm') + '\npracticeForm();', {
  notify() {}, select: field, selectAll: () => [], catalog: { java_backend: { name: 'Java 后端', themes: [] } },
  readSession: () => identity, document: { body: { dataset: { api: '/api' } } },
  URLSearchParams, addEventListener(){}, location: { search: '?duration=10' }
});
assert.equal(field('#practice-duration').value, '10');
const submit = () => form.events.submit({ preventDefault() {} });
await submit();
assert.equal(modal.open, true);
assert.equal(field('#preview-confirm').hidden, false);
assert.equal(field('#preview-detail').textContent, '简历：已填写文本');
field('#preview-back').events.click();
assert.equal(modal.open, false);
assert.equal(field('#resume-text').value, '合成项目经验');
field('#resume-pdf').files = [{ name: 'empty.pdf', type: 'application/pdf', size: 0 }];
field('#resume-pdf').events.change();
await submit();
assert.equal(modal.open, false);
assert.equal(field('#resume-pdf').getAttribute('aria-invalid'), 'true');
assert.equal(field('#form-error').focused, true);
field('#resume-pdf').files = [];
await submit();
identity = { access_token: 'new-session' };
field('#preview-confirm').events.click();
assert.match(field('#form-error').textContent, /登录状态已变化/);

const deviceCode = readFileSync(new URL('../ui/modules/home/navigation.js', import.meta.url), 'utf8');
const deviceStart = deviceCode.indexOf('  function deviceHome(');
const deviceSource = deviceCode.slice(deviceStart).split('\n  }')[0] + '\n  }\ndeviceHome();';
function deviceState(navigator, matches, coarse) {
  const document = { documentElement: { dataset: {} } };
  const compactHome = { matches, addEventListener(_, fn) { this.change = fn; } };
  const touch = { matches: coarse, addEventListener(_, fn) { this.change = fn; } };
  const label = {};
  vm.runInNewContext(deviceSource, { navigator, document, compactHome, matchMedia: () => touch, select: () => label });
  return { dataset: document.documentElement.dataset, compactHome, label };
}
const phone = deviceState({ userAgent: 'Android Mobile' }, true, true);
assert.equal(phone.dataset.device, 'mobile');
assert.equal(phone.dataset.homeLayout, 'compact');
assert.match(phone.label.textContent, /手机/);
const desktop = deviceState({ userAgent: 'Windows' }, false, false);
assert.equal(desktop.dataset.device, 'desktop');
desktop.compactHome.matches = true;
desktop.compactHome.change();
assert.equal(desktop.dataset.homeLayout, 'compact', 'Narrow desktop uses the mobile layout independently of device type');
const tablet = deviceState({ platform: 'MacIntel', maxTouchPoints: 5, userAgent: 'Macintosh' }, true, true);
assert.equal(tablet.dataset.device, 'touch');

const resumeSource = readFileSync(new URL('../ui/modules/home/input.js', import.meta.url), 'utf8');
const inputDoc = { activeElement: field('#resume-text') };
field('#resume-text').blur = () => { inputDoc.activeElement = null; };
vm.runInNewContext(resumeSource + '\nresumeInput();', { select: field, document: inputDoc });
const inputEvents = field('#resume-text').events;
const doneKey = { key: 'Enter', ctrlKey: true, preventDefault() { this.prevented = true; } };
inputEvents.compositionstart();
inputEvents.keydown(doneKey);
assert.equal(doneKey.prevented, undefined, 'IME candidate confirmation keeps the editor focused');
inputEvents.compositionend();
inputEvents.keydown({ key: 'Enter', preventDefault() { assert.fail('Plain Enter must keep line breaks'); } });
inputEvents.keydown(doneKey);
assert.equal(doneKey.prevented, true);
assert.equal(inputDoc.activeElement, null);
assert.match(field('#resume-completion').textContent, /已填写/);
field('#resume-done').events.click();
assert.equal(field('#resume-text').value, '合成项目经验');

const dashboardSource = readFileSync(new URL('../ui/pages/dashboard.js', import.meta.url), 'utf8');
const nextStart = dashboardSource.indexOf('  function nextStep(');
const nextEnd = dashboardSource.indexOf('\n  //', nextStart);
const chooseNext = vm.runInNewContext(dashboardSource.slice(nextStart, nextEnd) + '\nnextStep', {
  reportPath: (row, prefix) => '/' + prefix + '/' + row.interview_id
});
const empty = { active: [], recent: [], tasks: { overdue: 0, today: 0 }, preparation: { items: [] } };
assert.equal(chooseNext(empty).path, '/?duration=5#start');
const due = { ...empty, tasks: { overdue: 1, today: 2 } };
assert.equal(chooseNext(due).path, '/revision?status=todo&due=overdue');
const running = { ...due, active: [{ interview_id: 'a'.repeat(32), answer_count: 2 }] };
assert.equal(chooseNext(running).path, '/interview/' + 'a'.repeat(32));
assert.equal(chooseNext({ ...empty, preparation: { items: [{ name: '准备英语面试' }] } }).path, '/plans');
assert.equal(chooseNext({ ...empty, recent: [{ interview_id: 'b'.repeat(32) }] }).path, '/report/' + 'b'.repeat(32));
