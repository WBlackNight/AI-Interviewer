/* Generated: tools/build_ui.py */
/* 原生练习记录与账户筛选。 */
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
	const find = (selector) => document.querySelector(selector);
	const names = { all: '全部记录', created: '尚未开始', running: '进行中', finished: '已完成', cancelled: '已取消' };
	const levels = { easy: '轻松', mid: '标准', hard: '挑战' };
	let page = null;
	let account = null;
	let busy = false;
	let anonymousCache = null;
	let claimOffset = 0;
	let confirmation = null;
	const claimed = new Set();
	const defaults = () => ({ status: 'all', position: '', difficulty: '' });
	const session = readSession;
	function anonymousToken(id) { try { return sessionStorage.getItem('interview:' + id + ':token'); } catch { return null; } }
	function anonymousIds() {
		const ids = [];
		try {
			for (let index = sessionStorage.length - 1; index >= 0 && ids.length < 50; index--) {
				const match = sessionStorage.key(index)?.match(/^interview:([a-f0-9]{32}):token$/);
				if (match && /^[a-f0-9]{64}$/.test(anonymousToken(match[1]) || '') && !claimed.has(match[1])) ids.push(match[1]);
			}
		} catch { /* 无存储权限时显示空标签页，不枚举服务端记录。 */ }
		return ids;
	}
	async function request(path, options = {}, resourceToken, timeout = 15000) {
		const token = resourceToken === undefined ? session()?.access_token : resourceToken;
		if (!/^[a-f0-9]{64}$/.test(token || '')) throw Object.assign(new Error('凭据失效，请重新登录。'), { status: 401 });
		const controller = new AbortController();
		const timer = setTimeout(() => controller.abort(), timeout);
		try {
			const response = await guardedFetch('/api' + path, { ...options, cache: 'no-store', signal: controller.signal,
				headers: { 'Content-Type': 'application/json', [resourceToken === undefined ? 'Authorization' : 'X-Interview-Token']: resourceToken === undefined ? 'Bearer ' + token : token } });
			const data = await response.json().catch(() => null);
			if (!response.ok) throw Object.assign(new Error(typeof data?.detail === 'string' ? data.detail : '请求失败，请重试。'), { status: response.status });
			return data;
		} catch (error) {
			if (error.name === 'AbortError') throw new Error('请求超时，请刷新核实；写操作不会重试。');
			if (error instanceof TypeError) throw new Error('连接失败，请检查本机服务后重试。');
			throw error;
		} finally { clearTimeout(timer); }
	}
	const element = (tag, className, text) => createNode(tag, text, className);
	function onClick(selector, action) { find(selector).addEventListener('click', action); }
	function setBusy(value) {
		busy = value;
		document.querySelectorAll('#history-main button, #history-main select, #history-confirm button').forEach((node) => { node.disabled = value; });
		find('#history-previous').disabled = value || !page || page.offset === 0;
		find('#history-next').disabled = value || !page?.has_more;
	}
	function selection() { return page ? { status: page.status || 'all', position: page.position || '', difficulty: page.difficulty || '' } : defaults(); }
	function showError(error) {
		find('#history-alert').textContent = error.message || '操作失败，请刷新重试。';
		if (error.status === 401 && account) find('#history-alert').textContent = '登录失效，请重新登录。';
	}
	async function readAnonymous() {
		const ids = anonymousIds();
		const result = new Array(ids.length);
		const deadline = Date.now() + 20000;
		let cursor = 0;
		async function worker() {
			while (cursor < ids.length) {
				const index = cursor++;
				const id = ids[index];
				try {
					if (Date.now() >= deadline) throw new Error('读取超时，请刷新。');
					const summary = await request('/interview/' + id, {}, anonymousToken(id), Math.min(10000, deadline - Date.now()));
					result[index] = { id, summary };
				} catch (error) { result[index] = { id, error: error.message }; }
			}
		}
		await Promise.all(Array.from({ length: Math.min(4, ids.length) }, worker));
		return result;
	}
	function anonymousPage(filters, offset) {
		const known = anonymousCache.filter((item) => item.summary);
		const positions = Array.from(new Map(known.map(({ summary }) => [summary.position, summary.position_display_name || summary.position])).entries()).sort().map(([id, display_name]) => ({ id, display_name }));
		const scope = anonymousCache.filter(({ summary }) => !summary ? !filters.position && !filters.difficulty : (!filters.position || summary.position === filters.position) && (!filters.difficulty || summary.difficulty === filters.difficulty));
		const counts = Object.fromEntries(Object.keys(names).filter((key) => key !== 'all').map((key) => [key, scope.filter(({ summary }) => summary?.status === key).length]));
		const rows = scope.filter(({ summary }) => filters.status === 'all' || summary?.status === filters.status);
		const validOffset = rows.length && offset >= rows.length ? Math.floor((rows.length - 1) / 8) * 8 : offset;
		return { items: rows.slice(validOffset, validOffset + 8), total: rows.length, offset: validOffset, limit: 8, has_more: validOffset + 8 < rows.length,
			...filters, status_counts: counts, status_total: scope.length, positions };
	}
	function renderClaims() {
		const ids = account ? anonymousIds() : [];
		find('#history-claims').hidden = ids.length === 0;
		if (claimOffset >= ids.length) claimOffset = 0;
		find('#history-claim-list').replaceChildren(...ids.slice(claimOffset, claimOffset + 5).map((id) => {
			const item = element('li');
			const button = element('button', 'notes-button', '认领到此账户'); button.type = 'button';
			button.addEventListener('click', () => void claim(id));
			item.append(element('span', '', '匿名面试 · ' + id.slice(0, 8)), button);
			return item;
		}));
		find('#history-claims-next').hidden = ids.length <= 5;
		find('#history-claims-next').textContent = '下一组 · 共 ' + ids.length + ' 场';
	}
	async function renderPage(filters, offset) {
		let result;
		if (account) {
			function path(nextOffset) {
				const query = new URLSearchParams({ offset: String(nextOffset), limit: '8' });
				if (filters.status !== 'all') query.set('status', filters.status);
				if (filters.position) query.set('position', filters.position);
				if (filters.difficulty) query.set('difficulty', filters.difficulty);
				return '/account/interviews?' + query;
			}
			result = await request(path(offset));
			if (!result.items.length && offset > 0 && result.total > 0) result = await request(path(Math.floor((result.total - 1) / result.limit) * result.limit));
			result.items = result.items.map((summary) => ({ id: summary.interview_id, summary }));
		} else {
			if (!anonymousCache) anonymousCache = await readAnonymous();
			result = anonymousPage(filters, offset);
		}
		page = result;
		find('#history-list').replaceChildren(...result.items.map(card));
		find('#history-empty').hidden = result.total > 0;
		find('#history-pagination').hidden = result.total === 0;
		find('#history-page').textContent = '第 ' + (Math.floor(result.offset / 8) + 1) + ' 页 · 共 ' + result.total + ' 项';
		find('#history-position').replaceChildren(new Option('全部岗位', ''), ...result.positions.map((item) => new Option(item.display_name, item.id)));
		find('#history-position').value = result.position || '';
		find('#history-difficulty').value = result.difficulty || '';
		find('#history-review').hidden = !account;
		find('#history-scope').textContent = account ? account.username + '的账户记录。' : '最多50条标签页匿名记录；关闭标签页后凭据失效。';
		document.querySelectorAll('[data-status]').forEach((button) => {
			const key = button.dataset.status;
			const count = key === 'all' ? result.status_total ?? Object.values(result.status_counts).reduce((sum, value) => sum + value, 0) : result.status_counts[key];
			button.textContent = names[key] + ' · ' + count;
			button.setAttribute('aria-pressed', String((result.status || 'all') === key));
		});
		renderClaims();
	}
	async function load(filters = selection(), offset = 0, refresh = false) {
		if (busy) return;
		setBusy(true); find('#history-alert').textContent = ''; find('#history-loading').hidden = false;
		try {
			const current = session();
			if ((account?.id || null) !== (current?.account.id || null)) { page = null; anonymousCache = null; find('#history-list').replaceChildren(); }
			account = current?.account || null;
			if (refresh) anonymousCache = null;
			await renderPage(filters, offset);
		} catch (error) { showError(error); }
		finally { find('#history-loading').hidden = true; setBusy(false); }
	}
	function timestamp(value) {
		if (!value) return '尚未开始';
		const time = new Date(/Z$|[+-]\d\d:\d\d$/.test(value) ? value : value + 'Z');
		return Number.isNaN(time.getTime()) ? '时间暂不可用' : time.toLocaleString('zh-CN');
	}
	function link(text, href, primary = false) {
		const node = element('a', primary ? 'notes-button notes-primary' : 'notes-button', text); node.href = href; return node;
	}
	function card({ id, summary, error }) {
		const article = element('article', 'note-card history-card'); article.dataset.interviewId = id;
		if (!summary) {
			article.append(element('h2', '', '暂时无法读取这条练习'), element('p', 'notes-alert', error));
			return article;
		}
		const heading = element('div', 'note-card-heading');
		heading.append(element('h2', '', summary.position_display_name || summary.position), element('span', 'note-task-status', names[summary.status] || '状态待确认'));
		const meta = element('p', 'note-context', (levels[summary.difficulty] || summary.difficulty) + ' · ' + summary.theme_count + ' 个主题 · 已回答 ' + summary.answer_count + ' 轮');
		const activity = element('p', 'history-activity', '最近活动：' + timestamp(summary.last_activity_at));
		const actions = element('div', 'note-actions');
		if (['created', 'running'].includes(summary.status)) actions.append(link(summary.status === 'created' ? '进入面试' : '继续面试', '/interview/' + id, true));
		actions.append(link(summary.status === 'finished' ? '查看复盘报告' : summary.status === 'cancelled' ? '查看部分报告' : '查看当前报告', '/report/' + id, summary.status === 'finished'));
		function action(text, kind) {
			const button = element('button', 'notes-button' + (kind === 'delete' ? ' danger-button' : ''), text); button.type = 'button';
			button.addEventListener('click', () => openConfirmation(id, kind)); actions.append(button);
		}
		if (['created', 'running'].includes(summary.status)) action('取消面试', 'cancel');
		if (account && summary.status !== 'running') action('删除记录', 'delete');
		article.append(heading, meta, activity, actions);
		return article;
	}
	async function claim(id) {
		if (busy || !account) return;
		setBusy(true); find('#history-alert').textContent = '';
		try {
			await request('/account/interviews/' + id + '/claim', { method: 'POST', body: JSON.stringify({ access_token: anonymousToken(id) }) });
			claimed.add(id);
			try { sessionStorage.removeItem('interview:' + id + ':token'); } catch { /* 服务端认领已经生效。 */ }
			anonymousCache = null; find('#history-notice').textContent = '认领成功，原匿名凭据失效。';
			await renderPage(selection(), 0);
		} catch (error) { showError(error); }
		finally { setBusy(false); }
	}
	const dialog = find('#history-confirm');
	function openConfirmation(id, kind) {
		confirmation = { id, kind };
		find('#history-confirm-title').textContent = kind === 'delete' ? '永久删除记录？' : '取消面试？';
		find('#history-confirm-copy').textContent = find('#history-confirm-copy').dataset[kind];
		find('#history-confirm-submit').textContent = kind === 'delete' ? '确认永久删除' : '确认取消面试';
		find('#history-confirm-error').textContent = ''; dialog.showModal();
	}
	onClick('#history-confirm-back', () => dialog.close());
	dialog.addEventListener('cancel', (event) => { if (busy) event.preventDefault(); });
	dialog.addEventListener('close', () => { confirmation = null; });
	onClick('#history-confirm-submit', async () => {
		if (busy || !confirmation) return;
		const action = confirmation;
		setBusy(true);
		try {
			if (action.kind === 'delete') await request('/account/interviews/' + action.id, { method: 'DELETE' });
			else await request('/interview/' + action.id + '/cancel', { method: 'POST' }, account ? session()?.access_token || null : anonymousToken(action.id));
			dialog.close(); anonymousCache = null;
			find('#history-notice').textContent = action.kind === 'delete' ? '记录已永久删除。' : '面试已取消，可查看部分报告。';
			await renderPage(selection(), page.offset);
		} catch (error) { find('#history-confirm-error').textContent = error.message; showError(error); }
		finally { setBusy(false); }
	});
	find('#history-filters').addEventListener('submit', (event) => { event.preventDefault(); void load({ ...selection(), position: find('#history-position').value, difficulty: find('#history-difficulty').value }); });
	document.querySelectorAll('[data-status]').forEach((button) => button.addEventListener('click', () => void load({ ...selection(), status: button.dataset.status })));
	onClick('#history-refresh', () => void load(selection(), page?.offset || 0, true));
	onClick('#history-reset', () => void load(defaults()));
	onClick('#history-previous', () => void load(selection(), Math.max(0, page.offset - 8)));
	onClick('#history-next', () => void load(selection(), page.offset + 8));
	onClick('#history-claims-next', () => { claimOffset = claimOffset + 5 >= anonymousIds().length ? 0 : claimOffset + 5; renderClaims(); setBusy(false); });
	void load(defaults());
})();
