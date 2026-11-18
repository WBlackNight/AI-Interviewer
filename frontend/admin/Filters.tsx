import React from 'react';
import { Overview } from './api';
import {
  Route,
  Navigate,
  routeSearch,
  views,
  statusLabels,
  difficultyLabels,
  reviewLabels,
  actionLabels,
  sortOptions,
} from './state';

export function Filters({
  route,
  roles,
  navigate,
}: {
  route: Route;
  roles: Overview['roles'];
  navigate: Navigate;
}) {
  return (
    <form
      key={routeSearch(route)}
      className="admin-filters"
      role="search"
      aria-label={views[route.view] + '筛选'}
      onSubmit={(event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        navigate({
          q: String(form.get('q') || '').trim(),
          position: String(form.get('position') || ''),
          status: String(form.get('status') || ''),
          difficulty: String(form.get('difficulty') || ''),
          kind: String(form.get('kind') || ''),
          bound: String(form.get('bound') || ''),
          start: String(form.get('start') || ''),
          end: String(form.get('end') || ''),
          sort: String(form.get('sort') || 'default'),
          review: String(form.get('review') || ''),
          action: String(form.get('action') || ''),
          outcome: String(form.get('outcome') || ''),
          page: 1,
        });
      }}
    >
      <label className="admin-search">
        关键词
        <input
          name="q"
          type="search"
          maxLength={80}
          defaultValue={route.q}
          placeholder={
            route.view === 'audit'
              ? '操作者、对象或请求编号'
              : route.view === 'accounts'
                ? '用户名或昵称'
                : route.view === 'questions'
                  ? '题目、主题或编号'
                  : '场次编号或用户名'
          }
        />
      </label>
      {(route.view === 'questions' || route.view === 'interviews') && (
        <label>
          练习方向
          <select name="position" defaultValue={route.position}>
            <option value="">全部方向</option>
            {roles.map((role) => (
              <option key={role.id} value={role.id}>
                {role.name}
              </option>
            ))}
          </select>
        </label>
      )}
      {route.view === 'interviews' && (
        <label>
          练习状态
          <select name="status" defaultValue={route.status}>
            <option value="">全部状态</option>
            {Object.entries(statusLabels).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
      )}
      {route.view === 'questions' && (
        <>
          <label>
            题目难度
            <select name="difficulty" defaultValue={route.difficulty}>
              <option value="">全部难度</option>
              {Object.entries(difficultyLabels).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            审校状态
            <select name="review" defaultValue={route.review}>
              <option value="">全部审校状态</option>
              {Object.entries(reviewLabels).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            题型
            <select name="kind" defaultValue={route.kind}>
              <option value="">全部题型</option>
              <option value="knowledge">知识题</option>
              <option value="coding">编程题</option>
            </select>
          </label>
        </>
      )}
      {route.view === 'audit' && (
        <>
          <label>
            操作类型
            <select name="action" defaultValue={route.action}>
              <option value="">全部操作</option>
              {Object.entries(actionLabels).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            操作结果
            <select name="outcome" defaultValue={route.outcome}>
              <option value="">全部结果</option>
              <option value="succeeded">成功</option>
              <option value="denied">已拒绝</option>
            </select>
          </label>
        </>
      )}
      {route.view !== 'questions' && (
        <>
          <label>
            {route.view === 'accounts'
              ? '注册起始日期'
              : route.view === 'audit'
                ? '操作起始日期'
                : '练习开始日期'}
            <input
              type="date"
              name="start"
              defaultValue={route.start}
              max={route.end || undefined}
            />
          </label>
          <label>
            截至日期
            <input type="date" name="end" defaultValue={route.end} min={route.start || undefined} />
          </label>
        </>
      )}
      {route.view !== 'audit' && (
        <label>
          排序
          <select name="sort" defaultValue={route.sort === 'newest' ? 'default' : route.sort}>
            {Object.entries(sortOptions(route.view)).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
      )}
      {route.view === 'accounts' && (
        <label>
          邮箱绑定
          <select name="bound" defaultValue={route.bound}>
            <option value="">全部账户</option>
            <option value="bound">已绑定</option>
            <option value="unbound">未绑定</option>
          </select>
        </label>
      )}
      <div className="admin-filter-actions">
        <button className="notes-button notes-primary" type="submit">
          查询
        </button>
        <button
          className="notes-button"
          type="button"
          onClick={() => navigate({ view: route.view }, true)}
        >
          重置
        </button>
      </div>
    </form>
  );
}
