import type { AccountReview, InterviewCreateResponse, InterviewSummary, PositionOption, ReportData, ResumeResponse, RevisionTask, RevisionTaskList, RevisionDueFilter } from "./types";
import { forgetAnonymousAccess, getAccess, getAnonymousAccess, saveAccess } from "./access";
import { clearAccountSession, getAccountSession, saveAccountSession, type AccountInfo, type AccountSession } from "./account";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const account = getAccountSession();
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    cache: "no-store",
    headers: { ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(init?.headers as Record<string, string> | undefined),
      ...(account ? { Authorization: `Bearer ${account.access_token}` } : {}) },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = typeof body?.detail === "string" ? body.detail : response.statusText;
    throw new ApiError(detail || `请求失败（${response.status}）`, response.status);
  }
  return response.json() as Promise<T>;
}

export async function createResume(payload: {
  name: string;
  resume_text: string;
}): Promise<ResumeResponse> {
  const result = await request<ResumeResponse>("/api/resume", { method: "POST", body: JSON.stringify(payload) });
  if (result.access_token) saveAccess("resume", result.resume_id, result.access_token);
  return result;
}

export interface ResumeLimits {
  pdf_max_bytes: number;
  pdf_max_pages: number;
  text_max_chars: number;
  ocr_supported: boolean;
}

export function getResumeLimits(): Promise<ResumeLimits> {
  return request("/api/resume/limits");
}

export async function createResumePdf(file: File, name: string): Promise<ResumeResponse> {
  const body = new FormData();
  body.append("file", file);
  body.append("name", name);
  const result = await request<ResumeResponse>("/api/resume/pdf", { method: "POST", body });
  if (result.access_token) saveAccess("resume", result.resume_id, result.access_token);
  return result;
}

export async function createInterview(payload: {
  resume_id?: string;
  position: string;
  difficulty: string;
  themes?: string[];
}): Promise<InterviewCreateResponse> {
  const result = await request<InterviewCreateResponse>("/api/interview", {
    method: "POST", body: JSON.stringify(payload),
    headers: { "Content-Type": "application/json", "X-Resume-Token":
      payload.resume_id ? getAccess("resume", payload.resume_id) ?? "" : "" },
  });
  if (result.access_token) saveAccess("interview", result.interview_id, result.access_token);
  return result;
}

export async function createWeakPractice(interviewId: string): Promise<InterviewCreateResponse> {
  const result = await request<InterviewCreateResponse>(`/api/interview/${interviewId}/practice`, {
    method: "POST",
    headers: { "X-Interview-Token": getAccess("interview", interviewId) ?? "" },
  });
  if (result.access_token) saveAccess("interview", result.interview_id, result.access_token);
  return result;
}

export function getReport(interviewId: string): Promise<ReportData> {
  return request(`/api/interview/${interviewId}/report`, {
    headers: { "X-Interview-Token": getAccess("interview", interviewId) ?? "" },
  });
}

export interface InterviewCancellation {
  interview_id: string;
  status: "cancelled";
  changed: boolean;
  version: number;
  report_url: string;
}

export function cancelInterview(interviewId: string): Promise<InterviewCancellation> {
  return request(`/api/interview/${interviewId}/cancel`, { method: "POST",
    headers: { "X-Interview-Token": getAccess("interview", interviewId) ?? "" } });
}

export async function getInterviewSummary(interviewId: string, anonymousToken?: string): Promise<InterviewSummary> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10000);
  try {
    return await request(`/api/interview/${interviewId}`, {
      signal: controller.signal, cache: "no-store",
      headers: { "X-Interview-Token": anonymousToken ?? getAccess("interview", interviewId) ?? "" },
    });
  } catch (error) {
    if (controller.signal.aborted) throw new Error("读取超时，请刷新重试");
    throw error;
  } finally { clearTimeout(timer); }
}

export async function exportReport(interviewId: string, format: "markdown" | "json"): Promise<void> {
  const response = await fetch(`${API_BASE}/api/interview/${interviewId}/report/export?format=${format}`, {
    cache: "no-store", headers: { "X-Interview-Token": getAccess("interview", interviewId) ?? "" },
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(typeof data?.detail === "string" ? data.detail : "报告导出失败，请稍后重试");
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = `interview-${interviewId}.${format === "markdown" ? "md" : "json"}`;
  document.body.appendChild(link);
  try { link.click(); }
  finally {
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}

export { API_BASE };

export async function authenticate(mode: "login" | "register", username: string, password: string): Promise<AccountSession> {
  const result = await request<AccountSession>(`/api/auth/${mode}`, { method: "POST", body: JSON.stringify({ username, password }) });
  saveAccountSession(result);
  return result;
}

export function getCurrentAccount(): Promise<AccountInfo> { return request("/api/auth/me"); }

export async function logoutAccount(): Promise<void> {
  try { await request("/api/auth/logout", { method: "POST" }); }
  catch (error) { if (!(error instanceof ApiError && error.status === 401)) throw error; }
  clearAccountSession();
}

export interface AccountHistory { items: InterviewSummary[]; total: number; offset: number; limit: number; has_more: boolean }
export function getAccountHistory(offset = 0): Promise<AccountHistory> {
  return request(`/api/account/interviews?offset=${offset}&limit=20`);
}

export function getAccountReview(position?: string, theme?: string, offset = 0): Promise<AccountReview> {
  const query = new URLSearchParams({ offset: String(offset), limit: "20" });
  if (position) query.set("position", position);
  if (theme) query.set("theme", theme);
  return request(`/api/account/review?${query}`);
}

export async function claimInterview(id: string): Promise<void> {
  const token = getAnonymousAccess("interview", id);
  if (!token) throw new Error("当前标签页没有该面试的匿名凭据");
  await request(`/api/account/interviews/${id}/claim`, { method: "POST", body: JSON.stringify({ access_token: token }) });
  forgetAnonymousAccess(id);
}

export async function deleteAccountInterview(id: string): Promise<void> {
  await request(`/api/account/interviews/${id}`, { method: "DELETE" });
}

export async function deleteAccount(password: string): Promise<void> {
  await request("/api/account", { method: "DELETE", body: JSON.stringify({ password }) });
  clearAccountSession();
}

export function getPositions(): Promise<{ positions: PositionOption[] }> {
  return request('/api/positions', { cache: 'no-store' });
}

export function addRevisionTasks(interviewId: string): Promise<{ items: RevisionTask[]; added: number; existing: number }> {
  return request(`/api/account/interviews/${interviewId}/revision-tasks`, { method: "POST" });
}

export function getRevisionTasks(status?: "todo" | "done", position?: string, offset = 0, due: RevisionDueFilter = "all"): Promise<RevisionTaskList> {
  const query = new URLSearchParams({ offset: String(offset), limit: "20" });
  if (status) query.set("status", status);
  if (position) query.set("position", position);
  if (due !== "all") query.set("due", due);
  return request(`/api/account/revision-tasks?${query}`);
}

export function updateRevisionTask(id: string, status: "todo" | "done"): Promise<RevisionTask> {
  return request(`/api/account/revision-tasks/${id}`, { method: "PATCH", body: JSON.stringify({ status }) });
}

export function scheduleRevisionTask(id: string, due_date: string | null): Promise<RevisionTask> {
  return request(`/api/account/revision-tasks/${id}`, { method: "PATCH", body: JSON.stringify({ due_date }) });
}

export function createRevisionPractice(taskId: string): Promise<InterviewCreateResponse & { revision_task_id: string; reused: boolean }> {
  return request(`/api/account/revision-tasks/${taskId}/practice`, { method: "POST" });
}
