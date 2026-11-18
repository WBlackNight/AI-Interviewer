function notify(message, type = 'success', nextPage = false) {
  const detail = { message: String(message || '').slice(0, 240), type };
  if (!detail.message) return;
  if (nextPage) {
    try { sessionStorage.setItem('ui:notice', JSON.stringify({ ...detail, expires: Date.now() + 10000 })); } catch {}
  } else if (typeof CustomEvent === 'function') dispatchEvent(new CustomEvent('app:notice', { detail }));
}
