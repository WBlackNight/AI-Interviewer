import { ChatEvent, session } from './types';

export async function jsonRequest<T>(
  path: string,
  identity: string,
  options: RequestInit = {}
): Promise<T> {
  const controller = new AbortController();
  const cancel = () => controller.abort();
  if (options.signal?.aborted) cancel();
  else options.signal?.addEventListener('abort', cancel, { once: true });
  const timer = setTimeout(() => controller.abort(), 12000);
  try {
    const response = await fetch(path, {
      ...options,
      cache: 'no-store',
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...(identity ? { Authorization: 'Bearer ' + identity } : {}),
      },
    });
    if (identity !== (session()?.access_token || ''))
      throw new Error('账户已变化，请重新打开页面。');
    const body = await response.json();
    if (identity !== (session()?.access_token || ''))
      throw new Error('账户已变化，请重新打开页面。');
    if (!response.ok)
      throw new Error(typeof body.detail === 'string' ? body.detail : '操作暂未完成，请稍后重试。');
    return body as T;
  } catch (error) {
    if ((error as Error).name === 'AbortError') throw new Error('读取超时，请重试。');
    throw error;
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener('abort', cancel);
  }
}

export function parseFrame(frame: string): ChatEvent | null {
  const data = frame
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trimStart())
    .join('\n');
  if (!data) return null;
  const value = JSON.parse(data);
  if (
    !value ||
    typeof value !== 'object' ||
    !['stage', 'evidence', 'delta', 'revision', 'mode', 'done', 'error'].includes(value.type)
  ) {
    throw new Error('回答格式异常，请重新打开对话。');
  }
  const short = (text: unknown, limit: number) => typeof text === 'string' && text.length <= limit;
  const valid =
    value.type === 'stage'
      ? short(value.label, 200)
      : value.type === 'delta'
        ? short(value.text, 6000)
        : value.type === 'revision'
          ? short(value.text, 6000) && short(value.reason, 300)
          : value.type === 'error'
            ? short(value.message, 300)
            : value.type === 'done'
              ? Number.isInteger(value.version) && value.version >= 0
              : value.type === 'mode'
                ? ['ai', 'local', 'fallback'].includes(value.value) && short(value.label, 300)
                : Array.isArray(value.sources) &&
                  value.sources.length <= 4 &&
                  value.sources.every(
                    (source: Record<string, unknown>) =>
                      source &&
                      short(source.id, 10) &&
                      short(source.title, 300) &&
                      short(source.href, 500)
                  ) &&
                  Array.isArray(value.actions) &&
                  value.actions.length <= 3 &&
                  value.actions.every(
                    (action: Record<string, unknown>) =>
                      action && short(action.label, 60) && short(action.href, 500)
                  );
  if (!valid) throw new Error('回答格式异常，请重新打开对话。');
  return value as ChatEvent;
}

export async function streamChat(
  path: string,
  body: object,
  identity: string,
  signal: AbortSignal,
  receive: (value: ChatEvent) => void
) {
  const response = await fetch(path, {
    method: 'POST',
    body: JSON.stringify(body),
    signal,
    cache: 'no-store',
    headers: {
      'Content-Type': 'application/json',
      ...(identity ? { Authorization: 'Bearer ' + identity } : {}),
    },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === 'string' ? error.detail : '回答暂不可用，请稍后重试。');
  }
  if (!response.headers.get('content-type')?.includes('text/event-stream') || !response.body) {
    throw new Error('回答通道暂不可用，请重试。');
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '',
    completed = false,
    characters = 0;
  try {
    while (true) {
      const part = await reader.read();
      if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
      if (identity !== (session()?.access_token || ''))
        throw new Error('账户已变化，已停止展示此对话。');
      buffer += decoder.decode(part.value, { stream: !part.done });
      buffer = buffer.replace(/\r\n/g, '\n');
      if (buffer.length > 64000) throw new Error('回答内容过长，请重新提问。');
      let end;
      while ((end = buffer.indexOf('\n\n')) >= 0) {
        const frame = buffer.slice(0, end);
        buffer = buffer.slice(end + 2);
        const event = parseFrame(frame);
        if (event?.type === 'delta') {
          characters += event.text.length;
          if (characters > 6000) throw new Error('回答内容过长，请缩小问题范围。');
        }
        if (event?.type === 'revision') characters = event.text.length;
        if (event?.type === 'error') throw new Error(event.message);
        if (event?.type === 'done') completed = true;
        if (event) receive(event);
      }
      if (part.done) break;
    }
    if (!completed) throw new Error('连接中断，当前片段可能未保存。请重试或重新打开对话。');
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
