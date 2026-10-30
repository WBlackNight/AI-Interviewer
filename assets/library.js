/* Generated: tools/build_ui.py */
/* 我的题单：收藏、手动标记与主题练习，纯文本展示。 */
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
function createNode(tag, text, className) {
	const node = document.createElement(tag);
	if (text !== undefined) node.textContent = text;
	if (className) node.className = className;
	return node;
}
async function guardedFetch(url, options) {
	const identity = readSession()?.access_token || '';
	const response = await fetch(url, options);
	const read = response.json.bind(response);
	response.json = async () => {
		const data = await read();
		if ((readSession()?.access_token || '') !== identity) throw Object.assign(new Error('会话已变化，请重新读取。'), { status: 401 });
		return data;
	};
	return response;
}
	const find = (id) => document.querySelector('#library-' + id);
	const endpoint = '/api/account/question-marks';
	const levels = { easy: '基础', mid: '进阶', hard: '挑战' };
	let identity = '', busy = false, writing = false, saved = null, bank = null, removal = null, created = null;
	let filters = { position: '', status: '', query: '', offset: 0 };
	let picker = { position: '', query: '', offset: 0 };
	const incoming = new URLSearchParams(location.search);
	if (/^[a-z][a-z0-9_]{0,63}$/.test(incoming.get('position') || '') && /^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/.test(incoming.get('question') || '')) {
		picker.position = incoming.get('position'); picker.query = incoming.get('question');
		find('sign-in').href = '/account?' + new URLSearchParams({ collect_position: picker.position, collect_question: picker.query });
	}
	const session = readSession;
	function hidePrivate() {
		find('workspace').hidden = true; find('list').replaceChildren(); find('bank-list').replaceChildren();
		find('login').hidden = false; find('remove-dialog').close(); removal = null;
	}
	async function request(path, method = 'GET', body, authenticated = true) {
		const current = session();
		if (!current || current.account.id !== identity) { hidePrivate(); throw new Error('会话失效或账户变化，请重新登录。'); }
		const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 30000);
		try {
			const response = await guardedFetch(path, { method, cache: 'no-store', signal: controller.signal,
				headers: { ...(authenticated ? { Authorization: 'Bearer ' + current.access_token } : {}), ...(body ? { 'Content-Type': 'application/json' } : {}) },
				...(body ? { body: JSON.stringify(body) } : {}) });
			if (session()?.account.id !== identity) { hidePrivate(); throw new Error('账户变化，请重新读取。'); }
			if (response.status === 401) hidePrivate();
			const data = await response.json().catch(() => null);
			if (!data) throw new Error('服务响应无法读取，请重试。');
			if (!response.ok) { const error = new Error(typeof data.detail === 'string' ? data.detail : '请求失败，请重试。'); error.status = response.status; throw error; }
			return data;
		} catch (error) {
			if (error.name === 'AbortError') throw new Error(method === 'GET' ? '读取超时，请重试。' : '请求超时，先刷新核对；不会自动重试。');
			if (error instanceof TypeError) throw new Error(method === 'GET' ? '读取失败，请重试。' : '连接中断，先核对记录再操作。');
			throw error;
		} finally { clearTimeout(timer); }
	}
	const element = createNode;
	function button(text, action) {
		const control = element('button', text, 'notes-button'); control.type = 'button'; control.addEventListener('click', action); return control;
	}
	function options(select, rows, selected, all) {
		select.replaceChildren();
		if (all) { const option = element('option', all); option.value = ''; select.append(option); }
		rows.forEach((row) => { const option = element('option', row.display_name); option.value = row.id; select.append(option); });
		if (selected && !rows.some((row) => row.id === selected)) { const option = element('option', selected); option.value = selected; select.append(option); }
		select.value = selected;
	}
	function lock() {
		document.querySelectorAll('#library-workspace button, #library-workspace input, #library-workspace select, #library-remove-confirm').forEach((control) => { control.disabled = busy || !!created; });
		find('previous').disabled = busy || !!created || !filters.offset;
		find('next').disabled = busy || !!created || !saved?.has_more;
		find('bank-previous').disabled = busy || !!created || !picker.offset;
		find('bank-next').disabled = busy || !!created || !bank?.has_more;
		find('enter-created').hidden = !created; find('enter-created').disabled = busy;
		find('retry').disabled = busy;
	}
	function renderSaved() {
		options(find('position'), saved.positions, filters.position, '全部岗位'); find('status').value = filters.status; find('search').value = filters.query;
		find('counts').textContent = '当前岗位与关键词范围：收藏 ' + saved.counts.all + ' · 待回看 ' + saved.counts.todo + ' · 已看过 ' + saved.counts.done + ' · 不可用 ' + saved.counts.unavailable + '。上限 ' + saved.max_marks + ' 道。';
		find('list').replaceChildren();
		saved.items.forEach((row) => {
			const card = element('article', undefined, 'note-card library-card'); const question = row.question;
			const role = saved.positions.find((item) => item.id === row.position)?.display_name || row.position;
			card.append(element('p', role + ' · ' + (row.status === 'done' ? '已看过' : '待回看'), 'eyebrow'));
			card.append(element('h3', question?.content || '这道题当前已不在运行题库中。'));
			const detail = element('details', undefined, 'report-answer'); detail.append(element('summary', '题目与收藏信息'));
			detail.append(element('p', row.question_id + (question ? '\n' + question.theme + ' · ' + (levels[question.difficulty] || question.difficulty) + ' · 来源：' + (question.source || '未标注') : '\n当前不可用；仍可整理或移除标记。') + '\n收藏：' + new Date(row.created_at).toLocaleString('zh-CN') + (row.reviewed_at ? '\n标记看过：' + new Date(row.reviewed_at).toLocaleString('zh-CN') : ''), 'report-version')); card.append(detail);
			const actions = element('div', undefined, 'note-actions');
			actions.append(button(row.status === 'done' ? '恢复待回看' : '标记已看过', () => mutate(() => request(endpoint + '/' + row.id, 'PATCH', { status: row.status === 'done' ? 'todo' : 'done', expected_version: row.version }), '手动标记已保存。')));
			if (row.can_practice) actions.append(button('练习本主题', () => practice(row)));
			actions.append(button('移除收藏', () => { removal = row; find('remove-description').textContent = row.question_id; find('remove-dialog').showModal(); }));
			card.append(actions);
			if (!row.can_practice) card.append(element('p', question?.is_coding ? '编程题可收藏回看；不从这里创建知识主题专项。' : '当前没有可练知识主题，仍可整理收藏。', 'notes-boundary'));
			find('list').append(card);
		});
		find('empty').hidden = saved.items.length > 0; find('pages').hidden = saved.total <= saved.limit;
		find('page').textContent = '第 ' + (filters.offset / 8 + 1) + ' / ' + Math.max(1, Math.ceil(saved.total / 8)) + ' 页';
	}
	function renderBank() {
		picker.position = bank.position || ''; options(find('bank-position'), bank.positions, picker.position);
		find('query').value = picker.query; find('bank-count').textContent = '匹配 ' + bank.total + ' 题；重复收藏保持原标记。';
		find('bank-list').replaceChildren();
		bank.items.forEach((row) => {
			const card = element('article', undefined, 'note-card library-card');
			card.append(element('p', row.theme + ' · ' + (row.is_coding ? '编程题' : '知识题') + ' · ' + (levels[row.difficulty] || row.difficulty), 'eyebrow'), element('h3', row.content));
			card.append(element('p', row.id + ' · 来源：' + (row.source || '未标注'), 'report-version'));
			card.append(button('收藏这道题', () => mutate(async () => {
				const result = await request(endpoint, 'POST', { position: row.position, question_id: row.id });
				return result.reused ? '已在题单中，原标记保持。' : '已收藏，可清除筛选查看。';
			})));
			find('bank-list').append(card);
		});
		find('bank-empty').hidden = bank.items.length > 0; find('bank-pages').hidden = bank.total <= bank.limit;
		find('bank-page').textContent = '第 ' + (picker.offset / 4 + 1) + ' / ' + Math.max(1, Math.ceil(bank.total / 4)) + ' 组';
	}
	async function readSaved() {
		if (Array.from(filters.query).length > 100) throw new Error('关键词最多100个字符。');
		const query = new URLSearchParams({ offset: String(filters.offset), limit: '8' });
		if (filters.position) query.set('position', filters.position); if (filters.status) query.set('status', filters.status);
		if (filters.query) query.set('q', filters.query);
		saved = await request(endpoint + '?' + query);
		if (!saved.items.length && filters.offset) { filters.offset = saved.total ? Math.floor((saved.total - 1) / 8) * 8 : 0; return readSaved(); }
		renderSaved();
	}
	async function readBank() {
		if (Array.from(picker.query).length > 100) throw new Error('关键词最多100个字符。');
		const query = new URLSearchParams({ offset: String(picker.offset), limit: '4' });
		if (picker.position) query.set('position', picker.position); if (picker.query) query.set('q', picker.query);
		bank = await request('/api/catalog?' + query, 'GET', undefined, false);
		if (!bank.items.length && picker.offset) { picker.offset = bank.total ? Math.floor((bank.total - 1) / 4) * 4 : 0; return readBank(); }
		renderBank();
	}
	async function refresh() {
		if (busy || created) return;
		busy = true; lock(); find('error').textContent = ''; find('loading').hidden = false; find('retry').hidden = true;
		saved = bank = null;
		for (const part of ['list', 'bank-list']) find(part).replaceChildren();
		for (const part of ['empty', 'bank-empty', 'pages', 'bank-pages']) find(part).hidden = true;
		find('counts').textContent = find('bank-count').textContent = '正在读取…';
		find('workspace').hidden = !find('login').hidden;
		try {
			const results = await Promise.allSettled([readSaved(), readBank()]);
			['saved-error', 'bank-error'].forEach((id, index) => { const failed = results[index].status === 'rejected'; find(id).textContent = failed ? results[index].reason.message : ''; if (failed) find(index ? 'bank-count' : 'counts').textContent = '暂不可用，请调整条件或刷新。'; });
		}
		finally { busy = false; find('loading').hidden = true; lock(); }
	}
	async function mutate(action, notice) {
		if (busy || created) return;
		busy = writing = true; lock(); find('error').textContent = ''; find('notice').textContent = '';
		try { const result = await action(); find('notice').textContent = notice || result; await readSaved(); }
		catch (error) {
			find('error').textContent = error.message;
			if (error.status === 409) { try { await readSaved(); } catch { hidePrivate(); } }
		} finally { busy = writing = false; lock(); }
	}
	function enterCreated() {
		if (session()?.account.id !== identity) { hidePrivate(); throw new Error('账户已变化，先到原账户查记录。'); }
		writing = false; location.assign('/interview/' + created.interview_id);
	}
	async function practice(row) {
		if (busy || created || !row.can_practice) return;
		busy = writing = true; lock(); find('error').textContent = '';
		try {
			const result = await request('/api/interview', 'POST', { position: row.position, themes: [row.question.theme], difficulty: find('intensity').value });
			if (!/^[a-f0-9]{32}$/.test(result.interview_id) || !result.account_owned) throw new Error('创建结果不完整，请先查看练习记录。');
			created = result; enterCreated();
		} catch (error) { find('error').textContent = error.message; }
		finally { busy = writing = false; lock(); }
	}
	find('filters').addEventListener('submit', (event) => { event.preventDefault(); filters = { position: find('position').value, status: find('status').value, query: find('search').value.trim(), offset: 0 }; refresh(); });
	find('reset').addEventListener('click', () => { filters = { position: '', status: '', query: '', offset: 0 }; find('search').value = ''; refresh(); });
	find('picker').addEventListener('submit', (event) => { event.preventDefault(); picker = { position: find('bank-position').value, query: find('query').value.trim(), offset: 0 }; refresh(); });
	find('refresh').addEventListener('click', refresh);
	find('previous').addEventListener('click', () => { filters.offset = Math.max(0, filters.offset - 8); refresh(); });
	find('next').addEventListener('click', () => { filters.offset += 8; refresh(); });
	find('bank-previous').addEventListener('click', () => { picker.offset = Math.max(0, picker.offset - 4); refresh(); });
	find('bank-next').addEventListener('click', () => { picker.offset += 4; refresh(); });
	find('keep').addEventListener('click', () => find('remove-dialog').close());
	find('remove-confirm').addEventListener('click', () => {
		const row = removal; find('remove-dialog').close(); removal = null;
		if (row) mutate(() => request(endpoint + '/' + row.id + '?expected_version=' + row.version, 'DELETE'), '收藏已移除。');
	});
	find('enter-created').addEventListener('click', () => { try { enterCreated(); } catch (error) { find('error').textContent = error.message; } });
	async function boot() {
		if (busy) return;
		const current = session(); identity = current?.account.id || ''; saved = bank = created = null;
		find('workspace').hidden = true; find('login').hidden = true; find('retry').hidden = false;
		if (!current) { hidePrivate(); find('loading').hidden = true; return; }
		busy = true; lock(); find('loading').hidden = false;
		try { const me = await request('/api/auth/me'); find('identity').textContent = me.username + '的个人题单'; }
		catch (error) { find('error').textContent = error.message; hidePrivate(); }
		finally { busy = false; find('loading').hidden = true; lock(); }
		if (find('login').hidden) await refresh();
	}
	find('retry').addEventListener('click', () => created ? refresh() : boot());
	addEventListener('beforeunload', (event) => { if (writing) { event.preventDefault(); event.returnValue = ''; } });
	addEventListener('pageshow', (event) => { if (event.persisted) boot(); });
	boot();
}());
