/* Generated: tools/build_ui.py */
/* 原生报告：逐轮分页不改变评分。 */
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
	const find = (id) => document.querySelector('#report-' + id);
	const reportId = location.pathname.match(/^\/report\/([a-f0-9]{32})$/)?.[1];
	function setText(id, value) { find(id).textContent = value; }
	function setHidden(id, value) { find(id).hidden = value; }
	const pageSize = 4;
	let report = null;
	let kind = 'all';
	let page = 0;
	let busy = false;
	let loading = false;
	let loadVersion = 0;
	const session = readSession;
	function credential(accountOnly = false) {
		const account = session();
		let token = account?.access_token;
		if (!token && !accountOnly) {
			try { token = sessionStorage.getItem('interview:' + reportId + ':token'); } catch { /* 无凭据时由读取提示恢复。 */ }
		}
		if (!/^[a-f0-9]{64}$/.test(token || '')) throw new Error('请登录所属账户或检查匿名凭据。');
		return { token, account: !!account };
	}
	async function request(path, options = {}, accountOnly = false, blob = false) {
		const access = credential(accountOnly);
		const controller = new AbortController();
		const timer = setTimeout(() => controller.abort(), 20000);
		try {
			const response = await fetch('/api' + path, { ...options, cache: 'no-store', signal: controller.signal,
				headers: { 'X-Interview-Token': access.token, ...(access.account ? { Authorization: 'Bearer ' + access.token } : {}) } });
			const data = blob && response.ok ? await response.blob() : await response.json().catch(() => null);
			if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : '读取失败，请检查账户。');
			if (credential(accountOnly).token !== access.token) throw new Error('会话已变化，请刷新。');
			return data;
		} catch (error) {
			if (error.name === 'AbortError') throw new Error('请求超时，请刷新核对；未自动重试。');
			if (error instanceof TypeError) throw new Error('连接失败，请检查服务。');
			throw error;
		} finally { clearTimeout(timer); }
	}
	const node = createNode;
	function originText(origin = {}) {
		const names = { heuristic: '规则评分', llm: '模型评分', heuristic_fallback: '模型失败后规则回退' };
		return (names[origin.source] || '来源未记录') + (origin.cached ? ' · 缓存命中，本轮未调用评分模型' : '') + (origin.sandbox_applied ? ' · 含客观判题合分' : '');
	}
	function versions(origin = {}) {
		return [origin.scorer_version, origin.model, origin.prompt_version, origin.config_version && '配置 ' + origin.config_version,
			origin.prompt_digest && '提示词摘要 ' + origin.prompt_digest.slice(0, 12), origin.fallback_reason && '回退类别 ' + origin.fallback_reason].filter(Boolean).join(' · ') || '历史来源与版本未记录';
	}
	function setBusy(value) {
		busy = value;
		document.querySelectorAll('#report-content button, #report-confirm button').forEach((button) => { button.disabled = value; });
		if (!value && report) renderTurns();
	}
	function render() {
		const complete = report.is_complete;
		const active = !['finished', 'cancelled'].includes(report.status);
		const states = { created: '尚未开始', finished: '已完成', cancelled: '已取消' };
		setText('state', (states[report.status] || '进行中') + (complete ? ' · 完整报告' : ' · 部分报告'));
		setText('meta', (report.position_display_name || report.position) + ' · ' + report.question_count + ' 题 / ' + report.answer_count + ' 轮回答');
		setText('time', report.ended_at ? '结束于 ' + new Date(report.ended_at).toLocaleString('zh-CN') : '本场尚未结束');
		setText('score', report.overall == null ? '—' : Number(report.overall).toFixed(1));
		find('dimensions').replaceChildren();
		Object.entries(report.dimensions || {}).forEach(([label, value]) => {
			const row = node('div', undefined, 'report-dimension');
			const meter = node('meter');
			meter.min = 0; meter.max = 10; meter.value = Number(value) || 0; meter.setAttribute('aria-label', label);
			row.append(node('span', label), node('strong', report.overall == null ? '—' : Number(value).toFixed(1)));
			if (report.overall != null) row.append(meter);
			find('dimensions').append(row);
		});
		setText('aggregation', report.aggregation || '');
		setHidden('source', !report.revision_source);
		if (report.revision_source) {
			setText('source-theme', report.revision_source.theme);
			const source = report.revision_source.interview_id;
			if (/^[a-f0-9]{32}$/.test(source)) find('source-link').href = '/report/' + source;
		}
		setHidden('partial', complete);
		setText('partial-title', active ? '当前已提交的回答' : '本场已取消');
		setText('partial-copy', active ? '继续面试后可回来刷新。' : '取消前的回答保留，不计入跨场对照。');
		setHidden('active-actions', !active);
		find('continue').href = '/interview/' + reportId;
		find('recommendations').replaceChildren(...(report.recommendations?.length ? report.recommendations : ['暂无建议，可逐轮查看依据。']).map((tip) => node('li', tip)));
		setHidden('practice', !complete || !report.practice_themes?.length);
		setHidden('practice-copy', find('practice').hidden);
		setText('practice-themes', report.practice_themes?.join('、') || '');
		setHidden('add-tasks', !complete || !report.weak_points?.length || !session());
		setHidden('task-help', !complete || !report.weak_points?.length || !!session());
		const selected = find('theme').value;
		find('theme').replaceChildren(node('option', '全部主题'));
		find('theme').firstChild.value = '';
		[...new Set((report.per_question || []).map((turn) => turn.theme))].forEach((theme) => {
			const option = node('option', theme); option.value = theme; find('theme').append(option);
		});
		find('theme').value = selected;
		if (find('theme').selectedIndex < 0) find('theme').value = '';
		updateReviewLink(); renderTurns();
	}
	function updateReviewLink() {
		const query = new URLSearchParams({ position: report.position });
		if (find('theme').value) query.set('theme', find('theme').value);
		find('review').href = '/review?' + query;
	}
	async function loadPlanSource(version) {
		setHidden('preparation', true);
		if (!session()) return;
		try {
			const { source } = await request('/account/preparation-plans/source/' + reportId, {}, true);
			if (version !== loadVersion || !source) return;
			setText('preparation-name', source.name + (source.status === 'archived' ? ' · 已归档' : ' · 准备中'));
			find('preparation-link').href = '/plans?plan_id=' + encodeURIComponent(source.id);
		} catch {
			if (version !== loadVersion) return;
			setText('preparation-name', '来源暂不可读，可刷新报告重试。');
			find('preparation-link').href = '/plans';
		}
		setHidden('preparation', false);
	}
	function renderTurns() {
		const turns = report.per_question || [];
		const threshold = report.weak_score ?? 7;
		const selected = find('theme').value;
		const visible = turns.filter((turn) => (!selected || turn.theme === selected) && (kind === 'all' || (kind === 'weak' ? turn.score < threshold : turn.probe_depth > 0)));
		page = Math.min(page, Math.max(0, Math.ceil(visible.length / pageSize) - 1));
		setText('filter-count', '匹配' + visible.length + ' / ' + turns.length + ' 轮；待补强低于 ' + threshold + ' 分。导出始终包含完整报告。');
		document.querySelectorAll('[data-kind]').forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.kind === kind)));
		find('turns').replaceChildren();
		visible.slice(page * pageSize, (page + 1) * pageSize).forEach((turn) => {
			const card = node('article', undefined, 'report-turn');
			const heading = node('div', undefined, 'report-turn-heading');
			heading.append(node('p', turn.theme + (turn.probe_depth > 0 ? ' · 追问 ' + turn.probe_depth + ' 层' : ' · 主问题'), 'eyebrow'), node('strong', Number(turn.score).toFixed(1) + ' / 10', 'report-turn-score'));
			card.append(heading, node('h3', turn.content));
			const answer = node('details', undefined, 'report-answer');
			answer.append(node('summary', '查看你的回答'), node('p', turn.answer_text || '本轮未记录回答文本。', 'report-answer-text'));
			card.append(answer, node('p', '评分依据：' + (turn.evidence || '未记录'), 'report-evidence'));
			if (turn.key_points_hit?.length) card.append(node('p', '已覆盖：' + turn.key_points_hit.join('、'), 'report-evidence'));
			if (turn.key_points_missed?.length) card.append(node('p', '待补强：' + turn.key_points_missed.join('、'), 'report-missed'));
			if (turn.sandbox) card.append(node('p', '客观判题：' + turn.sandbox.passed + ' / ' + turn.sandbox.total + ' 通过', 'note-context'));
			card.append(node('p', originText(turn.scoring_origin), 'note-context'));
			const source = node('details', undefined, 'report-answer');
			source.append(node('summary', '评分来源与版本'), node('p', versions(turn.scoring_origin), 'report-version'));
			card.append(source);
			find('turns').append(card);
		});
		setHidden('empty', visible.length > 0);
		setHidden('pagination', visible.length <= pageSize);
		setText('page', '第 ' + (page + 1) + ' / ' + Math.max(1, Math.ceil(visible.length / pageSize)) + ' 页');
		find('previous').disabled = busy || page === 0;
		find('next').disabled = busy || (page + 1) * pageSize >= visible.length;
	}
	async function load() {
		if (busy || loading) return;
		const version = ++loadVersion;
		loading = true;
		setHidden('content', true); setHidden('error-panel', true); setHidden('loading', false);
		try {
			if (!reportId) throw new Error('报告地址无效，请从记录重开。');
			const result = await request('/interview/' + reportId + '/report');
			if (version !== loadVersion) return;
			report = result; render(); setBusy(false); setHidden('content', false); loadPlanSource(version);
		} catch (error) {
			if (version !== loadVersion) return;
			setText('error', error.message); setHidden('error-panel', false);
		} finally { if (version === loadVersion) { loading = false; setHidden('loading', true); } }
	}
	find('theme').addEventListener('change', () => { page = 0; updateReviewLink(); renderTurns(); });
	find('filter-form').addEventListener('submit', (event) => event.preventDefault());
	document.querySelectorAll('[data-kind]').forEach((button) => button.addEventListener('click', () => { kind = button.dataset.kind; page = 0; renderTurns(); }));
	find('reset').addEventListener('click', () => { kind = 'all'; page = 0; find('theme').value = ''; updateReviewLink(); renderTurns(); });
	find('previous').addEventListener('click', () => { page--; renderTurns(); find('turns-title').scrollIntoView({ block: 'start' }); });
	find('next').addEventListener('click', () => { page++; renderTurns(); find('turns-title').scrollIntoView({ block: 'start' }); });
	find('refresh').addEventListener('click', load);
	find('retry').addEventListener('click', load);
	async function action(path, accountOnly, done) {
		if (busy || loading) return;
		setBusy(true); setText('action-error', ''); setText('action-message', '');
		try { await done(await request(path, { method: 'POST' }, accountOnly)); }
		catch (error) { setText('action-error', error.message); }
		finally { setBusy(false); }
	}
	find('add-tasks').addEventListener('click', () => action('/account/interviews/' + reportId + '/revision-tasks', true, (data) => {
		setText('action-message', '新增 ' + data.added + ' 项，已有 ' + data.existing + ' 项。已有完成状态保持。');
	}));
	find('practice').addEventListener('click', () => action('/interview/' + reportId + '/practice', false, (data) => {
		if (!/^[a-f0-9]{32}$/.test(data.interview_id)) throw new Error('请查记录核对结果。');
		if (data.account_owned && session()) { location.assign('/interview/' + data.interview_id); return; }
		if (!/^[a-f0-9]{64}$/.test(data.access_token || '')) throw new Error('匿名凭据缺失。');
		sessionStorage.setItem('interview:' + data.interview_id + ':token', data.access_token);
		location.assign('/interview/' + data.interview_id);
	}));
	document.querySelectorAll('[data-export]').forEach((button) => button.addEventListener('click', async () => {
		if (busy || loading) return;
		setBusy(true); setText('export-error', '');
		try {
			const format = button.dataset.export;
			const blob = await request('/interview/' + reportId + '/report/export?format=' + format, {}, false, true);
			const url = URL.createObjectURL(blob);
			const link = node('a'); link.href = url; link.download = 'interview-' + reportId + (format === 'json' ? '.json' : '.md');
			document.body.append(link);
			try { link.click(); } finally { link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
		} catch (error) { setText('export-error', error.message); }
		finally { setBusy(false); }
	}));
	const dialog = find('confirm');
	find('cancel').addEventListener('click', () => { if (!busy && !loading) { setText('confirm-error', ''); dialog.showModal(); } });
	find('confirm-back').addEventListener('click', () => { if (!busy) dialog.close(); });
	dialog.addEventListener('cancel', (event) => { if (busy) event.preventDefault(); });
	find('confirm-submit').addEventListener('click', async () => {
		if (busy || loading) return;
		setBusy(true);
		try { await request('/interview/' + reportId + '/cancel', { method: 'POST' }); dialog.close(); setBusy(false); await load(); }
		catch (error) { setText('confirm-error', error.message); }
		finally { setBusy(false); }
	});
	window.addEventListener('pageshow', (event) => { if (event.persisted) { dialog.close(); busy = false; loading = false; load(); } });
	load();
}());
