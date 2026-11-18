import { useEffect, useRef, useState } from 'react';
import { getAccess } from '../lib/access';
import { getAccountSession } from '../lib/account';
import { notice } from '../assistant/types';
import {
  Action,
  initialState,
  parsePracticeEvent,
  PendingAnswer,
  reduceStudio,
  StudioState,
  terminal,
  validPending,
} from './state';

export function useStudio(interviewId: string) {
  const [state, render] = useState<StudioState>(initialState);
  const current = useRef(state);
  const socket = useRef<WebSocket | null>(null);
  const credential = useRef<string | null>(null);
  const transport = useRef({ connect: () => {}, stop: () => {} });
  const [cancelling, setCancelling] = useState(false);
  const [cancelError, setCancelError] = useState('');
  const cancelRequest = useRef<AbortController | null>(null);
  const owner = useRef(getAccountSession()?.account.id || 'anonymous');
  const pendingKey = `interview:${interviewId}:pending:${owner.current}`;
  function update(action: Action) {
    const next = reduceStudio(current.current, action);
    current.current = next;
    render(next);
    try {
      if (next.pending) sessionStorage.setItem(pendingKey, JSON.stringify(next.pending));
      else sessionStorage.removeItem(pendingKey);
    } catch {
      /* In-memory pending survives reconnect; never claim durable browser storage. */
    }
  }
  function identity() {
    if (credential.current && getAccess('interview', interviewId) !== credential.current) {
      transport.current.stop();
      cancelRequest.current?.abort();
      update({ type: 'identity' });
      return false;
    }
    return true;
  }
  useEffect(() => {
    let disposed = false,
      retry = 0;
    let reconnect: ReturnType<typeof setTimeout> | undefined,
      watchdog: ReturnType<typeof setTimeout> | undefined;
    function stop() {
      clearTimeout(reconnect);
      clearTimeout(watchdog);
      const ws = socket.current;
      socket.current = null;
      if (ws) {
        ws.onmessage = ws.onclose = ws.onopen = null;
        ws.close();
      }
    }
    function connect() {
      if (disposed || terminal(current.current) || !identity()) return;
      stop();
      credential.current = getAccess('interview', interviewId);
      if (!credential.current || !/^[a-f0-9]{32}$/.test(interviewId)) {
        update({ type: 'identity' });
        return;
      }
      update({ type: 'phase', phase: 'connecting', error: '' });
      try {
        const socketBase = document.body.dataset.wsBase || location.origin.replace(/^http/, 'ws');
        const url = socketBase + '/ws/interview/' + interviewId;
        const ws = new WebSocket(url, ['interview', credential.current]);
        socket.current = ws;
        watchdog = setTimeout(() => ws.close(), 195000);
        ws.onopen = () => {
          if (!disposed && ws === socket.current && identity())
            ws.send(JSON.stringify({ type: 'start' }));
        };
        ws.onmessage = (event) => {
          if (disposed || ws !== socket.current || !identity()) return;
          try {
            if (typeof event.data !== 'string' || event.data.length > 4000000)
              throw new Error('消息过长，请重新同步。');
            const data = parsePracticeEvent(JSON.parse(event.data));
            update({ type: 'event', event: data });
            if (data.type === 'snapshot') {
              retry = 0;
              clearTimeout(watchdog);
              if (current.current.pending && current.current.phase === 'active')
                ws.send(JSON.stringify(current.current.pending));
            }
            if (data.type === 'error' && data.code === 'stale_turn')
              ws.send(JSON.stringify({ type: 'start' }));
            if (
              current.current.denied ||
              terminal(current.current) ||
              current.current.phase === 'error'
            )
              stop();
          } catch (error) {
            update({ type: 'phase', phase: 'error', error: (error as Error).message });
            stop();
          }
        };
        ws.onclose = (event) => {
          if (disposed || ws !== socket.current || terminal(current.current)) return;
          clearTimeout(watchdog);
          if (event.code === 4403 || event.code === 1008) {
            update({ type: 'identity' });
            stop();
            return;
          }
          if (++retry > 6) {
            update({
              type: 'phase',
              phase: 'error',
              error: '连接暂不可用，请检查网络后重新同步。',
            });
            return;
          }
          update({ type: 'phase', phase: 'connecting' });
          reconnect = setTimeout(connect, Math.min(1000 * 2 ** (retry - 1), 10000));
        };
      } catch {
        update({ type: 'phase', phase: 'error', error: '连接暂不可用，请重新同步。' });
      }
    }
    transport.current = {
      connect: () => {
        retry = 0;
        connect();
      },
      stop,
    };
    try {
      const pending: unknown = JSON.parse(sessionStorage.getItem(pendingKey) || 'null');
      if (validPending(pending)) update({ type: 'submit', pending });
      else sessionStorage.removeItem(pendingKey);
    } catch {
      /* Invalid browser data never becomes an answer. */
    }
    function leave() {
      disposed = true;
      stop();
      cancelRequest.current?.abort();
    }
    function restore(event: PageTransitionEvent) {
      if (event.persisted && identity()) {
        disposed = false;
        connect();
      }
    }
    function before(event: BeforeUnloadEvent) {
      if (
        !terminal(current.current) &&
        (current.current.pending || current.current.text || current.current.code)
      ) {
        event.preventDefault();
        event.returnValue = '';
      }
    }
    const expires = setInterval(identity, 15000);
    addEventListener('account:changed', identity);
    addEventListener('account:expired', identity);
    addEventListener('pagehide', leave);
    addEventListener('pageshow', restore);
    addEventListener('beforeunload', before);
    connect();
    return () => {
      leave();
      clearInterval(expires);
      removeEventListener('account:changed', identity);
      removeEventListener('account:expired', identity);
      removeEventListener('pagehide', leave);
      removeEventListener('pageshow', restore);
      removeEventListener('beforeunload', before);
    };
  }, [interviewId]);

  function submit(skip = false) {
    const s = current.current,
      ws = socket.current;
    if (
      !identity() ||
      cancelling ||
      s.pending ||
      s.phase !== 'active' ||
      !s.question ||
      !ws ||
      ws.readyState !== WebSocket.OPEN
    )
      return;
    const text = skip ? '跳过' : s.text.trim(),
      code = !skip && s.question.is_coding ? s.code : '';
    if (
      (!text && !code.trim()) ||
      Array.from(text).length > 20000 ||
      new TextEncoder().encode(code).length > 16384
    ) {
      notice('请检查回答或代码的长度。', 'error');
      return;
    }
    if (skip && (s.text || s.code))
      current.current = { ...s, recovery: [s.text, s.code].filter(Boolean).join('\n\n') };
    const pending: PendingAnswer = {
      type: 'answer',
      message_id: crypto.randomUUID(),
      turn_id: s.question.turn_id,
      version: s.version,
      text: text || '（代码实现如下）',
      ...(code ? { code } : {}),
    };
    update({ type: 'submit', pending });
    try {
      ws.send(JSON.stringify(pending));
    } catch {
      ws.close();
      notice('发送中断，将在同步后核对保存状态。', 'error');
    }
  }
  async function cancel() {
    if (!identity() || cancelling || terminal(current.current)) return false;
    setCancelling(true);
    setCancelError('');
    const controller = new AbortController();
    cancelRequest.current = controller;
    const timer = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch('/api/interview/' + interviewId + '/cancel', {
        method: 'POST',
        cache: 'no-store',
        signal: controller.signal,
        headers: { 'X-Interview-Token': credential.current || '' },
      });
      const data = await response.json();
      if (!identity()) return false;
      if (!response.ok)
        throw new Error(typeof data.detail === 'string' ? data.detail : '取消未完成，请重新同步。');
      update({ type: 'cancel' });
      transport.current.stop();
      notice('本场练习已取消，已保存回答可在报告中查看。');
      return true;
    } catch (error) {
      if (identity())
        setCancelError(
          controller.signal.aborted ? '请求超时，请同步后核对结果。' : (error as Error).message
        );
      return false;
    } finally {
      clearTimeout(timer);
      cancelRequest.current = null;
      setCancelling(false);
    }
  }
  return {
    state,
    cancelling,
    cancelError,
    cancel,
    submit,
    sync: () => transport.current.connect(),
    setDraft: (text: string, code = current.current.code) => update({ type: 'draft', text, code }),
  };
}
