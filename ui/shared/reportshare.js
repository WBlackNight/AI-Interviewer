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
