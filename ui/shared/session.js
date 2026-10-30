function readSession() {
  try {
    const value = JSON.parse(sessionStorage.getItem('account:session'));
    return value && /^[a-f0-9]{64}$/.test(value.access_token)
      && /^[a-f0-9]{32}$/.test(value.account?.id)
      && typeof value.account.username === 'string'
      && Date.parse(value.expires_at) > Date.now() ? value : null;
  } catch { return null; }
}
