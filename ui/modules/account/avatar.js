  /* Avatar selection is local; only the confirmed PNG crop is uploaded. */
  const avatarDialog = find('#avatar-dialog');
  let avatarSelection = 0, avatarIdentity = '';
  function clearAvatarSelection() {
    avatarSelection++; selectedFile = null; crop.clear(); find('#profile-file').value = '';
    find('#avatar-file-name').textContent = ''; find('#avatar-choose').textContent = '选择图片';
    find('#avatar-drop').classList.remove('is-drag-over'); setBusy(busy);
  }
  function openAvatar() {
    if (busy || !account) return;
    clearAvatarSelection(); avatarIdentity = session()?.access_token || '';
    find('#avatar-message').textContent = ''; avatarDialog.showModal(); find('#avatar-choose').focus();
  }
  find('#profile-avatar-open').addEventListener('click', openAvatar);
  find('#avatar-open').addEventListener('click', openAvatar);
  find('#avatar-choose').addEventListener('click', () => {if (!busy) find('#profile-file').click();});
  for (const id of ['avatar-close', 'avatar-cancel']) find('#' + id).addEventListener('click', () => {if (!busy) avatarDialog.close();});
  avatarDialog.addEventListener('cancel', event => {if (busy) event.preventDefault();});
  avatarDialog.addEventListener('close', clearAvatarSelection);
  avatarDialog.addEventListener('click', event => {
    const rect = avatarDialog.getBoundingClientRect();
    if (!busy && event.target === avatarDialog && (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom)) avatarDialog.close();
  });
  async function chooseAvatar(file) {
    if (busy || !file) return;
    clearAvatarSelection(); const version = avatarSelection;
    find('#avatar-message').textContent = '正在读取图片…';
    try {
      if (!/^image\/(png|jpeg|webp)$/.test(file.type) || !/\.(png|jpe?g|webp)$/i.test(file.name)) throw new Error('请选择JPG、PNG或WebP图片。');
      if (!file.size || file.size > 2097152) throw new Error('图片不能为空，大小不能超过2MB。');
      if (!await crop.load(file) || version !== avatarSelection || !avatarDialog.open || session()?.access_token !== avatarIdentity) return;
      selectedFile = file; find('#avatar-file-name').textContent = file.name + ' · ' + Math.ceil(file.size / 1024) + ' KB';
      find('#avatar-choose').textContent = '更换图片';
      find('#avatar-message').textContent = '拖动图片或调整滑块，确认预览后保存。';
    } catch (error) {
      if (version === avatarSelection) {find('#avatar-message').textContent = error.message || '图片无法读取，请重新选择。'; notify(find('#avatar-message').textContent, 'error');}
    } finally {setBusy(busy);}
  }
  find('#profile-file').addEventListener('change', () => {const file = find('#profile-file').files[0]; void chooseAvatar(file);});
  const avatarDrop = find('#avatar-drop');
  for (const type of ['dragenter', 'dragover']) avatarDrop.addEventListener(type, event => {event.preventDefault(); if (!busy) avatarDrop.classList.add('is-drag-over');});
  for (const type of ['dragleave', 'drop']) avatarDrop.addEventListener(type, event => {event.preventDefault(); avatarDrop.classList.remove('is-drag-over');});
  avatarDrop.addEventListener('drop', event => {
    if (busy) return;
    if (event.dataTransfer?.files.length !== 1) {find('#avatar-message').textContent = '请一次选择一张图片。'; return;}
    void chooseAvatar(event.dataTransfer.files[0]);
  });
  find('#avatar-form').addEventListener('submit', async event => {
    event.preventDefault(); if (busy || !selectedFile) return;
    const identity = session()?.access_token; setBusy(true); find('#avatar-message').textContent = '正在保存裁剪后的头像…';
    try {
      const output = await crop.blob();
      if (session()?.access_token !== identity) throw new Error('登录状态已变化，请重新选择头像。');
      announceSession(await request('/account/avatar?size=' + output.size, {method:'POST',body:output.data,headers:{'Content-Type':'image/png'}}));
      selectedFile = null; avatarDialog.close(); notify('头像已更新');
      await loadAvatar().catch(() => notify('头像已保存，当前预览暂未刷新，请稍后重新打开账户页。', 'info'));
    } catch (error) {find('#avatar-message').textContent = error.message; notify(error.message, 'error');}
    finally {setBusy(false);}
  });
  find('#avatar-remove').addEventListener('click', async () => {
    if (busy) return; setBusy(true);
    try {announceSession(await request('/account/avatar', {method:'DELETE'})); await loadAvatar(); avatarDialog.close(); notify('已恢复默认头像');}
    catch (error) {find('#avatar-message').textContent = error.message; notify(error.message, 'error');}
    finally {setBusy(false);}
  });
  function checkAvatarIdentity() {if (avatarDialog.open && session()?.access_token !== avatarIdentity) {avatarDialog.close(); clearAvatarSelection();}}
  addEventListener('account:changed', checkAvatarIdentity); addEventListener('account:expired', checkAvatarIdentity);
  addEventListener('pagehide', () => {if (avatarDialog.open) avatarDialog.close(); clearAvatarSelection();});
