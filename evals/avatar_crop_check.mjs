import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const nodes=new Map(),draws=[];
function node(){return {value:'1',hidden:true,width:320,height:320,textContent:'',
  addEventListener(name,fn){this[name]=fn;},setPointerCapture(){},getBoundingClientRect(){return{width:320,height:320};},
  getContext(){return{drawImage(...args){draws.push(args);},clearRect(){},fillRect(){}};},toBlob(fn){fn({type:'image/png'});}};}
const find=id=>{if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);};
let closed=0;
const image={width:800,height:400,close(){closed++;}};
const context=vm.createContext({document:{createElement:node},createImageBitmap:async()=>image});
vm.runInContext(readFileSync(new URL('../ui/shared/avatarcrop.js',import.meta.url),'utf8'),context);
const editor=context.avatarCropEditor(find,()=>true);
await editor.load({});
assert.deepEqual(draws.at(-1).slice(1,5),[200,0,400,400]);
find('#avatar-zoom').value='2';find('#avatar-zoom').input();
find('#avatar-x').value='100';find('#avatar-x').input();
find('#avatar-y').value='100';find('#avatar-y').input();
assert.deepEqual(draws.at(-1).slice(1,5),[600,200,200,200]);
find('#avatar-size').value='512';assert.equal((await editor.blob()).size,512);
assert.deepEqual(draws.at(-1).slice(5),[0,0,512,512]);
find('#avatar-reset').click();assert.equal(find('#avatar-zoom').value,1);
editor.clear();assert.equal(find('#avatar-crop').hidden,true);assert.equal(closed,1);
await assert.rejects(editor.blob(),/选择/);
console.log('Passed: crop coordinates, zoom/pan bounds, output size, reset and bitmap cleanup.');
