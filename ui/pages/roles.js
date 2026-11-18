/* Public role directory. All capabilities come from the current server assets. */
(function () {
  'use strict';
/* @include element */
/* @include http */
  const find = id => document.getElementById('roles-' + id);
  let roles = [], group = '', generation = 0;
  const element = createNode;
  function render() {
    const term = find('search').value.trim().toLocaleLowerCase();
    const filtered = roles.filter(role => (!group || role.group === group) &&
      [role.name, role.summary, role.focus, ...role.themes].join(' ').toLocaleLowerCase().includes(term));
    find('list').replaceChildren();
    filtered.forEach(role => {
      const card = element('article', undefined, 'role-card');
      card.append(element('p', role.group, 'eyebrow'), element('h3', role.name), element('p', role.summary));
      const tags = element('div', undefined, 'role-tags');
      role.themes.slice(0, 3).forEach(theme => tags.append(element('span', theme)));
      card.append(tags, element('p', role.count + ' 道题 · ' + role.focus, 'notes-boundary'));
      const actions = element('div', undefined, 'note-actions');
      const start = element('a', '练习这个方向', 'notes-button notes-primary');
      start.href = '/?' + new URLSearchParams({ position: role.id }) + '#start';
      const browse = element('a', '浏览题目', 'link-arrow');
      browse.href = '/catalog?' + new URLSearchParams({ position: role.id });
      actions.append(start, browse); card.append(actions); find('list').append(card);
    });
    find('status').textContent = filtered.length ? '共 ' + filtered.length + ' 个方向' : '没有匹配的方向，请调整分类或关键词。';
    find('groups').querySelectorAll('button').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.group === group)));
  }
  async function load() {
    const version = ++generation;
    find('retry').hidden = true; find('error').textContent = ''; find('status').textContent = '正在读取可用方向…';
    try {
      const data = await requestJSON('/api/practice/config');
      if (version !== generation) return;
      roles = Object.entries(data.positions).map(([id, role]) => ({ ...role, id }));
      find('groups').replaceChildren();
      ['', ...new Set(roles.map(role => role.group))].forEach(name => {
        const button = element('button', name || '全部方向', 'notes-button');
        button.type = 'button'; button.dataset.group = name;
        button.addEventListener('click', () => { group = name; render(); });
        find('groups').append(button);
      });
      render();
    } catch (error) {
      if (version !== generation) return;
      find('status').textContent = ''; find('error').textContent = error.name === 'TimeoutError' ? '读取超时，请重新读取。' : '方向暂时无法读取，请重新读取。';
      find('retry').hidden = false;
    }
  }
  find('search').addEventListener('input', render);
  find('retry').addEventListener('click', load);
  addEventListener('pagehide', () => { generation++; });
  void load();
})();
