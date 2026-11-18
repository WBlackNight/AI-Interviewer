import React, { useEffect, useRef, useState } from 'react';
import { Row, Overview } from './api';
import { statusLabels, difficultyLabels, formatDate, reviewLabels, actionLabels } from './state';
import { ReviewEditor } from './ReviewEditor';

export function Detail({
  row,
  close,
  roles,
  identity,
  editable,
  saved,
}: {
  row: Row | null;
  close: () => void;
  roles: Overview['roles'];
  identity: string;
  editable: boolean;
  saved: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    setBusy(false);
    const dialog = ref.current;
    if (row && !dialog?.open) dialog?.showModal();
    else if (!row && dialog?.open) dialog.close();
  }, [row]);
  const names: Record<string, string> = {
    id: '编号',
    position: '练习方向',
    status: '练习状态',
    difficulty: '难度',
    started_at: '开始时间',
    ended_at: '结束时间',
    username: '用户名',
    scored_answers: '已评分轮数',
    nickname: '昵称',
    created_at: row?.action ? '操作时间' : '注册时间',
    email_bound: '邮箱绑定',
    active_sessions: '有效登录会话',
    interviews: '练习数量',
    is_admin: '管理员',
    theme: '题目主题',
    content: '题目内容',
    source: '参考来源',
    is_coding: '编程题',
    review_status: '审校状态',
    reviewed_at: '审校时间',
    review_stale: '需要重新审校',
    actor: '操作者',
    action: '操作',
    outcome: '结果',
    resource: '操作对象',
    request_id: '请求编号',
    details: '操作摘要',
  };
  function value(key: string, value: unknown) {
    if (key === 'position') return roles.find((r) => r.id === value)?.name || String(value);
    if (key === 'status') return statusLabels[String(value)] || String(value);
    if (key === 'difficulty') return difficultyLabels[String(value)] || String(value);
    if (key === 'review_status') return reviewLabels[String(value)] || String(value);
    if (key === 'action') return actionLabels[String(value)] || String(value);
    if (key === 'outcome') return value === 'succeeded' ? '成功' : '已拒绝';
    if (key === 'details') {
      const d = value as Record<string, unknown>;
      return d.rows !== undefined
        ? '导出 ' + d.rows + ' 条'
        : d.version !== undefined
          ? '审校第 ' +
            d.version +
            ' 版，' +
            (reviewLabels[String(d.from)] || d.from) +
            ' → ' +
            (reviewLabels[String(d.to)] || d.to)
          : '—';
    }
    if (key.endsWith('_at')) return value ? formatDate(String(value)) : '暂无';
    if (typeof value === 'boolean') return value ? '是' : '否';
    return value === null || value === '' ? '未填写' : String(value);
  }
  return (
    <dialog
      ref={ref}
      className="admin-detail"
      aria-labelledby="admin-detail-title"
      onClose={close}
      onCancel={(e) => {
        if (busy) e.preventDefault();
        else close();
      }}
      onClick={(e) => {
        if (!busy && e.target === e.currentTarget) {
          const r = e.currentTarget.getBoundingClientRect();
          if (
            e.clientX < r.left ||
            e.clientX > r.right ||
            e.clientY < r.top ||
            e.clientY > r.bottom
          )
            close();
        }
      }}
    >
      <header>
        <div>
          <p className="admin-eyebrow">记录概况</p>
          <h2 id="admin-detail-title">
            {row?.action
              ? '操作详情'
              : row?.content
                ? '题目详情'
                : row?.nickname || row?.username || '练习详情'}
          </h2>
        </div>
        <button type="button" disabled={busy} aria-label="关闭详情" onClick={close}>
          ×
        </button>
      </header>
      <dl>
        {row &&
          Object.entries(row)
            .filter(([key]) => !['content_hash', 'review_version', 'review_note'].includes(key))
            .map(([key, v]) => (
              <div key={key}>
                <dt>{names[key] || key}</dt>
                <dd>{value(key, v)}</dd>
              </div>
            ))}
      </dl>
      {row?.content_hash && (
        <ReviewEditor
          key={row.id + ':' + row.review_version}
          row={row}
          identity={identity}
          editable={editable}
          saved={saved}
          onBusy={setBusy}
        />
      )}
      <footer>
        <p className="admin-help">仅展示管理摘要，不含简历、回答原文或联系方式。</p>
        <button
          type="button"
          disabled={busy}
          className="notes-button notes-primary"
          onClick={close}
        >
          关闭
        </button>
      </footer>
    </dialog>
  );
}
