/* 原生语音状态回归：模拟音频分片间隙、播报结束及断线恢复，不联网。 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const html = readFileSync(new URL('../voice.html', import.meta.url), 'utf8');
const elements = new Map();
for (const id of html.matchAll(/id="voice-([^"]+)"/g)) {
  elements.set(id[1], { textContent: '', disabled: true, dataset: {},
    addEventListener(name, action) { this[name] = action; }, setAttribute() {} });
}
for (const entry of html.matchAll(/data-([a-z0-9-]+)="([^"]*)"/g)) {
  elements.get('copy').dataset[entry[1].replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())] = entry[2];
}
const nodes = [], sent = [];
let socket;
let currentToken = 'b'.repeat(64);
class Socket {
  static OPEN = 1;
  readyState = 1;
  bufferedAmount = 0;
  constructor() { socket = this; }
  send(value) { sent.push(JSON.parse(value)); }
  close() { this.readyState = 3; this.onclose?.(); }
  emit(value) { this.onmessage({ data: JSON.stringify(value) }); }
}
class Audio {
  state = 'running';
  currentTime = 0;
  resume() {}
  createBuffer(_, length) { return { duration: length / 24000, getChannelData: () => new Float32Array(length) }; }
  createBufferSource() {
    const node = { connect() {}, start() {}, stop() {} };
    nodes.push(node); return node;
  }
}
const modeLink = { addEventListener(name, action) { this[name] = action; } };
const sandbox = vm.createContext({ document: { querySelectorAll: () => [modeLink], querySelector: selector => elements.get(selector.slice(7)), body: { dataset: {} } },
  location: { pathname: '/interview/' + 'a'.repeat(32), origin: 'http://localhost' },
  sessionStorage: { getItem: key => key === 'account:session' ? null : currentToken },
  fetch: async () => ({ ok: true, json: async () => ({ enabled: true }) }),
  WebSocket: Socket, AudioContext: Audio, URL, AbortSignal, addEventListener() {},
  setTimeout, clearTimeout, atob, btoa, Uint8Array, Float32Array, DataView, console });
vm.runInContext(readFileSync(new URL('../assets/voice.js', import.meta.url), 'utf8'), sandbox);
await new Promise(setImmediate);
socket.emit({ type: 'snapshot', current_question: { turn_id: 'c'.repeat(32), content: '测试题', theme: 'MySQL' }, version: 1 });
assert.equal(elements.get('read').disabled, false);
await elements.get('read').click();
assert.equal(elements.get('read').disabled, true, '合成中禁止重复朗读');
const chunk = seq => ({ type: 'tts_chunk', utterance_id: 'u1', seq, format: 'pcm_s16le', sample_rate: 24000, channels: 1, data: 'ABAQEA==' });
socket.emit(chunk(0));
nodes[0].onended();
assert.equal(elements.get('read').disabled, true, '分片间隙仍等待本次播报');
socket.emit(chunk(1));
assert.equal(nodes.length, 2, '后续分片不能被当成已取消音频丢弃');
socket.emit({ type: 'tts_end' });
nodes[1].onended();
assert.equal(elements.get('read').disabled, false);
assert.equal(elements.get('interrupt').disabled, true, '播放结束必须复位停止按钮');
socket.emit({ type: 'voice_processing', turn_id:'c'.repeat(32) });
assert.equal(elements.get('start').disabled,true,'服务端判停后立即禁止再次录音');
assert.equal(elements.get('sync').disabled,true,'等待识别与保存期间不能重建连接');
socket.emit({ type: 'asr_final', text: '测试转写' });
let blockedNavigation = false;
modeLink.click({preventDefault(){blockedNavigation=true;}});
assert.equal(blockedNavigation, true, '保存期间不能切换对话模式');
assert.equal(elements.get('sync').disabled, true);
socket.close();
assert.equal(elements.get('sync').disabled, false, '等待保存时断线也可以重新同步');
assert.equal(elements.get('start').disabled, true);
assert.equal(sent.filter(event => event.type === 'read_question').length, 1);
await elements.get('sync').click();await new Promise(setImmediate);
socket.emit({ type: 'snapshot', current_question: { turn_id: 'd'.repeat(32), content: '下一题', theme: 'MySQL' }, version: 1 });
let resolveFile;
const reading=new Promise(resolve=>resolveFile=resolve);
elements.get('file').files=[{size:44,arrayBuffer:()=>reading}];
elements.get('file').change();await new Promise(setImmediate);
assert.equal(elements.get('file').disabled,true,'Reading a file must lock a second upload');
assert.equal(elements.get('stop').disabled,false,'File preparation must be cancellable');
elements.get('stop').click();resolveFile(new ArrayBuffer(44));await new Promise(setImmediate);
assert.equal(socket.readyState,1,'Cancelling a file read must preserve the formal practice connection');
assert.equal(elements.get('file').disabled,false);
assert.equal(sent.some(event=>event.type==='audio'),false,'A cancelled read must not send stale audio');
currentToken='e'.repeat(64);
assert.doesNotThrow(()=>socket.onopen(),'A changed identity while opening must not escape the event handler');
assert.equal(socket.readyState,3,'The changed-identity connection must close');
assert.equal(elements.get('error').textContent,elements.get('copy').dataset.identity);
console.log('Passed: synthesis lock, chunk gaps, completion reset, disconnect recovery. No network calls.');
