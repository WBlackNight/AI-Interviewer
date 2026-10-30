/* 题库探索：预览题干，按主题创建专项，不把预览题目ID提交给面试接口。 */
(function () {
  'use strict';
/* @include session */
/* @include element */
/* @include fetch */
  const find = (id) => document.querySelector('#catalog-' + id);
  const chosen = new Set();
  const names = { easy: '基础', mid: '进阶', hard: '挑战' };
  let filters = address();
  let data = null, reading = false, creating = false, reader = null;
  let requestVersion = 0, creationResult = null, creationIdentity = '';

  // 筛选地址：只读公开筛选字段，不读取或写入访问凭据。
  function address() {
    const query = new URLSearchParams(location.search);
    const short = (name, limit) => { const value = query.get(name) || ''; return Array.from(value).length <= limit ? value : ''; };
    const page = Number(query.get('page') || 1);
    return { position: short('position', 64), theme: short('theme', 64), query: short('q', 100),
      difficulty: ['easy', 'mid', 'hard'].includes(query.get('difficulty')) ? query.get('difficulty') : '',
      kind: ['knowledge', 'coding'].includes(query.get('kind')) ? query.get('kind') : 'all',
      offset: Number.isInteger(page) && page > 0 && page <= 166667 ? (page - 1) * 6 : 0 };
  }
  function saveAddress() {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries({ position: filters.position, theme: filters.theme, difficulty: filters.difficulty, q: filters.query })) if (value) query.set(key, value);
    if (filters.kind !== 'all') query.set('kind', filters.kind);
    if (filters.offset) query.set('page', String(filters.offset / 6 + 1));
    history.replaceState(null, '', '/catalog' + (query.size ? '?' + query : ''));
  }
  const account = readSession;
  const element = createNode;
  function role() { return data?.positions.find((item) => item.id === data.position); }
  function options(select, values, selected, placeholder) {
    select.replaceChildren();
    if (placeholder) { const option = element('option', placeholder); option.value = ''; select.append(option); }
    values.forEach(([value, label]) => { const option = element('option', label); option.value = value; select.append(option); });
    if (selected && !values.some(([value]) => value === selected)) { const option = element('option', selected + '（当前范围）'); option.value = selected; select.append(option); }
    select.value = selected;
  }

  // 主题篮：同岗位跨页保留，数量上限来自服务端，编程题不加入知识专项。
  function updateSelection() {
    const limit = role()?.practice_theme_limit || 0;
    const locked = reading || creating || !!creationResult;
    document.querySelectorAll('#catalog-themes input').forEach((input) => {
      input.checked = chosen.has(input.value);
      input.disabled = locked || (!input.checked && chosen.size >= limit);
    });
    document.querySelectorAll('[data-add-theme]').forEach((button) => {
      const selected = chosen.has(button.dataset.addTheme);
      button.textContent = selected ? '已选主题 · 移除' : '加入这个主题';
      button.setAttribute('aria-pressed', String(selected));
      button.disabled = locked || (!selected && chosen.size >= limit);
    });
    find('selected').textContent = chosen.size ? '已选 ' + chosen.size + ' / ' + limit + '：' + Array.from(chosen).join('、') : '还没有选择主题。';
    const current = account();
    find('identity').textContent = current ? '将保存到 ' + (current.account.username || '当前账户') + '的练习记录。' : '将创建匿名练习，访问凭据只保留在当前标签页。';
    find('create').disabled = reading || creating || (!creationResult && (!chosen.size || chosen.size > limit));
    find('create').textContent = creating ? '正在准备练习…' : creationResult ? '继续这场已创建练习' : '开始主题专项';
  }
  function lock() {
    document.querySelectorAll('#catalog-main button, #catalog-main input, #catalog-main select').forEach((control) => { control.disabled = reading || creating || !!creationResult; });
    updateSelection();
    find('previous').disabled = reading || creating || !!creationResult || !data?.offset;
    find('next').disabled = reading || creating || !!creationResult || !data?.has_more;
  }
  function selectTheme(theme) {
    if (reading || creating || creationResult) return;
    if (chosen.has(theme)) chosen.delete(theme);
    else if (role()?.themes.some((item) => item.name === theme && item.can_practice) && chosen.size < role().practice_theme_limit) chosen.add(theme);
    updateSelection();
  }

  // 预览卡片：内容与来源均用textContent，不输出锚点、答案或判题用例。
  function render() {
    filters.position = data.position || ''; filters.offset = data.offset;
    saveAddress();
    options(find('position'), data.positions.map((item) => [item.id, item.display_name]), data.position || '', data.positions.length ? null : '暂无可用岗位');
    options(find('theme'), (role()?.themes || []).map((item) => [item.name, item.name + ' · ' + item.question_count + '题']), filters.theme, '全部主题');
    find('level').value = filters.difficulty; find('query').value = filters.query;
    find('scope').textContent = (role()?.display_name || '题库') + ' · 岗位 ' + (role()?.total || 0) + ' 题，匹配 ' + data.total + ' 题。';
    const labels = { all: '全部题目', knowledge: '知识题', coding: '编程题' };
    document.querySelectorAll('[data-kind]').forEach((button) => {
      button.textContent = labels[button.dataset.kind] + ' · ' + data.counts[button.dataset.kind];
      button.setAttribute('aria-pressed', String(filters.kind === button.dataset.kind));
    });
    const allowed = new Set((role()?.themes || []).filter((item) => item.can_practice).map((item) => item.name));
    for (const theme of chosen) if (!allowed.has(theme)) { chosen.delete(theme); find('notice').textContent = '可练范围已更新，已移除失效主题。'; }
    find('role').textContent = (role()?.display_name || '当前岗位') + ' · 最多选择 ' + (role()?.practice_theme_limit || 0) + ' 个主题。';
    find('plan-note').textContent = data.note;
    find('themes').replaceChildren();
    (role()?.themes || []).filter((item) => item.can_practice).forEach((item, index) => {
      const label = element('label', undefined, 'catalog-topic');
      const input = element('input'); input.type = 'checkbox'; input.value = item.name; input.id = 'catalog-topic-' + index;
      const labelText = element('span', item.name + ' · ' + item.knowledge_count + '知识题');
      if (item.topics.length) labelText.append(element('small', item.topics.join(' / ')));
      label.htmlFor = input.id; label.append(input, labelText);
      input.addEventListener('change', () => selectTheme(item.name)); find('themes').append(label);
    });
    find('list').replaceChildren();
    data.items.forEach((item) => {
      const card = element('article', undefined, 'note-card catalog-card');
      card.append(element('p', item.theme + ' · ' + (item.is_coding ? '编程题' : '知识题') + ' · ' + (names[item.difficulty] || item.difficulty), 'eyebrow'), element('h3', item.content));
      const detail = element('details', undefined, 'report-answer');
      detail.append(element('summary', '题目编号与来源'), element('p', item.id + '\n来源：' + (item.source || '未标注'), 'report-version'));
      card.append(detail);
      if (item.can_practice) {
        const button = element('button', '加入这个主题', 'notes-button'); button.type = 'button'; button.dataset.addTheme = item.theme;
        button.addEventListener('click', () => selectTheme(item.theme)); card.append(button);
      } else card.append(element('p', item.is_coding ? '编程环节由综合面试大纲与服务配置决定，不加入本页知识专项。' : '本主题当前不可创建知识专项。', 'notes-boundary'));
      const link = element('a', '查看或收藏这题 ↗', 'link-arrow');
      link.href = '/library?' + new URLSearchParams({ position: item.position, question: item.id }) + '#library-discover'; card.append(link);
      find('list').append(card);
    });
    find('empty').hidden = data.items.length > 0;
    find('pagination').hidden = data.total <= data.limit;
    find('page').textContent = '第 ' + (Math.floor(data.offset / data.limit) + 1) + ' / ' + Math.max(1, Math.ceil(data.total / data.limit)) + ' 页';
    updateSelection();
  }

  // 列表恢复：过期读请求丢弃，错误重试保留筛选，末页失效回到有效页。
  async function load() {
    if (reading || creating || creationResult) return;
    reading = true; const version = ++requestVersion; lock();
    find('error').textContent = ''; find('loading').hidden = false; find('content').hidden = true;
    const controller = new AbortController(); reader = controller; const timer = setTimeout(() => controller.abort(), 15000);
    try {
      if (Array.from(filters.query).length > 100) throw new Error('关键词最多100个字符。');
      const query = new URLSearchParams({ offset: String(filters.offset), limit: '6', kind: filters.kind });
      for (const [key, value] of Object.entries({ position: filters.position, theme: filters.theme, difficulty: filters.difficulty, q: filters.query })) if (value) query.set(key, value);
      const response = await guardedFetch('/api/catalog?' + query, { cache: 'no-store', signal: controller.signal });
      const result = await response.json();
      if (version !== requestVersion) return;
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : '读取失败，请调整条件重试。');
      if (!result.items.length && filters.offset && result.total) {
        filters.offset = Math.floor((result.total - 1) / 6) * 6; reading = false; return load();
      }
      if (!result.total) result.offset = 0;
      data = result; render(); find('content').hidden = false;
    } catch (error) {
      if (version !== requestVersion) return;
      find('error').textContent = error.name === 'AbortError' ? '读取超时，请刷新题库重试。' : error instanceof TypeError ? '连接失败，请检查本机服务。' : error.message;
    } finally { clearTimeout(timer); if (version === requestVersion) { reading = false; find('loading').hidden = true; lock(); } }
  }
  function apply(kind = filters.kind) {
    filters = { position: find('position').value, theme: find('theme').value, difficulty: find('level').value, query: find('query').value.trim(), kind, offset: 0 }; load();
  }
  find('filters').addEventListener('submit', (event) => { event.preventDefault(); apply(); });
  find('position').addEventListener('change', () => {
    chosen.clear(); filters = { ...filters, position: find('position').value, theme: '', offset: 0 };
    find('notice').textContent = '已切换岗位，主题选择已清空。'; load();
  });
  document.querySelectorAll('[data-kind]').forEach((button) => button.addEventListener('click', () => apply(button.dataset.kind)));
  find('reset').addEventListener('click', () => { filters = { position: data?.position || '', theme: '', difficulty: '', query: '', kind: 'all', offset: 0 }; load(); });
  find('refresh').addEventListener('click', load);
  find('previous').addEventListener('click', () => { filters.offset = Math.max(0, filters.offset - 6); load(); });
  find('next').addEventListener('click', () => { if (data?.has_more) { filters.offset += 6; load(); } });

  // 创建专项：存储预检、账户归属校验和单次提交；保存失败可继续同一创建结果。
  function enterCreated() {
    if ((account()?.account.id || '') !== creationIdentity) throw new Error('账户已变化，请先到原账户的练习记录确认创建结果。');
    if (creationResult.account_owned) {
      if (!creationIdentity) throw new Error('账户会话已失效，请重新登录。');
    } else {
      if (!/^[a-f0-9]{64}$/.test(creationResult.access_token || '')) throw new Error('匿名访问凭据不完整，请检查服务响应。');
      sessionStorage.setItem('interview:' + creationResult.interview_id + ':token', creationResult.access_token);
    }
    creating = false;
    location.assign('/interview/' + creationResult.interview_id);
  }
  find('create').addEventListener('click', async () => {
    if (reading || creating || (!creationResult && (!role() || !chosen.size || chosen.size > role().practice_theme_limit))) return;
    creating = true; lock(); find('create-error').textContent = '';
    const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 30000);
    try {
      if (!creationResult) {
        sessionStorage.setItem('catalog-storage-check', '1'); sessionStorage.removeItem('catalog-storage-check');
        const current = account(); creationIdentity = current?.account.id || '';
        const response = await guardedFetch('/api/interview', { method: 'POST', cache: 'no-store', signal: controller.signal,
          headers: { 'Content-Type': 'application/json', ...(current ? { Authorization: 'Bearer ' + current.access_token } : {}) },
          body: JSON.stringify({ position: data.position, difficulty: find('intensity').value, themes: Array.from(chosen) }) });
        const result = await response.json();
        if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : '创建失败，请检查所选主题。');
        if (!/^[a-f0-9]{32}$/.test(result.interview_id)) throw new Error('结果不完整，先查练习记录。');
        if (!!current !== !!result.account_owned) throw new Error('创建结果的归属不一致，请先检查已有练习。');
        creationResult = result;
      }
      enterCreated();
    } catch (error) {
      find('create-error').textContent = error.name === 'AbortError' ? '请求超时，可能已创建。请先查看练习记录确认，不会自动重复提交。' : error instanceof TypeError ? '连接中断，请先查看练习记录确认创建结果。' : error.message;
    } finally { clearTimeout(timer); creating = false; lock(); }
  });
  addEventListener('beforeunload', (event) => { if (creating) { event.preventDefault(); event.returnValue = ''; } });
  addEventListener('popstate', () => {
    if (creating || creationResult) return;
    reader?.abort(); requestVersion++; reading = false;
    const next = address(); if (next.position !== filters.position) chosen.clear(); filters = next; load();
  });
  load();
}());
