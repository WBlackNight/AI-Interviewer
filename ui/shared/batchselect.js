/* 当前页选择：切页和刷新时清空，保留原生复选框语义。 */
function createBatchSelection(prefix, keyOf = (row) => row.id) {
  const root = document.querySelector('#' + prefix);
  const all = root.querySelector('[data-select-all]');
  const count = root.querySelector('[data-selection-count]');
  let rows = [], selected = new Map(), controls = [], disabled = false;
  function update(locked = disabled) {
    disabled = locked;
    count.textContent = '已选 ' + selected.size + ' 道';
    all.checked = rows.length > 0 && selected.size === rows.length;
    all.indeterminate = selected.size > 0 && selected.size < rows.length;
    all.disabled = disabled || !rows.length;
    root.querySelectorAll('[data-batch-action]').forEach((button) => { button.disabled = disabled || !selected.size; });
    controls.forEach(({ input, card, key }) => {
      input.checked = selected.has(key); input.disabled = disabled;
      card.classList.toggle('is-selected', input.checked);
    });
  }
  all.addEventListener('change', () => {
    if (disabled) return;
    selected = all.checked ? new Map(rows.map((row) => [keyOf(row), row])) : new Map(); update();
  });
  root.querySelector('[data-clear-selection]').addEventListener('click', () => { if (!disabled) clear(); });
  function clear() { selected.clear(); update(); }
  return {
    update, clear,
    reset(items = []) { rows = items; controls = []; selected.clear(); update(); },
    values() { return [...selected.values()]; },
    attach(card, row, text) {
      const key = keyOf(row), label = createNode('label', undefined, 'library-choice');
      const input = createNode('input'); input.type = 'checkbox';
      label.append(input, createNode('span', text)); card.prepend(label);
      controls.push({ input, card, key });
      input.addEventListener('change', () => {
        if (disabled) return;
        if (input.checked) selected.set(key, row); else selected.delete(key); update();
      });
      update();
    }
  };
}
