// Only explicit operation results trigger notices. Background reads stay quiet.
(function () {
  if (!document.createElement || !document.body) return;
  const box = document.createElement('div'), text = document.createElement('span'), close = document.createElement('button');
  box.className = 'app-notice'; box.hidden = true; box.setAttribute('aria-atomic', 'true');
  close.type = 'button'; close.textContent = '×'; close.setAttribute('aria-label', '关闭提示');
  box.append(text, close); document.body.append(box);
  let timer;
  function hide() { clearTimeout(timer); box.hidden = true; text.textContent = ''; }
  function show(detail) {
    if (!detail || typeof detail.message !== 'string' || !detail.message.trim()) return;
    hide();
    const error = detail.type === 'error';
    box.dataset.kind = error ? 'error' : 'success';
    box.setAttribute('role', error ? 'alert' : 'status');
    box.setAttribute('aria-live', error ? 'assertive' : 'polite');
    box.hidden = false; text.textContent = detail.message.slice(0, 240);
    timer = setTimeout(hide, 2000);
  }
  close.addEventListener('click', hide);
  addEventListener('app:notice', event => show(event.detail));
  addEventListener('account:changed', hide);
  addEventListener('pagehide', hide);
  function restored() {
    try {
      const pending = JSON.parse(sessionStorage.getItem('ui:notice'));
      sessionStorage.removeItem('ui:notice');
      if (pending?.expires > Date.now()) show(pending);
    } catch { /* Storage may be unavailable; it never blocks the operation. */ }
  }
  addEventListener('pageshow', restored);
})();
