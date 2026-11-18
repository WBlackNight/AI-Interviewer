import React from 'react';
import { Overview, Page, Row } from './api';
import {
  View,
  Route,
  Navigate,
  views,
  difficultyLabels,
  statusLabels,
  formatDate,
  reviewLabels,
  actionLabels,
} from './state';
import { Icon } from './Icon';

export function DataTable({
  view,
  page,
  roles,
  onInspect,
}: {
  view: View;
  page: Page;
  roles: Overview['roles'];
  onInspect: (row: Row) => void;
}) {
  const role = (id?: string) => roles.find((r) => r.id === id)?.name || id || '—';
  const labels =
    view === 'audit'
      ? ['操作时间', '操作者', '操作类型', '结果', '对象', '请求编号', '操作']
      : view === 'accounts'
        ? ['账户', '昵称', '注册时间', '邮箱', '练习数', '有效会话', '操作']
        : view === 'questions'
          ? ['题目与主题', '方向', '难度', '题型', '审校', '来源', '操作']
          : ['场次编号', '方向', '状态', '用户', '评分轮数', '开始时间', '操作'];
  return (
    <div
      className="admin-table-scroll"
      tabIndex={0}
      role="region"
      aria-label={views[view] + '表格，可横向滚动'}
    >
      <table className="admin-data-table">
        <caption className="sr-only">
          {views[view]}，共{page.total}条记录
        </caption>
        <thead>
          <tr>
            {labels.map((label) => (
              <th key={label} scope="col">
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {page.items.map((row) => (
            <tr key={row.id}>
              {view === 'audit' ? (
                <>
                  <th scope="row">{formatDate(row.created_at || null)}</th>
                  <td>{row.actor}</td>
                  <td>{actionLabels[row.action || ''] || row.action}</td>
                  <td>
                    <span
                      className={
                        'admin-badge ' + (row.outcome === 'succeeded' ? 'admin-badge-finished' : '')
                      }
                    >
                      {row.outcome === 'succeeded' ? '成功' : '已拒绝'}
                    </span>
                  </td>
                  <td>
                    <code>{row.resource}</code>
                  </td>
                  <td>
                    <code title={row.request_id}>{row.request_id?.slice(0, 12)}</code>
                  </td>
                </>
              ) : view === 'accounts' ? (
                <>
                  <th scope="row">
                    <span className="admin-cell-title">{row.username}</span>
                    {row.is_admin && <span className="admin-badge">管理员</span>}
                  </th>
                  <td>{row.nickname || '未设置'}</td>
                  <td>{formatDate(row.created_at || null)}</td>
                  <td>
                    <span
                      className={'admin-badge ' + (row.email_bound ? 'admin-badge-finished' : '')}
                    >
                      {row.email_bound ? '已绑定' : '未绑定'}
                    </span>
                  </td>
                  <td>{row.interviews}</td>
                  <td>{row.active_sessions}</td>
                </>
              ) : view === 'questions' ? (
                <>
                  <th scope="row" className="admin-question-cell">
                    <span className="admin-question-title">{row.content}</span>
                    <small>
                      {row.theme} · {row.id}
                    </small>
                  </th>
                  <td>{role(row.position)}</td>
                  <td>{difficultyLabels[row.difficulty || ''] || row.difficulty}</td>
                  <td>{row.is_coding ? '编程题' : '知识题'}</td>
                  <td>
                    <span
                      className={
                        'admin-badge ' +
                        (row.review_status === 'approved'
                          ? 'admin-badge-finished'
                          : row.review_status === 'needs_revision'
                            ? 'admin-badge-revision'
                            : '')
                      }
                    >
                      {reviewLabels[row.review_status || 'pending']}
                    </span>
                    {row.review_stale && <small className="admin-cell-sub">内容已更新</small>}
                  </td>
                  <td className="admin-source-cell">{row.source || '未标注'}</td>
                </>
              ) : (
                <>
                  <th scope="row">
                    <code>{row.id.slice(0, 8)}</code>
                    <small className="admin-cell-sub">
                      {difficultyLabels[row.difficulty || ''] || row.difficulty}
                    </small>
                  </th>
                  <td>{role(row.position)}</td>
                  <td>
                    <span
                      className={
                        'admin-badge admin-badge-' +
                        (Object.hasOwn(statusLabels, row.status || '') ? row.status : 'other')
                      }
                    >
                      {statusLabels[row.status || ''] || '其他状态'}
                    </span>
                  </td>
                  <td>{row.username}</td>
                  <td>{row.scored_answers}</td>
                  <td>{formatDate(row.started_at || null)}</td>
                </>
              )}
              <td>
                <button
                  className="admin-text-button"
                  type="button"
                  aria-label={
                    '查看' +
                    (view === 'questions'
                      ? '题目'
                      : view === 'accounts'
                        ? '账户'
                        : view === 'audit'
                          ? '操作'
                          : '场次') +
                    ' ' +
                    row.id +
                    (row.username ? '，用户 ' + row.username : '') +
                    '的概况'
                  }
                  onClick={() => onInspect(row)}
                >
                  查看
                  <Icon name="arrow" />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
export function Pagination({
  route,
  page,
  navigate,
}: {
  route: Route;
  page: Page;
  navigate: Navigate;
}) {
  const current = Math.floor(page.offset / page.limit) + 1,
    total = Math.max(1, Math.ceil(page.total / page.limit));
  return (
    <nav className="admin-pagination" aria-label="数据分页">
      <p aria-live="polite">
        共 <strong>{page.total}</strong> 条 · 第 {current} / {total} 页
      </p>
      <div>
        <label>
          每页
          <select
            aria-label="每页记录数"
            value={route.limit}
            onChange={(e) => navigate({ limit: Number(e.target.value), page: 1 })}
          >
            {[10, 20, 50].map((n) => (
              <option key={n} value={n}>
                {n} 条
              </option>
            ))}
          </select>
        </label>
        <button
          className="notes-button"
          type="button"
          disabled={current <= 1}
          onClick={() => navigate({ page: current - 1 })}
        >
          上一页
        </button>
        <button
          className="notes-button"
          type="button"
          disabled={current >= total}
          onClick={() => navigate({ page: current + 1 })}
        >
          下一页
        </button>
      </div>
    </nav>
  );
}
