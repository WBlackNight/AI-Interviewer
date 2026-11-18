import { useCallback, useEffect, useRef, useState } from 'react';
import { Conversation, Message, notice, Role, session, Session } from './types';
import { jsonRequest, streamChat } from './transport';
import { rememberConversation, rememberedConversation } from './memory';

export function useAssistant() {
  const [identity, setIdentity] = useState<Session | null>(session);
  const [roles, setRoles] = useState<Record<string, Role>>({});
  const [position, setPosition] = useState('java_backend');
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [current, setCurrent] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState('');
  const [error, setError] = useState('');
  const [includeFocus, setIncludeFocus] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const working = useRef(false);
  const retryTurn = useRef<{ text: string; request_id: string; base: Message[] } | null>(null);
  const token = identity?.access_token || '';
  const activeToken = useRef(token);
  const resumed = useRef(false);
  const remember = (id: string | null) => rememberConversation(identity?.account.id, id);

  const list = useCallback(async () => {
    if (!token) {
      setConversations([]);
      return [] as Conversation[];
    }
    const data = await jsonRequest<{ items: Conversation[] }>(
      '/api/assistant/conversations',
      token
    );
    setConversations(data.items);
    return data.items;
  }, [token]);
  const loadRoles = useCallback(async () => {
    try {
      const data = await jsonRequest<{ positions: Record<string, Role> }>(
        '/api/practice/config',
        session()?.access_token || ''
      );
      setRoles(data.positions);
      setPosition((previous) =>
        data.positions[previous] ? previous : Object.keys(data.positions)[0]
      );
    } catch {
      setError('练习方向未能读取，请重新加载。');
    }
  }, []);
  useEffect(() => {
    void loadRoles();
  }, [loadRoles]);
  useEffect(() => {
    resumed.current = false;
    void list()
      .then((items) => {
        if (resumed.current || working.current) return;
        resumed.current = true;
        const id = rememberedConversation(identity?.account.id);
        const previous = items.find((item) => item.id === id);
        if (previous) void open(previous);
      })
      .catch(() => setError('对话列表暂时无法读取，请重试。'));
  }, [list]);
  useEffect(() => {
    function changed() {
      const next = session();
      if ((next?.access_token || '') === activeToken.current) {
        setIdentity(next);
        return;
      }
      activeToken.current = next?.access_token || '';
      generation.current++;
      controller.current?.abort();
      working.current = false;
      setIdentity(next);
      setCurrent(null);
      setMessages([]);
      setDraft('');
      setConversations([]);
      setIncludeFocus(false);
      setError('');
      setBusy(false);
      setStage('');
      retryTurn.current = null;
    }
    function leave() {
      generation.current++;
      controller.current?.abort();
    }
    function restore(event: PageTransitionEvent) {
      if (event.persisted) location.reload();
    }
    addEventListener('account:changed', changed);
    addEventListener('account:expired', changed);
    addEventListener('pagehide', leave);
    addEventListener('pageshow', restore);
    return () => {
      removeEventListener('account:changed', changed);
      removeEventListener('account:expired', changed);
      removeEventListener('pagehide', leave);
      removeEventListener('pageshow', restore);
      leave();
    };
  }, []);

  function reset() {
    if (working.current) return;
    generation.current++;
    resumed.current = true;
    remember(null);
    setCurrent(null);
    setMessages([]);
    setDraft('');
    setError('');
    setStage('');
    retryTurn.current = null;
  }
  async function open(item: Conversation) {
    if (working.current) return;
    working.current = true;
    setBusy(true);
    setError('');
    const version = ++generation.current;
    try {
      const data = await jsonRequest<Conversation>(
        '/api/assistant/conversations/' + item.id,
        token
      );
      if (version !== generation.current) return;
      setCurrent(data);
      remember(data.id);
      setPosition(data.position);
      setMessages(data.messages);
      setDraft('');
      retryTurn.current = null;
    } catch (failure) {
      if (version === generation.current) setError((failure as Error).message);
    } finally {
      if (version === generation.current) {
        working.current = false;
        setBusy(false);
      }
    }
  }
  async function send(text = draft, retry = false) {
    if (!token || working.current || !text.trim() || text.length > 1200 || !roles[position]) return;
    const version = ++generation.current;
    const attempt =
      retry && retryTurn.current
        ? retryTurn.current
        : {
            text: text.trim(),
            request_id: crypto.randomUUID().replace(/-/g, ''),
            base: messages,
          };
    retryTurn.current = attempt;
    working.current = true;
    setBusy(true);
    setError('');
    setStage('正在连接小青');
    setDraft('');
    setMessages([
      ...attempt.base,
      { role: 'user', content: attempt.text },
      { role: 'assistant', content: '' },
    ]);
    const abort = new AbortController();
    controller.current = abort;
    const timer = setTimeout(() => abort.abort('timeout'), 90000);
    let conversation = current;
    const patchLast = (patch: (last: Message) => Message) =>
      setMessages((previous) =>
        previous.map((message, index) => (index === previous.length - 1 ? patch(message) : message))
      );
    try {
      if (!conversation) {
        conversation = await jsonRequest<Conversation>('/api/assistant/conversations', token, {
          method: 'POST',
          body: JSON.stringify({ position }),
          signal: abort.signal,
        });
        if (version !== generation.current || abort.signal.aborted) return;
        setCurrent(conversation);
        remember(conversation.id);
      }
      const path = '/api/assistant/conversations/' + conversation.id + '/turns';
      const body = {
        text: attempt.text,
        request_id: attempt.request_id,
        expected_version: conversation.version,
        include_focus: includeFocus,
      };
      await streamChat(path, body, token, abort.signal, (event) => {
        if (version !== generation.current) return;
        if (event.type === 'stage') setStage(event.label);
        if (event.type === 'delta')
          patchLast((last) => ({ ...last, content: last.content + event.text }));
        if (event.type === 'revision') {
          patchLast((last) => ({ ...last, content: event.text }));
          notice(event.reason, 'info');
        }
        if (event.type === 'evidence') patchLast((last) => ({ ...last, evidence: event }));
        if (event.type === 'mode') patchLast((last) => ({ ...last, mode: event }));
        if (event.type === 'done') {
          if (conversation) setCurrent({ ...conversation, version: event.version });
          retryTurn.current = null;
        }
      });
      if (version === generation.current && token)
        await list().catch(() => setError('回答已保存，对话列表暂未刷新，请稍后刷新列表。'));
    } catch (failure) {
      if (version !== generation.current) return;
      const message = abort.signal.aborted
        ? '已停止接收。当前片段不作为完整回答；可重试或重新打开对话核对保存状态。'
        : (failure as Error).message;
      setError(message);
      notice(message, 'error');
    } finally {
      clearTimeout(timer);
      if (version === generation.current) {
        setBusy(false);
        setStage('');
        working.current = false;
        controller.current = null;
      }
    }
  }
  async function manage(action: 'rename' | 'delete', item: Conversation, title?: string) {
    if (working.current) return false;
    const version = ++generation.current;
    working.current = true;
    setBusy(true);
    try {
      const result = await jsonRequest<Conversation>(
        '/api/assistant/conversations/' +
          item.id +
          (action === 'delete' ? '?expected_version=' + item.version : ''),
        token,
        {
          method: action === 'delete' ? 'DELETE' : 'PATCH',
          ...(action === 'rename'
            ? {
                body: JSON.stringify({ title, expected_version: item.version }),
              }
            : {}),
        }
      );
      if (version !== generation.current) return false;
      if (current?.id === item.id) {
        if (action === 'delete') {
          remember(null);
          setCurrent(null);
          setMessages([]);
          retryTurn.current = null;
        } else setCurrent(result);
      }
      await list();
      notice(action === 'delete' ? '对话已删除' : '对话名称已更新');
      return true;
    } catch (failure) {
      if (version === generation.current) {
        setError((failure as Error).message);
        notice((failure as Error).message, 'error');
      }
      return false;
    } finally {
      if (version === generation.current) {
        working.current = false;
        setBusy(false);
      }
    }
  }
  return {
    identity,
    roles,
    position,
    setPosition,
    conversations,
    current,
    messages,
    draft,
    setDraft,
    busy,
    stage,
    error,
    includeFocus,
    setIncludeFocus,
    reset,
    open,
    send,
    manage,
    list,
    loadRoles,
    stop: () => controller.current?.abort(),
    retry: () => retryTurn.current && void send(retryTurn.current.text, true),
    refresh: () =>
      void list().catch(() => {
        setError('对话列表暂未读取，请稍后重试。');
        notice('对话列表读取失败', 'error');
      }),
    canRetry: Boolean(retryTurn.current) && !busy,
  };
}
