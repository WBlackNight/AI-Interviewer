(function () {
	'use strict';
/* @include session */
/* @include token */
/* @include microphone */
	const find = (id) => document.querySelector('#voice-' + id);
	const copy = find('copy').dataset;
	const interviewId = location.pathname.match(/^\/interview\/([a-f0-9]{32})$/)?.[1];
	let socket, grant, config, question, context, stream, capture, source, mute, workletReady = false;
	let version = 0, frameSeq = 0, epoch = 0, recording = false, pending = false, active = false, disposed = false;
	let boundTurn = '', samples = new Float32Array(0), speech = '', playSequence = 0, nextPlay = 0, blocked = false;
	let recordingTimer, acquiring = false, generating = false, uploadEpoch = 0;
	let connecting = false, connectionTimer;
	const playing = new Set(), cancelled = new Set();
	const say = (id, text) => { find(id).textContent = text; };

	// 账户鉴权。
	const token = () => interviewToken(interviewId);
	const microphone = microphonePicker(find('device'), find('device-status'));
	function send(event) {
		if (disposed || socket?.readyState !== WebSocket.OPEN || token() !== grant) throw new Error(copy.identity);
		if (socket.bufferedAmount > 65536) throw new Error(copy.queue);
		socket.send(JSON.stringify(event));
	}
	function render() {
		const available = active && config?.enabled && question && !pending && !recording && !acquiring;
		find('start').disabled = !available || question.is_coding || !microphone.supported();
		find('file').disabled = !available || !!question.is_coding;
		find('stop').disabled = !recording && !acquiring;
		find('stop').textContent = acquiring ? '取消启动' : '停止录音并提交';
		find('device').disabled = recording || acquiring || pending;
		find('devices').disabled = recording || acquiring || pending;
		find('read').disabled = !available || generating || !!speech;
		find('interrupt').disabled = !speech && !playing.size && !find('playing').textContent;
		find('sync').disabled = recording || pending || acquiring || connecting;
		const state = acquiring ? 'preparing' : pending ? 'saving' : recording ? 'recording' : generating || playing.size ? 'speaking' : active && config?.enabled ? 'ready' : 'offline';
		document.body.dataset.voiceState = state;
		find('transcript').setAttribute('aria-busy', String(pending));
		say('hint', question?.is_coding ? copy.code : copy.hint);
	}

	// 资源清理。
	function stopCapture() {
		epoch++; uploadEpoch++; clearTimeout(recordingTimer); acquiring = false;
		recording = false; samples = new Float32Array(0);
		stream?.getTracks().forEach((track) => track.stop()); stream = null;
		if (capture) { capture.port.onmessage = null; capture.disconnect(); capture = null; }
		source?.disconnect(); source = null;
		mute?.disconnect(); mute = null;
		find('level').value = 0;
		find('file').value = '';
		say('capture', copy.idleCapture); render();
	}
	function clearPlayback() {
		if (speech) cancelled.add(speech);
		while (cancelled.size > 32) cancelled.delete(cancelled.values().next().value);
		for (const node of playing) { try { node.stop(); } catch { /* 已结束 */ } }
		playing.clear(); speech = ''; generating = false; nextPlay = 0; playSequence = 0;
		say('playing', ''); render();
	}
	async function prepareAudio() {
		if (typeof AudioContext === 'undefined') throw new Error('当前浏览器无法播放音频，请用 Edge 或 Chrome 打开。');
		if (!context || context.state === 'closed') { context = new AudioContext(); workletReady = false; }
		await context.resume();
	}
	function fail(error, close = false) {
		say('error', error.message || copy.fallback);
		stopCapture(); clearPlayback(); pending = false;
		if (close) { connecting = false; clearTimeout(connectionTimer); active = false; socket?.close(); }
		render();
	}
	function toBase64(bytes) {
		let text = '';
		for (const byte of bytes) text += String.fromCharCode(byte);
		return btoa(text);
	}
	function sendFrame(bytes) {
		if (!recording || boundTurn !== question?.turn_id) return;
		const seconds = Math.floor(frameSeq / 10);
		say('timer', String(Math.floor(seconds / 60)).padStart(2, '0') + ':' + String(seconds % 60).padStart(2, '0'));
		send({ type: 'audio', turn_id: boundTurn, seq: frameSeq++, format: 'pcm_s16le', sample_rate: 16000, channels: 1, data: toBase64(bytes) });
	}

	// 分帧。
	function captureBlock(block) {
		if (!recording) return;
		try {
			const merged = new Float32Array(samples.length + block.length);
			merged.set(samples); merged.set(block, samples.length);
			const size = Math.round(context.sampleRate / 10);
			let offset = 0, energy = 0;
			for (const value of block) energy += value * value;
			find('level').value = Math.min(1, Math.sqrt(energy / block.length) * 4);
			while (merged.length - offset >= size) {
				const bytes = new Uint8Array(3200), view = new DataView(bytes.buffer);
				for (let index = 0; index < 1600; index++) {
					const position = index * size / 1600, left = Math.floor(position), fraction = position - left;
					const value = merged[offset + left] * (1 - fraction) + merged[offset + Math.min(left + 1, size - 1)] * fraction;
					view.setInt16(index * 2, Math.round(Math.max(-1, Math.min(1, value)) * (value < 0 ? 32768 : 32767)), true);
				}
				sendFrame(bytes); offset += size;
			}
			samples = merged.slice(offset);
		} catch (error) { fail(error, true); }
	}
	async function startCapture() {
		if (recording || acquiring || pending || !config?.enabled || !active || !question || question.is_coding) return;
		const attempt = ++epoch;
		acquiring = true; render(); say('error', '');
		try {
			await prepareAudio();
			if (disposed || attempt !== epoch || !active) return;
			if (!context.audioWorklet) throw new Error('当前浏览器不支持录音处理，请用新版 Edge 或 Chrome 打开。');
			say('capture', '等待麦克风授权，请查看浏览器权限提示');
			const media = await microphone.acquire();
			if (disposed || attempt !== epoch || !active) { media.getTracks().forEach((track) => track.stop()); return; }
			stream = media; void microphone.refresh();
			const processor = "class Capture extends AudioWorkletProcessor { process(i) { if (i[0]?.[0]) this.port.postMessage(i[0][0].slice()); return true; } } registerProcessor('qingzhan-capture', Capture);";
			const url = URL.createObjectURL(new Blob([processor], { type: 'text/javascript' }));
			try { if (!workletReady) { await context.audioWorklet.addModule(url); workletReady = true; } } finally { URL.revokeObjectURL(url); }
			if (disposed || attempt !== epoch) { media.getTracks().forEach((track) => track.stop()); return; }
			blocked = true; clearPlayback(); send({ type: 'interrupt' });
			boundTurn = question.turn_id; frameSeq = 0; recording = true; acquiring = false; say('timer', '00:00');
			source = context.createMediaStreamSource(media);
			capture = new AudioWorkletNode(context, 'qingzhan-capture');
			capture.port.onmessage = (event) => captureBlock(event.data);
			mute = context.createGain(); mute.gain.value = 0;
			source.connect(capture); capture.connect(mute); mute.connect(context.destination);
			media.getAudioTracks().forEach((track) => track.addEventListener('ended', () => { if (recording) fail(new Error(copy.microphoneLost), true); }));
			say('capture', copy.capture);
			recordingTimer = setTimeout(finishCapture, config.max_seconds * 1000);
			render();
		} catch (error) { if (attempt === epoch) fail(microphoneError(error)); }
	}
	function finishCapture() {
		if (acquiring) { stopCapture(); say('capture', '已取消启动，麦克风不会继续采集。'); return; }
		if (!recording) return;
		if (samples.length) captureBlock(new Float32Array(Math.round(context.sampleRate / 10) - samples.length));
		const turn = boundTurn;
		stopCapture(); pending = true; render(); say('capture', copy.sampleDone);
		try { send({ type: 'audio_end', turn_id: turn }); } catch (error) { fail(error, true); }
	}

	// WAV上传。
	async function uploadWave(file) {
		const turn = question?.turn_id;
		if (recording || pending || acquiring || !active || !config?.enabled || !turn || question.is_coding || !file) return;
		const attempt = ++epoch; acquiring = true; say('capture','正在读取录音文件…'); render();
		try {
			if (file.size > config.max_seconds * 32000 + 65536) throw new Error(copy.oversize);
			await prepareAudio();
			const buffer = await file.arrayBuffer(), view = new DataView(buffer);
			const word = (offset) => String.fromCharCode(...new Uint8Array(buffer, offset, 4));
			if (buffer.byteLength < 44 || word(0) !== 'RIFF' || word(8) !== 'WAVE') throw new Error(copy.invalidWave);
			let valid = false, pcm;
			for (let offset = 12; offset + 8 <= buffer.byteLength;) {
				const length = view.getUint32(offset + 4, true), start = offset + 8;
				if (start + length > buffer.byteLength) throw new Error(copy.incompleteWave);
				if (word(offset) === 'fmt ' && length >= 16) valid = view.getUint16(start, true) === 1 && view.getUint16(start + 2, true) === 1 && view.getUint32(start + 4, true) === 16000 && view.getUint16(start + 14, true) === 16;
				if (word(offset) === 'data') pcm = new Uint8Array(buffer, start, length);
				offset = start + length + length % 2;
			}
			if (!valid || !pcm?.length || pcm.length % 2 || pcm.length > config.max_seconds * 32000) throw new Error(copy.wave);
			if (disposed || attempt !== epoch || !active || turn !== question?.turn_id) return;
			blocked = true; clearPlayback(); send({ type: 'interrupt' });
			boundTurn = turn; frameSeq = 0; recording = true; acquiring = false; say('timer', '00:00'); const uploadAttempt = ++uploadEpoch;
			say('capture', copy.upload); say('error', ''); render();
			for (let offset = 0; offset < pcm.length && recording && uploadAttempt === uploadEpoch; offset += 3200) {
				sendFrame(pcm.subarray(offset, offset + 3200));
				await new Promise((resolve) => setTimeout(resolve, 100));
			}
			if (recording && uploadAttempt === uploadEpoch) finishCapture();
		} catch (error) { if(attempt===epoch)fail(error, recording); }
		finally { if(attempt===epoch){acquiring=false;find('file').value='';render();} }
	}

	// 播放。
	function play(event) {
		if (blocked || !context || cancelled.has(event.utterance_id)) return;
		if (event.format !== 'pcm_s16le' || event.sample_rate !== 24000 || event.channels !== 1) throw new Error(copy.invalidAudio);
		if (speech !== event.utterance_id) { clearPlayback(); speech = event.utterance_id; playSequence = 0; }
		if (event.seq !== playSequence++) throw new Error(copy.sequence);
		const text = atob(event.data), bytes = Uint8Array.from(text, (char) => char.charCodeAt(0));
		if (!bytes.length || bytes.length % 2 || bytes.length > 64000) throw new Error(copy.incompleteAudio);
		nextPlay = Math.max(context.currentTime, nextPlay);
        if (nextPlay - context.currentTime + bytes.length / 48000 > 30) throw new Error(copy.bufferFull);
		const buffer = context.createBuffer(1, bytes.length / 2, 24000), values = buffer.getChannelData(0), view = new DataView(bytes.buffer);
		for (let index = 0; index < values.length; index++) values[index] = view.getInt16(index * 2, true) / 32768;
		const node = context.createBufferSource(); node.buffer = buffer; node.connect(context.destination);
		playing.add(node); node.onended = () => { playing.delete(node); if (!playing.size && !generating) { speech = ''; say('playing', ''); render(); } };
		generating = true; node.start(nextPlay); nextPlay += buffer.duration; say('playing', copy.playing); render();
	}

	// 保存。
	function receive(event) {
		if (event.type === 'snapshot') {
			connecting = false; clearTimeout(connectionTimer);
			question = event.current_question; version = event.version;
			active = !event.finished && !event.cancelled;
			pending = false; say('status', active ? copy.ready : copy.ended);
		} else if (event.type === 'question') {
			stopCapture(); question = event; version = event.version; active = true; pending = false; blocked = false;
			say('status', copy.next);
        } else if (event.type === 'voice_processing') {
            stopCapture(); pending = true; say('capture', copy.sampleDone); render();
        } else if (event.type === 'asr_partial' || event.type === 'asr_final') {
			say('transcript', event.text);
			if (event.type === 'asr_final') { stopCapture(); pending = true; say('saved', copy.saving); }
		} else if (event.type === 'answer_ack') {
			say('saved', copy.saved);
		} else if (event.type === 'report_ready' || event.type === 'interview_cancelled') {
			active = false; pending = false; stopCapture(); say('status', copy.finished);
		} else if (event.type === 'tts_chunk') play(event);
		else if (event.type === 'tts_end') { generating = false; if (!playing.size) { speech = ''; say('playing', ''); } }
		else if (event.type === 'barge_in_ack') { if (event.utterance_id) cancelled.add(event.utterance_id); }
		else if (['voice_empty', 'voice_error', 'voice_gap', 'tts_error', 'error'].includes(event.type)) {
			fail(new Error(event.detail || copy.failed), event.type === 'voice_gap');
		}
		if (event.version !== undefined) version = event.version;
		say('question', question?.content || copy.emptyQuestion);
		say('meta', question ? question.theme + (question.is_probe ? ' · 追问' : copy.mainQuestion) : 'PRACTICE SAVED'); render();
	}
	async function connect() {
		if (connecting) return;
		stopCapture(); clearPlayback(); active = false; pending = false;
		if (socket) { socket.onopen = socket.onerror = socket.onclose = socket.onmessage = null; socket.close(); }
		say('error', ''); say('status', copy.loading); grant = token();
		if (!grant || !interviewId) { say('error', copy.access); return; }
		connecting = true; render();
		try {
			const response = await fetch('/api/voice/config', { cache: 'no-store', signal: AbortSignal.timeout(10000) });
			if (!response.ok) throw new Error(copy.invalidConfig);
			config = await response.json();
			if (disposed) return;
			if(token()!==grant)throw new Error(copy.accountChanged);
			say('provider', config.enabled ? config.demo_only ? copy.demo : copy.provider : copy.disabled);
			const base = document.body.dataset.wsBase || location.origin.replace(/^http/, 'ws');
			const target = new URL(base);
			if (!['ws:', 'wss:'].includes(target.protocol) || target.username || target.password || target.search || target.hash) throw new Error(copy.invalidConnection);
			socket = new WebSocket(base.replace(/\/$/, '') + '/ws/interview/' + interviewId, ['interview', grant]);
			connectionTimer=setTimeout(()=>fail(new Error('语音连接超时，请检查网络后重新同步。'),true),15000);
			socket.onopen = () => { try { if (!disposed) send({ type: 'start' }); } catch (error) { fail(error, true); } };
			socket.onmessage = (message) => { try { if (token() !== grant) throw new Error(copy.accountChanged); receive(JSON.parse(message.data)); } catch (error) { fail(error, true); } };
			socket.onerror=()=>fail(new Error('语音连接失败，请检查网络，或重新登录后同步。'),true);
			socket.onclose = () => { connecting=false;clearTimeout(connectionTimer);pending = false; active = false; stopCapture(); clearPlayback(); say('status', copy.closed); render(); };
		} catch (error) { fail(error, true); }
	}

	// 显式操作。
	find('start').addEventListener('click', startCapture);
	find('devices').addEventListener('click', () => void microphone.refresh());
	find('stop').addEventListener('click', finishCapture);
	find('file').addEventListener('change', () => void uploadWave(find('file').files[0]));
	find('sync').addEventListener('click', connect);
	find('read').addEventListener('click', async () => {
		try { await prepareAudio(); blocked = false; clearPlayback(); send({ type: 'read_question', turn_id: question.turn_id, version }); generating = true; say('playing', copy.generating); render(); }
		catch (error) { fail(error); }
	});
	find('interrupt').addEventListener('click', () => { blocked = true; clearPlayback(); try { send({ type: 'interrupt' }); } catch (error) { fail(error); } });
	addEventListener('pagehide', () => { disposed = true; connecting=false;clearTimeout(connectionTimer);stopCapture(); clearPlayback(); socket?.close(); void context?.close(); });
	addEventListener('pageshow', (event) => { if (event.persisted) { disposed = false; void connect(); } });
	find('text-link').href = '/interview/' + interviewId;
	find('report').href = '/report/' + interviewId;
	void microphone.refresh(); connect();
  document.querySelectorAll('a[href*="mode="], #voice-text-link').forEach(link => link.addEventListener('click', event => {
    if (recording || acquiring || pending) { event.preventDefault(); say('error', '请先停止录音并等待本轮保存，再切换对话模式。'); }
  }));
}());
