import React, { useEffect, useRef, useState } from 'react';
import { adminRequest, AdminError, Row } from './api';
import { reviewLabels } from './state';

export function ReviewEditor({
  row,
  identity,
  editable,
  saved,
  onBusy,
}: {
  row: Row;
  identity: string;
  editable: boolean;
  saved: () => void;
  onBusy: (value: boolean) => void;
}) {
  const [status, setStatus] = useState(row.review_status || 'pending');
  const [note, setNote] = useState(row.review_note || '');
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<AdminError | null>(null);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  return (
    <form
      className="admin-review"
      onSubmit={async (e) => {
        e.preventDefault();
        if (busy || !editable) return;
        const active = new AbortController();
        controller.current = active;
        setBusy(true);
        onBusy(true);
        setError(null);
        try {
          await adminRequest(
            '/api/admin/questions/' + encodeURIComponent(row.id) + '/review',
            identity,
            active.signal,
            {
              method: 'PATCH',
              body: JSON.stringify({
                status,
                note,
                expected_version: row.review_version,
                content_hash: row.content_hash,
              }),
            }
          );
          if (!active.signal.aborted) saved();
        } catch (value) {
          if (!active.signal.aborted)
            setError(
              value instanceof AdminError
                ? value
                : new AdminError('保存未完成，请重新读取核对后再试。')
            );
        } finally {
          if (!active.signal.aborted) {
            setBusy(false);
            onBusy(false);
          }
        }
      }}
    >
      <h3>题目审校</h3>
      <p className="admin-help">
        记录核对结果与修改建议，不会直接更改运行中的题目。
        {row.review_stale ? '题目内容已更新，之前的审校结果需要重新确认。' : ''}
      </p>
      <label>
        审校状态
        <select
          value={status}
          disabled={!editable || busy}
          onChange={(e) => setStatus(e.target.value)}
        >
          {Object.entries(reviewLabels).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label>
        审校说明
        <textarea
          value={note}
          maxLength={500}
          minLength={status === 'needs_revision' ? 5 : undefined}
          required={status === 'needs_revision'}
          disabled={!editable || busy}
          onChange={(e) => setNote(e.target.value)}
          placeholder="需修改时请填写至少5字，避免填写个人敏感信息。"
          rows={3}
        />
        <small>{note.length}/500</small>
      </label>
      {error && (
        <p className="admin-operation-error" role="alert">
          {error.message}
          {error.requestId && <small>请求编号：{error.requestId}</small>}
        </p>
      )}
      {editable ? (
        <button className="notes-button notes-primary" disabled={busy} type="submit">
          {busy ? '保存中…' : '保存审校结果'}
        </button>
      ) : (
        <p className="admin-help">当前为只读角色，请联系管理员修改审校结果。</p>
      )}
    </form>
  );
}
