import type { QuestionEvent, ScoreEvent } from '../lib/types';

export interface PendingAnswer {
  type: 'answer';
  message_id: string;
  turn_id: string;
  version: number;
  text: string;
  code?: string;
}
export interface SavedTurn extends QuestionEvent {
  answer?: string;
  score?: ScoreEvent;
}
export type Phase = 'connecting' | 'active' | 'waiting' | 'finished' | 'cancelled' | 'error';
export interface StudioState {
  phase: Phase;
  version: number;
  sequence: number;
  question: QuestionEvent | null;
  turns: SavedTurn[];
  lastScore: ScoreEvent | null;
  pending: PendingAnswer | null;
  text: string;
  code: string;
  recovery: string;
  error: string;
  denied: boolean;
}
export type PracticeEvent =
  | (QuestionEvent & { seq?: number; version?: number })
  | (ScoreEvent & { seq?: number; version?: number })
  | {
      type: 'answer_ack';
      turn_id: string;
      message_id: string;
      answer_text: string;
      seq?: number;
      version?: number;
    }
  | {
      type: 'snapshot';
      version: number;
      state: string;
      finished: boolean;
      cancelled?: boolean;
      current_question: QuestionEvent | null;
      events: PracticeEvent[];
    }
  | { type: 'report_ready' | 'interview_cancelled'; seq?: number; version?: number }
  | { type: 'error'; detail: string; code?: string; seq?: number; version?: number }
  | { type: 'state' | 'greeting' | 'agent_message' | 'closing'; seq?: number; version?: number };
export type Action =
  | { type: 'event'; event: PracticeEvent }
  | { type: 'draft'; text: string; code: string }
  | { type: 'submit'; pending: PendingAnswer }
  | { type: 'phase'; phase: Phase; error?: string }
  | { type: 'identity' }
  | { type: 'cancel' };

export const initialState = (): StudioState => ({
  phase: 'connecting',
  version: 0,
  sequence: -1,
  question: null,
  turns: [],
  lastScore: null,
  pending: null,
  text: '',
  code: '',
  recovery: '',
  error: '',
  denied: false,
});
export const terminal = (state: StudioState) =>
  state.phase === 'finished' || state.phase === 'cancelled';
const draft = (state: StudioState) => [state.text, state.code].filter(Boolean).join('\n\n');
function changeQuestion(state: StudioState, question: QuestionEvent | null): StudioState {
  if (state.question?.turn_id === question?.turn_id) return { ...state, question };
  return {
    ...state,
    question,
    recovery: !state.pending && draft(state) ? draft(state) : state.recovery,
    text: '',
    code: '',
  };
}
function merge(state: StudioState, id: string, patch: Partial<SavedTurn>): SavedTurn[] {
  const found = state.turns.some((row) => row.turn_id === id);
  return found
    ? state.turns.map((row) => (row.turn_id === id ? { ...row, ...patch } : row))
    : [...state.turns, { type: 'question', id: '', turn_id: id, theme: '', content: '', ...patch }];
}
function wire(state: StudioState, event: PracticeEvent, replay = false): StudioState {
  if (event.type === 'snapshot') {
    let restored = initialState();
    for (const item of event.events) restored = wire(restored, item, true);
    const committed =
      state.pending &&
      event.events.some(
        (item) => item.type === 'answer_ack' && item.message_id === state.pending?.message_id
      );
    const complete =
      event.cancelled || event.state === 'cancelled'
        ? 'cancelled'
        : event.finished
          ? 'finished'
          : 'active';
    const resend =
      !committed &&
      complete === 'active' &&
      state.pending?.turn_id === event.current_question?.turn_id &&
      state.pending?.version === event.version;
    const stale = state.pending && !committed && !resend;
    const same = state.question?.turn_id === event.current_question?.turn_id;
    return {
      ...restored,
      version: event.version,
      question: event.current_question,
      phase: complete,
      pending: resend ? state.pending : null,
      text: !committed && same ? state.text : '',
      code: !committed && same ? state.code : '',
      recovery: stale
        ? [state.pending?.text, state.pending?.code].filter(Boolean).join('\n\n')
        : !same && !committed && draft(state)
          ? draft(state)
          : state.recovery,
      error: stale ? '轮次已经更新，旧回答已保留在草稿恢复区，请核对后再作答。' : '',
    };
  }
  if (event.seq !== undefined && event.seq <= state.sequence) return state;
  let next = {
    ...state,
    sequence: event.seq ?? state.sequence,
    version: event.version ?? state.version,
  };
  if (event.type === 'question') {
    next.turns = merge(next, event.turn_id, event);
    if (!replay)
      next = { ...changeQuestion(next, event), phase: 'active', pending: null, error: '' };
  } else if (event.type === 'answer_ack') {
    next.turns = merge(next, event.turn_id, { answer: event.answer_text });
    if (!replay && next.pending?.message_id === event.message_id)
      next = { ...next, pending: null, text: '', code: '', phase: 'waiting' };
  } else if (event.type === 'score') {
    next.turns = merge(next, event.turn_id, { score: event });
    next.lastScore = event;
  } else if (event.type === 'report_ready' || event.type === 'interview_cancelled') {
    next.phase = event.type === 'report_ready' ? 'finished' : 'cancelled';
    if (!replay) next = { ...changeQuestion(next, null), pending: null };
  } else if (event.type === 'error') {
    if (event.code === 'access_revoked')
      return {
        ...initialState(),
        phase: 'error',
        denied: true,
        error: '访问授权已变化，请重新登录所属账户。',
      };
    next.error = event.detail;
    if (next.pending)
      next.recovery = [next.pending.text, next.pending.code].filter(Boolean).join('\n\n');
    next.pending = null;
    if (['assets_changed', 'legacy_session', 'not_found'].includes(event.code || ''))
      next.phase = 'error';
  }
  return next;
}
export function reduceStudio(state: StudioState, action: Action): StudioState {
  if (action.type === 'event') return wire(state, action.event);
  if (action.type === 'draft') return { ...state, text: action.text, code: action.code };
  if (action.type === 'submit') return { ...state, pending: action.pending, error: '' };
  if (action.type === 'identity')
    return {
      ...initialState(),
      phase: 'error',
      denied: true,
      error: '账户已变化，请重新打开这场练习。',
    };
  if (action.type === 'cancel')
    return { ...changeQuestion(state, null), phase: 'cancelled', pending: null };
  return { ...state, phase: action.phase, error: action.error ?? state.error };
}

