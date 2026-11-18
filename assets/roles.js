/* Generated: tools/build_ui.py */
/* Public role directory. All capabilities come from the current server assets. */
(function () {
	'use strict';
function createNode(tag, text, className) {
	const node = document.createElement(tag);
	if (text !== undefined) node.textContent = text;
	if (className) node.className = className;
	return node;
}
async function requestJSON(path, { auth = false, timeout = 10000, signal, ...options } = {}) {
	const identity = auth ? readSession()?.access_token : '';
	if (auth && !identity) throw Object.assign(new Error('请先登录后继续。'), { status: 401 });
	const controller = new AbortController();
	const cancel = () => controller.abort();
	if (signal?.aborted) cancel(); else signal?.addEventListener('abort', cancel, { once: true });
	const timer = setTimeout(cancel, timeout);
	const ensureIdentity = () => {
		if (auth && readSession()?.access_token !== identity) {
			throw Object.assign(new Error('账户已变化，请重新读取。'), { status: 401 });
		}
	};
	try {
		const response = await fetch(path, { ...options, cache: 'no-store', signal: controller.signal,
			headers: { ...(auth ? { Authorization: 'Bearer ' + identity } : {}), ...options.headers } });
		ensureIdentity();
		let data;
		try { data = await response.json(); }
		catch (error) { if (error.name === 'AbortError') throw error; throw new Error('返回内容暂时无法读取，请重试。'); }
		ensureIdentity();
		if (!response.ok) throw Object.assign(new Error(typeof data?.detail === 'string' ? data.detail :
			response.status === 401 ? '登录已过期，请重新登录。' : '操作暂未完成，请稍后重试。'), { status: response.status });
		return data;
	} catch (error) {
		if (error.name === 'AbortError' && !signal?.aborted) throw Object.assign(new Error('等待超时，请稍后重试。'), { code: 'TIMEOUT' });
		if (error instanceof TypeError) throw new Error('连接暂时中断，请检查网络后重试。');
		throw error;
	} finally {
		clearTimeout(timer);
		signal?.removeEventListener('abort', cancel);
	}
}
	const find = id => document.getElementById('roles-' + id);
	let roles = [], group = '', generation = 0;
	const element = createNode;
	function render() {
		const term = find('search').value.trim().toLocaleLowerCase();
		const filtered = roles.filter(role => (!group || role.group === group) &&
			[role.name, role.summary, role.focus, ...role.themes].join(' ').toLocaleLowerCase().includes(term));
		find('list').replaceChildren();
		filtered.forEach(role => {
			const card = element('article', undefined, 'role-card');
			card.append(element('p', role.group, 'eyebrow'), element('h3', role.name), element('p', role.summary));
			const tags = element('div', undefined, 'role-tags');
			role.themes.slice(0, 3).forEach(theme => tags.append(element('span', theme)));
			card.append(tags, element('p', role.count + ' 道题 · ' + role.focus, 'notes-boundary'));
			const actions = element('div', undefined, 'note-actions');
			const start = element('a', '练习这个方向', 'notes-button notes-primary');
			start.href = '/?' + new URLSearchParams({ position: role.id }) + '#start';
			const browse = element('a', '浏览题目', 'link-arrow');
			browse.href = '/catalog?' + new URLSearchParams({ position: role.id });
			actions.append(start, browse); card.append(actions); find('list').append(card);
		});
		find('status').textContent = filtered.length ? '共 ' + filtered.length + ' 个方向' : '没有匹配的方向，请调整分类或关键词。';
		find('groups').querySelectorAll('button').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.group === group)));
	}
	async function load() {
		const version = ++generation;
		find('retry').hidden = true; find('error').textContent = ''; find('status').textContent = '正在读取可用方向…';
		try {
			const data = await requestJSON('/api/practice/config');
			if (version !== generation) return;
			roles = Object.entries(data.positions).map(([id, role]) => ({ ...role, id }));
			find('groups').replaceChildren();
			['', ...new Set(roles.map(role => role.group))].forEach(name => {
				const button = element('button', name || '全部方向', 'notes-button');
				button.type = 'button'; button.dataset.group = name;
				button.addEventListener('click', () => { group = name; render(); });
				find('groups').append(button);
			});
			render();
		} catch (error) {
			if (version !== generation) return;
			find('status').textContent = ''; find('error').textContent = error.name === 'TimeoutError' ? '读取超时，请重新读取。' : '方向暂时无法读取，请重新读取。';
			find('retry').hidden = false;
		}
	}
	find('search').addEventListener('input', render);
	find('retry').addEventListener('click', load);
	addEventListener('pagehide', () => { generation++; });
	void load();
})();
