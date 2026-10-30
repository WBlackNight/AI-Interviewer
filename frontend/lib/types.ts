/** 与后端 domain.py / schemas.py 严格对应的类型定义（单一事实来源的镜像）。 */

export interface PlanItem {
  theme: string;
  weight: number;
  difficulty: string;
  question_count: number;
  include_coding: boolean;
}

export interface PositionOption {
  id: string;
  display_name: string;
  roots: string[];
  question_count: number;
  practice_themes?: string[];
  practice_theme_limit?: number;
}

export interface ResumeResponse {
  access_token: string | null;
  account_owned?: boolean;
  resume_id: string;
  user_id: string;
  skills: string[];
  projects: string[];
  education: string;
}

export interface InterviewCreateResponse {
  access_token: string | null;
  account_owned?: boolean;
  interview_id: string;
  position: string;
  plan: PlanItem[];
  ws_url: string;
}

export interface QuestionEvent {
  turn_id: string;
  skill_node_id?: string;
  type: "question";
  id: string;
  theme: string;
  content: string;
  difficulty?: string;
  is_coding?: boolean;
  is_probe?: boolean;
  probe_depth?: number;
  testcases?: { input: string; expected: string }[] | null;
}

export interface ScoreEvent {
  scoring_origin?: ScoringOrigin;
  turn_id: string;
  type: "score";
  question_id: string;
  score: number;
  dimensions: Record<string, number>;
  key_points_hit: string[];
  key_points_missed: string[];
  evidence: string;
  sandbox: { passed: number; total: number; detail: unknown[] } | null;
}

/** 语音链路事件与上行载荷（P1，对应 backend/app/domain.py EventType）。 */

export interface AudioFramePayload {
  type: "audio";
  turn_id: string;
  seq: number;
  data: string; // base64(PCM s16le)
  format?: "pcm_s16le";
  sample_rate?: 16000;
  channels?: 1;
}

export interface AudioEndPayload {
  type: "audio_end";
  turn_id: string;
}

export interface InterruptPayload {
  type: "interrupt";
  utterance_id?: string;
}

export type VoiceEvent =
  | { type: "asr_partial"; turn_id: string; text: string }
  /** t_vad_end：服务端单调时钟的 VAD 判定点（用于与服务端 t_emit 相减）。 */
  | { type: "asr_final"; turn_id: string; text: string; t_vad_end?: number }
  | {
      type: "tts_chunk";
      utterance_id: string;
      seq: number;
      format: string;
      sample_rate: number;
      channels: number;
      data: string;
      /** t_emit：首个分片（seq=0）的服务端入队时刻。 */
      t_emit?: number;
    }
  | { type: "tts_end"; utterance_id: string }
  | { type: "barge_in_ack"; utterance_id: string | null; note?: string }
  | { type: "voice_gap"; turn_id: string; detail: string }
  | { type: "voice_empty"; turn_id: string; detail: string }
  | { type: "voice_error"; turn_id: string; detail: string }
  | { type: "voice_cancelled"; turn_id: string; reason: string };

export type ServerEvent =
  | { type: "state"; state: string }
  | { type: "greeting"; text: string }
  | QuestionEvent
  | { type: "answer_ack"; question_id: string; turn_id: string; answer_text: string; message_id: string; probe_depth: number }
  | ScoreEvent
  | { type: "agent_message"; text: string }
  | { type: "closing"; text: string }
  | { type: "report_ready"; interview_id: string }
  | { type: "interview_cancelled"; text: string }
  | { type: "error"; detail: string; code?: string; retryable?: boolean }
  | { type: "snapshot"; state: string; finished: boolean; cancelled?: boolean; version: number;
      current_question: QuestionEvent | null; events: WireEvent[] }
  | VoiceEvent;

export type WireEvent = ServerEvent & { seq?: number; version?: number };

export interface ChatMessage {
  id: number;
  role: "agent" | "user";
  text: string;
  kind?: "greeting" | "question" | "probe" | "coding" | "reaction" | "closing";
}

export interface PerQuestionReport {
  scoring_origin?: ScoringOrigin;
  turn_id?: string;
  main_question_id?: string;
  answer_text?: string;
  question_id: string;
  theme: string;
  content: string;
  score: number;
  probe_depth: number;
  evidence: string;
  key_points_hit: string[];
  key_points_missed: string[];
  sandbox: { passed: number; total: number } | null;
}

export interface ReportData {
  revision_source?: { task_id: string; interview_id: string; theme: string } | null;
  is_cancelled?: boolean;
  is_terminal?: boolean;
  scoring_sources?: Record<string, number>;
  practice_themes?: string[];
  position_display_name?: string;
  weak_score?: number;
  answer_count?: number;
  is_complete?: boolean;
  interview_id: string;
  position: string;
  status: string;
  overall?: number;
  question_count?: number;
  dimensions: Record<string, number>;
  theme_avg?: Record<string, number>;
  weak_points?: string[];
  recommendations?: string[];
  per_question?: PerQuestionReport[];
  started_at?: string | null;
  ended_at?: string | null;
  message?: string;
}

export interface InterviewSummary {
  position_display_name?: string;
  interview_id: string;
  position: string;
  difficulty: string;
  status: string;
  theme_count: number;
  answer_count: number;
  started_at: string | null;
  ended_at: string | null;
  last_activity_at: string | null;
}

export interface ScoringOrigin {
  source: string;
  scorer_version?: string | null;
  model?: string | null;
  prompt_version?: string | null;
  prompt_digest?: string | null;
  config_version?: string | null;
  cached?: boolean;
  fallback_reason?: string | null;
  sandbox_applied?: boolean;
  question_difficulty?: string | null;
  main_question_version?: string | null;
  question_version?: string | null;
}

export interface ReviewItem {
  interview_id: string;
  position: string;
  position_display_name: string;
  theme: string;
  difficulty: string;
  ended_at: string | null;
  score: number;
  question_count: number;
  answer_count: number;
  repeat_question_count: number;
  known_question_version_count: number;
  unknown_question_version_count: number;
  question_difficulties: Record<string, number>;
  scoring_sources: Record<string, number>;
  scoring_profiles: (ScoringOrigin & { answer_count: number; cached_count: number })[];
}

export interface AccountReview {
  positions: { id: string; display_name: string; themes: string[] }[];
  position: string | null;
  theme: string | null;
  items: ReviewItem[];
  total: number;
  offset: number;
  limit: number;
  has_more: boolean;
  session_count: number;
  completed_only: boolean;
  aggregation: string;
  repeat_definition: string;
  note: string;
}
export interface RevisionTask {
  id: string;
  interview_id: string;
  position: string;
  theme: string;
  source_score: number;
  weak_score: number;
  focus_points: string[];
  status: "todo" | "done";
  created_at: string;
  completed_at: string | null;
  due_date: string | null;
  latest_practice?: { interview_id: string; status: string } | null;
}

export type RevisionDueFilter = "all" | "today" | "overdue" | "upcoming" | "unscheduled";

export interface RevisionTaskList {
  items: RevisionTask[];
  total: number;
  offset: number;
  limit: number;
  has_more: boolean;
  status: "todo" | "done" | null;
  position: string | null;
  due: RevisionDueFilter;
  today: string;
  timezone: string;
  date_counts: Record<Exclude<RevisionDueFilter, "all">, number>;
  counts: { todo: number; done: number };
  positions: { id: string; display_name: string }[];
}

