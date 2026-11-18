function setupRecovery(find,request,setBusy,isBusy){
  let captcha=null,identity=null,challenge='',timer=null,remaining=0,loading=false;
  const message=find('#recovery-message'),send=find('#recovery-send');
  async function refresh(){
    if(loading||isBusy())return;loading=true;captcha=null;send.disabled=true;
    find('#recovery-captcha-code').value='';message.textContent='正在加载图形验证码…';
    try{const data=await request('/auth/captcha',{},true);if(!data.image?.startsWith('data:image/png;base64,'))throw new Error('验证码读取失败');captcha=data;find('#recovery-captcha-image').src=data.image;message.textContent='填写用户名和已绑定邮箱，验证后设置新密码。';}
    catch(error){message.textContent=error.message;}finally{loading=false;send.disabled=isBusy()||remaining>0||!captcha;}
  }
  find('#account-recovery').addEventListener('toggle',()=>{if(find('#account-recovery').open&&!captcha)void refresh();});
  find('#recovery-refresh').addEventListener('click',refresh);
  for(const id of ['recovery-username','recovery-email'])find('#'+id).addEventListener('input',()=>{if(challenge)message.textContent='账号或邮箱已修改，请重新获取验证码。';identity=null;challenge='';find('#recovery-reset').hidden=true;});
  find('#recovery-request').addEventListener('submit',async event=>{
    event.preventDefault();if(isBusy()||remaining||!captcha)return;setBusy(true);
    try{
      challenge='';identity={username:find('#recovery-username').value.trim(),email:find('#recovery-email').value.trim()};
      const data=await request('/auth/recovery/code',{method:'POST',body:JSON.stringify({...identity,captcha_id:captcha.captcha_id,captcha_code:find('#recovery-captcha-code').value})},true);
      challenge=data.challenge_id;find('#recovery-reset').hidden=false;remaining=60;
      clearInterval(timer);timer=setInterval(()=>{remaining--;send.textContent=remaining>0?remaining+'秒后可重发':'重新发送验证码';send.disabled=isBusy()||remaining>0||!captcha;if(remaining<=0){clearInterval(timer);timer=null;}},1000);
      message.textContent='若用户名与已绑定邮箱匹配，验证码将发送至该邮箱，10分钟内有效。本机测试请查看测试收件箱。';
    }catch(error){message.textContent=error.message;}
    finally{setBusy(false);captcha=null;send.disabled=true;}
  });
  find('#recovery-reset').addEventListener('submit',async event=>{
    event.preventDefault();if(isBusy()||!identity||!challenge)return;
    if(find('#recovery-new').value!==find('#recovery-confirm').value){message.textContent='两次新密码不一致';return;}
    setBusy(true);
    try{
      await request('/auth/recovery/reset',{method:'POST',body:JSON.stringify({...identity,challenge_id:challenge,code:find('#recovery-code').value,new_password:find('#recovery-new').value,password_confirm:find('#recovery-confirm').value})},true);
      message.textContent='密码已重置，旧会话已退出。请使用新密码登录。';challenge='';find('#recovery-reset').hidden=true;
      find('#account-username').value=identity.username;find('#account-password').focus();
    }catch(error){message.textContent=error.message;}
    finally{find('#recovery-new').value='';find('#recovery-confirm').value='';setBusy(false);}
  });
  addEventListener('pagehide',()=>{clearInterval(timer);remaining=0;captcha=null;identity=null;challenge='';find('#account-recovery').open=false;find('#recovery-reset').reset();find('#recovery-reset').hidden=true;send.textContent='发送邮箱验证码';});
  return {update:()=>{send.disabled=isBusy()||remaining>0||!captcha||loading;}};
}
