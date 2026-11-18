/* Exercise the real selection helper with DOM events; no browser/network needed. */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

function node() {
  const classes = new Set();
  return {
    textContent: '', children: [], checked: false, disabled: false, indeterminate: false, events: {},
    append(...items) { this.children.push(...items); },
    prepend(item) { this.children.unshift(item); },
    addEventListener(name, fn) { this.events[name] = fn; },
    classList: { toggle(name, enabled) { if (enabled) classes.add(name); else classes.delete(name); }, contains(name) { return classes.has(name); } },
    emit(name) { this.events[name]?.(); }
  };
}
const all = node(), count = node(), action = node(), clear = node();
const root = {
  querySelector: selector => selector === '[data-select-all]' ? all : selector === '[data-selection-count]' ? count : clear,
  querySelectorAll: () => [action, clear]
};
const source = ['element', 'batchselect'].map(name => readFileSync(new URL('../ui/shared/' + name + '.js', import.meta.url), 'utf8')).join('\n');
const create = vm.runInNewContext(source + '\ncreateBatchSelection', {
  document: { querySelector: () => root, createElement: () => node() }
});
const selection = create('selection');
const rows = [{ id: 'first', version: 2 }, { id: 'second', version: 7 }];
const cards = rows.map(() => node());
selection.reset(rows);
rows.forEach((row, i) => selection.attach(cards[i], row, row.id));
const inputs = cards.map(card => card.children[0].children[0]);
selection.update(false);
assert.equal(action.disabled, true);
inputs[0].checked = true; inputs[0].emit('change');
assert.equal(count.textContent, '已选 1 道');
assert.equal(all.indeterminate, true);
assert.equal(all.checked, false);
assert.equal(cards[0].classList.contains('is-selected'), true);
assert.equal(cards[1].classList.contains('is-selected'), false);
assert.equal(selection.values()[0], rows[0]); // retains version from the displayed snapshot
all.checked = true; all.emit('change');
assert.equal(selection.values().length, 2);
assert.equal(all.indeterminate, false);
assert.equal(inputs[1].checked, true);
selection.update(true);
assert.equal(action.disabled, true);
assert.equal(inputs[0].disabled, true);
clear.emit('click');
assert.equal(selection.values().length, 2); // pending operation locks selection
selection.update(false); clear.emit('click');
assert.equal(selection.values().length, 0);
assert.equal(inputs[0].checked, false);
assert.equal(action.disabled, true);
all.checked = true; all.emit('change');
selection.reset([]); // pagination, refresh or account invalidation
assert.equal(count.textContent, '已选 0 道');
assert.equal(all.disabled, true);
assert.equal(all.checked, false);
assert.equal(all.indeterminate, false);
assert.equal(selection.values().length, 0);
console.log('Passed: partial/all/clear selection, selected visuals, displayed versions, pending lock, pagination/account reset.');
