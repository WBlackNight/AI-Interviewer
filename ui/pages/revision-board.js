/* 原生复习任务板：复用账户接口，日期、状态和练习分别提交。 */
(function () {
  'use strict';
/* @include session */
/* @include element */
/* @include fetch */
  const find = (selector) => document.querySelector(selector);
  const states = new Map();
  const dueNames = { all: '全部日期', today: '今日', overdue: '逾期', upcoming: '未来', unscheduled: '未安排' };
  let page = null;
  let busy = false;
  let leaving = false;
  const defaults = () => ({ status: 'todo', position: '', due: 'all', query: '', note_filter: 'all' });

  // 账户请求：只沿用当前标签页会话，错误不自动重试写入。
  async function request(path, options = {}) {
    let account;
    try { account = JSON.parse(sessionStorage.getItem('account:session')); } catch { /* 无会话时统一提示登录。 */ }
    if (!account || !/^[a-f0-9]{64}$/.test(account.access_token) || !(Date.parse(account.expires_at) > Date.now())) throw Object.assign(new Error('请先登录账户。'), { status: 401 });
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await guardedFetch('/api' + path, { ...options, cache: 'no-store', signal: controller.signal,
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + account.access_token } });
      const data = await response.json().catch(() => null);
      if (!response.ok) throw Object.assign(new Error(typeof data?.detail === 'string' ? data.detail : '请求失败，请重试。'), { status: response.status });
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('请求超时。日期输入已保留，请刷新确认操作结果。');
      if (error instanceof TypeError) throw new Error('连接失败，请检查本机服务后重试。');
      throw error;
    } finally { clearTimeout(timer); }
  }
  function showError(error) {
    find('#board-alert').textContent = error.message || '操作失败，请稍后重试。';
    if (error.status === 401) find('#board-login').hidden = false;
  }
  const element = (tag, className, text) => createNode(tag, text, className);

  // 日期草稿：筛选、翻页和跳转前保留选择权，保存一项也不静默丢弃其他项。
  function dirty(exceptId) {
    return Array.from(states.values()).some((state) => state.task.id !== exceptId && (state.date.value !== (state.task.due_date || '') || state.date.validity.badInput));
  }
  addEventListener('beforeunload', (event) => {
    if (!dirty() || leaving) return;
    event.preventDefault(); event.returnValue = '';
  });
  addEventListener('pageshow', () => { leaving = false; });
  async function allowChange(exceptId) {
    if (!dirty(exceptId)) return true;
    const dialog = find('#board-discard');
    if (dialog.open) return false;
    dialog.returnValue = 'cancel';
    return new Promise((resolve) => {
      dialog.addEventListener('close', () => resolve(dialog.returnValue === 'discard'), { once: true });
      dialog.showModal();
    });
  }
  function setBusy(value) {
    busy = value;
    document.querySelectorAll('#board-toolbar button, #board-toolbar input, #board-toolbar select').forEach((control) => { control.disabled = value; });
    states.forEach((state) => {
      state.date.disabled = value;
      state.buttons.forEach((button) => { button.disabled = value; });
      state.clear.disabled = value || !(state.date.value || state.task.due_date);
    });
    find('#board-previous').disabled = value || !page || page.offset === 0;
    find('#board-next').disabled = value || !page?.has_more;
  }
  function filters() {
    return page ? { status: page.status || 'all', position: page.position || '', due: page.due,
      query: page.query || '', note_filter: page.note_filter } : defaults();
  }
  function selected() {
    return { ...filters(), status: find('#board-status').value, position: find('#board-position').value,
      query: find('#board-query').value.trim(), note_filter: find('#board-note-filter').value };
  }

  // 列表读取：搜索与计数由服务端统一计算，末页消失时回到有效页。
  async function renderPage(selection, offset) {
    function path(nextOffset) {
      const query = new URLSearchParams({ offset: String(nextOffset), limit: '8', due: selection.due, note_filter: selection.note_filter });
      if (selection.status !== 'all') query.set('status', selection.status);
      if (selection.position) query.set('position', selection.position);
      if (selection.query) query.set('q', selection.query);
      return '/account/revision-tasks?' + query;
    }
    let result = await request(path(offset));
    if (!result.items.length && offset > 0 && result.total > 0) result = await request(path(Math.floor((result.total - 1) / result.limit) * result.limit));
    page = result;
    states.clear();
    find('#board-list').replaceChildren(...result.items.map(card));
    find('#board-empty').hidden = result.total > 0;
    find('#board-pagination').hidden = result.total === 0;
    find('#board-page').textContent = '第 ' + (Math.floor(result.offset / result.limit) + 1) + ' 页 · 共 ' + result.total + ' 项';
    find('#board-position').replaceChildren(new Option('全部岗位', ''), ...result.positions.map((item) => new Option(item.display_name, item.id)));
    find('#board-position').value = result.position || '';
    find('#board-status').value = result.status || 'all';
    find('#board-query').value = result.query || '';
    find('#board-note-filter').value = result.note_filter;
    find('#board-today').textContent = result.today + ' · 北京时间';
    find('#board-counts').textContent = '当前搜索、笔记与岗位范围：待复习 ' + result.counts.todo + ' 项 · 已复习 ' + result.counts.done + ' 项';
    document.querySelectorAll('[data-due]').forEach((button) => {
      const key = button.dataset.due;
      const count = key === 'all' ? Object.values(result.date_counts).reduce((sum, value) => sum + value, 0) : result.date_counts[key];
      button.textContent = dueNames[key] + ' · ' + count;
      button.setAttribute('aria-pressed', String(result.due === key));
    });
  }
  async function load(selection = filters(), offset = 0) {
    if (busy || !await allowChange() || busy) return;
    setBusy(true);
    find('#board-alert').textContent = '';
    find('#board-loading').hidden = false;
    try { await renderPage(selection, offset); }
    catch (error) { showError(error); }
    finally { find('#board-loading').hidden = true; setBusy(false); }
  }

  // 修改任务：只提交本次明确选择的字段，保存成功后重新计算日期视图与统计。
  async function update(state, changes) {
    const ownDate = Object.hasOwn(changes, 'due_date') ? state.task.id : undefined;
    if (busy || !await allowChange(ownDate) || busy) return;
    setBusy(true);
    find('#board-alert').textContent = '';
    try {
      state.task = await request('/account/revision-tasks/' + state.task.id, { method: 'PATCH', body: JSON.stringify(changes) });
      state.date.value = state.task.due_date || '';
      state.draft.textContent = '';
      state.caption.textContent = dateCaption(state.task);
      state.status.textContent = state.task.status === 'done' ? '已复习' : '待复习';
      state.toggle.textContent = state.task.status === 'done' ? '恢复待复习' : '标记已复习';
      find('#board-notice').textContent = '「' + state.task.theme + '」' + (ownDate ? state.task.due_date ? '已安排在 ' + state.task.due_date + ' 复习。' : '已清空复习日期。' : state.task.status === 'done' ? '已标记为已复习。' : '已恢复待复习。');
      await renderPage(filters(), page.offset);
    } catch (error) { showError(error); }
    finally { setBusy(false); }
  }

  // 专项练习：账户归属和主题由服务端确定，复用同一任务尚未结束的练习。
  async function practice(state) {
    if (busy || !await allowChange() || busy) return;
    setBusy(true);
    find('#board-alert').textContent = '';
    try {
      const result = await request('/account/revision-tasks/' + state.task.id + '/practice', { method: 'POST' });
      if (!/^[a-f0-9]{32}$/.test(result.interview_id) || result.account_owned !== true) throw new Error('练习信息不完整，请刷新任务后继续。');
      leaving = true;
      location.assign('/interview/' + result.interview_id);
    } catch (error) { leaving = false; showError(error); }
    finally { setBusy(false); }
  }
  function dateCaption(task) {
    if (!task.due_date) return '未安排复习日期';
    if (task.status === 'done') return '原定复习日 ' + task.due_date;
    return task.due_date + (task.due_date < page.today ? ' · 已逾期' : task.due_date === page.today ? ' · 今日复习' : ' · 计划中');
  }

  // 卡片渲染：所有用户文本使用textContent；日期输入保留规范日历格式。
  function card(task) {
    const article = element('article', 'note-card board-card');
    article.dataset.taskId = task.id;
    const heading = element('div', 'note-card-heading');
    const status = element('span', 'note-task-status', task.status === 'done' ? '已复习' : '待复习');
    heading.append(element('h2', '', task.theme), status);
    const position = page.positions.find((item) => item.id === task.position)?.display_name || task.position;
    const context = element('p', 'note-context', position + ' · 加入时主题分 ' + Number(task.source_score).toFixed(1) + ' / 10');
    const caption = element('p', 'board-date-caption', dateCaption(task));
    const focus = element('ul', 'board-focus');
    (task.focus_points || []).forEach((point) => focus.append(element('li', '', point)));
    const focusTitle = element('p', 'board-label', focus.childElementCount ? '上次没有讲清的' : '结合来源报告回看本主题的回答。');
    const form = element('form', 'board-schedule');
    const label = element('label', '', '安排复习日期');
    const date = element('input');
    date.type = 'date'; date.id = 'date-' + task.id; date.min = '2000-01-01'; date.max = '2100-12-31'; date.value = task.due_date || '';
    label.htmlFor = date.id;
    const save = element('button', 'notes-button', '保存日期'); save.type = 'submit';
    const clear = element('button', 'notes-button', '清空日期'); clear.type = 'button';
    form.append(label, date, save, clear);
    // 快捷日期：基于服务端北京时间，只填写草稿，仍需显式保存。
    const shortcuts = element('div', 'board-quick-dates');
    const quickButtons = [0, 1, 7].map((days, index) => {
      const button = element('button', 'notes-button', ['今天', '明天', '一周后'][index]);
      button.type = 'button';
      button.addEventListener('click', () => {
        const target = new Date(page.today + 'T00:00:00Z');
        target.setUTCDate(target.getUTCDate() + days);
        date.value = target.toISOString().slice(0, 10);
        date.dispatchEvent(new Event('input'));
      });
      return button;
    });
    shortcuts.append(...quickButtons);
    form.append(shortcuts);
    const dateDraft = element('p', 'board-date-draft');
    dateDraft.setAttribute('role', 'status');
    const preview = element('p', 'board-note-preview');
    const note = Array.from(task.note?.content || '');
    preview.textContent = note.length ? '个人笔记 · ' + note.slice(0, 100).join('') + (note.length > 100 ? '…' : '') : '还没有个人笔记，留下自己的解释与边界条件。';
    const actions = element('div', 'note-actions');
    const toggle = element('button', 'notes-button', task.status === 'done' ? '恢复待复习' : '标记已复习'); toggle.type = 'button';
    const start = element('button', 'notes-button notes-primary', ['created', 'running'].includes(task.latest_practice?.status) ? '继续本主题练习' : '练习本主题'); start.type = 'button';
    actions.append(start, toggle);
    const links = element('div', 'note-links');
    const report = element('a', '', '查看来源报告 ↗'); report.href = '/report/' + task.interview_id;
    const notes = element('a', '', '打开个人笔记 ↗'); notes.href = '/notes';
    links.append(notes, report);
    article.append(heading, context, caption, focusTitle, focus, form, dateDraft, preview, actions, links);
    const state = { task, date, clear, status, caption, toggle, draft: dateDraft, buttons: [save, clear, toggle, start, ...quickButtons] };
    states.set(task.id, state);
    date.addEventListener('input', () => {
      dateDraft.textContent = date.value !== (state.task.due_date || '') || date.validity.badInput ? '日期尚未保存。选择后请点击保存，或点击清空。' : '';
      clear.disabled = busy || !(date.value || state.task.due_date);
    });
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      if (!date.value) { dateDraft.textContent = '请先选择日期，或点击清空日期。'; return; }
      void update(state, { due_date: date.value });
    });
    clear.addEventListener('click', () => void update(state, { due_date: null }));
    toggle.addEventListener('click', () => void update(state, { status: state.task.status === 'done' ? 'todo' : 'done' }));
    start.addEventListener('click', () => void practice(state));
    return article;
  }

  // 初始化与导航：概览链接只携带状态/日期；搜索词和凭据不写入页面URL。
  find('#board-filters').addEventListener('submit', (event) => { event.preventDefault(); void load(selected()); });
  find('#board-reset').addEventListener('click', () => void load(defaults()));
  find('#board-refresh').addEventListener('click', () => void load(filters(), page?.offset || 0));
  find('#board-previous').addEventListener('click', () => void load(filters(), Math.max(0, page.offset - page.limit)));
  find('#board-next').addEventListener('click', () => void load(filters(), page.offset + page.limit));
  document.querySelectorAll('[data-due]').forEach((button) => button.addEventListener('click', () => void load({ ...filters(), due: button.dataset.due })));
  async function start() {
    try {
      const account = await request('/auth/me');
      find('#board-account').textContent = account.username + '的复习任务';
      find('#board-toolbar').hidden = false;
      const query = new URLSearchParams(location.search);
      const initial = defaults();
      if (Object.hasOwn(dueNames, query.get('due'))) initial.due = query.get('due');
      if (['todo', 'done', 'all'].includes(query.get('status'))) initial.status = query.get('status');
      await load(initial);
    } catch (error) { showError(error); }
  }
  void start();
})();
