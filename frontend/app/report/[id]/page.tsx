"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import RadarChart from "@/components/RadarChart";
import { createWeakPractice, exportReport, getReport } from "@/lib/api";
import type { ReportData } from "@/lib/types";
import { filterReportTurns, type ReviewKind } from "@/lib/report-filter";
import { originLabel, originVersions } from "@/lib/score-origin";
import CancelInterviewButton from "@/components/CancelInterviewButton";
import { isInterviewTerminal } from "@/lib/interview-status";
import AddRevisionTasks from "@/components/AddRevisionTasks";

export default function ReportPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const creating = useRef(false);
  const [practicing, setPracticing] = useState(false);
  const [practiceError, setPracticeError] = useState("");
  const [report, setReport] = useState<ReportData | null>(null);
  const [error, setError] = useState("");
  const [exportError, setExportError] = useState("");
  const [exporting, setExporting] = useState(false);
  const [reviewKind, setReviewKind] = useState<ReviewKind>("all");
  const [theme, setTheme] = useState("");
  async function practice() {
    if (creating.current) return;
    creating.current = true; setPracticing(true); setPracticeError("");
    try {
      const created = await createWeakPractice(params.id);
      router.push(`/interview/${created.interview_id}`);
    } catch (error) { setPracticeError(error instanceof Error ? error.message : "创建复练失败，请重试"); }
    finally { creating.current = false; setPracticing(false); }
  }
  async function download(format: "markdown" | "json") {
    setExporting(true); setExportError("");
    try { await exportReport(params.id, format); }
    catch (error) { setExportError(error instanceof Error ? error.message : "导出失败，请重试"); }
    finally { setExporting(false); }
  }

  useEffect(() => {
    getReport(params.id)
      .then(setReport)
      .catch((err) => setError(err instanceof Error ? err.message : "加载失败"));
  }, [params.id]);

  if (error) {
    return (
      <div className="rounded-2xl border border-red-200 bg-red-50 p-8 text-center text-sm text-red-700">
        {error}
      </div>
    );
  }
  if (!report) {
    return <div className="py-20 text-center text-sm text-slate-500">报告生成中…</div>;
  }

  const radarPoints = Object.entries(report.dimensions ?? {}).map(([label, value]) => ({
    label,
    value: Number(value) || 0,
  }));
  const turns = report.per_question ?? [];
  const themes = [...new Set(turns.map(turn => turn.theme))];
  const visibleTurns = filterReportTurns(turns, theme, reviewKind, report.weak_score ?? 7);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link href="/history" className="text-sm text-brand-600 hover:underline">返回练习记录</Link>
        <div className="flex gap-2">
          <button disabled={exporting} onClick={() => void download("markdown")} className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm disabled:opacity-50">{exporting ? "导出中…" : "导出 Markdown"}</button>
          <button disabled={exporting} onClick={() => void download("json")} className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm disabled:opacity-50">导出 JSON</button>
        </div>
      </div>
      {exportError && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{exportError}</p>}
      {report.revision_source && <section className="space-y-2 rounded-xl border border-brand-200 bg-brand-50 p-4 text-sm text-slate-700">
        <p>本场来自「{report.revision_source.theme}」复习任务。练习完成不会自动改变任务的手动复习状态。</p>
        <div className="flex flex-wrap gap-4"><Link href="/revision" className="text-brand-600 underline">返回复习任务板</Link><Link href={`/report/${report.revision_source.interview_id}`} className="text-brand-600 underline">查看原始报告</Link></div>
      </section>}
      {report.status === "cancelled" ? <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-800">面试已取消。这份部分报告仅包含取消前已提交的回答，不计入已完成面试的跨场对照。</p> : !report.is_complete && <div className="space-y-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-800"><p>这是当前已提交回答的部分报告。<Link href={`/interview/${params.id}`} className="ml-2 underline">继续面试</Link></p>
        {!isInterviewTerminal(report.status) && <CancelInterviewButton interviewId={params.id} onCancelled={async () => setReport(await getReport(params.id))} />}</div>}
      <section className="report-summary flex items-center justify-between rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div>
          <span className="section-eyebrow">YOUR INTERVIEW, REFLECTED</span>
          <h1 className="text-xl font-semibold">面试复盘报告</h1>
          <p className="mt-1 text-sm text-slate-500">
            岗位 {report.position_display_name ?? report.position} · 共 {report.question_count ?? 0} 题 / {report.answer_count ?? 0} 轮 ·{" "}
            {report.status === "cancelled" ? "已取消" : report.ended_at ? "已结束" : "进行中"}
          </p>
        </div>
        <div className="text-right">
          <div className="text-4xl font-semibold text-brand-600">
            {report.overall ?? "--"}
          </div>
          <div className="text-xs text-slate-400">综合得分 / 10</div>
        </div>
      </section>

      <div className="report-insights">
      {radarPoints.length >= 3 && (
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-sm font-medium text-slate-700">能力雷达</h2>
          <RadarChart points={radarPoints} />
        </section>
      )}

      {report.recommendations && report.recommendations.length > 0 && (
        <section className="rounded-2xl border border-amber-200 bg-amber-50 p-6">
          <h2 className="mb-3 text-sm font-medium text-amber-900">薄弱点与复习建议</h2>
          <ul className="space-y-2 text-sm leading-6 text-amber-900/90">
            {report.recommendations.map((tip, i) => (
              <li key={i} className="flex gap-2">
                <span>▸</span>
                <span>{tip}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
      </div>

      {report.is_complete && !!report.practice_themes?.length && <section className="space-y-3 rounded-2xl border border-brand-200 bg-white p-6">
        <h2 className="text-sm font-medium">复练薄弱主题</h2>
        <p className="text-sm text-slate-600">本场待补强：{report.practice_themes.join("、")}。按原岗位与强度创建新练习，每个主题最多2题，保留追问。跨场题目可能重复。</p>
        <button type="button" disabled={practicing} onClick={() => void practice()}
          className="rounded-lg bg-brand-600 px-4 py-2 text-sm text-white disabled:opacity-50">{practicing ? "正在创建…" : "开始薄弱项复练"}</button>
      </section>}
      {practiceError && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{practiceError}</p>}
      {report.is_complete && !!report.weak_points?.length && <AddRevisionTasks interviewId={params.id} />}

      {report.per_question && (
        <section className="space-y-4">
          <h2 className="text-sm font-medium text-slate-700">逐题明细</h2>
          <div className="space-y-3 rounded-xl border border-slate-200 bg-white p-4">
            <div className="flex flex-wrap items-center gap-3">
              <label className="text-sm text-slate-600">题目主题
                <select value={theme} onChange={event => setTheme(event.target.value)} className="ml-2 rounded-lg border border-slate-200 px-3 py-2">
                  <option value="">全部主题</option>
                  {themes.map(value => <option key={value} value={value}>{value}</option>)}
                </select>
              </label>
              <div role="group" aria-label="复盘范围" className="flex flex-wrap gap-2">
                {([['all', '全部回答'], ['weak', '待补强'], ['probe', '追问']] as const).map(([kind, text]) =>
                  <button key={kind} type="button" aria-pressed={reviewKind === kind} onClick={() => setReviewKind(kind)}
                    className={`rounded-lg border px-3 py-2 text-sm ${reviewKind === kind ? 'border-brand-600 bg-brand-50 text-brand-600' : 'border-slate-200 text-slate-600'}`}>{text}</button>)}
              </div>
            </div>
            <p aria-live="polite" className="text-xs text-slate-500">显示 {visibleTurns.length} / {turns.length} 轮回答；待补强为低于 {report.weak_score ?? 7} 分。导出始终包含完整报告。</p>
          </div>
          {visibleTurns.length === 0 && <div className="rounded-xl border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">
            当前筛选没有匹配的回答。
            {(theme || reviewKind !== 'all') && <button type="button" onClick={() => { setTheme(''); setReviewKind('all'); }} className="ml-3 text-brand-600 underline">清除筛选</button>}
          </div>}
          {visibleTurns.map((q, idx) => (
            <div
              key={`${q.question_id}-${idx}`}
              className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1">
                  <div className="flex items-center gap-2 text-xs text-slate-500">
                    <span className="rounded bg-slate-100 px-1.5 py-0.5">{q.theme}</span>
                    {q.probe_depth > 0 && (
                      <span className="rounded bg-amber-100 px-1.5 py-0.5 text-amber-800">
                        被追问 {q.probe_depth} 层
                      </span>
                    )}
                    {q.sandbox && (
                      <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-emerald-800">
                        判题 {q.sandbox.passed}/{q.sandbox.total}
                      </span>
                    )}
                  </div>
                  <p className="mt-2 text-sm leading-6">{q.content}</p>
                  {q.answer_text && <p className="mt-2 whitespace-pre-wrap text-xs leading-5 text-slate-600">你的回答：{q.answer_text}</p>}
                  <p className="mt-2 text-xs leading-5 text-slate-500">
                    评分依据：{q.evidence}
                  </p>
                  <p className="mt-2 text-xs leading-5 text-slate-600">{originLabel(q.scoring_origin)}</p>
                  <details className="mt-1 text-xs leading-5 text-slate-500"><summary className="cursor-pointer">评分来源与版本</summary><p className="mt-1 break-all">{originVersions(q.scoring_origin)}</p></details>
                  {q.key_points_missed.length > 0 && (
                    <p className="mt-1 text-xs text-amber-700">
                      待补强：{q.key_points_missed.join("、")}
                    </p>
                  )}
                </div>
                <div
                  className={`shrink-0 rounded-xl px-3 py-2 text-center ${
                    q.score >= 7
                      ? "bg-emerald-50 text-emerald-700"
                      : q.score >= 4
                        ? "bg-amber-50 text-amber-700"
                        : "bg-red-50 text-red-700"
                  }`}
                >
                  <div className="text-xl font-semibold">{q.score.toFixed(1)}</div>
                  <div className="text-[10px]">得分</div>
                </div>
              </div>
            </div>
          ))}
        </section>
      )}

      <div className="text-center">
        <Link
          href="/"
          className="inline-block rounded-lg bg-brand-600 px-6 py-3 text-sm font-medium text-white hover:bg-brand-800"
        >
          再来一场
        </Link>
      </div>
    </div>
  );
}
