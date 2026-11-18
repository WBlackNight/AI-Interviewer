// Native disclosure menus keep their keyboard semantics, with one common dismissal policy.
(function () {
  const menus = Array.from(document.querySelectorAll?.('[data-navigation-menu], .user-menu-group') || []);
  if (!menus.length) return;
  menus.forEach(menu => menu.addEventListener('toggle', () => {
    if (menu.open) menus.forEach(other => { if (other !== menu) other.open = false; });
  }));
  menus.forEach(menu => menu.addEventListener('click', event => {
    if (event.target.closest?.('a[href]')) {
      menu.open = false;
      if (event.target.closest('a[href]').hash) menu.querySelector('summary')?.focus({ preventScroll: true });
    }
  }));
  document.addEventListener('pointerdown', event => {
    menus.forEach(menu => { if (!menu.contains(event.target)) menu.open = false; });
  });
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    const current = menus.find(menu => menu.open);
    if (current) { current.open = false; current.querySelector('summary').focus(); }
  });
  document.addEventListener('focusin', event => {
    menus.forEach(menu => { if (!menu.contains(event.target)) menu.open = false; });
  });
})();
