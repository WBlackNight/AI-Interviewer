/* 原生跨场复盘：只读账户内已完成记录，不推断能力增减。 */
(function () {
  'use strict';
/* @include session */
/* @include element */
/* @include fetch */
  const find = (selector) => document.querySelector(selector);
  const pageSize = 4;
  let data = null;
  let loading = false;
  let requestVersion = 0;
  let filters = readAddress();

  // 地址只保留岗位、主题与页码；拒绝超长参数，不接受访问凭据。
  function readAddress() {
    const query = new URLSearchParams(location.search);
    const position = query.get('position') || '';
    const theme = query.get('theme') || '';
    const page = Number(query.get('page') || 1);
    return { position: position.length <= 64 ? position : '', theme: theme.length <= 64 ? theme : '',
      offset: Number.isInteger(page) && page > 0 && page <= 250001 ? (page - 1) * pageSize : 0 };
  }
  function saveAddress() {
    const query = new URLSearchParams();
    if (filters.position) query.set('position', filters.position);
    if (filters.theme) query.set('theme', filters.theme);
    if (filters.offset) query.set('page', String(filters.offset / pageSize + 1));
    history.replaceState(null, '', '/review' + (query.size ? '?' + query : ''));
  }
  const session = readSession;
  const node = createNode;
  function setLoading(value) {
    loading = value;
    find('#review-loading').hidden = !value;
    document.querySelectorAll('#review-filters button, #review-filters select, #review-retry, #review-pagination button').forEach((element) => { element.disabled = value; });
    if (!value && data) {
      find('#review-previous').disabled = data.offset === 0;
      find('#review-next').disabled = !data.has_more;
    }
  }

  // 筛选恢复：未知主题保留为可见选项，空结果不悄悄扩大读取范围。
  function populateSelect(select, values, selected, placeholder) {
    select.replaceChildren();
    if (placeholder) { const option = node('option', placeholder); option.value = ''; select.append(option); }
    values.forEach(([value, label]) => { const option = node('option', label); option.value = value; select.append(option); });
    if (selected && !values.some(([value]) => value === selected)) {
      const option = node('option', selected + '（当前范围）'); option.value = selected; select.append(option);
    }
    select.value = selected;
  }
  function themeOptions() {
    const position = find('#review-position').value;
    const themes = data?.positions.find((item) => item.id === position)?.themes || [];
    populateSelect(find('#review-theme'), themes.map((theme) => [theme, theme]), filters.theme, '全部主题');
  }
  function render() {
    filters.position = data.position || '';
    filters.theme = data.theme || '';
    filters.offset = data.offset;
    saveAddress();
    populateSelect(find('#review-position'), data.positions.map((item) => [item.id, item.display_name]), filters.position, data.positions.length ? null : '暂无已完成岗位');
    themeOptions();
    find('#review-note').textContent = data.note;
    find('#review-aggregation').textContent = data.aggregation;
    find('#review-count').textContent = '本页 ' + data.session_count + ' 场 / 共 ' + data.total + ' 场\n' + data.items.length + ' 条主题记录';
    find('#review-repeat').textContent = '重复题口径：' + data.repeat_definition;
    find('#review-list').replaceChildren();
    data.items.forEach((row) => {
      const card = node('article', undefined, 'note-card review-card');
      const heading = node('div', undefined, 'note-card-heading');
      heading.append(node('h2', row.theme), node('strong', Number(row.score).toFixed(1) + ' / 10', 'review-score'));
      const levels = { easy: '轻松', mid: '标准', hard: '挑战', unknown: '未记录' };
      card.append(heading, node('p', row.position_display_name + ' · ' + (levels[row.difficulty] || row.difficulty), 'note-context'),
        node('p', row.ended_at ? new Date(row.ended_at).toLocaleString('zh-CN') : '完成时间未记录', 'note-time'));
      const stats = node('dl', undefined, 'review-stats');
      [['主问题', row.question_count + ' 题'], ['已回答', row.answer_count + ' 轮'], ['同版本重复', row.repeat_question_count + ' 题']].forEach(([label, value]) => {
        const group = node('div'); group.append(node('dt', label), node('dd', value)); stats.append(group);
      });
      card.append(stats, node('p', '实际主问题难度：' + Object.entries(row.question_difficulties).map(([level, count]) => (level === 'unknown' ? '未记录' : level) + ' ' + count + ' 题').join('、'), 'note-context'),
        node('p', row.known_question_version_count + ' 题有版本；另 ' + row.unknown_question_version_count + ' 题版本未记录。', 'note-context'));
      const profiles = row.scoring_profiles || [];
      const names = { heuristic: '规则评分', llm: '模型评分', heuristic_fallback: '模型失败后规则回退' };
      card.append(node('p', profiles.map((profile) => (names[profile.source] || '来源未记录') + ' ' + profile.answer_count + ' 轮' + (profile.cached_count ? '（缓存 ' + profile.cached_count + ' 轮）' : '') + (profile.sandbox_applied ? ' · 含判题合分' : '')).join('；'), 'review-origins'));
      const detail = node('details', undefined, 'report-answer');
      detail.append(node('summary', '评分来源与版本'), node('p', profiles.map((profile) => {
        return [names[profile.source] || '来源未记录', profile.scorer_version, profile.model, profile.prompt_version,
          profile.config_version && '配置 ' + profile.config_version, profile.prompt_digest && '提示词摘要 ' + profile.prompt_digest.slice(0, 12),
          profile.fallback_reason && '回退类别 ' + profile.fallback_reason].filter(Boolean).join(' · ');
      }).join('\n') || '历史来源与版本未记录', 'report-version'));
      const links = node('div', undefined, 'note-links');
      if (/^[a-f0-9]{32}$/.test(row.interview_id)) {
        const link = node('a', '回看逐轮报告 ↗'); link.href = '/report/' + row.interview_id; links.append(link);
      }
      card.append(detail, links); find('#review-list').append(card);
    });
    find('#review-empty').hidden = data.items.length > 0;
    find('#review-pagination').hidden = data.total <= pageSize;
    find('#review-page').textContent = '第 ' + (Math.floor(data.offset / data.limit) + 1) + ' / ' + Math.max(1, Math.ceil(data.total / data.limit)) + ' 页 · 按场次分页';
  }

  // 只读请求：超时与失效提供恢复入口，重试保留当前岗位、主题及页码。
  async function load() {
    if (loading) return;
    const version = ++requestVersion;
    const account = session();
    find('#review-sign-in').hidden = !!account;
    find('#review-error-panel').hidden = true; find('#review-content').hidden = true;
    if (!account) { data = null; setLoading(false); return; }
    setLoading(true);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      const query = new URLSearchParams({ offset: String(filters.offset), limit: String(pageSize) });
      if (filters.position) query.set('position', filters.position);
      if (filters.theme) query.set('theme', filters.theme);
      const response = await guardedFetch('/api/account/review?' + query, { cache: 'no-store', signal: controller.signal, headers: { Authorization: 'Bearer ' + account.access_token } });
      const result = await response.json().catch(() => null);
      if (version !== requestVersion) return;
      if (session()?.access_token !== account.access_token) throw new Error('当前会话已变化，请重新读取。');
      if (!response.ok) {
        if (response.status === 401) find('#review-sign-in').hidden = false;
        throw new Error(typeof result?.detail === 'string' ? result.detail : '读取失败，请重试。');
      }
      data = result;
      if (!data.total) data.offset = 0;
      if (!data.items.length && filters.offset && data.total > 0) {
        filters.offset = Math.floor((data.total - 1) / pageSize) * pageSize;
        setLoading(false); return load();
      }
      render(); find('#review-content').hidden = false;
    } catch (error) {
      if (version !== requestVersion) return;
      find('#review-error').textContent = error.name === 'AbortError' ? '读取超时，可按当前筛选重试。' : error instanceof TypeError ? '连接失败，请检查本机服务。' : error.message;
      find('#review-error-panel').hidden = false;
    } finally { clearTimeout(timer); if (version === requestVersion) setLoading(false); }
  }
  find('#review-position').addEventListener('change', () => {
    filters = { position: find('#review-position').value, theme: '', offset: 0 }; themeOptions(); load();
  });
  find('#review-filters').addEventListener('submit', (event) => {
    event.preventDefault(); if (loading) return;
    filters = { position: find('#review-position').value, theme: find('#review-theme').value, offset: 0 }; load();
  });
  find('#review-reset').addEventListener('click', () => { filters.theme = ''; filters.offset = 0; load(); });
  find('#review-refresh').addEventListener('click', load);
  find('#review-retry').addEventListener('click', load);
  find('#review-previous').addEventListener('click', () => { filters.offset = Math.max(0, filters.offset - pageSize); load(); });
  find('#review-next').addEventListener('click', () => { if (data?.has_more) { filters.offset += pageSize; load(); } });
  window.addEventListener('popstate', () => { requestVersion++; loading = false; filters = readAddress(); load(); });
  window.addEventListener('pageshow', (event) => { if (event.persisted) { requestVersion++; loading = false; filters = readAddress(); load(); } });
  load();
}());
