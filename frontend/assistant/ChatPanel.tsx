import React, { useEffect, useRef, useState } from 'react';
import { Message, notice, safeLink } from './types';
import { AnswerText } from './AnswerText';

export function QingMark({ small = false }: { small?: boolean }) {
  return (
    <span className={'qing-mark' + (small ? ' qing-mark-small' : '')} aria-hidden="true">
      <svg viewBox="0 0 48 48" fill="none">
        <path
          d="M11 29C9 15 21 8 36 11c2 16-6 29-19 27"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
        <path
          d="M13 37 30 20m-9 9 1-9m-2 10 10-1"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
      </svg>
    </span>
  );
}

const Answer = React.memo(function Answer({ message }: { message: Message }) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (copied) {
      const timer = setTimeout(() => setCopied(false), 2000);
      return () => clearTimeout(timer);
    }
  }, [copied]);
  async function copy() {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      notice('回答已复制');
    } catch {
      notice('复制失败，可选择文字手动复制。', 'error');
    }
  }
  return (
    <>
      <AnswerText text={message.content || '正在整理相关资料…'} />
      {message.mode && <p className="qing-answer-note">{message.mode.label}</p>}
      {message.evidence && (
        <>
          <details className="qing-evidence">
            <summary>参考资料 · {message.evidence.sources.length} 项</summary>
            <div>
              {message.evidence.sources.map((source) =>
                source.content ? (
                  <article className="qing-guide-source" key={source.id}>
                    <span>{source.id} · 学习指引</span>
                    <h4>{source.title}</h4>
                    <p>{source.content}</p>
                  </article>
                ) : (
                  <a href={safeLink(source.href)} key={source.id}>
                    <span>{source.id}</span>
                    <p>
                      {source.theme && <small>{source.theme}</small>}
                      {source.title}
                    </p>
                  </a>
                )
              )}
            </div>
          </details>
          <div className="qing-answer-actions">
            {message.evidence.actions.map((action) => (
              <a href={safeLink(action.href)} key={action.href}>
                {action.label}
                <span aria-hidden="true">↗</span>
              </a>
            ))}
          </div>
        </>
      )}
      {message.content && (
        <button className="qing-copy" type="button" onClick={() => void copy()}>
          {copied ? '已复制' : '复制回答'}
        </button>
      )}
    </>
  );
});

export function ChatPanel({ messages, busy }: { messages: Message[]; busy: boolean }) {
  const scroll = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  useEffect(() => {
    if (follow.current && scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight;
  }, [messages, busy]);
  return (
    <div
      className="qing-chat-log"
      ref={scroll}
      role="region"
      aria-label="对话内容"
      tabIndex={0}
      onScroll={() => {
        const node = scroll.current;
        if (node) follow.current = node.scrollHeight - node.scrollTop - node.clientHeight < 100;
      }}
    >
      {messages.map((message, index) => (
        <article className={'qing-message qing-message-' + message.role} key={index}>
          <div className="qing-message-label">
            {message.role === 'assistant' ? (
              <>
                <QingMark small />
                <span>小青</span>
              </>
            ) : (
              <span>你</span>
            )}
          </div>
          <div className="qing-message-body">
            {message.role === 'assistant' ? <Answer message={message} /> : <p>{message.content}</p>}
          </div>
        </article>
      ))}
      <span className="sr-only" role="status">
        {busy ? '小青正在回答' : messages.length ? '回答已结束，可阅读对话内容' : ''}
      </span>
    </div>
  );
}
