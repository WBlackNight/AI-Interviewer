import React, { useEffect, useRef, useState } from 'react';
import { notice } from '../assistant/types';
import { useStudio } from './useStudio';
import { SavedTurn, terminal } from './state';

const PHASE = {
  connecting: '正在连接并核对保存状态',
  active: '已同步，可以继续回答',
  waiting: '回答已保存，正在整理下一步',
  finished: '本场练习已完成',
  cancelled: '本场练习已取消',
  error: '连接已暂停，请检查后重新同步',
};
function History({ turns, hideEvidence }: { turns: SavedTurn[]; hideEvidence: boolean }) {
  const [page, setPage] = useState(0);
  const saved = turns.filter((row) => row.answer !== undefined || row.score);
  const pages = Math.max(1, Math.ceil(saved.length / 4)),
    shown = Math.min(page, pages - 1);
  return (
    <section className="practice-card practice-history" aria-labelledby="practice-history-title">
      <div className="practice-card-heading">
        <h2 id="practice-history-title">已保存的回答</h2>
        <span>{saved.length} 轮</span>
      </div>
      {!saved.length && (
        <p className="practice-muted">第一轮保存后，可以在这里回看回答与评分依据。</p>
      )}
      {saved.slice(shown * 4, shown * 4 + 4).map((row) => (
        <details key={row.turn_id} className="practice-history-item">
          <summary>
            {row.theme || '本轮'} · {row.is_probe ? '追问' : '主问题'}
            <span>{row.score ? `${row.score.score.toFixed(1)} / 10` : '已保存'}</span>
          </summary>
          <h3>{row.content}</h3>
          <p className="practice-answer-copy">{row.answer || '本轮未记录回答文本。'}</p>
          {row.score && !hideEvidence && (
            <p className="practice-evidence">评分依据：{row.score.evidence}</p>
          )}
        </details>
      ))}
      {pages > 1 && (
        <nav className="practice-pagination" aria-label="回答分页">
          <button disabled={!shown} onClick={() => setPage(shown - 1)}>
            上一页
          </button>
          <span>
            {shown + 1} / {pages}
          </span>
          <button disabled={shown + 1 >= pages} onClick={() => setPage(shown + 1)}>
            下一页
          </button>
        </nav>
      )}
    </section>
  );
}
export function StudioApp({ interviewId }: { interviewId: string }) {
  const studio = useStudio(interviewId),
    { state: s } = studio;
  const dialog = useRef<HTMLDialogElement>(null),
    form = useRef<HTMLFormElement>(null);
  const finished = terminal(s),
    question = s.question,
    blocked = Boolean(s.pending) || studio.cancelling;
  const length = Array.from(s.text).length;
  const codeBytes = new TextEncoder().encode(s.code).length;
  const canSubmit =
    !blocked &&
    s.phase === 'active' &&
    Boolean(question) &&
    length <= 20000 &&
    codeBytes <= 16384 &&
    Boolean(question?.is_coding ? s.code.trim() : s.text.trim());
  const report = '/report/' + interviewId;
  useEffect(() => {
    if (s.denied || finished) dialog.current?.close();
  }, [s.denied, finished]);
  async function copyRecovery() {
    try {
      await navigator.clipboard.writeText(s.recovery);
      notice('草稿已复制');
    } catch {
      notice('复制失败，可手动选择草稿文字。', 'error');
    }
  }
  return (
    <>
      <section className="practice-intro">
        <div>
          <h1>文字练习</h1>
        </div>
        <p>回答当前问题，完成后查看评分与建议。</p>
      </section>
      <section className="practice-status" aria-label="练习连接状态">
        <p role="status">
          <span data-phase={s.phase} className="practice-status-dot" />
          {s.pending ? '已发送，正在等待本轮保存' : PHASE[s.phase]}
        </p>
        {!finished && (s.phase !== 'active' || s.pending) && (
          <button type="button" onClick={studio.sync} disabled={studio.cancelling}>
            重新同步
          </button>
        )}
      </section>
      {!finished && (
        <nav className="practice-modes" aria-label="练习方式">
          <a href="?mode=text" aria-current="page">
            文字作答
          </a>
          <a href="?mode=realtime">
            实时对话<span>自由交流，不计分</span>
          </a>
          <a href="?mode=voice">
            语音输入<span>转写后保存答案</span>
          </a>
        </nav>
      )}
      {s.error && (
        <p className="practice-error" role="alert">
          {s.error}
        </p>
      )}
      {s.denied ? (
        <section className="practice-card practice-access">
          <h2>检查这场练习的访问范围</h2>
          <p>请登录所属账户，或回到保留匿名凭据的标签页。</p>
          <div className="practice-actions">
            <a href={'/account?next=' + encodeURIComponent('/interview/' + interviewId)}>
              检查账户
            </a>
            <a href="/history">练习记录</a>
          </div>
        </section>
      ) : (
        <div className="practice-grid">
          <div className="practice-primary">
            {finished ? (
              <section
                className="practice-card practice-complete"
                aria-labelledby="practice-complete-title"
              >
                <span className="practice-complete-icon" aria-hidden="true">
                  {s.phase === 'finished' ? '✓' : '—'}
                </span>
                <p className="eyebrow">
                  {s.phase === 'finished' ? 'PRACTICE COMPLETE' : 'PRACTICE SAVED'}
                </p>
                <h2 id="practice-complete-title">
                  {s.phase === 'finished' ? '这一场练习，完成了。' : '已结束本场练习。'}
                </h2>
                <p>
                  {s.phase === 'finished'
                    ? '回看表现与不足，再把一个改进点带进下一次练习。'
                    : '取消前已保存的回答会保留在部分报告中。'}
                </p>
                <div className="practice-actions">
                  <a className="practice-primary-action" href={report}>
                    {s.phase === 'finished' ? '查看评分与不足' : '查看部分报告'}
                  </a>
                  <a href="/#start">再练一场</a>
                </div>
              </section>
            ) : (
              <section
                className="practice-card practice-question"
                aria-labelledby="practice-question-title"
              >
                <p className="eyebrow">
                  {question
                    ? `${question.theme} · ${question.is_probe ? '追问 ' + (question.probe_depth || 1) + ' 层' : question.is_coding ? '编程问题' : '主问题'}`
                    : '准备当前问题'}
                </p>
                <h2 id="practice-question-title" key={question?.turn_id}>
                  {question?.content ||
                    (s.phase === 'error' ? '同步后继续你的练习' : '正在准备下一道题…')}
                </h2>
                {question?.testcases?.length ? (
                  <details className="practice-tests">
                    <summary>公开测试用例</summary>
                    {question.testcases.map((item, index) => (
                      <pre key={index}>
                        用例 {index + 1}
                        {'\n'}输入：{item.input}
                        {'\n'}预期：{item.expected}
                      </pre>
                    ))}
                  </details>
                ) : null}
                {question && (
                  <form
                    ref={form}
                    onSubmit={(event) => {
                      event.preventDefault();
                      studio.submit();
                    }}
                    onKeyDown={(event) => {
                      if (
                        event.key === 'Enter' &&
                        (event.ctrlKey || event.metaKey) &&
                        !event.nativeEvent.isComposing
                      ) {
                        event.preventDefault();
                        if (canSubmit) form.current?.requestSubmit();
                      }
                    }}
                  >
                    <label htmlFor="practice-answer">
                      你的回答<span>先说明背景，再补上行动、依据与结果。</span>
                    </label>
                    <textarea
                      id="practice-answer"
                      rows={7}
                      value={s.text}
                      disabled={blocked}
                      maxLength={40000}
                      placeholder="按自己的节奏整理思路，Enter 换行。"
                      onChange={(event) => studio.setDraft(event.target.value)}
                    />
                    {question.is_coding && (
                      <>
                        <label htmlFor="practice-code">Python 代码</label>
                        <textarea
                          id="practice-code"
                          className="practice-code"
                          rows={10}
                          spellCheck={false}
                          value={s.code}
                          disabled={blocked}
                          onChange={(event) => studio.setDraft(s.text, event.target.value)}
                        />
                        <p className={codeBytes > 16384 ? 'practice-error' : 'practice-muted'}>
                          代码 {codeBytes.toLocaleString()} / 16,384
                          字节；运行结果以实际判题反馈为准。
                        </p>
                      </>
                    )}
                    <div className="practice-submit-row">
                      <span className={length > 20000 ? 'practice-error' : 'practice-muted'}>
                        {length.toLocaleString()} / 20,000
                        <span className="practice-key-hint"> · Ctrl / ⌘ + Enter 提交</span>
                      </span>
                      <div>
                        <button
                          type="button"
                          disabled={blocked || s.phase !== 'active'}
                          onClick={() => studio.submit(true)}
                        >
                          跳过本题
                        </button>
                        <button
                          type="submit"
                          className="practice-primary-action"
                          disabled={!canSubmit}
                        >
                          {s.pending ? '等待保存…' : '提交回答'}
                        </button>
                      </div>
                    </div>
                    <p className="practice-muted practice-privacy">
                      点击提交后才会发送回答。连接恢复时先核对保存状态，避免重复作答。
                    </p>
                  </form>
                )}
              </section>
            )}
            {s.recovery && (
              <details className="practice-card practice-recovery">
                <summary>查看保留的旧轮草稿</summary>
                <p className="practice-answer-copy">{s.recovery}</p>
                <button onClick={() => void copyRecovery()}>复制草稿</button>
              </details>
            )}
            <History turns={s.turns} hideEvidence={Boolean(question?.is_probe)} />
          </div>
          <aside className="practice-sidebar">
            <section className="practice-card">
              <p className="eyebrow">LAST SAVED ROUND</p>
              <h2>上一轮反馈</h2>
              <p className="practice-last-score">
                {s.lastScore ? s.lastScore.score.toFixed(1) : '—'}
                <span>/ 10</span>
              </p>
              <p className="practice-muted">本轮参考得分；整场综合表现见报告。</p>
              <div className="practice-dimensions">
                {Object.entries(s.lastScore?.dimensions || {}).map(([name, value]) => (
                  <div key={name}>
                    <span>{name === '技术深度' ? '内容完整度' : name}</span>
                    <strong>{value.toFixed(1)}</strong>
                    <meter min="0" max="10" value={value} aria-label={name} />
                  </div>
                ))}
              </div>
              {!question?.is_probe && (
                <>
                  <p className="practice-evidence">
                    {s.lastScore?.evidence || '保存回答后，这里会展示具体反馈。'}
                  </p>
                  {Boolean(s.lastScore?.key_points_missed.length) && (
                    <p className="practice-missed">
                      待补强：{s.lastScore?.key_points_missed.join('、')}
                    </p>
                  )}
                </>
              )}
              {question?.is_probe && (
                <p className="practice-muted">先独立完成追问，评分依据稍后可在报告中回看。</p>
              )}
              <a href={report}>查看当前报告</a>
            </section>
            <section className="practice-guide">
              <h2>给自己一点思考时间</h2>
              <ol>
                <li>说明概念与前提。</li>
                <li>解释选择与取舍。</li>
                <li>用例子讲清边界。</li>
              </ol>
              <a href="/assistant">需要准备思路？找小青聊聊</a>
              {!finished && (
                <button
                  className="practice-cancel"
                  disabled={studio.cancelling}
                  onClick={() => dialog.current?.showModal()}
                >
                  取消本场练习
                </button>
              )}
            </section>
          </aside>
        </div>
      )}
      <dialog
        ref={dialog}
        className="practice-dialog"
        aria-labelledby="practice-dialog-title"
        onCancel={(event) => {
          if (studio.cancelling) event.preventDefault();
        }}
      >
        <h2 id="practice-dialog-title">结束这场练习？</h2>
        <p>已保存的回答会保留，结束后可查看部分报告。</p>
        {studio.cancelError && (
          <p className="practice-error" role="alert">
            {studio.cancelError}
          </p>
        )}
        <div>
          <button disabled={studio.cancelling} onClick={() => dialog.current?.close()}>
            继续练习
          </button>
          <button
            className="practice-primary-action"
            disabled={studio.cancelling}
            onClick={() =>
              void studio.cancel().then((done) => {
                if (done) dialog.current?.close();
              })
            }
          >
            {studio.cancelling ? '正在结束…' : '确认结束'}
          </button>
        </div>
      </dialog>
    </>
  );
}
