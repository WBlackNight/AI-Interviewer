/* Generated: tools/build_ui.py */
(function () {
	'use strict';
function readSession() {
	try {
		const value = JSON.parse(sessionStorage.getItem('account:session'));
		return value && /^[a-f0-9]{64}$/.test(value.access_token)
			&& /^[a-f0-9]{32}$/.test(value.account?.id)
			&& typeof value.account.username === 'string'
			&& Date.parse(value.expires_at) > Date.now() ? value : null;
	} catch { return null; }
}
function interviewToken(id) {
	const account = readSession();
	if (account) return account.access_token;
	try {
		const value = sessionStorage.getItem('interview:' + id + ':token');
		return /^[a-f0-9]{64}$/.test(value || '') ? value : null;
	} catch { return null; }
}
function microphoneError(error) {
	const messages = {
		NotAllowedError: '麦克风未获授权。请在浏览器地址栏的站点权限中允许麦克风，再点击开始；内置浏览器不支持时，请用 Edge 或 Chrome 打开本页。',
		NotFoundError: '没有找到麦克风，请连接设备后刷新设备列表。',
		NotReadableError: '麦克风无法读取，可能被其他应用占用。请关闭占用程序，并检查系统麦克风权限。',
		OverconstrainedError: '所选麦克风已不可用，请切回系统默认或刷新设备列表。',
		SecurityError: '浏览器限制了录音，请用 HTTPS 或 localhost 地址在 Edge、Chrome 中打开。',
		AbortError: '麦克风启动中断，请重新选择设备后再试。'
	};
	return new Error(messages[error.name] || error.message || '麦克风暂不可用，请重试或上传录音。');
}
function microphonePicker(select, status) {
	const supported = () => typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia && typeof AudioContext !== 'undefined';
	let generation = 0;
	async function refresh() {
		const attempt = ++generation;
		if (!supported()) { status.textContent = '当前浏览器未开放录音，请在 Edge 或 Chrome 中打开 localhost 页面。仍可上传录音。'; return; }
		status.textContent = '使用系统默认麦克风；点击开始时才会请求录音授权。';
		if (!navigator.mediaDevices.enumerateDevices) return;
		try {
			const devices = (await navigator.mediaDevices.enumerateDevices()).filter(item => item.kind === 'audioinput' && item.deviceId && item.deviceId !== 'default');
			if (attempt !== generation) return;
			const previous = select.value;
			select.replaceChildren();
			const add = (value, label) => { const option = document.createElement('option'); option.value = value; option.textContent = label; select.append(option); };
			add('', '系统默认麦克风');
			devices.forEach((item, index) => add(item.deviceId, item.label || '麦克风 ' + (index + 1)));
			select.value = devices.some(item => item.deviceId === previous) ? previous : '';
			status.textContent = '点击开始后授权麦克风；首次授权后可查看设备名称。';
		} catch { status.textContent = '暂时无法读取设备列表，可使用系统默认麦克风。'; }
	}
	async function acquire() {
		if (!supported()) throw new Error('当前浏览器不支持录音，请用 Edge 或 Chrome 打开本页，或上传录音。');
		let expired = false, timer;
		const pending = navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, ...(select.value ? { deviceId: { exact: select.value } } : {}) } });
		pending.then(media => { if (expired) media.getTracks().forEach(track => track.stop()); }, () => {});
		try {
			return await Promise.race([pending, new Promise((_, reject) => { timer = setTimeout(() => { expired = true; reject(new Error('等待麦克风授权超时。请处理浏览器的权限提示，再重新开始。')); }, 20000); })]);
		} finally { clearTimeout(timer); }
	}
	return { supported, refresh, acquire };
}
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
