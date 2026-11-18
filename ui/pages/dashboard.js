/* 练习概览：本账户只读汇总，跳转后继续使用原任务和面试接口。 */
(function () {
  'use strict';
/* @include session */
/* @include element */
/* @include http */
  const find = (id) => document.querySelector('#dashboard-' + id);
  let loading = false;
  let version = 0;
  const session = readSession;
  const element = createNode;
  function link(label, path) { const node = element('a', label, 'link-arrow'); node.href = path; return node; }
  function reportPath(item, prefix) {
    return /^[a-f0-9]{32}$/.test(item.interview_id) ? '/' + prefix + '/' + item.interview_id : '/history';
  }

  function nextStep(data) {
    const active = data.active.find(item => /^[a-f0-9]{32}$/.test(item.interview_id));
    if (active) {
      return { title: '接着上一次，继续练习', description: (active.position_display_name || '这场练习') + '已保存 ' + active.answer_count + ' 轮回答，可从当前题继续。',
        label: '继续练习', path: reportPath(active, 'interview') };
    }
    if (data.tasks.overdue || data.tasks.today) {
      return { title: '先回看一个到期的知识点', description: '你有 ' + data.tasks.today + ' 项今日复习和 ' + data.tasks.overdue + ' 项此前待完成的复习。可以先挑一项回看。',
        label: '查看到期任务', path: '/revision?status=todo&due=' + (data.tasks.overdue ? 'overdue' : 'today') };
    }
    if (data.preparation.items.length) {
      return { title: '从准备计划，开始今天的练习', description: data.preparation.items[0].name,
        label: '查看准备计划', path: '/plans' };
    }
    if (data.recent.length) {
      return { title: '回看一次回答，再练一个弱项', description: '从最近一份报告中找出待补强要点，安排一次主题练习。',
        label: '查看最近报告', path: reportPath(data.recent[0], 'report') };
    }
    return { title: '用五分钟，完成第一次练习', description: '先选择熟悉的岗位，回答两道主问题，看看自己的思路是否讲清楚。',
      label: '配置短练习', path: '/?duration=5#start' };
  }

  // 数字与日历：零值来自服务端，七日场数按北京时间完成日期统计。
  function render(data) {
    const action = nextStep(data);
    find('next-title').textContent = action.title;
    find('next-description').textContent = action.description;
    find('next-link').textContent = action.label;
    find('next-link').href = action.path;
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
      const names = { java_backend: 'Java 后端', python_backend: 'Python 后端', marketing: '市场营销',
        operations: '运营管理', education: '教育教学', english_interview: '英语面试' };
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
    renderFocus(data.practice_focus);
  }

  function renderFocus(focus) {
    find('focus-list').replaceChildren();
    find('focus-empty').hidden = !!focus;
    find('focus-note').textContent = focus ? focus.position_display_name + ' · ' + focus.sample_count +
      ' 道主问题。' + (focus.local_feedback ? '含本地规则或旧版反馈，仅作练习参考。' : '评分仅供练习参考。') + focus.note : '';
    if (!focus) return;
    focus.themes.forEach(theme => {
      const card = element('article', undefined, 'focus-card');
      card.append(element('p', theme.priority ? '优先补强' : '继续巩固', 'eyebrow'),
        element('h3', theme.name), element('strong', theme.score.toFixed(1) + ' / 10', 'focus-score'),
        element('p', '来自本场 ' + theme.question_count + ' 道主问题', 'notes-boundary'));
      const actions = element('div', undefined, 'note-actions');
      actions.append(link('查看评分依据', '/report/' + focus.interview_id));
      if (theme.can_practice) {
        const start = element('a', '按主题再练', 'notes-button notes-primary');
        start.href = '/?' + new URLSearchParams({ position: focus.position, mode: 'topic', theme: theme.name, duration: '5' }) + '#start';
        actions.append(start);
      }
      card.append(actions); find('focus-list').append(card);
    });
  }

  // 主动准备：只显示三个最近目标，数量和目标日期不推断能力。
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
      if (plan.target_sessions) {
        card.append(element('p', '阶段进度 ' + plan.finished_count + ' / ' + plan.target_sessions + ' 场' + (plan.finished_count >= plan.target_sessions ? ' · 已达成' : ''), 'plan-goal-label'));
      }
      find('plans').append(card);
    });
    find('plans-empty').hidden = plans.items.length > 0;
  }

  // 读取恢复：切换账户或离页回来后重读；失败不沿用旧账户的数据。
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
      const result = await requestJSON('/api/account/dashboard', { auth: true, signal: controller.signal });
      if (version !== requestVersion) return;
      if (session()?.access_token !== account.access_token) throw new Error('账户已变化，请刷新概览。');
      render(result); find('content').hidden = false;
    } catch (error) {
      if (version !== requestVersion) return;
      if (error.status === 401) find('login').hidden = false;
      find('error').textContent = error.name === 'AbortError' ? '读取超时，可重试。' : error instanceof TypeError ? '连接失败，请检查网络后重试。' : error.message;
      find('error-panel').hidden = false;
    } finally {
      clearTimeout(timer);
      if (version === requestVersion) { loading = false; find('loading').hidden = true; find('refresh').disabled = find('retry').disabled = false; }
    }
  }
  find('refresh').addEventListener('click', load);
  find('retry').addEventListener('click', load);
  addEventListener('pageshow', (event) => { if (event.persisted) { version++; loading = false; load(); } });
  addEventListener('account:changed', () => { version++; loading = false; load(); });
  load();
}());
