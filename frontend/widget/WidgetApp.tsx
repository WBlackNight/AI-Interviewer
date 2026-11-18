import React, { useEffect, useRef } from 'react';
import { useAssistant } from '../assistant/useAssistant';
import { ChatPanel, QingMark } from '../assistant/ChatPanel';
import { LoginPrompt } from '../assistant/LoginPrompt';

function pagePrompt() {
  const path = location.pathname;
  if (path.startsWith('/report/'))
    return '怎样把一份练习报告里的不足，变成下一次能执行的练习步骤？';
  if (path.startsWith('/interview/'))
    return '请教我怎样组织面试回答，先讲方法，不替我回答正在练习的题目。';
  if (path === '/catalog' || path === '/roles')
    return '我该怎样从这个方向的题库里，选择今天值得练习的主题？';
  return '我今天有15分钟准备面试，请帮我安排一个能完成的小目标。';
}
export function WidgetApp() {
  const chat = useAssistant();
  const textarea = useRef<HTMLTextAreaElement>(null);
  const contextApplied = useRef(false);
  useEffect(() => {
    if (contextApplied.current || !Object.keys(chat.roles).length) return;
    contextApplied.current = true;
    const position = new URLSearchParams(location.search).get('position');
    if (!chat.current && position && chat.roles[position]) chat.setPosition(position);
  }, [chat.roles, chat.current]);
  const close = () => dispatchEvent(new Event('qing:close'));
  useEffect(() => {
    textarea.current?.focus({ preventScroll: true });
  }, []);
  useEffect(() => {
    dispatchEvent(new CustomEvent('qing:busy', { detail: chat.busy }));
    return () => {
      dispatchEvent(new CustomEvent('qing:busy', { detail: false }));
    };
  }, [chat.busy]);
  const full = '/assistant';
  if (!chat.identity) {
    return (
      <div className="qing-widget">
        <header className="qing-widget-header">
          <strong>小青助手</strong>
          <button type="button" aria-label="收起小青聊天" onClick={close}>
            ×
          </button>
        </header>
        <LoginPrompt returnTo={location.pathname + location.search} />
      </div>
    );
  }
  return (
    <div className="qing-widget">
      <header className="qing-widget-header">
        <div>
          <QingMark small />
          <span>
            <strong>小青</strong>
            <small>你的面试准备搭子</small>
          </span>
        </div>
        <nav aria-label="小青窗口操作">
          <a href={full}>完整页面</a>
          <button type="button" aria-label="收起小青聊天" onClick={close}>
            ×
          </button>
        </nav>
      </header>
      <div className="qing-widget-tools">
        <label>
          练习方向
          <select
            value={chat.position}
            disabled={chat.busy || Boolean(chat.current)}
            onChange={(event) => chat.setPosition(event.target.value)}
          >
            {Object.entries(chat.roles).map(([id, role]) => (
              <option key={id} value={id}>
                {role.name}
              </option>
            ))}
          </select>
        </label>
        <button type="button" disabled={chat.busy} onClick={chat.reset}>
          新对话
        </button>
      </div>
      {chat.identity && chat.conversations.length > 0 && (
        <label className="qing-widget-history">
          最近对话
          <select
            aria-label="切换最近对话"
            disabled={chat.busy}
            value={chat.current?.id || ''}
            onChange={(event) => {
              const row = chat.conversations.find((item) => item.id === event.target.value);
              if (row) void chat.open(row);
            }}
          >
            <option value="">选择一段对话</option>
            {chat.conversations.map((item) => (
              <option value={item.id} key={item.id}>
                {item.title}
              </option>
            ))}
          </select>
        </label>
      )}
      {chat.messages.length ? (
        <ChatPanel messages={chat.messages} busy={chat.busy} />
      ) : (
        <section className="qing-widget-welcome">
          <QingMark />
          <h2>有个问题，想一起理理吗？</h2>
          <p>讲清知识点，整理经历，或找到下一道值得练的题。</p>
          <button
            onClick={() => {
              chat.setDraft(pagePrompt());
              textarea.current?.focus();
            }}
          >
            从当前准备开始
          </button>
          <button
            onClick={() => {
              chat.setDraft('怎样把项目经历讲得更具体？');
              textarea.current?.focus();
            }}
          >
            把经历讲清楚
          </button>
          {!chat.identity && (
            <p className="qing-widget-guest">
              当前可体验题库指引。
              <a href={'/account?next=' + encodeURIComponent(location.pathname + location.search)}>
                登录后保存对话
              </a>
            </p>
          )}
        </section>
      )}
      {chat.stage && (
        <p className="qing-widget-stage" role="status">
          {chat.stage}
        </p>
      )}
      {chat.error && (
        <div className="qing-widget-error" role="alert">
          <p>{chat.error}</p>
          {chat.canRetry && (
            <button disabled={chat.busy} onClick={chat.retry}>
              重新回答
            </button>
          )}
        </div>
      )}
      <form
        className="qing-widget-composer"
        onSubmit={(event) => {
          event.preventDefault();
          void chat.send();
        }}
      >
        <label className="sr-only" htmlFor="qing-widget-message">
          向小青提问
        </label>
        <textarea
          id="qing-widget-message"
          ref={textarea}
          rows={2}
          placeholder="说说你正在准备什么…"
          maxLength={1200}
          value={chat.draft}
          disabled={chat.busy}
          onChange={(event) => chat.setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              void chat.send();
            }
          }}
        />
        <div>
          <small>{chat.draft.length}/1200</small>
          {chat.busy ? (
            <button type="button" onClick={chat.stop}>
              停止接收
            </button>
          ) : (
            <button type="submit" disabled={!chat.draft.trim() || !Object.keys(chat.roles).length}>
              发送 ↑
            </button>
          )}
        </div>
      </form>
      <footer className="qing-widget-footer">
        {chat.identity && (
          <label>
            <input
              type="checkbox"
              checked={chat.includeFocus}
              disabled={chat.busy}
              onChange={(event) => chat.setIncludeFocus(event.target.checked)}
            />
            结合最近练习摘要
          </label>
        )}
        <span>建议供准备参考</span>
      </footer>
    </div>
  );
}
