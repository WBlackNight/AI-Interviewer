import { getAccountSession } from '../lib/account';
export type Overview = {
  role: 'administrator' | 'viewer';
  permissions: { export: boolean; review: boolean; audit: boolean };
  generated_at: string;
  days: number;
  timezone: string;
  metrics: {
    interviews: number;
    finished: number;
    accounts: number;
    new_accounts: number;
    questions: number;
    positions: number;
    completion_rate: number;
    scored_answers: number;
    answer_average: number | null;
  };
  trend: { date: string; started: number; completed: number }[];
  statuses: { key: string; count: number }[];
  coverage: { position: string; name: string; count: number }[];
  roles: { id: string; name: string }[];
};
export type Row = {
  review_status?: string;
  review_note?: string;
  review_version?: number;
  content_hash?: string;
  review_stale?: boolean;
  reviewed_at?: string | null;
  actor?: string;
  action?: string;
  outcome?: string;
  resource?: string;
  request_id?: string;
  details?: Record<string, unknown>;
  id: string;
  position?: string;
  status?: string;
  difficulty?: string;
  started_at?: string | null;
  ended_at?: string | null;
  username?: string;
  scored_answers?: number;
  nickname?: string;
  created_at?: string;
  email_bound?: boolean;
  active_sessions?: number;
  interviews?: number;
  is_admin?: boolean;
  theme?: string;
  content?: string;
  source?: string;
  is_coding?: boolean;
};
export type Page = { items: Row[]; total: number; offset: number; limit: number };
export class AdminError extends Error {
  constructor(
    message: string,
    public status = 0,
    public requestId = ''
  ) {
    super(message);
  }
}
export async function adminRequest<T>(
  path: string,
  identity: string,
  signal: AbortSignal,
  options: { method?: string; body?: string } = {}
): Promise<T> {
  const controller = new AbortController();
  const cancel = () => controller.abort();
  if (signal.aborted) cancel();
  else signal.addEventListener('abort', cancel, { once: true });
  const timer = setTimeout(cancel, 12000);
  try {
    const response = await fetch(path, {
      ...options,
      headers: {
        Authorization: 'Bearer ' + identity,
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      },
      signal: controller.signal,
      cache: 'no-store',
    });
    if (getAccountSession()?.access_token !== identity)
      throw new AdminError('登录账户已变化，请重新打开工作台。', 401);
    const data = await response.json();
    if (getAccountSession()?.access_token !== identity)
      throw new AdminError('登录账户已变化，请重新打开工作台。', 401);
    if (!response.ok)
      throw new AdminError(
        typeof data.detail === 'string' ? data.detail : '读取失败，请检查筛选条件后重试。',
        response.status,
        response.headers?.get('X-Request-ID') || ''
      );
    return data as T;
  } catch (error) {
    if (error instanceof AdminError) throw error;
    throw new AdminError(
      (error as Error).name === 'AbortError'
        ? '请求超时，请稍后重试。'
        : '暂时连接不上服务，请检查网络后重试。'
    );
  } finally {
    clearTimeout(timer);
    signal.removeEventListener('abort', cancel);
  }
}
export async function downloadCsv(path: string, identity: string, signal: AbortSignal) {
  const controller = new AbortController();
  const cancel = () => controller.abort();
  signal.addEventListener('abort', cancel, { once: true });
  if (signal.aborted) cancel();
  const timer = setTimeout(cancel, 12000);
  try {
    const response = await fetch(path, {
      headers: { Authorization: 'Bearer ' + identity },
      signal: controller.signal,
      cache: 'no-store',
    });
    if (getAccountSession()?.access_token !== identity)
      throw new AdminError('登录已失效，请重新登录。', 401);
    if (!response.ok) {
      const data = await response.json();
      throw new AdminError(
        typeof data.detail === 'string' ? data.detail : '导出失败，请重试。',
        response.status,
        response.headers.get('X-Request-ID') || ''
      );
    }
    if (!response.headers.get('Content-Type')?.startsWith('text/csv'))
      throw new AdminError('文件格式异常，请重试。');
    const blob = await response.blob();
    if (getAccountSession()?.access_token !== identity || signal.aborted)
      throw new AdminError('登录已失效或导出已取消。', 401);
    if (blob.size > 5 * 1024 * 1024) throw new AdminError('文件超过5MB，请缩小筛选范围。');
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download =
      'qingzhan-' + new URL(path, location.origin).searchParams.get('resource') + '.csv';
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    return Number(response.headers.get('X-Export-Rows') || 0);
  } catch (error) {
    if (error instanceof AdminError) throw error;
    throw new AdminError('导出未完成，请检查网络后重试。');
  } finally {
    clearTimeout(timer);
    signal.removeEventListener('abort', cancel);
  }
}
