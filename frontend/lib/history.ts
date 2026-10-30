import type { InterviewSummary } from "./types";

export interface HistoryEntry {
  id: string;
  summary?: InterviewSummary;
  error?: string;
}

/** 有界并发，单条失败保留重试入口；不请求报告、回答或外部模型。 */
export async function loadHistory(ids: string[], fetchSummary: (id: string) => Promise<InterviewSummary>): Promise<HistoryEntry[]> {
  const entries: HistoryEntry[] = [];
  const selected = [...new Set(ids)].slice(0, 50);
  for (let start = 0; start < selected.length; start += 4) {
    const chunk = await Promise.all(selected.slice(start, start + 4).map(async id => {
      try { return { id, summary: await fetchSummary(id) }; }
      catch (error) { return { id, error: error instanceof Error ? error.message : "暂时无法读取，请重试" }; }
    }));
    entries.push(...chunk);
  }
  return entries.sort((a, b) => (b.summary?.last_activity_at ?? "").localeCompare(a.summary?.last_activity_at ?? ""));
}
