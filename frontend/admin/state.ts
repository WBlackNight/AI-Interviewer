export type View = 'overview' | 'interviews' | 'questions' | 'accounts' | 'audit';
export type Route = {
  view: View;
  q: string;
  position: string;
  status: string;
  difficulty: string;
  kind: string;
  bound: string;
  start: string;
  end: string;
  sort: string;
  review: string;
  action: string;
  outcome: string;
  page: number;
  limit: number;
  days: number;
};
export type Navigate = (patch: Partial<Route>, reset?: boolean) => void;
export const views = {
  overview: '运营概览',
  interviews: '练习记录',
  questions: '题库目录',
  accounts: '用户概况',
  audit: '操作记录',
};
export const reviewLabels: Record<string, string> = {
  pending: '待审校',
  approved: '已核对',
  needs_revision: '需修改',
};
export const actionLabels: Record<string, string> = {
  data_export: '数据导出',
  question_review: '题目审校',
  permission_denied: '权限拒绝',
};
export const sortOptions = (view: View) =>
  view === 'questions'
    ? { default: '默认顺序', name: '题目名称', difficulty: '难度从低到高' }
    : view === 'audit'
      ? { default: '最近操作优先' }
      : {
          default: '最近时间优先',
          oldest: '最早时间优先',
          ...(view === 'accounts' ? { name: '用户名排序' } : {}),
        };
function validDate(value: string | null) {
  return value &&
    /^\d{4}-\d{2}-\d{2}$/.test(value) &&
    !Number.isNaN(Date.parse(value)) &&
    new Date(value).toISOString().slice(0, 10) === value
    ? value
    : '';
}
export const statusLabels: Record<string, string> = {
  created: '待开始',
  running: '进行中',
  finished: '已完成',
  cancelled: '已取消',
};
export const difficultyLabels: Record<string, string> = { easy: '基础', mid: '进阶', hard: '挑战' };
export function readRoute(search: string): Route {
  const p = new URLSearchParams(search);
  const pick = (key: string, allowed: string[], fallback = '') =>
    allowed.includes(p.get(key) || '') ? p.get(key)! : fallback;
  const view = pick('view', Object.keys(views), 'overview') as View;
  return {
    view,
    q: (p.get('q') || '').slice(0, 80),
    position: /^[a-z0-9_]{1,64}$/.test(p.get('position') || '') ? p.get('position')! : '',
    status: pick('status', Object.keys(statusLabels)),
    difficulty: pick('difficulty', Object.keys(difficultyLabels)),
    kind: pick('kind', ['coding', 'knowledge']),
    bound: pick('bound', ['bound', 'unbound']),
    start: validDate(p.get('start')),
    end: validDate(p.get('end')),
    sort: pick(
      'sort',
      [
        ...Object.keys(sortOptions(view)),
        ...(view === 'interviews' || view === 'accounts' ? ['newest'] : []),
      ],
      'default'
    ),
    review: pick('review', Object.keys(reviewLabels)),
    action: pick('action', Object.keys(actionLabels)),
    outcome: pick('outcome', ['succeeded', 'denied']),
    page: /^[1-9]\d{0,3}$/.test(p.get('page') || '') ? Math.min(2000, Number(p.get('page'))) : 1,
    limit: [10, 20, 50].includes(Number(p.get('limit'))) ? Number(p.get('limit')) : 10,
    days: [7, 14, 30, 90].includes(Number(p.get('days'))) ? Number(p.get('days')) : 14,
  };
}
export function routeSearch(route: Route) {
  const p = new URLSearchParams({ view: route.view });
  for (const key of [
    'q',
    'position',
    'status',
    'difficulty',
    'kind',
    'bound',
    'start',
    'end',
    'review',
    'action',
    'outcome',
  ] as const)
    if (route[key]) p.set(key, route[key]);
  if (route.sort !== 'default') p.set('sort', route.sort);
  if (route.page > 1) p.set('page', String(route.page));
  if (route.limit !== 10) p.set('limit', String(route.limit));
  if (route.days !== 14) p.set('days', String(route.days));
  return p.toString();
}
export function listPath(route: Route) {
  const view = route.view === 'overview' ? 'interviews' : route.view;
  const p = new URLSearchParams({
    offset: String((route.page - 1) * route.limit),
    limit: String(route.limit),
  });
  if (route.q) p.set('q', route.q);
  const keys =
    view === 'interviews'
      ? ['position', 'status', 'start', 'end', 'sort']
      : view === 'questions'
        ? ['position', 'difficulty', 'kind', 'review', 'sort']
        : view === 'audit'
          ? ['action', 'outcome', 'start', 'end']
          : ['bound', 'start', 'end', 'sort'];
  for (const key of keys as (keyof Route)[]) if (route[key]) p.set(key, String(route[key]));
  return '/api/admin/' + view + '?' + p;
}
export function exportPath(route: Route) {
  const url = new URL(listPath(route), 'http://localhost');
  url.searchParams.delete('offset');
  url.searchParams.delete('limit');
  url.searchParams.set('resource', route.view === 'overview' ? 'interviews' : route.view);
  return '/api/admin/export?' + url.searchParams;
}
export function trendPoints(values: number[], width = 560, height = 164, ceiling?: number) {
  const max = Math.max(1, ceiling ?? Math.max(0, ...values));
  return values.map(
    (value, index) =>
      [
        40 + (index * width) / Math.max(1, values.length - 1),
        20 + height - (Math.max(0, value) / max) * height,
      ] as const
  );
}
export const formatDate = (value: string | null) =>
  value
    ? new Intl.DateTimeFormat('zh-CN', {
        timeZone: 'Asia/Shanghai',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      }).format(new Date(value))
    : '尚未开始';
