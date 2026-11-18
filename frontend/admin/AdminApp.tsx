import React, { useEffect, useState, useRef } from 'react';
import { Row, downloadCsv, AdminError } from './api';
import { CoverageChart, StatusChart, TrendChart } from './Charts';
import {
  formatDate,
  readRoute,
  Route,
  routeSearch,
  View,
  views,
  Navigate,
  exportPath,
} from './state';
import { useAdmin } from './useAdmin';
import { Icon } from './Icon';
import { Metrics } from './Metrics';
import { Filters } from './Filters';
import { DataTable, Pagination } from './Records';
import { Detail } from './Detail';

const descriptions: Record<View, string> = {
  overview: '把握练习活动与题库覆盖，查看平台的整体运行情况。',
  interviews: '按方向与状态查找场次，了解练习的启动和完成情况。',
  questions: '浏览当前运行题库，核对方向、难度和参考来源。',
  accounts: '查看注册账户、资料完善情况与练习数量。',
  audit: '追踪导出、审校与权限拒绝记录，按请求编号定位操作。',
};
export function AdminApp() {
  const [route, setRoute] = useState(() => readRoute(location.search));
  const [expanded, setExpanded] = useState(false),
    [detail, setDetail] = useState<Row | null>(null);
  const data = useAdmin(route);
  const [exporting, setExporting] = useState(false),
    [operationError, setOperationError] = useState<AdminError | null>(null),
    [notice, setNotice] = useState('');
  const exportController = useRef<AbortController | null>(null);
  useEffect(() => {
    setOperationError(null);
  }, [route]);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(''), 2200);
    return () => clearTimeout(timer);
  }, [notice]);
  useEffect(() => {
    setOperationError(null);
    setNotice('');
    return () => exportController.current?.abort();
  }, [data.identity]);
  async function exportData() {
    if (exporting) return;
    const controller = new AbortController();
    exportController.current = controller;
    setExporting(true);
    setOperationError(null);
    try {
      const count = await downloadCsv(exportPath(route), data.identity, controller.signal);
      if (!controller.signal.aborted)
        setNotice('已生成 ' + count + ' 条记录，文件已交给浏览器下载。');
    } catch (error) {
      if (!controller.signal.aborted)
        setOperationError(
          error instanceof AdminError ? error : new AdminError('导出未完成，请重试。')
        );
    } finally {
      setExporting(false);
    }
  }
  useEffect(() => {
    const pop = () => {
      setRoute(readRoute(location.search));
      setDetail(null);
      setExpanded(false);
    };
    addEventListener('popstate', pop);
    return () => removeEventListener('popstate', pop);
  }, []);
  const navigate: Navigate = (patch, reset = false) => {
    const next = readRoute('?' + routeSearch({ ...(reset ? readRoute('') : route), ...patch }));
    history.pushState(null, '', '/admin?' + routeSearch(next));
    setRoute(next);
    setExpanded(false);
    setDetail(null);
  };
  useEffect(() => {
    setDetail(null);
  }, [data.identity, data.error]);
  const login = '/account?next=' + encodeURIComponent('/admin?' + routeSearch(route));
  const count = (view: View) => {
    const m = data.data?.overview.metrics;
    return !m
      ? '—'
      : view === 'interviews'
        ? m.interviews
        : view === 'questions'
          ? m.questions
          : view === 'accounts'
            ? m.accounts
            : null;
  };
  return (
    <div className="admin-layout">
      <aside className="admin-sidebar" aria-label="管理导航">
        <div className="admin-sidebar-heading">
          <span className="admin-workspace-mark">青</span>
          <div>
            <strong>管理工作台</strong>
            <small>QINGZHAN CONSOLE</small>
          </div>
          <button
            type="button"
            className="admin-mobile-toggle"
            aria-expanded={expanded}
            aria-controls="admin-side-links"
            aria-label="展开或收起管理导航"
            onClick={() => setExpanded((v) => !v)}
          >
            <Icon name="menu" />
          </button>
        </div>
        <nav id="admin-side-links" className="admin-side-links" data-expanded={expanded}>
          {(Object.keys(views) as View[])
            .filter((view) => view !== 'audit' || data.data?.overview.permissions.audit)
            .map((view) => (
              <a
                key={view}
                href={'/admin?view=' + view}
                aria-current={route.view === view ? 'page' : undefined}
                onClick={(e) => {
                  if (!e.metaKey && !e.ctrlKey && !e.shiftKey) {
                    e.preventDefault();
                    navigate({ view }, true);
                  }
                }}
              >
                <Icon name={view} />
                <span>{views[view]}</span>
                {count(view) !== null && <small>{count(view)}</small>}
              </a>
            ))}
          <div className="admin-sidebar-foot">
            <p>运营与内容</p>
            <span>
              查看趋势、核对题库，
              <br />
              让每一次准备更有方向。
            </span>
            <a href="/guide">
              使用指南
              <Icon name="arrow" />
            </a>
          </div>
        </nav>
      </aside>
      <div className="admin-main" id="admin-main-content">
        <header className="admin-page-header">
          <div>
            <p className="admin-eyebrow">平台管理 / {views[route.view]}</p>
            <h1 id="admin-section-title">{views[route.view]}</h1>
            <p>{descriptions[route.view]}</p>
          </div>
          <div className="admin-header-actions">
            {data.data?.overview.role === 'administrator' && (
              <a className="notes-button" href="/forum?view=moderation">
                举报审核
              </a>
            )}
            {data.data && (
              <span className="admin-badge">
                {data.data.overview.role === 'administrator' ? '管理员' : '只读观察员'}
              </span>
            )}
            {data.data?.overview.permissions.export &&
              route.view !== 'overview' &&
              route.view !== 'audit' && (
                <button
                  type="button"
                  className="notes-button"
                  disabled={exporting || data.loading}
                  onClick={exportData}
                >
                  {exporting ? '正在导出…' : '导出 CSV'}
                </button>
              )}
            {route.view === 'overview' && (
              <label>
                <span className="sr-only">趋势统计时段</span>
                <select
                  aria-label="趋势统计时段"
                  value={route.days}
                  onChange={(e) => navigate({ days: Number(e.target.value) })}
                >
                  {[7, 14, 30, 90].map((days) => (
                    <option key={days} value={days}>
                      最近 {days} 天
                    </option>
                  ))}
                </select>
              </label>
            )}
            <button
              className="notes-button"
              type="button"
              disabled={data.loading || !data.identity}
              onClick={data.refresh}
            >
              <Icon name="refresh" />
              刷新数据
            </button>
          </div>
        </header>
        {!data.identity || data.error?.status === 401 ? (
          <section className="admin-state" aria-labelledby="admin-gate-title">
            <span className="admin-state-icon">
              <Icon name="accounts" />
            </span>
            <h2 id="admin-gate-title">请登录管理账户</h2>
            <p>登录后核对管理权限，再查看平台数据。</p>
            <a className="notes-button notes-primary" href={login}>
              登录账户
            </a>
            <a href="/">返回首页</a>
          </section>
        ) : data.error ? (
          <section className="admin-state" role="alert">
            <span className="admin-state-icon">
              <Icon name="overview" />
            </span>
            <h2>{data.error.status === 403 ? '暂时没有访问权限' : '数据暂未加载'}</h2>
            <p>{data.error.message}</p>
            {data.error.requestId && (
              <code className="admin-request-id">请求编号：{data.error.requestId}</code>
            )}
            <div className="admin-state-actions">
              {data.error.status === 422 && (
                <button
                  className="notes-button notes-primary"
                  type="button"
                  onClick={() => navigate({ view: route.view }, true)}
                >
                  清除筛选
                </button>
              )}
              <button className="notes-button" type="button" onClick={data.refresh}>
                重新读取
              </button>
              <a className="notes-button" href="/account">
                账户中心
              </a>
            </div>
          </section>
        ) : data.loading || !data.data ? (
          <section
            className="admin-loading"
            role="status"
            aria-label="正在加载管理数据"
            aria-busy="true"
          >
            <span className="sr-only">正在读取统计与记录，请稍候。</span>
            <div className="admin-skeleton-metrics">
              {[1, 2, 3, 4].map((n) => (
                <div key={n} />
              ))}
            </div>
            <div className="admin-skeleton-panel" />
            <div className="admin-skeleton-panel" />
          </section>
        ) : (
          <>
            <div className="admin-update">
              <span className="admin-live-dot" />
              数据更新于 {formatDate(data.data.overview.generated_at)}
              <span>北京时间 · 当前部署</span>
            </div>
            {operationError && (
              <div className="admin-operation-error" role="alert">
                {operationError.message}
                {operationError.requestId && <small>请求编号：{operationError.requestId}</small>}
                <button
                  type="button"
                  className="admin-text-button"
                  onClick={() => setOperationError(null)}
                >
                  关闭提示
                </button>
              </div>
            )}
            {route.view === 'overview' && (
              <>
                <Metrics data={data.data.overview} navigate={navigate} />
                <div className="admin-chart-grid">
                  <section
                    className="admin-panel admin-trend-panel"
                    aria-labelledby="activity-title"
                  >
                    <header>
                      <div>
                        <p className="admin-eyebrow">ACTIVITY</p>
                        <h2 id="activity-title">练习活动趋势</h2>
                      </div>
                      <span className="admin-badge">最近 {route.days} 天</span>
                    </header>
                    <TrendChart rows={data.data.overview.trend} />
                  </section>
                  <section className="admin-panel" aria-labelledby="status-title">
                    <header>
                      <div>
                        <p className="admin-eyebrow">PROGRESS</p>
                        <h2 id="status-title">练习状态分布</h2>
                      </div>
                    </header>
                    <StatusChart
                      rows={data.data.overview.statuses}
                      total={data.data.overview.metrics.interviews}
                    />
                    <p className="admin-help">
                      全部练习中，已完成 {data.data.overview.metrics.finished} 场。
                    </p>
                  </section>
                </div>
                <div className="admin-secondary-grid">
                  <section className="admin-panel" aria-labelledby="coverage-title">
                    <header>
                      <div>
                        <p className="admin-eyebrow">QUESTION BANK</p>
                        <h2 id="coverage-title">各方向题库覆盖</h2>
                      </div>
                      <a
                        href="/admin?view=questions"
                        onClick={(e) => {
                          e.preventDefault();
                          navigate({ view: 'questions' }, true);
                        }}
                      >
                        查看题库
                      </a>
                    </header>
                    <CoverageChart rows={data.data.overview.coverage} />
                  </section>
                  <section className="admin-panel admin-quality" aria-labelledby="quality-title">
                    <p className="admin-eyebrow">LEARNING SIGNALS</p>
                    <h2 id="quality-title">从反馈，回到下一步</h2>
                    <strong>
                      {data.data.overview.metrics.answer_average ?? '—'}
                      <small>/ 10</small>
                    </strong>
                    <p>已评分回答均分</p>
                    <dl>
                      <div>
                        <dt>评分样本</dt>
                        <dd>{data.data.overview.metrics.scored_answers} 轮</dd>
                      </div>
                      <div>
                        <dt>运行方向</dt>
                        <dd>{data.data.overview.metrics.positions} 个</dd>
                      </div>
                    </dl>
                    <p className="admin-help">
                      按已评分回答轮次汇总。样本量与题型会影响均分，不用于比较用户或判断录用。
                    </p>
                  </section>
                </div>
              </>
            )}
            <section className="admin-panel admin-records" aria-labelledby="records-title">
              <header>
                <div>
                  <p className="admin-eyebrow">
                    {route.view === 'overview' ? 'LATEST RECORDS' : 'DATA EXPLORER'}
                  </p>
                  <h2 id="records-title">
                    {route.view === 'overview' ? '最近练习' : views[route.view]}
                  </h2>
                </div>
                {route.view === 'overview' ? (
                  <a
                    href="/admin?view=interviews"
                    onClick={(e) => {
                      e.preventDefault();
                      navigate({ view: 'interviews' }, true);
                    }}
                  >
                    查看全部
                    <Icon name="arrow" />
                  </a>
                ) : (
                  <span className="admin-badge">{data.data.page.total} 条记录</span>
                )}
              </header>
              {route.view !== 'overview' && (
                <Filters route={route} roles={data.data.overview.roles} navigate={navigate} />
              )}
              {data.data.page.items.length ? (
                <DataTable
                  view={route.view}
                  page={data.data.page}
                  roles={data.data.overview.roles}
                  onInspect={setDetail}
                />
              ) : (
                <div className="admin-empty" role="status">
                  <Icon name={route.view} />
                  <h3>没有找到相关记录</h3>
                  <p>可以调整关键词或筛选条件后再试。</p>
                  {route.view !== 'overview' && (
                    <button
                      className="notes-button"
                      type="button"
                      onClick={() => navigate({ view: route.view }, true)}
                    >
                      清除筛选
                    </button>
                  )}
                </div>
              )}
              {route.view !== 'overview' && (
                <Pagination route={route} page={data.data.page} navigate={navigate} />
              )}
            </section>
            <footer className="admin-data-note">
              <details>
                <summary>统计口径与数据范围</summary>
                <p>
                  累计指标来自当前数据库；运行题库来自当前生效的题目集合。趋势按北京时间自然日统计已启动和已完成的练习，未启动场次只计入累计练习。完成率为已完成场次占全部场次的比例。业务列表提供摘要，不包含简历、回答正文、邮箱地址或登录凭据。审校结果独立保存，题目内容变化后会重新标记为待审校。导出遵循当前筛选条件，最多1000条、5MB。
                </p>
              </details>
              <span>青栈 · 管理工作台</span>
            </footer>
          </>
        )}
        <Detail
          row={detail}
          close={() => setDetail(null)}
          roles={data.data?.overview.roles || []}
          identity={data.identity}
          editable={!!data.data?.overview.permissions.review}
          saved={() => {
            setDetail(null);
            setNotice('审校结果已保存');
            data.refresh();
          }}
        />
        {notice && (
          <div className="admin-toast" role="status">
            {notice}
          </div>
        )}
      </div>
    </div>
  );
}
