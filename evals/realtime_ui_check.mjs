/* Exercise the actual client with deferred audio/file work; no network or devices. */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
const script = readFileSync(new URL('../assets/realtime.js', import.meta.url), 'utf8');
const html = readFileSync(new URL('../realtime.html', import.meta.url), 'utf8');
const tick = () => new Promise(setImmediate);
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; };
function setup(enabled = true, resume = null, mediaError = null, permission = null) {
  const elements = new Map(), sockets = [], nodes = [], tracks = [], sent = [];
  let mediaRequests = 0;
  function element() { return { textContent: '', disabled: false, checked: true, children: [], dataset: {},
    append(...items) { this.children.push(...items); }, addEventListener(name, fn) { this[name] = fn; } }; }
  for (const match of html.matchAll(/id="rt-([^"]+)"/g)) elements.set(match[1], element());
  class Socket {
    static OPEN = 1; readyState = 1; bufferedAmount = 0;
    constructor() { sockets.push(this); }
    send(value) { sent.push(JSON.parse(value)); }
    close() { this.readyState = 3; this.onclose?.(); }
    emit(event) { this.onmessage?.({ data: JSON.stringify(event) }); }
  }
  const track = { enabled: true, stopped: false, stop() { this.stopped = true; }, addEventListener() {} };
  const media = { getTracks: () => [track], getAudioTracks: () => [track] }; tracks.push(track);
  const modeLink = element();
  class Audio {
    state = 'running'; currentTime = 0; sampleRate = 48000;
    audioWorklet = { addModule: async () => {} };
    async resume() { if (resume) await resume.promise; }
    close() { this.state = 'closed'; }
    createMediaStreamSource() { return { connect() {}, disconnect() {} }; }
    createGain() { return { gain: {}, connect() {}, disconnect() {} }; }
    createBuffer(_, count) { return { duration: count / 24000, getChannelData: () => new Float32Array(count) }; }
    createBufferSource() { const n = { connect() {}, start() {}, stop() { this.stopped = true; } }; nodes.push(n); return n; }
  }
  class Worklet { port = {}; connect() {} disconnect() {} }
  vm.runInNewContext(script, {
    document: { querySelectorAll: () => [modeLink], querySelector: q => elements.get(q.slice(4)), createElement: element, body: { dataset: {} } },
    location: { pathname: '/interview/' + 'a'.repeat(32), origin: 'http://localhost' },
    sessionStorage: { getItem: k => k === 'account:session' ? null : 'b'.repeat(64) },
    fetch: async path => ({ ok: true, json: async () => path === '/api/voice/config' ? { realtime_enabled: enabled } : { question: { content: '测试题', theme: 'MySQL' } } }),
    navigator: { mediaDevices: { getUserMedia: async () => { mediaRequests++; if(mediaError)throw Object.assign(new Error('raw device error'),{name:mediaError});if(permission)await permission.promise; return media; } } },
    AudioContext: Audio, AudioWorkletNode: Worklet, WebSocket: Socket, URL, Blob, AbortSignal,
    setInterval: () => 1, clearInterval() {}, setTimeout, clearTimeout,
    atob, btoa, Uint8Array, Float32Array, DataView, addEventListener() {},
  });
  return { elements, sockets, nodes, tracks, sent, modeLink, mediaRequests: () => mediaRequests };
}
const disabled = setup(false); await tick();
assert.equal(disabled.elements.get('start').disabled, true);
await disabled.elements.get('start').click();
assert.equal(disabled.mediaRequests(), 0, 'Disabled service must not request microphone');
const resume = deferred(), opening = setup(true, resume); await tick();
const pendingStart = opening.elements.get('start').click();
opening.elements.get('end').click(); resume.resolve(); await pendingStart;
assert.equal(opening.mediaRequests(), 0, 'Ending during audio preparation must prevent microphone request');
const file = deferred(), reading = setup(); await tick();
reading.elements.get('file').files = [{ size: 44, arrayBuffer: () => file.promise }];
reading.elements.get('file').change(); await tick();
assert.equal(reading.elements.get('end').disabled, false, 'Pending file read must be cancellable');
reading.elements.get('end').click(); file.resolve(new ArrayBuffer(44)); await tick();
assert.equal(reading.sockets.length, 0, 'Cancelled file read must not open a supplier connection');
assert.equal(reading.elements.get('error').textContent, '', 'Old cancellation must not replace current UI with an error');
const live = setup(); await tick();
const started = live.elements.get('start').click(); await tick();
live.sockets[0].emit({ type: 'ready', max_seconds: 120, question: { content: '新题', theme: 'MySQL' } }); await started;
assert.equal(live.elements.get('title').textContent, '新题');
assert.equal(live.elements.get('clock').textContent, '02:00', 'Countdown must display the server limit immediately');
live.elements.get('pause').click(); assert.equal(live.tracks[0].enabled, false);
assert.equal(live.sent.at(-1).type, 'pause');
live.elements.get('pause').click(); assert.equal(live.tracks[0].enabled, true);
let blocked=false;live.modeLink.click({preventDefault(){blocked=true;}});assert.ok(blocked,'Active microphone must not navigate to another mode');
live.sockets[0].emit({ type: 'speaking' }); live.sockets[0].emit({ type: 'audio', data: 'ABAQEA==' });
live.elements.get('interrupt').click(); assert.equal(live.nodes[0].stopped, true);
assert.equal(live.sent.at(-1).type, 'interrupt');
live.elements.get('end').click(); assert.equal(live.tracks[0].stopped, true);
assert.equal(live.sockets[0].readyState, 3);
assert.equal(live.elements.get('start').disabled, false);
assert.equal(live.sent.some(e => /submit|score/.test(e.type)), false);
// A normal English reply can arrive faster than playback and exceed six seconds.
const burst=setup(); await tick();
const burstStart=burst.elements.get('start').click(); await tick();
burst.sockets[0].emit({type:'ready',max_seconds:120,question:{content:'English question'}}); await burstStart;
burst.sockets[0].emit({type:'speaking'});
const oneSecond=Buffer.alloc(48000,1).toString('base64');
for(let i=0;i<8;i++)burst.sockets[0].emit({type:'audio',data:oneSecond});
assert.equal(burst.sockets[0].readyState,1,'Eight seconds of burst audio is a valid short reply');
assert.equal(burst.elements.get('error').textContent,'');
for(let i=8;i<31;i++)burst.sockets[0].emit({type:'audio',data:oneSecond});
assert.equal(burst.sockets[0].readyState,3,'Playback memory remains bounded at thirty seconds');
assert.ok(burst.nodes.every(n=>n.stopped));
for(const [name,copy] of [['NotAllowedError','站点权限'],['NotFoundError','没有找到麦克风'],['NotReadableError','占用'],['OverconstrainedError','系统默认']]){
  const denied=setup(true,null,name);await tick();await denied.elements.get('start').click();
  assert.ok(denied.elements.get('error').textContent.includes(copy),name);
  assert.equal(denied.elements.get('start').disabled,false,'A failed microphone request must allow retry');
  assert.equal(denied.sockets.length,0,'A microphone failure must not start a billed connection');
}
const permission=deferred(),late=setup(true,null,null,permission);await tick();
const lateStart=late.elements.get('start').click();await tick();late.elements.get('end').click();permission.resolve();await lateStart;
assert.equal(late.tracks[0].stopped,true,'Permission granted after ending must release the late microphone stream');
assert.equal(late.sockets.length,0);
console.log('Passed: disabled capability, preparation/file cancellation, current question, countdown, pause/resume, playback interruption, device release, no formal submission.');
