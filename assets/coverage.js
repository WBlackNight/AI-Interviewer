/* Generated: tools/build_ui.py */
/* 题库覆盖：读取公开统计、按岗位查看缺口并导出当前范围，不接触账户凭据。 */
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
	const find = (id) => document.querySelector('#coverage-' + id);
	const names = { easy: '基础', mid: '进阶', hard: '挑战' };
	let result = null, reading = false, version = 0, controller = null;
	let position = '', gapsOnly = false;
	function address() {
		const query = new URLSearchParams(location.search);
		const value = query.get('position') || '';
		position = Array.from(value).length <= 64 ? value : '';
		gapsOnly = query.get('gaps') === '1';
	}
	function saveAddress() {
		const query = new URLSearchParams(); if (position) query.set('position', position); if (gapsOnly) query.set('gaps', '1');
		history.replaceState(null, '', '/coverage' + (query.size ? '?' + query : ''));
	}
	const element = createNode;
	function catalogLink(row, difficulty) {
		const query = new URLSearchParams({ position: row.position, theme: row.theme });
		if (difficulty) { query.set('difficulty', difficulty); query.set('kind', 'knowledge'); }
		return '/catalog?' + query;
	}
	function lock() {
		find('position').disabled = reading; find('refresh').disabled = reading; find('gaps').disabled = reading;
		find('export').disabled = reading || !result || find('content').hidden;
	}
	function renderMatrix() {
		find('matrix').replaceChildren();
		const themes = result.themes.filter((row) => !gapsOnly || row.missing_difficulties.length);
		find('theme-count').textContent = '当前显示 ' + themes.length + ' / ' + result.themes.length + ' 个根主题';
		themes.forEach((row) => {
			const card = element('article', undefined, 'coverage-theme');
			const heading = element('div'); heading.append(element('p', row.position_name, 'eyebrow'));
			const link = element('a', row.theme); link.href = catalogLink(row); const title = element('h3'); title.append(link); heading.append(title);
			heading.append(element('p', '知识题 ' + row.knowledge + ' · 编程题 ' + row.coding, 'notes-boundary')); card.append(heading);
			const levels = element('div', undefined, 'coverage-levels');
			if (row.coding_only) levels.append(element('p', '仅编码主题，不计知识难度缺口。', 'coverage-coding'));
			else Object.entries(names).forEach(([level, name]) => {
				const count = row.difficulties[level];
				const cell = element('a', undefined, 'coverage-cell' + (count ? ' is-populated' : ''));
				cell.href = catalogLink(row, level); cell.setAttribute('aria-label', row.theme + ' · ' + name + ' · ' + count + '道知识题');
				cell.append(element('span', name), element('strong', String(count)), element('small', count ? '查看题目 ↗' : '待补题目 ↗')); levels.append(cell);
			});
			card.append(levels); find('matrix').append(card);
		});
		find('empty').hidden = themes.length > 0; find('gaps').setAttribute('aria-pressed', String(gapsOnly));
	}
	function renderSources() {
		find('sources').replaceChildren();
		result.sources.forEach((source) => {
			const card = element('article', undefined, 'note-card coverage-source');
			card.append(element('p', source.count + ' 道题 · ' + (source.origin === 'self_authored' ? '项目自编' : source.origin === 'licensed' ? '许可来源声明' : '来源未知'), 'eyebrow'), element('h3', source.label));
			card.append(element('p', source.review_state === 'reference_checked' ? '已登记参考资料核对' : source.registered ? '已登记来源，参考资料尚未核对。' : '来源尚未登记，请补充来源声明。', 'notes-boundary'));
			card.append(element('p', source.id, 'report-version'));
			source.references.forEach((reference) => {
				const link = element('a', reference.title + ' ↗', 'link-arrow');
				try { const url = new URL(reference.url); if (url.protocol !== 'https:' || url.username || url.password) return; link.href = url.href; }
				catch { return; }
				link.target = '_blank'; link.rel = 'noopener noreferrer';
				card.append(link, element('p', '资料核对登记日期：' + reference.checked_on, 'notes-boundary'));
			});
			find('sources').append(card);
		});
	}
	function render() {
		find('position').replaceChildren(); const all = element('option', '全部岗位'); all.value = ''; find('position').append(all);
		result.positions.forEach((row) => { const option = element('option', row.display_name); option.value = row.id; find('position').append(option); });
		find('position').value = position;
		find('total').textContent = result.counts.all; find('roots').textContent = result.counts.knowledge_themes;
		find('kinds').textContent = '知识题 ' + result.counts.knowledge + ' · 编程题 ' + result.counts.coding;
		find('missing').textContent = result.counts.missing_cells; find('review').textContent = result.counts.not_reference_checked;
		find('definition').textContent = result.note;
		find('registry').textContent = result.registry_state === 'available' ? '来源未登记 ' + result.counts.unregistered + ' 道' : '来源登记文件暂不可用，统计按未登记呈现。';
		find('notice').textContent = result.counts.unmapped ? '有 ' + result.counts.unmapped + ' 道题尚未映射到当前技能树根主题。' : '';
		find('version').textContent = '当前题库摘要：' + result.corpus_sha256;
		renderMatrix(); renderSources(); saveAddress();
	}
	async function load() {
		if (reading) return;
		reading = true; const currentVersion = ++version;
		find('content').hidden = true; find('error').textContent = ''; find('loading').hidden = false; lock();
		const active = new AbortController(); controller = active; const timer = setTimeout(() => active.abort(), 15000);
		try {
			const query = new URLSearchParams(); if (position) query.set('position', position);
			const response = await guardedFetch('/api/catalog/coverage' + (query.size ? '?' + query : ''), { cache: 'no-store', signal: active.signal });
			const data = await response.json(); if (currentVersion !== version) return;
			if (!response.ok) { if (response.status === 404) { position = ''; find('position').value = ''; } throw new Error(typeof data.detail === 'string' ? data.detail : '统计读取失败，请重试。'); }
			result = data; render(); find('content').hidden = false;
		} catch (error) {
			if (currentVersion !== version) return;
			find('error').textContent = error.name === 'AbortError' ? '读取超时，请刷新重试。' : error instanceof TypeError ? '连接失败，请检查本机服务。' : error.message;
			if (!result) { find('position').replaceChildren(); const reset = element('option', '清除岗位筛选'); reset.value = ''; find('position').append(reset); }
		} finally { clearTimeout(timer); if (currentVersion === version) { reading = false; find('loading').hidden = true; lock(); } }
	}
	find('position').addEventListener('change', () => { position = find('position').value; load(); });
	find('refresh').addEventListener('click', () => { if (!result) position = find('position').value; load(); });
	find('gaps').addEventListener('click', () => { if (!result) return; gapsOnly = !gapsOnly; renderMatrix(); saveAddress(); });
	find('export').addEventListener('click', () => {
		if (reading || !result) return;
		const data = { format_version: 1, corpus_sha256: result.corpus_sha256, position: result.position,
			gaps: result.themes.flatMap((row) => row.missing_difficulties.map((level) => ({ position: row.position, theme: row.theme, difficulty: level }))),
			sources: result.sources, note: result.note };
		const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2) + '\n'], { type: 'application/json' }));
		const link = element('a'); link.href = url; link.download = 'question-bank-gaps-' + result.corpus_sha256.slice(0, 12) + '.json';
		document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
		find('notice').textContent = '已导出当前岗位范围的待补清单，题库未修改。';
	});
	addEventListener('popstate', () => { controller?.abort(); version++; reading = false; address(); load(); });
	address(); load();
}());
