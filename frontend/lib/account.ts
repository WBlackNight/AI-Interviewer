export interface AccountInfo { id: string; username: string }
export interface AccountSession { account: AccountInfo; access_token: string; expires_at: string }
const KEY = "account:session";

export function getAccountSession(): AccountSession | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(KEY) ?? "null") as AccountSession | null;
    if (!value || !/^[a-f0-9]{64}$/.test(value.access_token) ||
        !/^[a-f0-9]{32}$/.test(value.account?.id) || typeof value.account?.username !== "string" ||
        !(Date.parse(value.expires_at) > Date.now())) return null;
    return value;
  } catch { return null; }
}

export function saveAccountSession(value: AccountSession) { sessionStorage.setItem(KEY, JSON.stringify(value)); }
export function clearAccountSession() { sessionStorage.removeItem(KEY); }
