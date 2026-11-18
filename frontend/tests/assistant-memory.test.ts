import {test} from 'node:test';
import assert from 'node:assert/strict';
import {rememberConversation, rememberedConversation} from '../assistant/memory';

test('cross-page chat memory is account scoped and stores only a valid conversation id', t => {
  const original = Object.getOwnPropertyDescriptor(globalThis, 'sessionStorage');
  const values = new Map<string, string>();
  Object.defineProperty(globalThis, 'sessionStorage', {configurable:true,value:{getItem:(k:string)=>values.get(k)||null,setItem:(k:string,v:string)=>values.set(k,v),removeItem:(k:string)=>values.delete(k)}});
  t.after(()=>original?Object.defineProperty(globalThis,'sessionStorage',original):Reflect.deleteProperty(globalThis,'sessionStorage'));
  const a='a'.repeat(32),b='b'.repeat(32),id='1'.repeat(32);
  rememberConversation(a,id); assert.equal(rememberedConversation(a),id); assert.equal(rememberedConversation(b),null);
  rememberConversation(b,'not-a-valid-id'); assert.equal(values.size,1);
  values.set('qing:last-conversation:'+b,'https://outside.example'); assert.equal(rememberedConversation(b),null);
  rememberConversation(a,null); assert.equal(rememberedConversation(a),null);
});
