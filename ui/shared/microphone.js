// Device selection never requests permission; capture is only started by a user action.
function microphoneError(error) {
  const messages = {
    NotAllowedError: '麦克风未获授权。请在浏览器地址栏的站点权限中允许麦克风，再点击开始；内置浏览器不支持时，请用 Edge 或 Chrome 打开本页。',
    NotFoundError: '没有找到麦克风，请连接设备后刷新设备列表。',
    NotReadableError: '麦克风无法读取，可能被其他应用占用。请关闭占用程序，并检查系统麦克风权限。',
    OverconstrainedError: '所选麦克风已不可用，请切回系统默认或刷新设备列表。',
    SecurityError: '浏览器限制了录音，请用 HTTPS 或 localhost 地址在 Edge、Chrome 中打开。',
    AbortError: '麦克风启动中断，请重新选择设备后再试。'
  };
  return new Error(messages[error.name] || error.message || '麦克风暂不可用，请重试或上传录音。');
}
function microphonePicker(select, status) {
  const supported = () => typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia && typeof AudioContext !== 'undefined';
  let generation = 0;
  async function refresh() {
    const attempt = ++generation;
    if (!supported()) { status.textContent = '当前浏览器未开放录音，请在 Edge 或 Chrome 中打开 localhost 页面。仍可上传录音。'; return; }
    status.textContent = '使用系统默认麦克风；点击开始时才会请求录音授权。';
    if (!navigator.mediaDevices.enumerateDevices) return;
    try {
      const devices = (await navigator.mediaDevices.enumerateDevices()).filter(item => item.kind === 'audioinput' && item.deviceId && item.deviceId !== 'default');
      if (attempt !== generation) return;
      const previous = select.value;
      select.replaceChildren();
      const add = (value, label) => { const option = document.createElement('option'); option.value = value; option.textContent = label; select.append(option); };
      add('', '系统默认麦克风');
      devices.forEach((item, index) => add(item.deviceId, item.label || '麦克风 ' + (index + 1)));
      select.value = devices.some(item => item.deviceId === previous) ? previous : '';
      status.textContent = '点击开始后授权麦克风；首次授权后可查看设备名称。';
    } catch { status.textContent = '暂时无法读取设备列表，可使用系统默认麦克风。'; }
  }
  async function acquire() {
    if (!supported()) throw new Error('当前浏览器不支持录音，请用 Edge 或 Chrome 打开本页，或上传录音。');
    let expired = false, timer;
    const pending = navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, ...(select.value ? { deviceId: { exact: select.value } } : {}) } });
    pending.then(media => { if (expired) media.getTracks().forEach(track => track.stop()); }, () => {});
    try {
      return await Promise.race([pending, new Promise((_, reject) => { timer = setTimeout(() => { expired = true; reject(new Error('等待麦克风授权超时。请处理浏览器的权限提示，再重新开始。')); }, 20000); })]);
    } finally { clearTimeout(timer); }
  }
  return { supported, refresh, acquire };
}
