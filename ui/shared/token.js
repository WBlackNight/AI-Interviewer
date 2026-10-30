function interviewToken(id) {
  const account = readSession();
  if (account) return account.access_token;
  try {
    const value = sessionStorage.getItem('interview:' + id + ':token');
    return /^[a-f0-9]{64}$/.test(value || '') ? value : null;
  } catch { return null; }
}
