/* 复习笔记：原生DOM、账户授权、显式保存与版本冲突处理。 */
(function () {
  'use strict';
/* @include session */
/* @include element */
/* @include fetch */
  const find = (selector) => document.querySelector(selector);
  const states = new Map();
  let page = null;
  let busy = false;
  let leavingForPractice = false;

  // 访问控制：沿用现有标签页账户会话，不读取匿名资源作为笔记权限。
  const session = readSession;

  async function request(path, options = {}) {
    const account = session();
    if (!account) throw Object.assign(new Error('请先登录账户。未保存内容仍在当前页，离开前请保存或复制。'), { status: 401 });
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await guardedFetch('/api' + path, { ...options, cache: 'no-store', signal: controller.signal,
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + account.access_token } });
      const data = await response.json().catch(() => null);
      if (!response.ok) throw Object.assign(new Error(typeof data?.detail === 'string' ? data.detail : '请求失败，请重试。'), { status: response.status });
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('请求超时。草稿保留，请读取最新版本确认是否保存成功。');
      throw error;
    } finally { clearTimeout(timer); }
  }

  // 草稿保护：离页时提醒，筛选和翻页时由用户决定是否丢弃未保存修改。
  function dirty() {
    return Array.from(states.values()).some((state) => state.input.value !== state.note.content);
  }
  addEventListener('beforeunload', (event) => {
    if (!dirty() || leavingForPractice) return;
    event.preventDefault();
    event.returnValue = '';
  });
  addEventListener('pageshow', () => { leavingForPractice = false; });
  async function allowChange() {
    if (!dirty()) return true;
    const dialog = find('#notes-discard');
    if (dialog.open) return false;
    dialog.returnValue = 'cancel';
    return new Promise((resolve) => {
      dialog.addEventListener('close', () => resolve(dialog.returnValue === 'discard'), { once: true });
      dialog.showModal();
    });
  }
  function setBusy(value) {
    busy = value;
    document.querySelectorAll('#notes-toolbar button, #notes-toolbar input, #notes-toolbar select, #notes-pagination button').forEach((control) => { control.disabled = value; });
    states.forEach(syncEditor);
    if (!value && page) {
      find('#notes-previous').disabled = page.offset === 0;
      find('#notes-next').disabled = !page.has_more;
    }
  }
  function showError(error) {
    find('#notes-alert').textContent = error.message || '操作失败，请稍后重试。';
    if (error.status === 401) find('#notes-login').hidden = false;
  }
  const element = (tag, className, text) => createNode(tag, text, className);

  // 编辑器：按Unicode字符计数，内容只用textContent或value展示，不解析HTML。
  function syncEditor(state) {
    const count = Array.from(state.input.value).length;
    const changed = state.input.value !== state.note.content;
    state.counter.textContent = count.toLocaleString() + ' / 2,000 字' + (changed ? ' · 未保存' : '');
    state.counter.classList.toggle('is-over-limit', count > 2000);
    state.save.disabled = busy || !changed || count > 2000;
    state.reset.disabled = busy || !changed;
    state.latest.disabled = busy;
    state.practice.disabled = busy;
  }
  function showSaved(state) {
    const characters = Array.from(state.note.content);
    state.preview.textContent = characters.length ? characters.slice(0, 150).join('') + (characters.length > 150 ? '…（展开编辑查看全文）' : '') : '还没有笔记。展开后写下自己的理解。';
    state.time.textContent = state.note.updated_at ? '上次保存：' + new Date(state.note.updated_at).toLocaleString('zh-CN') : '尚未保存笔记';
    syncEditor(state);
  }

  // 保存：携带读取时的版本；冲突时不重试覆盖，也不清除当前草稿。
  async function saveNote(state) {
    if (busy || Array.from(state.input.value).length > 2000) return;
    const content = state.input.value;
    setBusy(true);
    state.input.disabled = true;
    state.message.textContent = '正在保存…';
    try {
      state.note = await request('/account/revision-tasks/' + state.task.id + '/note', {
        method: 'PUT', body: JSON.stringify({ content, expected_version: state.note.version })
      });
      state.input.value = state.note.content;
      state.conflict.hidden = true;
      state.message.textContent = state.note.content ? '笔记已保存。' : '笔记已清空。';
      showSaved(state);
    } catch (error) {
      state.message.textContent = error.message || '保存失败，草稿保留，请重试。';
      if (error.status === 409) state.conflict.hidden = false;
      if (error.status === 401) showError(error);
    } finally {
      state.input.disabled = false;
      setBusy(false);
    }
  }

  // 合并：读取最新内容只更新保存基线，保留编辑框供用户比较和手动合并。
  async function readLatest(state) {
    if (busy) return;
    setBusy(true);
    state.message.textContent = '正在读取最新版本…';
    try {
      state.note = await request('/account/revision-tasks/' + state.task.id + '/note');
      state.serverText.textContent = state.note.content || '（最新笔记为空）';
      state.conflict.hidden = false;
      state.serverText.hidden = false;
      state.adopt.hidden = false;
      state.message.textContent = '已读取最新版本。草稿未改动，请比较后合并，再点击保存。';
      showSaved(state);
    } catch (error) {
      state.message.textContent = error.message || '读取失败，草稿保留。';
      if (error.status === 401) showError(error);
    } finally { setBusy(false); }
  }

  // 专项练习：沿用所属任务的主题和原岗位，已有未结束练习时由服务端复用。
  async function practiceTask(state) {
    if (busy || !await allowChange() || busy) return;
    setBusy(true);
    state.message.textContent = '正在准备本主题练习…';
    try {
      const result = await request('/account/revision-tasks/' + state.task.id + '/practice', { method: 'POST' });
      if (!/^[a-f0-9]{32}$/.test(result.interview_id) || result.account_owned !== true) throw new Error('练习返回信息不完整，请刷新任务后继续。');
      leavingForPractice = true;
      location.assign('/interview/' + result.interview_id);
    } catch (error) {
      leavingForPractice = false;
      state.message.textContent = error.message || '练习准备失败，请重试。';
      showError(error);
    } finally { setBusy(false); }
  }

  function card(task, positions) {
    const article = element('article', 'note-card');
    article.dataset.taskId = task.id;
    const heading = element('div', 'note-card-heading');
    const title = element('h2', '', task.theme);
    const status = element('span', 'note-task-status', task.status === 'done' ? '已复习' : '待复习');
    heading.append(title, status);
    const position = positions.find((item) => item.id === task.position)?.display_name || task.position;
    const context = element('p', 'note-context', position + ' · ' + (task.due_date ? '原定复习日 ' + task.due_date : '未安排复习日期'));
    const preview = element('p', 'note-preview');
    const time = element('p', 'note-time');
    const details = element('details', 'note-editor');
    const summary = element('summary', '', '编辑个人笔记');
    const form = element('form');
    const label = element('label', '', task.theme + '的个人复习笔记');
    const input = element('textarea');
    input.id = 'note-' + task.id;
    input.rows = 7;
    input.maxLength = 4000;
    input.placeholder = '概念解释、边界条件、下次练习时要补上的那句话……';
    label.htmlFor = input.id;
    const note = task.note || { content: '', version: 0, updated_at: null };
    input.value = note.content;
    const counter = element('p', 'note-counter');
    const actions = element('div', 'note-actions');
    const save = element('button', 'notes-button notes-primary', '保存笔记');
    save.type = 'submit';
    const reset = element('button', 'notes-button', '撤销草稿');
    reset.type = 'button';
    const latest = element('button', 'notes-button', '读取最新版本');
    latest.type = 'button';
    actions.append(save, reset, latest);
    const message = element('p', 'note-result');
    message.setAttribute('role', 'status');
    const conflict = element('section', 'note-conflict');
    conflict.hidden = true;
    const conflictHeading = element('h3', '', '服务端最新笔记');
    const serverText = element('pre', 'note-server-text');
    serverText.hidden = true;
    const adopt = element('button', 'notes-button', '用最新版本替换草稿');
    adopt.type = 'button';
    adopt.hidden = true;
    conflict.append(conflictHeading, serverText, adopt);
    form.append(label, input, counter, actions, message, conflict);
    details.append(summary, form);
    const links = element('div', 'note-links');
    const continuing = ['created', 'running'].includes(task.latest_practice?.status);
    const practice = element('button', 'notes-button', continuing ? '继续本主题练习' : '练习本主题');
    practice.type = 'button';
    const report = element('a', '', '查看来源报告 ↗');
    report.href = '/report/' + task.interview_id;
    const board = element('a', '', '日期与状态到任务板管理 ↗');
    board.href = '/revision';
    links.append(practice, report, board);
    article.append(heading, context, preview, time, details, links);
    const state = { task, note, input, counter, preview, time, save, reset, latest, practice, message, conflict, serverText, adopt };
    states.set(task.id, state);
    input.addEventListener('input', () => syncEditor(state));
    form.addEventListener('submit', (event) => { event.preventDefault(); void saveNote(state); });
    reset.addEventListener('click', () => { input.value = state.note.content; syncEditor(state); message.textContent = '草稿已恢复为当前读取的版本。'; });
    latest.addEventListener('click', () => void readLatest(state));
    practice.addEventListener('click', () => void practiceTask(state));
    adopt.addEventListener('click', () => { input.value = state.note.content; syncEditor(state); message.textContent = '已采用最新版本。'; conflict.hidden = true; });
    showSaved(state);
    return article;
  }

  // 列表：服务端筛选和分页，末页为空时回到有效页；读取失败保留现有卡片。
  async function load(offset = 0, applyFilters = false) {
    if (busy || !await allowChange() || busy) return;
    setBusy(true);
    find('#notes-alert').textContent = '';
    find('#notes-loading').hidden = false;
    const status = applyFilters ? find('#notes-status').value : page ? page.status || 'all' : 'todo';
    const position = applyFilters ? find('#notes-position').value : page?.position || '';
    const due = applyFilters ? find('#notes-date').value : page?.due || 'all';
    const search = applyFilters ? find('#notes-query').value.trim() : page?.query || '';
    const noteFilter = applyFilters ? find('#notes-note-filter').value : page?.note_filter || 'all';
    function path(nextOffset) {
      const query = new URLSearchParams({ offset: String(nextOffset), limit: '10', due });
      query.set('note_filter', noteFilter);
      if (search) query.set('q', search);
      if (status !== 'all') query.set('status', status);
      if (position) query.set('position', position);
      return '/account/revision-tasks?' + query;
    }
    try {
      let result = await request(path(offset));
      if (!result.items.length && offset > 0 && result.total > 0) result = await request(path(Math.floor((result.total - 1) / result.limit) * result.limit));
      page = result;
      states.clear();
      find('#notes-list').replaceChildren(...result.items.map((task) => card(task, result.positions)));
      find('#notes-empty').hidden = result.items.length > 0;
      find('#notes-pagination').hidden = result.total === 0;
      find('#notes-page').textContent = '第 ' + (Math.floor(result.offset / result.limit) + 1) + ' 页 · 共 ' + result.total + ' 项';
      const options = [new Option('全部岗位', ''), ...result.positions.map((item) => new Option(item.display_name, item.id))];
      find('#notes-position').replaceChildren(...options);
      find('#notes-position').value = result.position || '';
      find('#notes-status').value = result.status || 'all';
      find('#notes-date').value = result.due;
      find('#notes-query').value = result.query || '';
      find('#notes-note-filter').value = result.note_filter || 'all';
      find('#notes-today').textContent = result.today + ' · 北京时间';
    } catch (error) { showError(error); }
    finally { find('#notes-loading').hidden = true; setBusy(false); }
  }

  // 初始化：身份有效才读取任务，不在URL传递会话或笔记。
  find('#notes-filter-form').addEventListener('submit', (event) => { event.preventDefault(); void load(0, true); });
  find('#notes-refresh').addEventListener('click', () => void load(page?.offset || 0));
  find('#notes-previous').addEventListener('click', () => void load(Math.max(0, page.offset - page.limit)));
  find('#notes-next').addEventListener('click', () => void load(page.offset + page.limit));
  async function start() {
    try {
      const account = await request('/auth/me');
      find('#notes-account').textContent = account.username + '的复习笔记';
      find('#notes-toolbar').hidden = false;
      await load();
    } catch (error) { showError(error); }
  }
  void start();
})();
