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

/* One cached account menu shared by every page. Credentials never enter URLs. */
(function(){
  'use strict';
function readSession() {
  try {
    const value = JSON.parse(sessionStorage.getItem('account:session'));
    return value && /^[a-f0-9]{64}$/.test(value.access_token)
      && /^[a-f0-9]{32}$/.test(value.account?.id)
      && typeof value.account.username === 'string'
      && Date.parse(value.expires_at) > Date.now() ? value : null;
  } catch { return null; }
}

  const root=document.querySelector('.user-menu');
  if(!root)return;
  const menu = root.parentElement;
  const personalLinks = menu?.querySelectorAll('[data-account-only]') || [];
  const adminLinks = menu?.querySelectorAll('[data-admin-only]') || [];
  const accountEntry = menu?.querySelector('[data-account-entry]');
  function accountLinks(authenticated) {
    adminLinks.forEach(link => {link.hidden = true;});
    personalLinks.forEach(link => { link.hidden = !authenticated; });
    if (accountEntry) accountEntry.textContent = authenticated ? '账户中心' : '登录 / 注册';
  }
  const label=root.querySelector('[data-user-name]'),image=root.querySelector('img'),initial=root.querySelector('[data-user-initial]');
  let generation=0,url='';
  function revoke(){if(url)URL.revokeObjectURL(url);url='';image.removeAttribute('src');image.hidden=true;initial.hidden=false;}
  async function refresh(){
    const version=++generation,session=readSession();revoke();
    label.textContent='登录 / 注册';root.setAttribute('aria-label','账户与登录');accountLinks(!!session);
    if(!session)return;
    try{
      const response=await fetch('/api/auth/me',{headers:{Authorization:'Bearer '+session.access_token},cache:'no-store',signal:AbortSignal.timeout(8000)});
      const data=await response.json();
      if(version!==generation||readSession()?.access_token!==session.access_token)return;
      if(!response.ok){if(response.status===401){sessionStorage.removeItem('account:session');accountLinks(false);dispatchEvent(new Event('account:expired'));}return;}
      adminLinks.forEach(link => {link.hidden = data.is_admin !== true;});
      label.textContent=data.nickname||data.username;initial.textContent=Array.from(label.textContent)[0];
      root.setAttribute('aria-label',label.textContent+'，账户管理');
      if(!data.avatar_version)return;
      const avatar=await fetch('/api/account/avatar',{headers:{Authorization:'Bearer '+session.access_token},cache:'no-store',signal:AbortSignal.timeout(8000)});
      const blob=await avatar.blob();
      if(version!==generation||readSession()?.access_token!==session.access_token||!avatar.ok||blob.type!=='image/png')return;
      url=URL.createObjectURL(blob);image.src=url;image.hidden=false;initial.hidden=true;
    }catch{if(version===generation&&readSession()?.access_token===session.access_token){label.textContent=session.account.nickname||session.account.username;initial.textContent=Array.from(label.textContent)[0];}}
  }
  addEventListener('account:changed',refresh);
  addEventListener('pageshow', event => { if (event.persisted) refresh(); });
  addEventListener('pagehide',()=>{generation++;revoke();});
  refresh();
})();
