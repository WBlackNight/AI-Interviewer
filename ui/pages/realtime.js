(function () {
  'use strict';
/* @include session */
/* @include token */
/* @include microphone */
  const find = (id) => document.querySelector('#rt-' + id);
  const interviewId = location.pathname.match(/^\/interview\/([a-f0-9]{32})$/)?.[1];
  let available = false;
  let socket, context, stream, source, processor, mute, credential, ready, opening, uploading, paused;
  let samples = new Float32Array(0), sequence = 0, epoch = 0, nextPlay = 0, startedAt = 0, timer;
  let userCaption, assistantCaption, speaking = false, connectionTimer, rejectConnection;
  const playing = new Set();
  const token = () => interviewToken(interviewId);
  const microphone = microphonePicker(find('device'), find('device-status'));
  async function loadContext() {
    const identity = token(); available = false; render();
    find('error').textContent = ''; find('status').textContent = '正在检查实时语音服务…';
    try {
      if (!interviewId || !identity) throw new Error('请登录所属账户，或回到原匿名练习标签页。');
      const response = await fetch('/api/interview/' + interviewId + '/realtime-context', { headers: { 'X-Interview-Token': token() || '' }, cache: 'no-store', signal: AbortSignal.timeout(8000) });
      if (!response.ok) throw new Error(response.status === 403 ? '本场访问已失效，请登录所属账户或返回原练习。' : response.status === 409 ? '本场练习已结束，请从首页开始新练习。' : '当前题暂不可用，请返回文字作答并同步。');
      const data = await response.json();
      const config = await fetch('/api/voice/config', { cache: 'no-store', signal: AbortSignal.timeout(8000) });
      available = config.ok && (await config.json()).realtime_enabled === true;
      if (identity !== token()) throw new Error('账户已变化，请重新检查本场访问。');
      showContext(data);
      find('status').textContent = available ? '语音服务已启用，选择麦克风后点击开始。' : '实时服务尚未启用，可重新检查或切换文字作答。';
      find('hint').textContent = available ? '麦克风尚未开启' : '当前无法连接实时服务';
    } catch (error) { available = false; find('error').textContent = error.name === 'TimeoutError' ? '服务检查超时，请重新检查。' : error.message; find('status').textContent = '暂未就绪，请重新检查。'; }
    finally { render(); }
  }
  function showContext(data) {
    find('title').textContent = data.question?.content || '还没有当前题，可以先自由交流。';
    find('topic').textContent = data.question?.theme || '自由陪练';
  }
  function render() {
    find('start').disabled = !available || !microphone.supported() || !!ready || !!opening || !!uploading;
    find('device').disabled = !!stream || !!opening || !!uploading;
    find('devices').disabled = !!stream || !!opening || !!uploading;
    find('end').disabled = !socket && !opening && !uploading;
    find('file').disabled = !available || !!stream || !!opening || !!uploading;
    find('pause').disabled = !stream || !ready;
    find('pause').textContent = paused ? '继续说话' : '暂停麦克风';
    find('interrupt').disabled = !ready || !speaking && !playing.size;
    find('sync').disabled = !!ready || !!opening || !!uploading;
    document.body.dataset.voiceState = speaking || playing.size ? 'speaking' : ready && (stream && !paused || uploading) ? 'recording' : opening ? 'preparing' : 'ready';
  }
  function send(event) {
    if (!ready || socket?.readyState !== WebSocket.OPEN || token() !== credential) throw new Error('连接或账户已变化，请结束后重新开始。');
    if (socket.bufferedAmount > 65536) throw new Error('音频积压，已停止连接。');
    socket.send(JSON.stringify(event));
  }
  function clearPlayback() {
    for (const node of playing) { node.onended = null; try { node.stop(); } catch {} }
    playing.clear(); nextPlay = 0; speaking = false;
  }
  function stop() {
    epoch++; ready = opening = uploading = false; clearInterval(timer);
    clearTimeout(connectionTimer); rejectConnection?.(new Error('会话已结束。')); rejectConnection = null;
    stream?.getTracks().forEach((track) => track.stop()); stream = null;
    find('level').value = 0;
    processor?.disconnect(); source?.disconnect(); mute?.disconnect(); processor = source = mute = null;
    samples = new Float32Array(0); clearPlayback();
    find('file').value = '';
    if (socket) { socket.onerror = socket.onclose = socket.onmessage = null; socket.close(); socket = null; }
    void context?.close(); context = null; userCaption = assistantCaption = null;
    find('status').textContent = '对话已结束，可重新开始；正式练习记录未改变。';
    find('hint').textContent = '麦克风已释放'; render();
  }
  function fail(error) { stop(); find('error').textContent = error.message || '实时语音暂不可用，请返回正式练习。'; }
  async function audioContext() {
    if (typeof AudioContext === 'undefined') throw new Error('当前浏览器无法播放音频，请用 Edge 或 Chrome 打开。');
    if (!context || context.state === 'closed') context = new AudioContext();
    await context.resume();
  }
  async function connect() {
    if (!available) throw new Error('实时陪练尚未就绪。');
    if (ready) return;
    credential = token();
    if (!/^[a-f0-9]{64}$/.test(credential || '') || !interviewId) throw new Error('请从所属场次进入实时陪练。');
    sequence = 0; opening = true; render();
    find('status').textContent = '正在连接豆包实时会话…'; find('error').textContent = '';
    const base = document.body.dataset.wsBase || location.origin.replace(/^http/, 'ws');
    const target = new URL(base);
    if (!['ws:', 'wss:'].includes(target.protocol) || target.username || target.password || target.search || target.hash) throw new Error('连接配置无效。');
    await new Promise((resolve, reject) => {
      rejectConnection = reject;
      const deadline = connectionTimer = setTimeout(() => reject(new Error('实时连接超时，请重新开始。')), 20000);
      socket = new WebSocket(base + '/ws/realtime/' + interviewId, ['interview', credential]);
      socket.onmessage = (message) => {
        try {
          const event = JSON.parse(message.data);
          if (event.type === 'ready') {
            showContext(event);
            clearTimeout(deadline); rejectConnection = null; ready = true; opening = false; startedAt = Date.now();
            const countdown = () => {
              const seconds = Math.max(0, Math.ceil(event.max_seconds - (Date.now() - startedAt) / 1000));
              find('clock').textContent = String(Math.floor(seconds / 60)).padStart(2, '0') + ':' + String(seconds % 60).padStart(2, '0');
            }; countdown(); timer = setInterval(countdown, 1000);
            find('status').textContent = '实时连接已建立 · 本次最长 ' + event.max_seconds + ' 秒';
            render(); resolve();
          } else receive(event);
        } catch (error) { clearTimeout(deadline); reject(error); fail(error); }
      };
      socket.onclose = () => { clearTimeout(deadline); reject(new Error('连接已关闭或未获授权。')); fail(new Error('实时连接已关闭，请主动重新开始。')); };
      socket.onerror = () => { clearTimeout(deadline); reject(new Error('实时连接不可用。')); fail(new Error('实时连接不可用。')); };
    });
  }
  function caption(role, text, final) {
    let node = role === 'user' ? userCaption : assistantCaption;
    if (!node) {
      const article = document.createElement('article'), label = document.createElement('p');
      article.className = 'realtime-bubble'; article.dataset.role = role;
      label.className = 'eyebrow'; label.textContent = role === 'user' ? '你说' : '豆包陪练';
      node = document.createElement('p'); article.append(label, node); find('messages').append(article);
      while (find('messages').children.length > 8) find('messages').firstElementChild.remove();
      if (role === 'user') userCaption = node; else assistantCaption = node;
      find('empty').hidden = true;
    }
    node.textContent = (final && text ? text : node.textContent + text).slice(0, 20000);
    if (find('follow').checked) find('messages').scrollTop = find('messages').scrollHeight;
  }
  function receive(event) {
    if (token() !== credential) throw new Error('账户已变化，请重新连接。');
    if (event.type === 'listening') {
      clearPlayback(); userCaption = assistantCaption = null;
      find('hint').textContent = '正在听你说，停顿后自动回复';
    } else if (event.type === 'caption') caption(event.role, event.text, event.final);
    else if (event.type === 'speaking') { speaking = true; find('hint').textContent = '陪练正在回复，可以继续开口打断'; }
    else if (event.type === 'audio') play(event.data);
    else if (event.type === 'interrupted') { clearPlayback(); find('hint').textContent = '已打断，继续说说你的想法'; }
    else if (event.type === 'audio_end') { speaking = false; if (!playing.size) find('hint').textContent = '回复已结束，可以继续说话'; }
    else if (event.type === 'ended') stop();
    else if (event.type === 'error') throw new Error(({realtime_disabled:'实时服务未启用，请切换文字或稍后重试。',capacity:'语音连接已满，请先结束其他页面的语音，再重新开始。',provider_auth:'语音服务鉴权失败，请检查服务端语音配置。',provider_timeout:'语音服务响应超时，请稍后重新开始。'})[event.code] || '语音连接中断，请重新开始；如果反复失败，请检查网络或使用录音上传。');
    render();
  }
  function play(encoded) {
    const text = atob(encoded), bytes = Uint8Array.from(text, (char) => char.charCodeAt(0));
    if (!context || !bytes.length || bytes.length % 2 || bytes.length > 64000) throw new Error('播放格式不正确。');
    nextPlay = Math.max(nextPlay, context.currentTime);
    // 服务端可能以快于播放的速度返回完整短回复，保留有界的30秒播放窗口。
    if (nextPlay - context.currentTime + bytes.length / 48000 > 30) throw new Error('回复音频超过播放上限，请重新开始。');
    const buffer = context.createBuffer(1, bytes.length / 2, 24000), values = buffer.getChannelData(0), view = new DataView(bytes.buffer);
    for (let index = 0; index < values.length; index++) values[index] = view.getInt16(index * 2, true) / 32768;
    const node = context.createBufferSource(); node.buffer = buffer; node.connect(context.destination); playing.add(node);
    node.onended = () => { playing.delete(node); if (!playing.size && !speaking) find('hint').textContent = '回复已结束，可以继续说话'; render(); }; node.start(nextPlay); nextPlay += buffer.duration;
  }
  function interrupt() {
    clearPlayback(); send({ type: 'interrupt' }); render();
  }
  function sendPCM(bytes) {
    let text = ''; for (const byte of bytes) text += String.fromCharCode(byte);
    send({ type: 'audio', seq: sequence++, data: btoa(text) });
  }
  function block(input) {
    if (!ready || paused) return;
    try {
      let energy = 0; for (const value of input) energy += value * value;
      find('level').value = Math.min(1, Math.sqrt(energy / input.length) * 4);
      const merged = new Float32Array(samples.length + input.length); merged.set(samples); merged.set(input, samples.length);
      const size = Math.round(context.sampleRate / 10); let offset = 0;
      while (merged.length - offset >= size) {
        const bytes = new Uint8Array(3200), view = new DataView(bytes.buffer);
        for (let index = 0; index < 1600; index++) {
          const position = index * size / 1600, left = Math.floor(position), fraction = position - left;
          const value = Math.max(-1, Math.min(1, merged[offset + left] * (1 - fraction) + merged[offset + Math.min(left + 1, size - 1)] * fraction));
          view.setInt16(index * 2, Math.round(value * (value < 0 ? 32768 : 32767)), true);
        }
        sendPCM(bytes); offset += size;
      }
      samples = merged.slice(offset);
    } catch (error) { fail(error); }
  }
  async function start() {
    if (!available || opening || uploading || ready) return;
    const attempt = ++epoch; opening = true; render();
    try {
      await audioContext();
      if (attempt !== epoch) return;
      if (!/^[a-f0-9]{64}$/.test(token() || '')) throw new Error('请从所属场次进入。');
      if (!context.audioWorklet) throw new Error('当前浏览器不支持实时音频处理，请用新版 Edge 或 Chrome 打开本页。');
      find('hint').textContent = '等待麦克风授权，请查看浏览器权限提示';
      const media = await microphone.acquire();
      if (attempt !== epoch) { media.getTracks().forEach(track => track.stop()); return; }
      stream = media; void microphone.refresh(); await connect();
      if (attempt !== epoch) return;
      const url = URL.createObjectURL(new Blob(["class Capture extends AudioWorkletProcessor { process(i) { if (i[0]?.[0]) this.port.postMessage(i[0][0].slice()); return true; } } registerProcessor('realtime-capture', Capture);"], { type: 'text/javascript' }));
      try { await context.audioWorklet.addModule(url); } finally { URL.revokeObjectURL(url); }
      if (attempt !== epoch) return;
      paused = false; source = context.createMediaStreamSource(media); processor = new AudioWorkletNode(context, 'realtime-capture');
      mute = context.createGain(); mute.gain.value = 0;
      source.connect(processor); processor.connect(mute); mute.connect(context.destination); processor.port.onmessage = event => block(event.data);
      media.getTracks().forEach(track => track.addEventListener('ended', () => { if (stream === media) fail(new Error('麦克风已断开，请检查设备后重新开始。')); }));
      find('hint').textContent = '麦克风已开启，连续对话中'; render();
    } catch (error) { if (attempt === epoch) fail(microphoneError(error)); }
  }
  async function upload(file) {
    if (!available || !file || opening || uploading || stream) return;
    const fileEpoch = epoch;
    uploading = true; render();
    try {
      if (file.size > 385536) throw new Error('录音过大，最长十秒。');
      await audioContext();
      const buffer = await file.arrayBuffer(), view = new DataView(buffer);
      if (fileEpoch !== epoch) return;
      const word = offset => String.fromCharCode(...new Uint8Array(buffer, offset, 4));
      if (buffer.byteLength < 44 || word(0) !== 'RIFF' || word(8) !== 'WAVE') throw new Error('需要PCM16 WAV文件。');
      let valid, pcm;
      for (let offset = 12; offset + 8 <= buffer.byteLength;) {
        const length = view.getUint32(offset + 4, true), at = offset + 8;
        if (at + length > buffer.byteLength) throw new Error('录音文件不完整。');
        if (word(offset) === 'fmt ' && length >= 16) valid = view.getUint16(at, true) === 1 && view.getUint16(at + 2, true) === 1 && view.getUint32(at + 4, true) === 16000 && view.getUint16(at + 14, true) === 16;
        if (word(offset) === 'data') pcm = new Uint8Array(buffer, at, length);
        offset = at + length + length % 2;
      }
      if (!valid || !pcm?.length || pcm.length % 2 || pcm.length > 320000) throw new Error('需要十秒以内16kHz单声道PCM16。');
      await connect();
      if (fileEpoch !== epoch) return;
      const attempt = fileEpoch; interrupt();
      find('hint').textContent = '正在发送录音，随后等待实时回复';
      for (let offset = 0; offset < pcm.length && attempt === epoch; offset += 3200) { sendPCM(pcm.subarray(offset, offset + 3200)); await new Promise(resolve => setTimeout(resolve, 100)); }
      if (attempt === epoch) send({ type: 'pause' });
    } catch (error) { if (fileEpoch === epoch) fail(error); }
    finally { if (fileEpoch === epoch) { uploading = false; find('file').value = ''; render(); } }
  }
  find('start').addEventListener('click', start);
  find('devices').addEventListener('click', () => void microphone.refresh());
  find('sync').addEventListener('click', loadContext);
  find('end').addEventListener('click', stop);
  find('interrupt').addEventListener('click', () => { try { interrupt(); } catch (error) { fail(error); } });
  find('pause').addEventListener('click', () => {
    try { paused = !paused; samples = new Float32Array(0); find('level').value=0; stream.getAudioTracks().forEach(track => { track.enabled = !paused; }); if (paused) send({ type: 'pause' }); find('hint').textContent = paused ? '已暂停收音，点击结束可释放麦克风。' : '正在听你说'; render(); }
    catch (error) { fail(error); }
  });
  find('file').addEventListener('change', () => void upload(find('file').files[0]));
  addEventListener('pagehide', stop);
  addEventListener('pageshow', event => { if (event.persisted) void loadContext(); });
  document.querySelectorAll('a[href*="mode="]').forEach(link => link.addEventListener('click', event => {
    if (opening || uploading || stream) { event.preventDefault(); find('error').textContent = '请先结束对话，再切换练习方式。'; }
  }));
  render(); void microphone.refresh(); loadContext();
}());