const id = (value: unknown) => typeof value === 'string' && /^[a-f0-9]{32}$/.test(value);
const text = (value: unknown, limit: number) => typeof value === 'string' && value.length <= limit;
const integer = (value: unknown) => Number.isSafeInteger(value) && Number(value) >= 0;
export function validPending(value: unknown): value is PendingAnswer {
  if (!value || typeof value !== 'object') return false;
  const p = value as PendingAnswer;
  return (
    p.type === 'answer' &&
    text(p.message_id, 64) &&
    /^[A-Za-z0-9_-]+$/.test(p.message_id) &&
    id(p.turn_id) &&
    integer(p.version) &&
    typeof p.text === 'string' &&
    Array.from(p.text).length <= 20000 &&
    (p.code === undefined ||
      (typeof p.code === 'string' && new TextEncoder().encode(p.code).length <= 16384))
  );
}
export function parsePracticeEvent(value: unknown, nested = false): PracticeEvent {
  if (!value || typeof value !== 'object') throw new Error('消息格式异常，请重新同步。');
  const e = value as Record<string, unknown>;
  if (typeof e.type !== 'string') throw new Error('消息类型异常，请重新同步。');
  const score = (n: unknown) => typeof n === 'number' && Number.isFinite(n) && n >= 0 && n <= 10;
  const strings = (v: unknown) =>
    Array.isArray(v) && v.length <= 50 && v.every((s) => text(s, 2000));
  if ((e.seq !== undefined && !integer(e.seq)) || (e.version !== undefined && !integer(e.version)))
    throw new Error('消息版本异常，请重新同步。');
  let valid = false;
  if (e.type === 'snapshot') {
    valid =
      !nested &&
      integer(e.version) &&
      typeof e.finished === 'boolean' &&
      (e.cancelled === undefined || typeof e.cancelled === 'boolean') &&
      text(e.state, 40) &&
      Array.isArray(e.events) &&
      e.events.length <= 2000;
    if (valid && Array.isArray(e.events)) {
      e.events = e.events.map((item: unknown) => parsePracticeEvent(item, true));
      if (e.current_question !== null) {
        const question = parsePracticeEvent(e.current_question, true);
        e.current_question = question;
        valid = question.type === 'question';
      }
    }
  } else if (e.type === 'question')
    valid =
      id(e.turn_id) &&
      text(e.id, 120) &&
      text(e.theme, 120) &&
      text(e.content, 20000) &&
      (e.is_probe === undefined || typeof e.is_probe === 'boolean') &&
      (e.is_coding === undefined || typeof e.is_coding === 'boolean') &&
      (e.probe_depth === undefined || (integer(e.probe_depth) && Number(e.probe_depth) <= 20)) &&
      (e.testcases == null ||
        (Array.isArray(e.testcases) &&
          e.testcases.length <= 50 &&
          e.testcases.every((value: unknown) => {
            if (!value || typeof value !== 'object') return false;
            const t = value as Record<string, unknown>;
            return text(t.input, 20000) && text(t.expected, 20000);
          })));
  else if (e.type === 'score')
    valid =
      id(e.turn_id) &&
      score(e.score) &&
      text(e.evidence, 20000) &&
      e.dimensions !== null &&
      typeof e.dimensions === 'object' &&
      !Array.isArray(e.dimensions) &&
      Object.keys(e.dimensions).length <= 20 &&
      Object.values(e.dimensions).every(score) &&
      strings(e.key_points_hit) &&
      strings(e.key_points_missed);
  else if (e.type === 'answer_ack')
    valid = id(e.turn_id) && text(e.message_id, 64) && text(e.answer_text, 40000);
  else if (e.type === 'error') valid = text(e.detail, 1000);
  else
    valid = [
      'state',
      'greeting',
      'agent_message',
      'closing',
      'report_ready',
      'interview_cancelled',
    ].includes(e.type);
  if (!valid) throw new Error('消息格式异常，请重新同步。');
  return e as unknown as PracticeEvent;
}
