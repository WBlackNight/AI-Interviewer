import React from 'react';
import { Overview } from './api';
import { Navigate, View } from './state';
import { Icon } from './Icon';

export function Metrics({ data, navigate }: { data: Overview; navigate: Navigate }) {
  const m = data.metrics;
  const cards: [View, string, number, string][] = [
    [
      'interviews',
      '累计练习',
      m.interviews,
      '近' + data.days + '日启动 ' + data.trend.reduce((sum, r) => sum + r.started, 0) + ' 场',
    ],
    ['interviews', '已完成练习', m.finished, '全站完成率 ' + m.completion_rate + '%'],
    ['accounts', '注册账户', m.accounts, '近' + data.days + '日新增 ' + m.new_accounts + ' 位'],
    ['questions', '运行题库', m.questions, '覆盖 ' + m.positions + ' 个练习方向'],
  ];
  return (
    <section className="admin-metrics" aria-label="核心指标">
      {cards.map(([view, label, value, note]) => (
        <a
          key={label}
          href={'/admin?view=' + view}
          onClick={(e) => {
            if (!e.metaKey && !e.ctrlKey && !e.shiftKey) {
              e.preventDefault();
              navigate({ view }, true);
            }
          }}
        >
          <div>
            <span>{label}</span>
            <span className="admin-metric-icon">
              <Icon name={view} />
            </span>
          </div>
          <strong>{value.toLocaleString('zh-CN')}</strong>
          <p>{note}</p>
        </a>
      ))}
    </section>
  );
}
