/* Generated: tools/build_ui.py */
/* 原生报告：逐轮分页不改变评分。 */
(function () {
	'use strict';
function notify(message, type = 'success', nextPage = false) {
	const detail = { message: String(message || '').slice(0, 240), type };
	if (!detail.message) return;
	if (nextPage) {
		try { sessionStorage.setItem('ui:notice', JSON.stringify({ ...detail, expires: Date.now() + 10000 })); } catch {}
	} else if (typeof CustomEvent === 'function') dispatchEvent(new CustomEvent('app:notice', { detail }));
}
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
function reportSharing(find, request, reportId) {
	let writing = false, generation = 0;
	const names = { summary: '评分摘要', answers: '含题目与回答' };
	function clear() {
		generation++;
		find('share-url').value = '';
		find('share-created').hidden = true;
		find('share-list').replaceChildren();
		find('share-message').textContent = '';
		find('share-error').textContent = '';
		find('sharing').hidden = true;
		find('sharing').open = false;
	}
	function lock(value) {
		writing = value;
		find('sharing').querySelectorAll('button, select, input').forEach(control => { control.disabled = value; });
	}
	async function refresh() {
		const version = ++generation;
		try {
			const data = await request('/account/interviews/' + reportId + '/shares', {}, true);
			if (version !== generation) return;
			find('share-list').replaceChildren();
			data.items.forEach(item => {
				const row = createNode('div', undefined, 'share-list-row');
				row.append(createNode('p', names[item.scope] + ' · ' + (item.active ? '有效至 ' + new Date(item.expires_at).toLocaleString('zh-CN') : item.revoked ? '已撤销' : '已到期')));
				if (item.active) {
					const revoke = createNode('button', '撤销链接', 'notes-button');
					revoke.type = 'button';
					revoke.addEventListener('click', async () => {
						if (writing) return;
						lock(true);
						try {
							await request('/account/report-shares/' + item.id + '/revoke', { method: 'POST' }, true);
							find('share-url').value = '';
							find('share-created').hidden = true;
							find('share-message').textContent = '链接已撤销。';
							await refresh();
						} catch (error) { find('share-error').textContent = error.message; }
						finally { lock(false); }
					});
					row.append(revoke);
				}
				find('share-list').append(row);
			});
		} catch (error) { if (version === generation) find('share-error').textContent = error.message; }
	}
	find('share-form').addEventListener('submit', async event => {
		event.preventDefault();
		if (writing) return;
		lock(true);
		find('share-error').textContent = '';
		find('share-created').hidden = true;
		find('share-url').value = '';
		try {
			const data = await request('/account/interviews/' + reportId + '/shares', {
				method: 'POST', body: JSON.stringify({ hours: Number(find('share-hours').value),
					scope: find('share-answers').checked ? 'answers' : 'summary' })
			}, true);
			if (!/^\/share#[a-f0-9]{64}$/.test(data.share_path)) throw new Error('链接生成结果无法读取，请刷新管理列表。');
			find('share-url').value = location.origin + data.share_path;
			find('share-created').hidden = false;
			find('share-message').textContent = '链接已生成，有效至 ' + new Date(data.expires_at).toLocaleString('zh-CN') + '。';
			await refresh();
		} catch (error) { find('share-error').textContent = error.message; }
		finally { lock(false); }
	});
	find('share-copy').addEventListener('click', async () => {
		const value = find('share-url').value;
		if (!value) return;
		try { await navigator.clipboard.writeText(value); find('share-message').textContent = '链接已复制。'; }
		catch { find('share-url').focus(); find('share-url').select(); find('share-message').textContent = '请手动复制选中的链接。'; }
	});
	addEventListener('pagehide', clear);
	addEventListener('account:changed', clear);
	return { refresh };
}
	function renderAssessment(report, find) {
		const assessment = report.assessment;
		find('assessment').hidden = !assessment;
		if (!assessment) return;
		find('assessment-summary').textContent = assessment.summary + (report.is_complete ? '' : ' 当前为已提交回答的阶段反馈。');
		const strengths = find('strengths'), priorities = find('priorities');
		strengths.replaceChildren(); priorities.replaceChildren();
		for (const item of assessment.strengths) strengths.append(createNode('li', item.theme + ' · ' + item.point));
		if (!assessment.strengths.length) strengths.append(createNode('li', report.answer_count ? '继续补充完整回答，积累可复盘的表现。' : '完成一轮回答后，在这里回看已覆盖的要点。'));
		for (const item of assessment.priorities) priorities.append(createNode('li', item.theme + ' · ' + item.action));
		if (!assessment.priorities.length) priorities.append(createNode('li', report.answer_count ? '尝试变化场景，检查自己能否解释边界和取舍。' : '开始回答后生成具体建议。'));
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
	const sharing = reportSharing(find, request, reportId);
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
				headers: { 'X-Interview-Token': access.token, ...(access.account ? { Authorization: 'Bearer ' + access.token } : {}),
					...(options.body ? { 'Content-Type': 'application/json' } : {}) } });
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
	function setBusy(value) {
		busy = value;
		document.querySelectorAll('#report-content button, #report-confirm button').forEach((button) => { button.disabled = value; });
		if (!value && report) renderTurns();
	}
	function render() {
		setHidden('sharing', !session() || !report.is_complete);
		if (!find('sharing').hidden) void sharing.refresh();
		renderComparison();
		renderAssessment(report, find);
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
		const rubric = report.dimensions?.['证据支撑'] != null
			? '五维评分按内容 35%、表达 20%、岗位 15%、证据 15%、应用 15% 加权。新增维度只汇总实际有分数的回答。'
			: '当前记录展示三项评分，逐题详情包含得分依据。';
		setText('aggregation', [report.aggregation, report.answer_count ? rubric : ''].filter(Boolean).join(' '));
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
	function renderComparison() {
		const comparison = report.retry_comparison;
		setHidden('comparison', !comparison);
		find('comparison-cards').replaceChildren();
		if (!comparison) return;
		for (const [label, result] of [['上次回答', comparison.original], ['本次回答', comparison.current]]) {
			const card = node('article', undefined, 'retry-answer');
			card.append(node('h3', label));
			if (result) {
				card.append(node('strong', Number(result.score).toFixed(1) + ' / 10', 'retry-score'));
				card.append(node('p', result.content));
				card.append(node('p', result.answer_text || '本轮未记录回答文本。', 'report-answer-text'));
				card.append(node('p', '已覆盖：' + (result.key_points_hit?.join('、') || '暂无'), 'report-evidence'));
				card.append(node('p', '待补强：' + (result.key_points_missed?.join('、') || '本轮未记录待补强要点'), 'report-missed'));
			} else {
				card.append(node('p', '完成本次主问题作答后，在这里对照两次表现。'));
			}
			find('comparison-cards').append(card);
		}
		if (/^[a-f0-9]{32}$/.test(comparison.source_interview_id)) find('comparison-source').href = '/report/' + comparison.source_interview_id;
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
			if (turn.dimensions) {
				const scores = Object.entries(turn.dimensions).map(([label, value]) => label + ' ' + Number(value).toFixed(1));
				if (scores.length) card.append(node('p', scores.join(' · '), 'report-evidence'));
			}
			if (turn.key_points_hit?.length) card.append(node('p', '已覆盖：' + turn.key_points_hit.join('、'), 'report-evidence'));
			if (turn.key_points_missed?.length) card.append(node('p', '待补强：' + turn.key_points_missed.join('、'), 'report-missed'));
			if (turn.sandbox) card.append(node('p', '客观判题：' + turn.sandbox.passed + ' / ' + turn.sandbox.total + ' 通过', 'note-context'));
			if (turn.can_retry && session()) {
				const retry = node('button', '重新回答这道题', 'notes-button');
				retry.type = 'button'; retry.disabled = busy;
				retry.addEventListener('click', () => action('/interview/' + reportId + '/question-practice', true, (data) => {
					if (!data.account_owned || !/^[a-f0-9]{32}$/.test(data.interview_id)) throw new Error('创建结果不完整，请先查看练习记录。');
					location.assign('/interview/' + data.interview_id);
				}, { question_id: turn.question_id }));
				card.append(retry, node('p', '从原题重新作答。已有未完成的同题复练时，将继续该场练习。', 'notes-boundary'));
			}
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
	async function action(path, accountOnly, done, body) {
		if (busy || loading) return;
		setBusy(true); setText('action-error', ''); setText('action-message', '');
		try { await done(await request(path, { method: 'POST', ...(body ? { body: JSON.stringify(body) } : {}) }, accountOnly)); }
		catch (error) { setText('action-error', error.message); notify(error.message, 'error'); }
		finally { setBusy(false); }
	}
	find('add-tasks').addEventListener('click', () => action('/account/interviews/' + reportId + '/revision-tasks', true, (data) => {
		setText('action-message', '新增 ' + data.added + ' 项，已有 ' + data.existing + ' 项。已有完成状态保持。');
		notify('复习任务已更新');
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
			notify('报告下载已开始');
		} catch (error) { setText('export-error', error.message); notify(error.message, 'error'); }
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
