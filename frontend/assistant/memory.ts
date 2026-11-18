const identifier = (value: unknown): value is string =>
  typeof value === 'string' && /^[a-f0-9]{32}$/.test(value);
export function rememberedConversation(accountId?: string): string | null {
  if (!identifier(accountId)) return null;
  try {
    const value = sessionStorage.getItem('qing:last-conversation:' + accountId);
    return identifier(value) ? value : null;
  } catch {
    return null;
  }
}
export function rememberConversation(accountId: string | undefined, conversationId: string | null) {
  if (!identifier(accountId) || (conversationId !== null && !identifier(conversationId))) return;
  try {
    if (conversationId)
      sessionStorage.setItem('qing:last-conversation:' + accountId, conversationId);
    else sessionStorage.removeItem('qing:last-conversation:' + accountId);
  } catch {
    /* Server history remains available. */
  }
}
