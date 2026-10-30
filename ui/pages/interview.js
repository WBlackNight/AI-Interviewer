/* 练习室：幂等提交与恢复。 */
(function () {
  'use strict';
/* @include session */
/* @include element */
/* @include token */
  const find = (id) => document.querySelector('#studio-' + id);
  const copy = find('copy').dataset;
  const interviewId = location.pathname.match(/^\/interview\/([a-f0-9]{32})$/)?.[1];
  const pendingKey = 'interview:' + interviewId + ':pending';
  const turns = new Map();
  let socket, connectionToken, reconnectTimer, watchdog;
  let question = null, pending = null, lastScore = null;
  let version = 0, lastSequence = -1, retries = 0, historyPage = 0;
  let status = 'connecting', cancelling = false, disposed = false, denied = false;
  let draftTurn = null;

  const token = () => interviewToken(interviewId);
  const element = createNode;
  function setText(id, value) { find(id).textContent = value; }
  function terminal() { return status === 'finished' || status === 'cancelled'; }
  function clearPending() {
    pending = null;
    try { sessionStorage.removeItem(pendingKey); } catch { /* 按事件恢复。 */ }
  }
  function preserveDraft({ text, code } = { text: find('answer').value, code: find('code').value }) {
    if (!text && !code) return;
    setText('recovery-copy', [text, code].filter(Boolean).join('\n\n'));
    find('recovery').hidden = false;
  }
  function changeQuestion(next) {
    if (question?.turn_id !== next?.turn_id) {
      if (draftTurn && draftTurn !== next?.turn_id && !pending) preserveDraft();
      find('answer').value = ''; find('code').value = ''; draftTurn = null;
    }
    question = next;
  }
  function clearCommitted() {
    clearPending(); draftTurn = null;
    find('answer').value = ''; find('code').value = '';
  }

  function render() {
    const accessLost = denied || !token() || token() !== connectionToken;
    setText('status', pending && status === 'active' ? copy.pending : copy[status]);
    find('indicator').dataset.state = status;
    find('access').hidden = !accessLost;
    find('workspace').hidden = accessLost || (!question && !terminal() && !turns.size);
    find('form').hidden = terminal() || !question;
    find('terminal').hidden = !terminal();
    find('cancel').hidden = terminal();
    setText('question-title', question?.content || (terminal() ? copy.savedTitle : copy.preparing));
    setText('question-meta', question ? question.theme + (question.is_probe ? ' · 追问 ' + (question.probe_depth || 1) + ' 层' : question.is_coding ? ' · Python 编程' : ' · 主问题') : 'PRACTICE SAVED');
    find('code-field').hidden = !question?.is_coding;
    find('tests').hidden = !question?.is_coding || !question?.testcases?.length;
    setText('test-copy', (question?.testcases || []).map((item, index) => '用例 ' + (index + 1) + '\n输入：' + item.input + '\n预期：' + item.expected).join('\n\n'));
    renderComposer();
    find('sync').disabled = find('cancel').disabled = cancelling;
    setText('terminal-title', copy[status + 'Title']);
    setText('terminal-copy', copy[status + 'Copy']);
    setText('report', copy[status + 'Link']);
    if (lastScore) {
      setText('last-score', Number(lastScore.score).toFixed(1));
      setText('evidence', lastScore.evidence);
      setText('missed', lastScore.key_points_missed?.length ? '待补强：' + lastScore.key_points_missed.join('、') : '');
      const origin = lastScore.scoring_origin || {};
      setText('origin', (copy[origin.source] || copy.unknownOrigin) + (origin.cached ? copy.cached : '') + (lastScore.sandbox ? ' · 判题 ' + lastScore.sandbox.passed + '/' + lastScore.sandbox.total : ''));
    }
    document.querySelectorAll('[data-dimension]').forEach((row) => {
      const value = lastScore?.dimensions?.[row.dataset.dimension];
      row.querySelector('strong').textContent = value == null ? '—' : Number(value).toFixed(1);
      row.querySelector('meter').hidden = value == null;
      row.querySelector('meter').value = value || 0;
    });
    renderHistory();
  }
  function renderComposer() {
    const answer = find('answer'), code = find('code'), submit = find('submit');
    answer.disabled = code.disabled = !!pending || cancelling;
    const length = Array.from(answer.value).length;
    setText('counter', length.toLocaleString());
    submit.disabled = cancelling || !!pending || status !== 'active' || !question || length > 20000 || !(question.is_coding ? code.value.trim() : answer.value.trim());
    submit.textContent = pending ? '等待保存…' : '提交回答';
    find('skip').disabled = cancelling || !!pending || status !== 'active' || !question;
  }

  function renderHistory() {
    const saved = Array.from(turns.values()).filter((row) => row.answer !== undefined || row.score);
    historyPage = Math.min(historyPage, Math.max(0, Math.ceil(saved.length / 4) - 1));
    setText('saved-count', saved.length + ' 轮');
    find('history-empty').hidden = saved.length > 0;
    find('turns').replaceChildren();
    saved.slice(historyPage * 4, historyPage * 4 + 4).forEach((row) => {
      const card = element('article', undefined, 'studio-saved-turn');
      const detail = element('details');
      detail.append(element('summary', (row.theme || '本轮') + (row.is_probe ? ' · 追问' : ' · 主问题') + (row.score ? ' · ' + Number(row.score.score).toFixed(1) + ' / 10' : ' · 已保存')));
      detail.append(element('h3', row.content), element('p', row.answer || '本轮未记录回答文本。', 'report-answer-text'));
      if (row.score) detail.append(element('p', '评分依据：' + row.score.evidence, 'report-evidence'));
      card.append(detail); find('turns').append(card);
    });
    find('pagination').hidden = saved.length <= 4;
    setText('page', '第 ' + (historyPage + 1) + ' / ' + Math.max(1, Math.ceil(saved.length / 4)) + ' 页');
    find('previous').disabled = historyPage === 0;
    find('next').disabled = (historyPage + 1) * 4 >= saved.length;
  }

  function dispatch(data, replay = false) {
    if (data.type === 'snapshot') {
      const previousPending = pending;
      turns.clear(); lastScore = null; lastSequence = -1;
      for (const event of data.events || []) dispatch(event, true);
      version = data.version; changeQuestion(data.current_question);
      status = data.cancelled || data.state === 'cancelled' ? 'cancelled' : data.finished ? 'finished' : 'active';
      setText('error', '');
      retries = 0; clearTimeout(watchdog);
      if (previousPending) {
        const committed = (data.events || []).some((event) => event.type === 'answer_ack' && event.message_id === previousPending.message_id);
        if (committed) clearCommitted();
        else if (!terminal() && previousPending.turn_id === question?.turn_id && previousPending.version === version) socket.send(JSON.stringify(previousPending));
        else { preserveDraft(previousPending); clearPending(); setText('notice', copy.staleDraft); }
      }
      if (terminal()) { clearPending(); socket?.close(); }
      render(); return;
    }
    if (data.seq !== undefined) {
      if (data.seq <= lastSequence) return;
      lastSequence = data.seq;
    }
    if (data.version !== undefined) version = data.version;
    if (data.type === 'question') {
      turns.set(data.turn_id, { ...(turns.get(data.turn_id) || {}), ...data });
      if (!replay) { changeQuestion(data); clearPending(); status = 'active'; }
    } else if (data.type === 'answer_ack') {
      const row = turns.get(data.turn_id) || {};
      turns.set(data.turn_id, { ...row, answer: data.answer_text });
      if (!replay && pending?.message_id === data.message_id) { clearCommitted(); status = 'connecting'; }
    } else if (data.type === 'score') {
      lastScore = data;
      turns.set(data.turn_id, { ...(turns.get(data.turn_id) || {}), score: data });
    } else if (data.type === 'report_ready' || data.type === 'interview_cancelled') {
      status = data.type === 'report_ready' ? 'finished' : 'cancelled';
      if (!replay) { clearPending(); changeQuestion(null); socket?.close(); }
    } else if (data.type === 'error') {
      setText('error', data.detail || copy.unsaved);
      if (pending) preserveDraft(pending);
      clearPending();
      if (data.code === 'stale_turn') { status = 'connecting'; socket?.send(JSON.stringify({ type: 'start' })); }
      else if (['access_revoked', 'not_found', 'assets_changed', 'legacy_session'].includes(data.code)) { denied = data.code === 'access_revoked'; status = 'error'; stopSocket(); }
    }
    if (!replay) render();
  }
  function stopSocket() {
    clearTimeout(reconnectTimer); clearTimeout(watchdog);
    if (socket) { socket.onclose = null; socket.onmessage = null; socket.close(); }
  }
  function connect() {
    if (disposed || terminal()) return;
    stopSocket(); denied = false; status = 'connecting'; connectionToken = token(); render();
    if (!interviewId || !connectionToken) { status = 'error'; render(); return; }
    try {
      const base = document.body.dataset.wsBase || location.origin.replace(/^http/, 'ws');
      const target = new URL(base);
      if (!['ws:', 'wss:'].includes(target.protocol) || target.username || target.password || target.search || target.hash) throw new Error(copy.configError);
      const ws = new WebSocket(base.replace(/\/$/, '') + '/ws/interview/' + interviewId, ['interview', connectionToken]);
      socket = ws;
      watchdog = setTimeout(() => { if (status === 'connecting') ws.close(); }, 195000);
      ws.onopen = () => { if (ws === socket && !disposed) ws.send(JSON.stringify({ type: 'start' })); };
      ws.onmessage = (event) => {
        if (ws !== socket || disposed) return;
        if (token() !== connectionToken) { status = 'error'; stopSocket(); render(); return; }
        try { dispatch(JSON.parse(event.data)); }
        catch { setText('error', copy.parseError); status = 'error'; stopSocket(); render(); }
      };
      ws.onclose = (event) => {
        if (ws !== socket || disposed || terminal()) return;
        clearTimeout(watchdog);
        if ([4403, 1008].includes(event.code) || ++retries > 6) { denied = event.code === 4403; status = 'error'; render(); return; }
        status = 'connecting'; render();
        reconnectTimer = setTimeout(connect, Math.min(1000 * 2 ** (retries - 1), 10000));
      };
    } catch (error) { status = 'error'; setText('error', error.message); render(); }
  }

  find('form').addEventListener('submit', (event) => {
    event.preventDefault();
    if (pending || cancelling || status !== 'active' || !question || socket?.readyState !== WebSocket.OPEN || token() !== connectionToken) return;
    const text = find('answer').value.trim();
    const code = question.is_coding ? find('code').value : '';
    if ((!text && !code.trim()) || Array.from(text).length > 20000 || new TextEncoder().encode(code).length > 16384) { setText('error', copy.lengthError); return; }
    const payload = { type: 'answer', message_id: crypto.randomUUID(), turn_id: question.turn_id, version, text: text || '（代码实现如下）', ...(code ? { code } : {}) };
    try { sessionStorage.setItem(pendingKey, JSON.stringify(payload)); pending = payload; socket.send(JSON.stringify(payload)); setText('error', ''); render(); }
    catch { setText('error', copy.submitError); render(); }
  });
  ['answer', 'code'].forEach((selector) => {
    find(selector).addEventListener('input', () => { draftTurn = question?.turn_id; renderComposer(); });
    find(selector).addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && (event.ctrlKey || event.metaKey) && !event.isComposing && event.keyCode !== 229) { event.preventDefault(); find('form').requestSubmit(); }
    });
  });
  find('skip').addEventListener('click', () => {
    if (find('skip').disabled) return;
    preserveDraft(); find('answer').value = '跳过'; find('code').value = ''; find('form').requestSubmit();
  });
  find('sync').addEventListener('click', () => { retries = 0; setText('error', ''); status = 'connecting'; connect(); });
  find('previous').addEventListener('click', () => { historyPage--; renderHistory(); });
  find('next').addEventListener('click', () => { historyPage++; renderHistory(); });

  const dialog = find('confirm');
  find('cancel').addEventListener('click', () => { setText('confirm-error', ''); dialog.showModal(); });
  find('confirm-back').addEventListener('click', () => { if (!cancelling) dialog.close(); });
  dialog.addEventListener('cancel', (event) => { if (cancelling) event.preventDefault(); });
  find('confirm-submit').addEventListener('click', async () => {
    if (cancelling || terminal()) return;
    cancelling = true; render();
    find('confirm-submit').disabled = find('confirm-back').disabled = true;
    const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch('/api/interview/' + interviewId + '/cancel', { method: 'POST', cache: 'no-store', signal: controller.signal, headers: { 'X-Interview-Token': token() || '' } });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || copy.cancelError);
      preserveDraft();
      status = 'cancelled'; clearPending(); changeQuestion(null); stopSocket(); dialog.close();
    } catch (error) { setText('confirm-error', error.name === 'AbortError' ? copy.cancelTimeout : error.message); }
    finally { clearTimeout(timer); cancelling = false; find('confirm-submit').disabled = find('confirm-back').disabled = false; render(); }
  });

  addEventListener('beforeunload', (event) => {
    if (!terminal() && (pending || find('answer').value || find('code').value)) { event.preventDefault(); event.returnValue = ''; }
  });
  addEventListener('pagehide', () => { disposed = true; stopSocket(); });
  addEventListener('pageshow', (event) => { if (event.persisted) { disposed = false; status = 'connecting'; connect(); } });
  try {
    const value = JSON.parse(sessionStorage.getItem(pendingKey));
    if (value?.type === 'answer' && /^[A-Za-z0-9_-]{1,64}$/.test(value.message_id) && /^[a-f0-9]{32}$/.test(value.turn_id) && Number.isInteger(value.version) && value.version >= 0 && typeof value.text === 'string' && Array.from(value.text).length <= 20000 && (value.code === undefined || typeof value.code === 'string' && new TextEncoder().encode(value.code).length <= 16384)) pending = value;
    else if (value) clearPending();
  } catch { clearPending(); }
  find('report').href = find('current-report').href = '/report/' + interviewId;
  connect();
}());
