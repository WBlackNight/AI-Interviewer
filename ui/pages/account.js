/* 原生账户：沿用已有会话契约，登录、退出与删除分别操作。 */
(function () {
  'use strict';
/* @include session */
/* @include fetch */
/* @include element */
  const find = (selector) => document.querySelector(selector);
  let mode = 'login';
  let busy = false;
  let checking = false;
  let account = null;
  let captcha=null,captchaLoading=false,securityConfig=null,avatarUrl='',selectedFile=null,loadedAccount='',nicknameDirty=false;
  let emailChallenge='',passwordChallenge='';
  const cooldown=new Map();
  function announceSession(data) {
    const current=session();if(!current)return;
    account=data;sessionStorage.setItem('account:session',JSON.stringify({...current,account:data}));
    dispatchEvent(new Event('account:changed'));render();
  }

  // 收藏回链：只重建同源题单地址，不接受任意跳转URL或传递账户凭据。
  const collection = new URLSearchParams(location.search);
  function safeReturn(value) {
    if (!value || !/^\/(?!\/)/.test(value)) return '';
    try {
      const target = new URL(value, location.origin);
      if (target.origin !== location.origin || !(/^(?:\/|\/(?:dashboard|catalog|plans|history|revision|notes|library|coverage|review|plan-history))$/.test(target.pathname) || /^\/(?:interview|report)\/[a-f0-9]{32}$/.test(target.pathname))) return '';
      return target.pathname + target.search + target.hash;
    } catch { return ''; }
  }
  const returnPath = safeReturn(collection.get('next'));
  const collectPosition = collection.get('collect_position') || '';
  const collectQuestion = collection.get('collect_question') || '';
  const returnCollection = /^[a-z][a-z0-9_]{0,63}$/.test(collectPosition) && /^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/.test(collectQuestion)
    ? '/library?' + new URLSearchParams({ position: collectPosition, question: collectQuestion }) + '#library-discover' : '';

  // 会话与请求：密码不持久化，凭据只在当前标签页并通过请求头使用。
  const session = readSession;
  function clearSession() { sessionStorage.removeItem('account:session'); }
  async function request(path, options = {}, publicRequest = false) {
    const current = session();
    if (!publicRequest && !current) throw Object.assign(new Error('登录已失效，请重新登录。'), { status: 401 });
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await guardedFetch('/api' + path, { ...options, cache: 'no-store', signal: controller.signal,
        headers: { 'Content-Type': 'application/json', ...(!publicRequest ? { Authorization: 'Bearer ' + current.access_token } : {}),...options.headers } });
      const data = await response.json();
      if (!response.ok) throw Object.assign(new Error(typeof data?.detail === 'string' ? data.detail : response.status === 422 ? '请检查用户名和密码格式。' : '请求失败，请重试。'), { status: response.status });
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('请求超时，请重新检查登录状态后再操作。');
      if (error instanceof TypeError) throw new Error('连接失败，请检查本机服务后重试。');
      throw error;
    } finally { clearTimeout(timer); }
  }
  function setBusy(value) {
    busy = value;
    document.querySelectorAll('#account-main button, #account-main input, #account-delete-dialog button, #account-delete-dialog input').forEach((node) => { node.disabled = value; });
    find('#account-submit').textContent = value ? '处理中…' : mode === 'login' ? '登录' : '注册并登录';
    find('#account-submit').disabled=value||(mode==='register'&&(!captcha||captchaLoading));
    find('#avatar-submit').disabled=value||!selectedFile;
    for(const id of ['email-send','password-send'])find('#'+id).disabled=value||!securityConfig?.email_available||cooldown.has(id);
  }
  function render() {
    find('#account-checking').hidden = !checking;
    find('#account-auth').hidden = checking || !!account;
    find('#account-profile').hidden = checking || !account;
    find('#account-return-collection').hidden = !account || !returnCollection;
    if (returnCollection) find('#account-return-collection').href = returnCollection;
    if (account) {
      find('#account-name').textContent = account.nickname||account.username;
      find('#profile-username').textContent='@'+account.username;
      find('#profile-initial').textContent=Array.from(account.nickname||account.username)[0];
      if(loadedAccount!==account.id){nicknameDirty=false;loadedAccount=account.id;}
      if(!nicknameDirty)find('#profile-nickname').value=account.nickname||account.username;
      find('#profile-email').textContent=account.email?'已验证：'+account.email:'尚未绑定邮箱';
      find('#email-form').hidden=!!account.email;
      find('#password-email-fields').hidden=!account.email;
      find('#password-code').required=!!account.email;
      find('#avatar-remove').hidden=!account.avatar_version;
      const expiry = session()?.expires_at;
      find('#account-expiry').textContent = expiry ? '本次登录有效至 ' + new Date(expiry).toLocaleString('zh-CN') + '，仅限当前标签页。' : '';
    }
  }

  // 概览：只读汇总，不将任务完成状态当作评分或能力提升。
  async function overview() {
    find('#account-overview-retry').hidden=true;
    for(const id of ['finished','active-count','task-count','note-count'])find('#account-'+id).textContent='—';
    for(const id of ['active','recent'])find('#account-'+id).replaceChildren();
    find('#account-next-title').textContent='安排下一步';find('#account-next-description').textContent='正在读取你的练习安排…';
    find('#account-next-link').href='/catalog';find('#account-next-link').textContent='探索题库';
    try {
      const data=await request('/account/dashboard');
      for(const [id,value] of Object.entries({'finished':data.interviews.finished,'active-count':data.interviews.running+data.interviews.created,'task-count':data.tasks.todo,'note-count':data.notes_with_content}))find('#account-'+id).textContent=String(value);
      for(const [id,items,report] of [['active',data.active,false],['recent',data.recent,true]]){
        const list=find('#account-'+id);list.replaceChildren();
        items.forEach(item=>{
          const row=createNode('a',undefined,'personal-record');
          row.href=/^[a-f0-9]{32}$/.test(item.interview_id)?'/'+(report?'report':'interview')+'/'+item.interview_id:'/history';
          row.append(createNode('strong',item.position_display_name||item.position),createNode('span',(report?'查看报告':item.status==='running'?'继续作答':'进入练习')+' · '+item.answer_count+'轮回答'));list.append(row);
        });
        if(!items.length)list.append(createNode('p',report?'完成一场练习后，报告会出现在这里。':'还没有待继续的练习，从题库选一个方向开始吧。','account-help'));
      }
      const due=data.tasks.today+data.tasks.overdue;
      find('#account-next-title').textContent=due?'给复习留一点时间':data.active.length?'把这一场讲完':'试试下一个主题';
      find('#account-next-description').textContent=due?'有'+due+'项到期或逾期任务，回看笔记后再试一次。':data.active.length?'已有练习等待继续，先把思路完整地说出来。':'从六个方向中选择一个主题，练一题也有收获。';
      const next=find('#account-next-link');next.href=due?'/revision':data.active.length?find('#account-active a').href:'/catalog';next.textContent=due?'查看复习任务':data.active.length?'继续练习':'探索题库';
      find('#account-overview-message').textContent='';
    } catch(error) {
      for(const id of ['finished','active-count','task-count','note-count'])find('#account-'+id).textContent='—';
      for(const id of ['active','recent'])find('#account-'+id).replaceChildren();
      find('#account-next-description').textContent='先从题库选择一个感兴趣的主题。';
      find('#account-overview-message').textContent=error.message||'练习近况暂时无法读取。';find('#account-overview-retry').hidden=false;
    }
  }
  async function check() {
    if (busy) return;
    checking = true; setBusy(true); render();
    find('#account-alert').textContent = '';
    find('#account-retry').hidden = true;
    try {
      if (!session()) { clearSession(); account = null; }
      else { account = await request('/auth/me'); await Promise.allSettled([overview(),loadSecurity(),loadAvatar()]); }
    } catch (error) {
      if (error.status === 401) { clearSession(); account = null; }
      else { find('#account-retry').hidden = false; }
      find('#account-alert').textContent = error.message;
    } finally { checking = false; setBusy(false); render(); }
  }

  // 登录注册：同源显式提交，验证返回契约后才写会话；密码每次提交后清空。
  find('#account-auth').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (busy) return;
    if(mode==='register'&&find('#account-password').value!==find('#account-password-confirm').value){find('#account-alert').textContent='两次输入的密码不一致';find('#account-password-confirm').focus();return;}
    setBusy(true); find('#account-alert').textContent = ''; find('#account-notice').textContent = '';
    try {
      const payload={username:find('#account-username').value.trim(),password:find('#account-password').value};
      if(mode==='register')Object.assign(payload,{password_confirm:find('#account-password-confirm').value,captcha_id:captcha?.captcha_id,captcha_code:find('#account-captcha-code').value.trim()});
      const result = await request('/auth/' + mode, { method: 'POST', body: JSON.stringify(payload) }, true);
      if (!/^[a-f0-9]{64}$/.test(result?.access_token) || !/^[a-f0-9]{32}$/.test(result.account?.id) || typeof result.account.username !== 'string' || !(Date.parse(result.expires_at) > Date.now())) throw new Error('登录信息不完整，请重试。');
      try { sessionStorage.setItem('account:session', JSON.stringify(result)); }
      catch { throw new Error('浏览器无法保留当前会话，请检查标签页存储设置后重新登录。'); }
      account = result.account; render();
      dispatchEvent(new Event('account:changed'));
      if(returnCollection||returnPath){find('#account-notice').textContent='登录成功，正在返回…';location.assign(returnCollection||returnPath);}
      else {await Promise.allSettled([overview(),loadSecurity(),loadAvatar()]);find('#account-notice').textContent=mode==='register'?'账户已创建，开始你的第一场练习吧。':'欢迎回来。';render();find('#account-name').focus();}
    } catch (error) { find('#account-alert').textContent = error.message; if(mode==='register')void loadCaptcha(); }
    finally { find('#account-password').value = '';find('#account-password-confirm').value='';resetPassword(); setBusy(false); render(); }
  });
  document.querySelectorAll('[data-mode]').forEach((button) => button.addEventListener('click', () => {
    if (busy) return;
    mode = button.dataset.mode;
    document.querySelectorAll('[data-mode]').forEach((item) => item.setAttribute('aria-pressed', String(item === button)));
    find('#account-form-title').textContent = mode === 'login' ? '登录账户' : '创建账户';
    find('#account-form-description').textContent = mode === 'login' ? '继续你的练习与复盘。' : '创建账户，保存每一次练习。';
    find('#account-register-help').hidden=mode!=='register';find('#account-username-status').textContent='';
    find('#account-password-status').hidden=mode!=='register';find('#account-password-status').textContent='';
    find('#account-username').removeAttribute('aria-invalid');find('#account-password-confirm').removeAttribute('aria-invalid');
    find('#account-auth').action = '/api/auth/' + mode;
    find('#account-password').autocomplete = mode === 'login' ? 'current-password' : 'new-password';
    find('#register-fields').hidden=mode!=='register';
    for(const id of ['account-password-confirm','account-captcha-code'])find('#'+id).required=mode==='register';
    find('#account-password-confirm').value='';
    find('#account-password').value = ''; resetPassword(); find('#account-alert').textContent = ''; setBusy(false);
    find('#account-username').focus();
    if(mode==='register')void loadCaptcha();
  }));
  function resetPassword() {
    document.querySelectorAll('[data-password-toggle]').forEach(button=>{
      find('#'+button.dataset.passwordToggle).type='password';button.setAttribute('aria-pressed','false');button.setAttribute('aria-label','显示密码');
    });
  }
  document.querySelectorAll('[data-password-toggle]').forEach(button=>button.addEventListener('click',()=>{
    const input=find('#'+button.dataset.passwordToggle),show=input.type==='password';input.type=show?'text':'password';
    button.setAttribute('aria-pressed',String(show));button.setAttribute('aria-label',show?'隐藏密码':'显示密码');
  }));

  async function loadCaptcha(){
    if(captchaLoading)return;captchaLoading=true;captcha=null;setBusy(busy);
    find('#account-captcha-code').value='';find('#account-captcha-status').textContent='正在加载验证码…';
    try{const data=await request('/auth/captcha',{},true);if(!/^[a-f0-9]{32}$/.test(data.captcha_id)||!data.image?.startsWith('data:image/png;base64,'))throw new Error('验证码无法读取，请换一张');captcha=data;find('#account-captcha-image').src=data.image;find('#account-captcha-status').textContent='2分钟内有效，不区分大小写。看不清可换一张。';}
    catch(error){find('#account-captcha-status').textContent=error.message;}
    finally{captchaLoading=false;setBusy(busy);}
  }
  find('#account-captcha-refresh').addEventListener('click',loadCaptcha);
  for(const id of ['account-password','account-password-confirm'])find('#'+id).addEventListener('input',()=>{
    if(mode!=='register')return;
    const password=find('#account-password').value,confirm=find('#account-password-confirm');
    const mismatch=!!confirm.value&&confirm.value!==password;
    confirm.setAttribute('aria-invalid',String(mismatch));
    find('#account-password-status').textContent=mismatch?'两次密码还不一致，请检查。':password.length<12?'至少12个字符，建议使用不易猜到的组合。':'密码长度符合要求。';
  });
  find('#account-username').addEventListener('blur',async()=>{
    const username=find('#account-username').value.trim();if(mode!=='register'||!/^[A-Za-z0-9_]{3,32}$/.test(username))return;
    try{const data=await request('/auth/username-availability?'+new URLSearchParams({username}),{},true);if(mode==='register'&&username===find('#account-username').value.trim()){find('#account-username-status').textContent=data.available?'这个用户名可以使用。':'用户名已被使用，换一个试试。';find('#account-username').setAttribute('aria-invalid',String(!data.available));}}catch{}
  });
  async function loadSecurity(){
    securityConfig=await request('/account/security');
    find('#mail-delivery').textContent=securityConfig.email_mode==='local_test'?'本机测试模式：邮件只进入测试收件箱，不会发送至外部邮箱。':securityConfig.email_available?'验证码将发送至你填写的邮箱。':'邮件服务尚未配置，暂时无法发送验证码。';
    find('#test-mail-link').hidden=securityConfig.email_mode!=='local_test';
  }
  async function loadAvatar(){
    if(avatarUrl)URL.revokeObjectURL(avatarUrl);avatarUrl='';find('#profile-avatar').hidden=true;find('#profile-initial').hidden=false;
    if(!account?.avatar_version)return;
    const identity=session()?.access_token;
    const response=await fetch('/api/account/avatar',{headers:{Authorization:'Bearer '+identity},cache:'no-store',signal:AbortSignal.timeout(8000)});
    const blob=await response.blob();if(session()?.access_token!==identity||!response.ok||blob.type!=='image/png')return;
    avatarUrl=URL.createObjectURL(blob);find('#profile-avatar').src=avatarUrl;find('#profile-avatar').hidden=false;find('#profile-initial').hidden=true;
  }
  find('#profile-nickname').addEventListener('input',()=>{nicknameDirty=true;});
  find('#profile-form').addEventListener('submit',async event=>{
    event.preventDefault();if(busy)return;setBusy(true);
    try{const data=await request('/account/profile',{method:'PATCH',body:JSON.stringify({nickname:find('#profile-nickname').value.trim()})});nicknameDirty=false;announceSession(data);find('#profile-message').textContent='昵称已保存。';}
    catch(error){find('#profile-message').textContent=error.message;}finally{setBusy(false);}
  });
  find('#profile-file').addEventListener('change',async()=>{
    selectedFile=null;find('#avatar-message').textContent='';setBusy(busy);const file=find('#profile-file').files[0];if(!file)return;
    try{
      if(!/^image\/(png|jpeg|webp)$/.test(file.type)||! /\.(png|jpe?g|webp)$/i.test(file.name))throw new Error('请选择JPG、PNG或WebP图片');
      if(file.size>2097152||!file.size)throw new Error('头像不能为空且不能超过2MB');
      const image=await createImageBitmap(file);const valid=image.width>=32&&image.height>=32&&image.width<=4096&&image.height<=4096;image.close();if(!valid)throw new Error('图片尺寸应为32–4096像素');
      if(find('#profile-file').files[0]!==file)return;selectedFile=file;find('#avatar-message').textContent=file.name+' · '+Math.ceil(file.size/1024)+'KB，点击上传后保存。';
    }catch(error){find('#profile-file').value='';find('#avatar-message').textContent=error.message||'图片无法读取';}finally{setBusy(busy);}
  });
  find('#avatar-form').addEventListener('submit',async event=>{
    event.preventDefault();if(busy||!selectedFile)return;setBusy(true);
    try{announceSession(await request('/account/avatar',{method:'POST',body:selectedFile,headers:{'Content-Type':selectedFile.type}}));selectedFile=null;find('#profile-file').value='';await loadAvatar();find('#avatar-message').textContent='头像已保存，右上角已同步更新。';}
    catch(error){find('#avatar-message').textContent=error.message;}finally{setBusy(false);}
  });
  find('#avatar-remove').addEventListener('click',async()=>{if(busy)return;setBusy(true);try{announceSession(await request('/account/avatar',{method:'DELETE'}));await loadAvatar();find('#avatar-message').textContent='已恢复默认头像。';}catch(error){find('#avatar-message').textContent=error.message;}finally{setBusy(false);}});
  function startCooldown(id,seconds){
    const button=find('#'+id),label=button.textContent,end=Date.now()+seconds*1000;
    function tick(){const left=Math.ceil((end-Date.now())/1000);if(left<=0){clearInterval(cooldown.get(id));cooldown.delete(id);button.textContent=label;setBusy(busy);}else{button.textContent=left+'秒后可重发';button.disabled=true;}}
    cooldown.set(id,setInterval(tick,1000));tick();
  }
  async function sendEmail(purpose){
    if(busy)return;const bind=purpose==='email_bind',id=bind?'email-send':'password-send',message=find(bind?'#email-message':'#password-message');
    const password=find(bind?'#email-password':'#security-current');if(!password.reportValidity())return;
    if(bind&&!find('#profile-email-input').reportValidity())return;
    setBusy(true);message.textContent='正在发送…';
    try{const data=await request('/account/email/code',{method:'POST',body:JSON.stringify({purpose,current_password:password.value,...(bind?{email:find('#profile-email-input').value.trim()}: {})})});if(bind)emailChallenge=data.challenge_id;else passwordChallenge=data.challenge_id;startCooldown(id,data.retry_after);message.textContent= data.delivery==='local_test'?'已投递到本机测试收件箱，请打开收件箱查看验证码。':'验证码已发送，10分钟内有效。';}
    catch(error){message.textContent=error.message;}finally{setBusy(false);}
  }
  find('#email-send').addEventListener('click',()=>sendEmail('email_bind'));
  find('#profile-email-input').addEventListener('input',()=>{if(emailChallenge){emailChallenge='';find('#email-message').textContent='邮箱地址已更改，请重新获取验证码。';}});
  find('#password-send').addEventListener('click',()=>sendEmail('password_change'));
  find('#email-form').addEventListener('submit',async event=>{
    event.preventDefault();if(busy)return;if(!emailChallenge){find('#email-message').textContent='请先获取邮箱验证码';return;}setBusy(true);
    try{announceSession(await request('/account/email/confirm',{method:'POST',body:JSON.stringify({purpose:'email_bind',current_password:find('#email-password').value,email:find('#profile-email-input').value.trim(),challenge_id:emailChallenge,code:find('#email-code').value})}));emailChallenge='';find('#email-form').reset();resetPassword();find('#email-message').textContent='邮箱已验证并绑定。';}
    catch(error){find('#email-message').textContent=error.message;}finally{setBusy(false);}
  });
  find('#password-form').addEventListener('submit',async event=>{
    event.preventDefault();if(busy)return;
    if(find('#security-new').value!==find('#security-confirm').value){find('#password-message').textContent='两次新密码不一致';find('#security-confirm').focus();return;}
    if(account.email&&!passwordChallenge){find('#password-message').textContent='请先获取已绑定邮箱的验证码';return;}
    setBusy(true);
    try{const data=await request('/account/password',{method:'POST',body:JSON.stringify({current_password:find('#security-current').value,new_password:find('#security-new').value,password_confirm:find('#security-confirm').value,...(account.email?{challenge_id:passwordChallenge,code:find('#password-code').value}: {})})});
      if(!/^[a-f0-9]{64}$/.test(data.access_token))throw new Error('会话无法更新，请重新登录');sessionStorage.setItem('account:session',JSON.stringify(data));account=data.account;dispatchEvent(new Event('account:changed'));find('#password-form').reset();passwordChallenge='';resetPassword();render();find('#password-message').textContent='密码已更新，所有旧会话已退出，当前会话已更新。';}
    catch(error){find('#password-message').textContent=error.message;}finally{setBusy(false);}
  });

  // 退出：服务端撤销成功后再清当前会话，保留本标签页的匿名资源凭据。
  find('#account-logout').addEventListener('click', async () => {
    if (busy) return;
    setBusy(true); find('#account-alert').textContent = '';
    try {
      try { await request('/auth/logout', { method: 'POST' }); }
      catch (error) { if (error.status !== 401) throw error; }
      clearSession(); account = null;dispatchEvent(new Event('account:changed'));void loadAvatar();
      find('#account-notice').textContent = '已退出当前会话。账户记录仍保留，重新登录可找回。';
    } catch (error) { find('#account-alert').textContent = error.message; }
    finally { setBusy(false); render(); }
  });

  // 删除：关闭或撤回不发送请求；密码确认失败与进行中保护仍由服务端判断。
  const dialog = find('#account-delete-dialog');
  find('#account-delete-open').addEventListener('click', () => {
    find('#account-delete-password').value = ''; find('#account-delete-error').textContent = ''; dialog.showModal();
  });
  find('#account-delete-cancel').addEventListener('click', () => dialog.close());
  dialog.addEventListener('cancel', (event) => { if (busy) event.preventDefault(); });
  dialog.addEventListener('close', () => { find('#account-delete-password').value = ''; });
  find('#account-delete-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (busy) return;
    setBusy(true); find('#account-delete-error').textContent = '';
    try {
      await request('/account', { method: 'DELETE', body: JSON.stringify({ password: find('#account-delete-password').value }) });
      clearSession(); account = null; dialog.close();
      find('#account-notice').textContent = '账户及所属内容已删除。';
    } catch (error) { find('#account-delete-error').textContent = error.message; }
    finally { find('#account-delete-password').value = ''; setBusy(false); render(); }
  });
  find('#account-retry').addEventListener('click', () => void check());
  find('#account-overview-retry').addEventListener('click',()=>void overview());
  find('#account-username').addEventListener('input',()=>{find('#account-username').removeAttribute('aria-invalid');find('#account-username-status').textContent='';});
  document.querySelectorAll('.profile-sections a').forEach(link=>link.addEventListener('click',()=>{const target=find(link.getAttribute('href'));if(target?.tagName==='DETAILS')target.open=true;}));
  addEventListener('pageshow', event => { if (event.persisted) void check(); });
  addEventListener('pagehide',()=>{if(avatarUrl)URL.revokeObjectURL(avatarUrl);cooldown.forEach(clearInterval);cooldown.clear();});
  addEventListener('account:expired',()=>{account=null;loadedAccount='';setBusy(false);render();void loadAvatar();find('#account-alert').textContent='登录已失效，请重新登录。';});
  if (returnPath || returnCollection) find('#account-form-description').textContent = '登录成功后返回刚才的页面，继续你的操作。';
  void check();
})();
