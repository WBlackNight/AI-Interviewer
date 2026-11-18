/* 计划记录与主题复盘。 */
(function () {
  'use strict';
/* @include session */
/* @include element */
/* @include fetch */
  const find = (id) => document.querySelector('#plan-history-' + id);
  const review = (id) => find('review-' + id);
  const states = { created: '未开始', running: '进行中', finished: '已完成', cancelled: '已取消' };
  const levels = { easy: '轻松', mid: '标准', hard: '挑战' };
  const roles = { java_backend: 'Java 后端', python_backend: 'Python 后端' };
  const query = new URLSearchParams(location.search);
  const planId = query.get('plan_id') || '';
  let status = query.get('status') || '';
  let page = Number(query.get('page') || '1');
  let busy = false, version = 0, controller = null;
  let data = null;
  let reviewData = null, reviewTheme = '', reviewOffset = 0, reviewVersion = 0;
  let reviewBusy = false, reviewWriting = false, reviewController = null;
  const clock = new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', dateStyle: 'medium', timeStyle: 'short' });

  // 身份：失效与旧响应保护。
  const session = readSession;
  const node = createNode;
  function link(label, path, className = 'link-arrow') { const element = node('a', label, className); element.href = path; return element; }
  function text(id, value) { find(id).textContent = value; }
  function hide(id, value) { find(id).hidden = value; }
  function lock() {
    document.querySelectorAll('#plan-history-filters :is(button,select), #plan-history-retry').forEach((element) => { element.disabled = busy || reviewWriting; });
    find('previous').disabled = busy || reviewWriting || page <= 1;
    find('next').disabled = busy || reviewWriting || !data?.has_more;
  }
  function clearPrivate() {
    hide('content', true); find('list').replaceChildren(); data = null; resetReview();
    ['name', 'range', 'target', 'state', 'count'].forEach((id) => text(id, ''));
  }
  function validAddress() {
    return /^[a-f0-9]{32}$/.test(planId) && (!status || Object.hasOwn(states, status)) && Number.isInteger(page) && page >= 1 && page <= 125001 && /^\d{1,6}$/.test(query.get('page') || '1');
  }

  // 记录：北京时间。
  function timestamp(list, label, value) {
    if (!value || !Number.isFinite(Date.parse(value))) return;
    const term = node('dt', label), description = node('dd'), time = node('time', clock.format(new Date(value)));
    time.dateTime = value; description.append(time); list.append(term, description);
  }
  function render() {
    const plan = data.plan;
    text('name', plan.name);
    text('state', plan.status === 'archived' ? '已归档 · 可回看练习' : '准备中');
    text('range', (roles[plan.position] || plan.position) + ' · ' + plan.themes.join(' / ') + ' · ' + levels[plan.difficulty]);
    text('target', plan.target_date ? '目标日期：' + plan.target_date : '未设目标日期');
    find('plan').href = '/plans?plan_id=' + planId;
    Object.keys(states).forEach((key) => text(key, data.status_counts[key]));
    find('status').value = status;
    const total = Object.values(data.status_counts).reduce((sum, count) => sum + count, 0);
    text('count', '保留 ' + total + ' 场 · 当前范围 ' + data.total + ' 场。关联顺序从新到旧，每页8条。');
    find('list').replaceChildren();
    data.items.forEach((item) => {
      const card = node('article', undefined, 'note-card history-card');
      const actions = node('div', undefined, 'note-actions'), add = node('button', '加入本场复习任务', 'notes-button'); add.type = 'button';
      add.addEventListener('click', () => addTasks(item.interview_id));
      actions.append(link('评分依据与版本 ↗', '/report/' + item.interview_id), add); card.append(actions); review('list').append(card);
    });
    hide('review-empty', reviewData.items.length > 0); hide('review-pages', reviewData.total <= 4);
    text('review-page', '第 ' + (reviewOffset / 4 + 1) + ' / ' + Math.max(1, Math.ceil(reviewData.total / 4)) + ' 页');
  }
  async function loadReview() {
    if (busy || reviewBusy || reviewWriting || find('content').hidden) return;
    const requestVersion = ++reviewVersion;
    reviewBusy = true; lockReview(); text('review-error', ''); hide('review-retry', true);
    review('list').replaceChildren(); hide('review-pages', true); hide('review-empty', true); text('review-count', '正在读取复盘…');
    try {
      const params = new URLSearchParams({ limit: '4', offset: String(reviewOffset) }); if (reviewTheme) params.set('theme', reviewTheme);
      const result = await reviewRequest('/account/preparation-plans/' + planId + '/review?' + params);
      if (requestVersion !== reviewVersion) return;
      if (!result.items.length && reviewOffset) { reviewOffset = Math.max(0, Math.ceil(result.total / 4) - 1) * 4; reviewBusy = false; await loadReview(); return; }
      reviewData = result; renderReview();
    } catch (error) {
      if (requestVersion === reviewVersion) { text('review-count', ''); text('review-error', error.message); hide('review-retry', false); }
    } finally { if (requestVersion === reviewVersion) { reviewBusy = false; lockReview(); } }
  }
  // 任务：原规则，保留状态。
  async function addTasks(interviewId) {
    if (busy || reviewBusy || reviewWriting) return;
    const requestVersion = reviewVersion;
    reviewWriting = true; lockReview(); text('review-error', ''); text('review-message', '');
    try {
      const result = await reviewRequest('/account/interviews/' + interviewId + '/revision-tasks', 'POST');
      if (!result || requestVersion !== reviewVersion) return;
      text('review-message', '新增 ' + result.added + ' 项，已有 ' + result.existing + ' 项。');
    } catch (error) { text('review-error', error.message); }
    finally { if (requestVersion === reviewVersion) { reviewWriting = false; lockReview(); } }
  }
  find('review').addEventListener('toggle', () => { if (find('review').open && !reviewData) loadReview(); });
  review('form').addEventListener('submit', (event) => { event.preventDefault(); if (!reviewBusy && !reviewWriting) { reviewTheme = review('theme').value; reviewOffset = 0; loadReview(); } });
  review('refresh').addEventListener('click', loadReview); review('retry').addEventListener('click', loadReview);
  review('previous').addEventListener('click', () => { reviewOffset = Math.max(0, reviewOffset - 4); loadReview(); });
  review('next').addEventListener('click', () => { reviewOffset += 4; loadReview(); });
  addEventListener('beforeunload', (event) => { if (reviewWriting) { event.preventDefault(); event.returnValue = ''; } });

  // 筛选：回第一页；翻页定位记录。
  find('filters').addEventListener('submit', (event) => { event.preventDefault(); if (!busy) { status = find('status').value; page = 1; load(); } });
  find('clear').addEventListener('click', () => { if (!busy) { status = ''; page = 1; load(); } });
  find('refresh').addEventListener('click', load); find('retry').addEventListener('click', load);
  async function turnPage(change) {
    if (busy) return;
    page += change; await load();
    if (!find('content').hidden) find('filters').scrollIntoView({ block: 'start' });
  }
  find('previous').addEventListener('click', () => turnPage(-1));
  find('next').addEventListener('click', () => turnPage(1));
  addEventListener('pagehide', () => { version++; controller?.abort(); resetReview(); });
  addEventListener('pageshow', (event) => { if (event.persisted) { busy = false; load(); } });
  load();
}());
