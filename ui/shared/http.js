// JSON transport: bounded lifetime, caller cancellation, identity checks and no write retries.
async function requestJSON(path, { auth = false, timeout = 10000, signal, ...options } = {}) {
  const identity = auth ? readSession()?.access_token : '';
  if (auth && !identity) throw Object.assign(new Error('请先登录后继续。'), { status: 401 });
  const controller = new AbortController();
  const cancel = () => controller.abort();
  if (signal?.aborted) cancel(); else signal?.addEventListener('abort', cancel, { once: true });
  const timer = setTimeout(cancel, timeout);
  const ensureIdentity = () => {
    if (auth && readSession()?.access_token !== identity) {
      throw Object.assign(new Error('账户已变化，请重新读取。'), { status: 401 });
    }
  };
  try {
    const response = await fetch(path, { ...options, cache: 'no-store', signal: controller.signal,
      headers: { ...(auth ? { Authorization: 'Bearer ' + identity } : {}), ...options.headers } });
    ensureIdentity();
    let data;
    try { data = await response.json(); }
    catch (error) { if (error.name === 'AbortError') throw error; throw new Error('返回内容暂时无法读取，请重试。'); }
    ensureIdentity();
    if (!response.ok) throw Object.assign(new Error(typeof data?.detail === 'string' ? data.detail :
      response.status === 401 ? '登录已过期，请重新登录。' : '操作暂未完成，请稍后重试。'), { status: response.status });
    return data;
  } catch (error) {
    if (error.name === 'AbortError' && !signal?.aborted) throw Object.assign(new Error('等待超时，请稍后重试。'), { code: 'TIMEOUT' });
    if (error instanceof TypeError) throw new Error('连接暂时中断，请检查网络后重试。');
    throw error;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', cancel);
  }
}
