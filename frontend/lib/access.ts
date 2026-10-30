import { getAccountSession } from "./account";

/** 资源与账户凭据仅保存在当前浏览器标签页，刷新后仍可恢复。 */
export function saveAccess(kind: "resume" | "interview", id: string, token: string) {
  sessionStorage.setItem(`${kind}:${id}:token`, token);
}
export function getAccess(kind: "resume" | "interview", id: string): string | null {
  return getAccountSession()?.access_token ?? getAnonymousAccess(kind, id);
}

export function getAnonymousAccess(kind: "resume" | "interview", id: string): string | null {
  try { return sessionStorage.getItem(`${kind}:${id}:token`); }
  catch { return null; }
}

export function forgetAnonymousAccess(id: string) {
  try { sessionStorage.removeItem(`interview:${id}:token`); } catch { /* 服务端认领已经生效。 */ }
}

/** 只从本标签页已有凭据发现记录；不向服务端枚举面试。 */
export function listInterviewIds(): string[] {
  try {
    const ids: string[] = [];
    for (let i = sessionStorage.length - 1; i >= 0 && ids.length < 50; i--) {
      const key = sessionStorage.key(i);
      const match = key?.match(/^interview:([a-f0-9]{32}):token$/);
      if (match && /^[a-f0-9]{64}$/.test(sessionStorage.getItem(key!) ?? "")) ids.push(match[1]);
    }
    return ids;
  } catch { return []; }
}
