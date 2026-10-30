/* Generated: tools/build_ui.py */
/* 准备计划：范围与练习入口。 */
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
	const find = (id) => document.querySelector('#plans-' + id);
	function setText(id, value) { find(id).textContent = value; }
	function setHidden(id, value) { find(id).hidden = value; }
	const endpoint = '/api/account/preparation-plans';
	const levels = { easy: '轻松', mid: '标准', hard: '挑战' };
	let identity = '', busy = false, writing = false, createDirty = false, editDirty = false;
	let roles = [], data = null, editing = null, removing = null, created = null;
	const focus = new URLSearchParams(location.search).get('plan_id') || '';
	let filters = { position: '', status: focus ? '' : 'active', offset: 0, plan_id: focus };
	const session = readSession;
	function hidePrivate() {
		setHidden('workspace', true); setHidden('login', false); find('list').replaceChildren();
		for (const id of ['edit', 'discard', 'remove']) find(id).close();
		find('create-form').reset(); find('edit-name').value = find('edit-target').value = '';
		editing = removing = null; createDirty = editDirty = false;
	}
	async function request(path, method = 'GET', body, publicRead = false) {
		const current = session();
		if (!current || current.account.id !== identity) { hidePrivate(); throw new Error('请重新登录。'); }
		const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 30000);
		try {
			const response = await guardedFetch(path, { method, cache: 'no-store', signal: controller.signal,
				headers: { ...(!publicRead ? { Authorization: 'Bearer ' + current.access_token } : {}), ...(body ? { 'Content-Type': 'application/json' } : {}) },
				...(body ? { body: JSON.stringify(body) } : {}) });
			if (session()?.access_token !== current.access_token || response.status === 401) { hidePrivate(); throw new Error('会话变化，请重新登录。'); }
			const result = await response.json().catch(() => null);
			if (!result) throw new Error('响应无效，请刷新核对。');
			if (!response.ok) { const error = new Error(typeof result.detail === 'string' ? result.detail : '操作失败，请重试。'); error.status = response.status; throw error; }
			return result;
		} catch (error) {
			if (error.name === 'AbortError') throw new Error(method === 'GET' ? '读取超时，请重试。' : '请求超时，请先核对结果。');
			if (error instanceof TypeError) throw new Error('连接中断，请刷新核对。');
			throw error;
		} finally { clearTimeout(timer); }
	}
	const element = createNode;
	function link(label, path) { const node = element('a', label, 'link-arrow'); node.href = path; return node; }
	function button(text, action) {
		const node = element('button', text, 'notes-button'); node.type = 'button'; node.addEventListener('click', action); return node;
	}
	function option(select, value, label) { const node = element('option', label); node.value = value; select.append(node); }
	function role() { return roles.find((row) => row.id === find('position').value); }
	function selectedThemes() { return Array.from(document.querySelectorAll('#plans-themes input:checked'), (node) => node.value); }
	function lock() {
		document.querySelectorAll('#plans-workspace :is(button,input,select), #plans-edit :is(button,input), #plans-remove-confirm').forEach((node) => { node.disabled = busy || !!created || node.dataset.blocked === 'true'; });
		const chosen = selectedThemes(); const limit = role()?.practice_theme_limit || 0;
		document.querySelectorAll('#plans-themes input').forEach((node) => { node.disabled = busy || !!created || (!node.checked && chosen.length >= limit); });
		setText('selected', '已选 ' + chosen.length + ' / ' + limit + ' 个主题');
		find('create').disabled = busy || !!created || !chosen.length || chosen.length > limit;
		find('previous').disabled = busy || !!created || !filters.offset;
		find('next').disabled = busy || !!created || !data?.has_more;
		find('retry').disabled = busy; setHidden('enter', !created); find('enter').disabled = busy;
	}
	function renderThemes() {
		find('themes').replaceChildren();
		(role()?.practice_themes || []).forEach((name) => {
			const label = element('label', undefined, 'plans-theme'); const input = element('input');
			input.type = 'checkbox'; input.value = name;
			label.append(input, element('span', name)); find('themes').append(label);
		});
		lock();
	}
	function render() {
		find('filter-position').replaceChildren(); option(find('filter-position'), '', '全部岗位');
		data.positions.forEach((row) => option(find('filter-position'), row.id, row.display_name));
		if (filters.position && !data.positions.some((row) => row.id === filters.position)) option(find('filter-position'), filters.position, filters.position);
		find('filter-position').value = filters.position; find('filter-status').value = filters.status;
		setText('active', data.counts.active); setText('archived', data.counts.archived); setText('past', data.counts.past_target);
		setText('calendar', '北京时间 ' + data.today + ' · 岗位计数 · 上限' + data.max_plans + ' 份');
		find('list').replaceChildren();
		data.items.forEach((row) => {
			const card = element('article', undefined, 'note-card plans-card');
			const roleName = data.positions.find((item) => item.id === row.position)?.display_name || row.position;
			card.append(element('p', roleName + ' · ' + (row.status === 'active' ? '准备中' : '已归档'), 'eyebrow'), element('h3', row.name));
			card.append(element('p', row.themes.join(' / ') + ' · ' + levels[row.difficulty], 'plans-topics'));
			card.append(element('p', row.target_date ? '目标日期：' + row.target_date + (row.target_date < data.today ? ' · 已过目标日期' : row.target_date === data.today ? ' · 今天' : '') : '尚未设置目标日期', 'notes-boundary'));
			card.append(element('p', '已完成练习 ' + row.finished_count + ' 场', 'notes-boundary'));
			const pending = row.latest_practice && ['created', 'running'].includes(row.latest_practice.status);
			const actions = element('div', undefined, 'note-actions');
			if (row.status === 'active') {
				const start = button(pending ? '继续本计划练习' : '开始本计划练习', () => practice(row));
				start.dataset.blocked = String(!row.available && !pending); actions.append(start);
			}
			actions.append(button('编辑计划', () => openEdit(row)), button(row.status === 'active' ? '归档计划' : '恢复计划', () => mutate(() => request(endpoint + '/' + row.id, 'PATCH', { status: row.status === 'active' ? 'archived' : 'active', expected_version: row.version }), '状态已保存。')));
			if (row.status === 'archived') actions.append(button('移除已归档计划', () => { removing = row; setText('remove-name', row.name); find('remove').showModal(); }));
			card.append(actions);
			card.append(link('计划练习记录 ↗', '/plan-history?plan_id=' + row.id));
			if (row.latest_practice) card.append(link(pending ? '继续已有场次 ↗' : '最近练习报告 ↗', (pending ? '/interview/' : '/report/') + row.latest_practice.interview_id));
			if (!row.available) card.append(element('p', '范围不可练，已有记录保留。', 'notes-boundary'));
			find('list').append(card);
		});
		setHidden('empty', data.items.length > 0); setHidden('pages', data.total <= data.limit);
		setText('page', '第' + (filters.offset / 8 + 1) + ' / ' + Math.max(1, Math.ceil(data.total / 8)) + ' 页'); lock();
	}
	async function readList() {
		const query = new URLSearchParams(Object.entries({ ...filters, limit: 8 }).filter(([, value]) => value !== ''));
		setHidden('focus', !filters.plan_id);
		data = await request(endpoint + '?' + query);
		if (!data.items.length && filters.offset) { filters.offset = data.total ? Math.floor((data.total - 1) / 8) * 8 : 0; return readList(); }
		render();
	}
	async function refresh() {
		if (busy || created) return;
		busy = true; lock(); setText('error', ''); setHidden('retry', true);
		find('list').replaceChildren(); setHidden('pages', find('empty').hidden = true);
		try { await readList(); }
		catch (error) { setText('error', error.message); setHidden('retry', false); }
		finally { busy = false; lock(); }
	}
	async function mutate(action, notice, errorId = 'error') {
		if (busy || created) return;
		busy = writing = true; lock(); find(errorId).textContent = '';
		try { await action(); setText('notice', notice); await readList(); }
		catch (error) { find(errorId === 'edit-error' && !find('edit').open ? 'error' : errorId).textContent = error.message; if (error.status === 409 && errorId === 'error') { try { await readList(); } catch { hidePrivate(); } } }
		finally { busy = writing = false; lock(); }
	}
	function planName(id) {
		const name = find(id).value.trim();
		if (!name || Array.from(name).length > 80) throw new Error('名称应为1–80字。');
		return name;
	}
	function openEdit(row) {
		editing = row; editDirty = false; find('edit-name').value = row.name; find('edit-target').value = row.target_date || '';
		setText('edit-error', ''); find('edit').showModal();
	}
	function closeEdit() { if (busy) return; if (editDirty) find('discard').showModal(); else find('edit').close(); }
	find('edit-form').addEventListener('input', () => { editDirty = true; });
	find('edit-close').addEventListener('click', closeEdit);
	find('edit').addEventListener('cancel', (event) => { event.preventDefault(); closeEdit(); });
	find('keep-edit').addEventListener('click', () => find('discard').close());
	find('discard-edit').addEventListener('click', () => { editDirty = false; find('discard').close(); find('edit').close(); });
	find('edit-form').addEventListener('submit', async (event) => {
		event.preventDefault(); if (busy || !editing) return;
		await mutate(async () => {
			await request(endpoint + '/' + editing.id, 'PATCH', { name: planName('edit-name'), target_date: find('edit-target').value || null, expected_version: editing.version });
			editDirty = false; find('edit').close();
		}, '已保存。', 'edit-error');
	});
	function clearDraft() { createDirty = false; find('create-form').reset(); renderThemes(); }
	find('clear').addEventListener('click', clearDraft);
	find('create-form').addEventListener('input', () => { createDirty = true; lock(); });
	find('position').addEventListener('change', () => { createDirty = true; renderThemes(); });
	find('themes').addEventListener('change', lock);
	find('create-form').addEventListener('submit', async (event) => {
		event.preventDefault(); if (busy || created) return;
		await mutate(async () => {
			await request(endpoint, 'POST', { name: planName('name'), position: find('position').value, themes: selectedThemes(), difficulty: find('difficulty').value, target_date: find('target').value || null });
			clearDraft(); filters = { position: '', status: 'active', offset: 0 }; history.replaceState(null, '', '/plans');
		}, '已保存计划，尚未创建练习。', 'create-error');
	});
	function enter() {
		if (session()?.account.id !== identity) { hidePrivate(); throw new Error('请重新登录后查记录。'); }
		writing = false; location.assign('/interview/' + created.interview_id);
	}
	async function practice(row) {
		if (busy || created) return;
		if (createDirty) { setText('error', '先保存或清空草稿，再开始练习。'); return; }
		busy = writing = true; lock(); setText('error', '');
		try {
			const result = await request(endpoint + '/' + row.id + '/practice', 'POST', { expected_version: row.version });
			if (!/^[a-f0-9]{32}$/.test(result.interview_id) || !result.account_owned) throw new Error('结果不完整，请查记录。');
			created = result; createDirty = editDirty = false; enter();
		} catch (error) { setText('error', error.message); }
		finally { busy = writing = false; lock(); }
	}
	find('enter').addEventListener('click', () => { try { enter(); } catch (error) { setText('error', error.message); } });
	find('keep').addEventListener('click', () => find('remove').close());
	find('remove-confirm').addEventListener('click', () => { const row = removing; removing = null; find('remove').close(); if (row) mutate(() => request(endpoint + '/' + row.id + '?expected_version=' + row.version, 'DELETE'), '已移除，练习记录保留。'); });
	find('apply').addEventListener('click', () => { filters = { position: find('filter-position').value, status: find('filter-status').value, offset: 0 }; history.replaceState(null, '', '/plans'); refresh(); });
	find('refresh').addEventListener('click', refresh);
	find('previous').addEventListener('click', () => { filters.offset = Math.max(0, filters.offset - 8); refresh(); });
	find('next').addEventListener('click', () => { filters.offset += 8; refresh(); });
	async function boot() {
		if (busy) return;
		identity = session()?.account.id || ''; created = null; setHidden('workspace', true); setHidden('login', true);
		if (!identity) { hidePrivate(); setHidden('loading', true); return; }
		busy = true; lock(); setHidden('loading', false); setText('error', '');
		try {
			if (focus && !/^[a-f0-9]{32}$/.test(focus)) throw new Error('来源地址无效。');
			const me = await request('/api/auth/me'); setText('identity', me.username + '的准备计划');
			roles = (await request('/api/positions', 'GET', undefined, true)).positions;
			find('position').replaceChildren(); roles.forEach((row) => option(find('position'), row.id, row.display_name)); renderThemes();
			setHidden('workspace', false); await readList(); setHidden('retry', true);
		} catch (error) { setText('error', error.message); setHidden('retry', false); }
		finally { busy = false; setHidden('loading', true); lock(); }
	}
	find('retry').addEventListener('click', () => find('workspace').hidden ? boot() : refresh());
	addEventListener('beforeunload', (event) => { if (writing || createDirty || editDirty) { event.preventDefault(); event.returnValue = ''; } });
	addEventListener('pageshow', (event) => { if (event.persisted) boot(); });
	boot();
}());
