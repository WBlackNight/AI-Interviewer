/* No real capture. Verify that public HTTP fails clearly and HTTPS only asks on start. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source=fs.readFileSync(new URL('../ui/shared/microphone.js',import.meta.url),'utf8');
function setup(secure) {
  let captures=0;
  const stream={getTracks:()=>[]};
  const sandbox=vm.createContext({isSecureContext:secure,navigator:{mediaDevices:{
    getUserMedia:async()=>{captures++;return stream;},enumerateDevices:async()=>[]}},
    AudioContext:class {},setTimeout,clearTimeout});
  vm.runInContext(source,sandbox);
  const select={value:'',replaceChildren(){},append(){}},status={textContent:''};
  return {picker:sandbox.microphonePicker(select,status),status,captures:()=>captures};
}
const insecure=setup(false);
assert.equal(insecure.picker.supported(),false);
await insecure.picker.refresh();
assert.match(insecure.status.textContent,/HTTPS/);
await assert.rejects(insecure.picker.acquire(),/HTTPS/);
assert.equal(insecure.captures(),0);
const secure=setup(true);
assert.equal(secure.picker.supported(),true);
await secure.picker.refresh();
assert.equal(secure.captures(),0,'Listing devices must not ask for capture');
await secure.picker.acquire();
assert.equal(secure.captures(),1);
console.log('Microphone HTTPS and explicit capture checks passed');
