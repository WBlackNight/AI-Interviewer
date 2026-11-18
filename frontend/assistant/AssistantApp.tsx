import React, { FormEvent, useRef, useState } from 'react';
import { ChatPanel, QingMark } from './ChatPanel';
import { Conversation } from './types';
import { useAssistant } from './useAssistant';
import { LoginPrompt } from './LoginPrompt';

const STARTERS = [
  {
    icon: '01',
    title: '把知识讲明白',
    description: '从原理、例子到使用边界',
    prompt: '我想理解这个方向常见问题的核心原理，帮我找一道题并讲讲回答思路。',
  },
  {
    icon: '02',
    title: '让回答更有条理',
    description: '理清背景、行动和具体证据',
    prompt: '面试时总是回答得很散，怎样把经历说得清楚、有重点？请给我一个练习方法。',
  },
  {
    icon: '03',
    title: '安排下一步练习',
    description: '把准备拆成今天能做的小事',
    prompt: '我今天有15分钟准备面试，请结合这个方向的题库给我安排练习步骤。',
  },
  {
    icon: '04',
    title: '试试英语表达',
    description: '把经历说成自然的英文',
    prompt:
      'How can I introduce a project clearly in an English interview? Give me a short example and a practice question.',
  },
];

export function AssistantApp() {
  const chat = useAssistant();
  const dialog = useRef<HTMLDialogElement>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const [operation, setOperation] = useState<{
    action: 'rename' | 'delete';
    item: Conversation;
  } | null>(null);
  const [title, setTitle] = useState('');
  function manage(action: 'rename' | 'delete', item: Conversation) {
    setOperation({ action, item });
    setTitle(item.title);
    dialog.current?.showModal();
  }
  async function confirm(event: FormEvent) {
    event.preventDefault();
    if (operation && (await chat.manage(operation.action, operation.item, title)))
      dialog.current?.close();
  }
  function starter(prompt: string, english = false) {
    if (english && !chat.current) chat.setPosition('english_interview');
    chat.setDraft(prompt);
    textarea.current?.focus();
  }
  if (!chat.identity) return <LoginPrompt returnTo="/assistant" fullPage />;
  return (
    <div className="qing-workspace">
      <aside className="qing-sidebar" aria-label="对话管理">
        <a className="qing-sidebar-brand" href="/assistant">
          <QingMark small />
          <span>
            小青<span>你的面试准备搭子</span>
          </span>
        </a>
        <button className="qing-new" type="button" onClick={chat.reset} disabled={chat.busy}>
          <span aria-hidden="true">＋</span>新建对话
        </button>
        <div className="qing-sidebar-history">
          <h2>最近对话</h2>
          {chat.identity ? (
            <>
              {!chat.conversations.length && (
                <p>
                  从一个问题开始，
                  <br />
                  准备思路会保存在这里。
                </p>
              )}
              <ul>
                {chat.conversations.map((item) => (
                  <li key={item.id} className={item.id === chat.current?.id ? 'is-active' : ''}>
                    <button
                      type="button"
                      disabled={chat.busy}
                      onClick={() => void chat.open(item)}
                      aria-current={item.id === chat.current?.id ? 'true' : undefined}
                    >
                      {item.title}
                    </button>
                    <details className="qing-conversation-menu">
                      <summary aria-label={'管理对话：' + item.title}>···</summary>
                      <div>
                        <button
                          type="button"
                          disabled={chat.busy}
                          onClick={() => manage('rename', item)}
                        >
                          重命名
                        </button>
                        <button
                          type="button"
                          disabled={chat.busy}
                          onClick={() => manage('delete', item)}
                        >
                          删除
                        </button>
                      </div>
                    </details>
                  </li>
                ))}
              </ul>
              <button
                className="qing-text-button"
                type="button"
                disabled={chat.busy}
                onClick={chat.refresh}
              >
                刷新对话
              </button>
            </>
          ) : (
            <div className="qing-login-card">
              <p>
                登录后可使用智能对话，
                <br />
                并保存你的准备思路。
              </p>
              <a href="/account?next=%2Fassistant">登录 / 注册</a>
              <small>未登录也能体验题库指引</small>
            </div>
          )}
        </div>
        <div className="qing-sidebar-bottom">
          <span className="qing-live-dot" />
          从提问，到下一次进步。<a href="/guide">了解青栈</a>
        </div>
      </aside>
      <section className="qing-main" aria-labelledby="qing-page-title">
        <header className="qing-topbar">
          <div>
            <span className="qing-kicker">QINGZHAN ASSISTANT</span>
            <h1 id="qing-page-title">小青助手</h1>
          </div>
          <label className="qing-role-label">
            练习方向
            <select
              aria-label="练习方向"
              value={chat.position}
              disabled={chat.busy || Boolean(chat.current)}
              onChange={(event) => chat.setPosition(event.target.value)}
            >
              {Object.entries(chat.roles).map(([id, role]) => (
                <option value={id} key={id}>
                  {role.name}
                </option>
              ))}
            </select>
          </label>
        </header>
        {!chat.messages.length ? (
          <div className="qing-welcome">
            <div className="qing-welcome-mark">
              <QingMark />
            </div>
            <p className="qing-kicker">每个好回答，都从一个好问题开始</p>
            <h2>
              你好，我是小青。
              <br />
              <span>一起把面试准备得更从容。</span>
            </h2>
            <p className="qing-welcome-lead">
              讲清一个知识点，理顺一段经历，或找到下一道值得练的题。
              <br className="qing-desktop-break" />
              从你现在最想解决的问题开始。
            </p>
            <div className="qing-starters">
              {STARTERS.map((item) => (
                <button
                  type="button"
                  key={item.icon}
                  onClick={() => starter(item.prompt, item.icon === '04')}
                  disabled={chat.busy}
                >
                  <span>
                    {item.icon}
                    <span aria-hidden="true">↗</span>
                  </span>
                  <strong>{item.title}</strong>
                  <small>{item.description}</small>
                </button>
              ))}
            </div>
            <p className="qing-try">
              也可以直接问：
              <button type="button" onClick={() => starter('怎样把项目经历讲得更具体？')}>
                怎样把项目经历讲得更具体？
              </button>
            </p>
          </div>
        ) : (
          <ChatPanel messages={chat.messages} busy={chat.busy} />
        )}
        <div className="qing-compose-area">
          {chat.stage && (
            <p className="qing-stage" role="status">
              <span className="qing-stage-dots" aria-hidden="true">
                <i />
                <i />
                <i />
              </span>
              {chat.stage}
            </p>
          )}
          {chat.error && (
            <div className="qing-error" role="alert">
              <p>{chat.error}</p>
              <div>
                {chat.canRetry && (
                  <button type="button" onClick={chat.retry}>
                    重新回答
                  </button>
                )}
                {!Object.keys(chat.roles).length && (
                  <button type="button" onClick={() => void chat.loadRoles()}>
                    重新加载
                  </button>
                )}
              </div>
            </div>
          )}
          <form
            className="qing-composer"
            onSubmit={(event) => {
              event.preventDefault();
              void chat.send();
            }}
          >
            <label className="sr-only" htmlFor="qing-message">
              向小青提问
            </label>
            <textarea
              id="qing-message"
              ref={textarea}
              rows={2}
              value={chat.draft}
              maxLength={1200}
              disabled={chat.busy}
              placeholder="说说你正在准备什么，或把想不明白的问题交给小青…"
              onChange={(event) => chat.setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                  event.preventDefault();
                  void chat.send();
                }
              }}
            />
            <div className="qing-compose-toolbar">
              <span>
                {chat.draft.length}/1200
                <span className="qing-key-hint"> · Enter 发送，Shift + Enter 换行</span>
              </span>
              {chat.busy ? (
                <button type="button" className="qing-send" onClick={chat.stop}>
                  停止接收<span aria-hidden="true">■</span>
                </button>
              ) : (
                <button
                  type="submit"
                  className="qing-send"
                  disabled={!chat.draft.trim() || !Object.keys(chat.roles).length}
                >
                  发送<span aria-hidden="true">↑</span>
                </button>
              )}
            </div>
          </form>
          <div className="qing-compose-foot">
            {chat.identity ? (
              <label>
                <input
                  type="checkbox"
                  checked={chat.includeFocus}
                  disabled={chat.busy}
                  onChange={(event) => chat.setIncludeFocus(event.target.checked)}
                />
                结合最近一场练习摘要<small>仅主题和反馈分数</small>
              </label>
            ) : (
              <span>当前为题库指引 · 登录后可保存对话</span>
            )}
            <span>建议供准备参考，不替代正式评分</span>
          </div>
        </div>
      </section>
      <dialog
        ref={dialog}
        className="qing-dialog"
        aria-labelledby="qing-dialog-title"
        onClick={(event) => {
          if (event.target === event.currentTarget && !chat.busy) dialog.current?.close();
        }}
      >
        <form onSubmit={(event) => void confirm(event)}>
          <h2 id="qing-dialog-title">
            {operation?.action === 'delete' ? '删除这段对话？' : '给对话换个名称'}
          </h2>
          {operation?.action === 'delete' ? (
            <p>对话内容将永久删除，不影响你的练习与报告。</p>
          ) : (
            <label>
              对话名称
              <input
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                required
                maxLength={60}
                autoFocus
              />
            </label>
          )}
          <div>
            <button type="button" disabled={chat.busy} onClick={() => dialog.current?.close()}>
              取消
            </button>
            <button
              type="submit"
              disabled={chat.busy || (operation?.action === 'rename' && !title.trim())}
            >
              {chat.busy ? '处理中…' : '确认'}
            </button>
          </div>
        </form>
      </dialog>
    </div>
  );
}
