/* One cached account menu shared by every page. Credentials never enter URLs. */
(function(){
  'use strict';
/* @include session */
  const root=document.querySelector('.user-menu');
  if(!root)return;
  const label=root.querySelector('[data-user-name]'),image=root.querySelector('img'),initial=root.querySelector('[data-user-initial]');
  let generation=0,url='';
  function revoke(){if(url)URL.revokeObjectURL(url);url='';image.removeAttribute('src');image.hidden=true;initial.hidden=false;}
  async function refresh(){
    const version=++generation,session=readSession();revoke();
    label.textContent='登录 / 注册';root.setAttribute('aria-label','账户与登录');
    if(!session)return;
    try{
      const response=await fetch('/api/auth/me',{headers:{Authorization:'Bearer '+session.access_token},cache:'no-store',signal:AbortSignal.timeout(8000)});
      const data=await response.json();
      if(version!==generation||readSession()?.access_token!==session.access_token)return;
      if(!response.ok){if(response.status===401){sessionStorage.removeItem('account:session');dispatchEvent(new Event('account:expired'));}return;}
      label.textContent=data.nickname||data.username;initial.textContent=Array.from(label.textContent)[0];
      root.setAttribute('aria-label',label.textContent+'，账户管理');
      if(!data.avatar_version)return;
      const avatar=await fetch('/api/account/avatar',{headers:{Authorization:'Bearer '+session.access_token},cache:'no-store',signal:AbortSignal.timeout(8000)});
      const blob=await avatar.blob();
      if(version!==generation||readSession()?.access_token!==session.access_token||!avatar.ok||blob.type!=='image/png')return;
      url=URL.createObjectURL(blob);image.src=url;image.hidden=false;initial.hidden=true;
    }catch{if(version===generation&&readSession()?.access_token===session.access_token){label.textContent=session.account.nickname||session.account.username;initial.textContent=Array.from(label.textContent)[0];}}
  }
  addEventListener('account:changed',refresh);addEventListener('pageshow',refresh);
  addEventListener('pagehide',()=>{generation++;revoke();});
  refresh();
})();
