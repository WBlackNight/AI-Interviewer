(function () {
  'use strict';
/* @include element */
  const find = id => document.querySelector('#share-' + id);
  let generation = 0, refreshTimer, expiryTimer;
  function clear() {
    clearInterval(refreshTimer); clearTimeout(expiryTimer);
    generation++;
    find('content').replaceChildren();
    find('content').hidden = true;
  }
  async function load(quiet = false) {
    const version = ++generation;
    const token = location.hash.slice(1);
    find('retry').disabled = true;
    if (!quiet) { find('status').textContent = '正在读取分享内容…'; find('content').hidden = true; }
    try {
      if (!/^[a-f0-9]{64}$/.test(token)) throw new Error('链接不完整，请向分享者索取完整链接。');
      const response = await fetch('/api/shared-report', { cache: 'no-store', credentials: 'omit',
        headers: { 'X-Report-Share': token }, signal: AbortSignal.timeout(10000) });
      const data = await response.json();
      if (version !== generation) return;
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '暂时无法读取，请重试。');
      const content = find('content'), report = data.report;
      content.replaceChildren();
      const overview = createNode('div', undefined, 'report-panel');
      overview.append(createNode('h2', report.position_display_name), createNode('strong', Number(report.overall).toFixed(1) + ' / 10', 'retry-score'),
        createNode('p', report.question_count + ' 道主问题 · ' + report.answer_count + ' 轮回答'));
      Object.entries(report.dimensions).forEach(([key, value]) => overview.append(createNode('p', key + ' · ' + Number(value).toFixed(1))));
      const tips = createNode('ul');
      report.recommendations.forEach(tip => tips.append(createNode('li', tip)));
      overview.append(createNode('h3', '改进建议'), tips);
      if (!report.recommendations.length) overview.append(createNode('p', '本次没有记录额外的主题复习建议。'));
      content.append(overview);
      (report.per_question || []).forEach(turn => {
        const card = createNode('article', undefined, 'report-turn');
        card.append(createNode('h3', turn.content), createNode('strong', Number(turn.score).toFixed(1) + ' / 10'),
          createNode('p', turn.answer_text || '本轮未记录回答文本。', 'report-answer-text'),
          createNode('p', '待补强：' + (turn.key_points_missed.join('、') || '暂无'), 'report-missed'));
        content.append(card);
      });
      content.hidden = false;
      find('error').textContent = '';
      find('status').textContent = (data.scope === 'answers' ? '包含题目与回答' : '评分摘要') + ' · 有效至 ' + new Date(data.expires_at).toLocaleString('zh-CN');
      clearTimeout(expiryTimer);
      expiryTimer = setTimeout(() => { clear(); find('status').textContent = '此分享已到期。'; }, Math.max(0, Date.parse(data.expires_at) - Date.now()));
    } catch (error) {
      if (version !== generation) return;
      clear(); find('error').textContent = error.name === 'TimeoutError' ? '读取超时，请重试。' : error.message;
      find('status').textContent = '暂时无法查看这份分享。';
    } finally { find('retry').disabled = false; }
  }
  function start() { clear(); void load(); refreshTimer = setInterval(() => void load(true), 30000); }
  find('retry').addEventListener('click', start);
  addEventListener('hashchange', start);
  addEventListener('pagehide', clear);
  addEventListener('pageshow', event => { if (event.persisted) start(); });
  start();
}());
