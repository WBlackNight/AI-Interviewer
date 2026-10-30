/* Generated: tools/build_ui.py */
/* 练习概览：本账户只读汇总，跳转后继续使用原任务和面试接口。 */
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
	const find = (id) => document.querySelector('#dashboard-' + id);
	let loading = false;
	let version = 0;
	const session = readSession;
	const element = createNode;
	function link(label, path) { const node = element('a', label, 'link-arrow'); node.href = path; return node; }
	function reportPath(item, prefix) {
		return /^[a-f0-9]{32}$/.test(item.interview_id) ? '/' + prefix + '/' + item.interview_id : '/history';
	}
	function render(data) {
		find('today').textContent = data.today + ' · 北京时间 · 只展示本账户已保存记录。';
		find('finished').textContent = data.interviews.finished;
		find('due').textContent = data.tasks.today;
		find('overdue').textContent = data.tasks.overdue;
		find('notes').textContent = data.notes_with_content;
		find('week-total').textContent = data.week.reduce((sum, day) => sum + day.finished, 0) + ' 场';
		find('week').replaceChildren();
		data.week.forEach((day) => {
			const item = element('li');
			if (day.date === data.today) item.className = 'is-today';
			const date = element('time', day.date.slice(5).replace('-', '/')); date.dateTime = day.date;
			item.append(date, element('strong', day.finished), element('span', day.date === data.today ? '今天' : '已完成'));
			find('week').append(item);
		});
		find('note').textContent = data.note;
		find('active-total').textContent = '共 ' + (data.interviews.created + data.interviews.running) + ' 场未结束，优先显示进行中的最多3场。';
		find('active').replaceChildren();
		data.active.forEach((item) => {
			const row = element('article', undefined, 'dashboard-compact');
			row.append(element('h3', item.position_display_name || item.position), element('p', (item.status === 'running' ? '进行中' : '尚未开始') + ' · 已保存 ' + item.answer_count + ' 轮', 'note-context'), link(item.status === 'running' ? '继续练习 ↗' : '进入练习 ↗', reportPath(item, 'interview')));
			find('active').append(row);
		});
		find('active-empty').hidden = data.active.length > 0;
		find('priority-caption').textContent = '待复习 ' + data.tasks.todo + ' 项 · 已复习 ' + data.tasks.done + ' 项 · 未安排日期 ' + data.tasks.unscheduled + ' 项。下方按到期日期列出最多4项。';
		find('priority').replaceChildren();
		data.priority_tasks.forEach((task) => {
			const card = element('article', undefined, 'note-card');
			const due = task.due_date < data.today ? 'overdue' : 'today';
			const names = { java_backend: 'Java 后端', python_backend: 'Python 后端' };
			card.append(element('p', due === 'today' ? '今日复习' : '此前安排，尚未完成', 'eyebrow'), element('h3', task.theme),
				element('p', (names[task.position] || task.position) + ' · ' + task.due_date, 'note-context'),
				link('打开' + (due === 'today' ? '今日' : '逾期') + '任务 ↗', '/revision?status=todo&due=' + due), link('回看来源报告 ↗', reportPath(task, 'report')));
			find('priority').append(card);
		});
		find('priority-empty').hidden = data.priority_tasks.length > 0;
		find('recent').replaceChildren();
		data.recent.forEach((item) => {
			const card = element('article', undefined, 'note-card');
			card.append(element('p', 'FINISHED PRACTICE', 'eyebrow'), element('h3', item.position_display_name || item.position),
				element('p', item.theme_count + ' 个主题 · ' + item.answer_count + ' 轮回答', 'note-context'),
				element('p', item.ended_at ? new Date(item.ended_at).toLocaleString('zh-CN') : '完成时间未记录', 'note-time'), link('回看逐轮报告 ↗', reportPath(item, 'report')));
			find('recent').append(card);
		});
		find('recent-empty').hidden = data.recent.length > 0;
		renderPreparation(data.preparation, data.today);
	}
	function renderPreparation(plans, today) {
		const counts = plans.counts;
		find('plan-caption').textContent = '准备中 ' + counts.active + ' 份 · 已归档 ' + counts.archived + ' 份 · 已过目标日期 ' + counts.past_target + ' 份。按目标日期从早到晚展示最多3份，未设日期排在最后。';
		find('plans').replaceChildren();
		plans.items.forEach((plan) => {
			const card = element('article', undefined, 'note-card');
			const date = plan.target_date;
			card.append(element('p', date ? date < today ? '已过目标日期' : date === today ? '今天的目标' : '接下来的目标' : '按自己的节奏', 'eyebrow'), element('h3', plan.name),
				element('p', date ? '目标日期：' + date : '尚未设置目标日期', 'note-context'),
				link('打开这份计划 ↗', '/plans?plan_id=' + encodeURIComponent(plan.id)));
			find('plans').append(card);
		});
		find('plans-empty').hidden = plans.items.length > 0;
	}
	async function load() {
		if (loading) return;
		const requestVersion = ++version;
		const account = session();
		find('content').hidden = true; find('error-panel').hidden = true;
		find('login').hidden = !!account; find('loading').hidden = !account;
		find('account').textContent = account ? (account.account?.username || '当前账户') + '的练习概览' : '登录后查看个人安排';
		if (!account) return;
		loading = true; find('refresh').disabled = find('retry').disabled = true;
		const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 15000);
		try {
			const response = await guardedFetch('/api/account/dashboard', { cache: 'no-store', signal: controller.signal, headers: { Authorization: 'Bearer ' + account.access_token } });
			const result = await response.json();
			if (version !== requestVersion) return;
			if (session()?.access_token !== account.access_token) throw new Error('账户已变化，请刷新概览。');
			if (!response.ok) {
				if (response.status === 401) find('login').hidden = false;
				throw new Error(result.detail || '读取失败，请重试。');
			}
			render(result); find('content').hidden = false;
		} catch (error) {
			if (version !== requestVersion) return;
			find('error').textContent = error.name === 'AbortError' ? '读取超时，可重试。' : error instanceof TypeError ? '连接失败，请检查本机服务。' : error.message;
			find('error-panel').hidden = false;
		} finally {
			clearTimeout(timer);
			if (version === requestVersion) { loading = false; find('loading').hidden = true; find('refresh').disabled = find('retry').disabled = false; }
		}
	}
	find('refresh').addEventListener('click', load);
	find('retry').addEventListener('click', load);
	addEventListener('pageshow', (event) => { if (event.persisted) { version++; loading = false; load(); } });
	load();
}());
