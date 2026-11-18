import React from 'react';
import { Overview } from './api';
import { statusLabels, trendPoints } from './state';
export function TrendChart({ rows }: { rows: Overview['trend'] }) {
  const max = Math.max(
    3,
    Math.ceil(Math.max(0, ...rows.map((r) => Math.max(r.started, r.completed))) / 3) * 3
  );
  const started = trendPoints(
      rows.map((r) => r.started),
      560,
      164,
      max
    ),
    completed = trendPoints(
      rows.map((r) => r.completed),
      560,
      164,
      max
    );
  const path = (points: readonly (readonly [number, number])[]) =>
    points.map(([x, y], i) => (i ? 'L' : 'M') + x.toFixed(2) + ' ' + y.toFixed(2)).join(' ');
  const hasData = rows.some((r) => r.started || r.completed);
  return (
    <>
      <div className="admin-chart-key">
        <span>启动练习</span>
        <span>完成练习</span>
      </div>
      <svg
        className="admin-trend"
        viewBox="0 0 640 224"
        role="img"
        aria-labelledby="admin-trend-title admin-trend-description"
      >
        <title id="admin-trend-title">练习活动趋势</title>
        <desc id="admin-trend-description">
          按北京时间自然日汇总，实线为启动练习，虚线为完成练习。下方可查看完整数据表。
        </desc>
        {[0, 1, 2, 3].map((i) => (
          <g key={i}>
            <line x1="40" x2="600" y1={20 + (i * 164) / 3} y2={20 + (i * 164) / 3} />
            <text x="28" y={25 + (i * 164) / 3} textAnchor="end">
              {Math.round(max * (1 - i / 3))}
            </text>
          </g>
        ))}
        <path className="admin-trend-area" d={path(started) + ' L600 184 L40 184 Z'} />
        <path className="admin-trend-started" d={path(started)} />
        <path className="admin-trend-completed" d={path(completed)} />
        {rows
          .filter(
            (_, i) => i === 0 || i === rows.length - 1 || i % Math.ceil(rows.length / 5) === 0
          )
          .map((row) => {
            const i = rows.indexOf(row);
            return (
              <text key={row.date} x={started[i][0]} y="213" textAnchor="middle">
                {row.date.slice(5).replace('-', '/')}
              </text>
            );
          })}
      </svg>
      {!hasData && <p className="admin-help">所选时段暂无已启动或已完成的练习。</p>}
      <details className="admin-chart-details">
        <summary>查看趋势数据</summary>
        <div className="admin-table-scroll">
          <table>
            <caption className="sr-only">每日启动与完成练习数量</caption>
            <thead>
              <tr>
                <th scope="col">日期</th>
                <th scope="col">启动</th>
                <th scope="col">完成</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.date}>
                  <th scope="row">{r.date}</th>
                  <td>{r.started}</td>
                  <td>{r.completed}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </>
  );
}
export function StatusChart({ rows, total }: { rows: Overview['statuses']; total: number }) {
  const colors: Record<string, string> = {
    created: '#b4c4b9',
    running: '#78a18b',
    finished: '#2d6b50',
    cancelled: '#c4a883',
  };
  let offset = 0;
  return (
    <div className="admin-status-chart">
      <svg viewBox="0 0 180 180" role="img" aria-label={'练习状态分布，共' + total + '场'}>
        <circle className="admin-donut-track" cx="90" cy="90" r="66" />
        {rows.map((row) => {
          const part = total ? (row.count / total) * 100 : 0,
            start = offset;
          offset += part;
          return (
            <circle
              key={row.key}
              cx="90"
              cy="90"
              r="66"
              fill="none"
              stroke={colors[row.key] || '#8b9290'}
              strokeWidth="18"
              pathLength="100"
              strokeDasharray={`${part} ${100 - part}`}
              strokeDashoffset={-start}
              transform="rotate(-90 90 90)"
            >
              <title>
                {statusLabels[row.key] || '其他'}：{row.count}场
              </title>
            </circle>
          );
        })}
        <text x="90" y="88" textAnchor="middle" className="admin-donut-total">
          {total}
        </text>
        <text x="90" y="110" textAnchor="middle">
          全部练习
        </text>
      </svg>
      <ul>
        {rows.length ? (
          rows.map((row) => (
            <li key={row.key}>
              <span>
                <svg
                  className="admin-legend-dot"
                  viewBox="0 0 10 10"
                  width="10"
                  height="10"
                  aria-hidden="true"
                >
                  <circle cx="5" cy="5" r="4" fill={colors[row.key] || '#8b9290'} />
                </svg>
                {statusLabels[row.key] || '其他状态'}
              </span>
              <strong>
                {row.count}
                <small>场</small>
              </strong>
            </li>
          ))
        ) : (
          <li>暂无练习记录</li>
        )}
      </ul>
    </div>
  );
}
export function CoverageChart({ rows }: { rows: Overview['coverage'] }) {
  const max = Math.max(1, ...rows.map((r) => r.count));
  return (
    <div className="admin-coverage">
      {rows.length ? (
        rows.map((row) => (
          <div key={row.position}>
            <div>
              <span>{row.name}</span>
              <strong>
                {row.count}
                <small>题</small>
              </strong>
            </div>
            <meter min="0" max={max} value={row.count} aria-label={row.name + '题库数量'}>
              {row.count}
            </meter>
          </div>
        ))
      ) : (
        <p className="admin-help">尚未加载运行题库。</p>
      )}
    </div>
  );
}
