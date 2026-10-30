// Keep each page's timeout, cancellation and error wording; never retry a write.
async function guardedFetch(url, options) {
  const identity = readSession()?.access_token || '';
  const response = await fetch(url, options);
  const read = response.json.bind(response);
  response.json = async () => {
    const data = await read();
    if ((readSession()?.access_token || '') !== identity) throw Object.assign(new Error('会话已变化，请重新读取。'), { status: 401 });
    return data;
  };
  return response;
}
