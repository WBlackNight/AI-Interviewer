"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { createRevisionPractice, getRevisionTasks, updateRevisionTask, scheduleRevisionTask } from "@/lib/api";
import type { RevisionTask, RevisionTaskList, RevisionDueFilter } from "@/lib/types";
import RevisionDateEditor from "@/components/RevisionDateEditor";

type TaskStatus = "todo" | "done";
export default function RevisionPage() {
  const router = useRouter();
  const [data, setData] = useState<RevisionTaskList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [changing, setChanging] = useState<string | null>(null);
  const [practicing, setPracticing] = useState<string | null>(null);
  const [scheduling, setScheduling] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const sequence = useRef(0);
  const working = useRef(false);
  const load = useCallback(async (status?: TaskStatus, position?: string, offset = 0, due: RevisionDueFilter = "all") => {
    const version = ++sequence.current;
    setLoading(true); setError("");
    try {
      let result = await getRevisionTasks(status, position, offset, due);
      if (result.items.length === 0 && offset > 0 && result.total > 0) {
        result = await getRevisionTasks(status, position, Math.floor((result.total - 1) / result.limit) * result.limit, due);
      }
      if (sequence.current === version) setData(result);
    } catch (error) {
      if (sequence.current === version) { setData(null); setError(error instanceof Error ? error.message : "读取失败，请重试"); }
    } finally { if (sequence.current === version) setLoading(false); }
  }, []);
  useEffect(() => { void load("todo"); return () => { sequence.current++; }; }, [load]);
  async function change(task: RevisionTask) {
    if (working.current || !data) return;
    working.current = true; setChanging(task.id); setActionError(""); setNotice("");
    try {
      const updated = await updateRevisionTask(task.id, task.status === "todo" ? "done" : "todo");
      setNotice(`「${updated.theme}」已${updated.status === "done" ? "标记为已复习" : "恢复为待复习"}。`);
      await load(data.status ?? undefined, data.position ?? undefined, data.offset, data.due);
    } catch (error) { setActionError(error instanceof Error ? error.message : "更新失败，请重试"); }
    finally { working.current = false; setChanging(null); }
  }
  async function schedule(task: RevisionTask, date: string | null) {
    if (working.current || !data) return;
    working.current = true; setScheduling(task.id); setActionError(""); setNotice("");
    try {
      const updated = await scheduleRevisionTask(task.id, date);
      setNotice(`「${updated.theme}」${updated.due_date ? `已安排在 ${updated.due_date} 复习` : "已清空复习日期"}。`);
      await load(data.status ?? undefined, data.position ?? undefined, data.offset, data.due);
    } catch (error) { setActionError(error instanceof Error ? error.message : "日期保存失败，请重试"); }
    finally { working.current = false; setScheduling(null); }
  }
  async function practice(task: RevisionTask) {
    if (working.current) return;
    working.current = true; setPracticing(task.id); setActionError(""); setNotice("");
    try {
      const created = await createRevisionPractice(task.id);
      router.push(`/interview/${created.interview_id}`);
    } catch (error) { setActionError(error instanceof Error ? error.message : "创建练习失败，请重试"); }
    finally { working.current = false; setPracticing(null); }
  }
  const busy = loading || changing !== null || practicing !== null || scheduling !== null;
  return <div className="space-y-6">
    <section className="space-y-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <div><span className="section-eyebrow">ONE STEP AT A TIME</span><h1 className="text-xl font-semibold">复习任务板</h1><p className="mt-2 text-sm leading-6 text-slate-600">从已完成报告保存待补强主题，按自己的节奏复习。任务保存在账户中，重新登录可继续查看。</p></div>
      <div className="flex flex-wrap gap-4 text-sm"><Link href="/history" className="text-brand-600 underline">选择报告加入任务</Link><Link href="/review" className="text-brand-600 underline">跨场复盘</Link><Link href="/account" className="text-brand-600 underline">登录与账户</Link></div>
      {data && <>
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-xl bg-amber-50 p-4"><p className="text-xs text-amber-800">待复习</p><p className="mt-1 text-2xl font-semibold text-amber-900">{data.counts.todo}</p></div>
          <div className="rounded-xl bg-emerald-50 p-4"><p className="text-xs text-emerald-800">已复习</p><p className="mt-1 text-2xl font-semibold text-emerald-900">{data.counts.done}</p></div>
        </div>
        <div className="flex flex-wrap items-center gap-4 text-sm">
          <label>任务状态<select aria-label="任务状态" value={data.status ?? "all"} disabled={busy} onChange={event => void load(event.target.value === "all" ? undefined : event.target.value as TaskStatus, data.position ?? undefined, 0, data.due)} className="ml-2 rounded-lg border px-3 py-2">
            <option value="todo">待复习</option><option value="done">已复习</option><option value="all">全部任务</option>
          </select></label>
          <label>岗位<select aria-label="任务岗位" value={data.position ?? ""} disabled={busy} onChange={event => void load(data.status ?? undefined, event.target.value || undefined, 0, data.due)} className="ml-2 rounded-lg border px-3 py-2">
            <option value="">全部岗位</option>{data.positions.map(position => <option key={position.id} value={position.id}>{position.display_name}</option>)}
          </select></label>
          <button type="button" disabled={busy} onClick={() => void load(data.status ?? undefined, data.position ?? undefined, data.offset, data.due)} className="rounded-lg border px-4 py-2 disabled:opacity-50">刷新任务</button>
        </div>
        <div className="revision-calendar-strip">
          <div className="flex flex-wrap items-baseline justify-between gap-2"><h2 className="text-sm font-semibold">安排你的复习节奏</h2><p className="text-xs text-slate-500">今日 {data.today} · 北京时间</p></div>
          <div role="group" aria-label="复习日期筛选" className="mt-3 flex flex-wrap gap-2">{([
            ["all", "全部日期"], ["today", "今日"], ["overdue", "逾期"], ["upcoming", "未来"], ["unscheduled", "未安排"],
          ] as const).map(([key, label]) => <button key={key} type="button" aria-pressed={data.due === key} disabled={busy} onClick={() => void load(data.status ?? undefined, data.position ?? undefined, 0, key)} className={`revision-date-tab ${data.due === key ? "is-active" : ""}`}>{label}{key !== "all" && <span>{data.date_counts[key]}</span>}</button>)}</div>
          <p className="mt-3 text-xs leading-5 text-slate-500">日期统计随当前岗位和任务状态变化。完成后保留原定日期；改期不会改变复习状态。跨日后请刷新任务。</p>
        </div>
      </>}
    </section>
    <p className="rounded-xl bg-slate-100 p-4 text-xs leading-6 text-slate-600">“已复习”由你手动标记，表示学习安排的完成状态，不修改面试分数，也不代表能力评估。任务保留加入时的主题分数；评分来源和版本可在来源报告查看。删除来源面试或账户会同时删除对应任务。</p>
    <p className="text-sm leading-6 text-slate-600">可直接练习任务主题，沿用原报告的岗位与强度，每场最多2道主问题。跨场题目可能重复；练习结束后，仍由你决定是否标记已复习。</p>
    {error && <div role="alert" className="space-y-2 rounded-xl bg-red-50 p-4 text-sm text-red-700"><p>{error}</p><button type="button" disabled={busy} onClick={() => void load()} className="underline">重试读取</button></div>}
    {actionError && <p role="alert" className="rounded-xl bg-red-50 p-4 text-sm text-red-700">{actionError}</p>}
    {notice && <p role="status" className="text-sm text-emerald-700">{notice}</p>}
    {loading && <p aria-live="polite" className="py-8 text-center text-sm text-slate-500">正在读取复习任务…</p>}
    {data && !loading && <>
      {data.items.length === 0 ? <section className="space-y-3 rounded-2xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-600"><p>当前筛选下没有复习任务。</p><Link href="/history" className="text-brand-600 underline">从已完成报告添加薄弱主题</Link></section> : <div className="grid gap-4 sm:grid-cols-2">{data.items.map(task => <article key={task.id} className="flex flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex items-start justify-between gap-3"><div><h2 className="font-semibold">{task.theme}</h2><p className="mt-1 text-xs text-slate-500">{data.positions.find(p => p.id === task.position)?.display_name ?? task.position}</p></div><span className={`shrink-0 rounded-full px-3 py-1 text-xs ${task.status === "done" ? "bg-emerald-50 text-emerald-800" : "bg-amber-50 text-amber-800"}`}>{task.status === "done" ? "已复习" : "待复习"}</span></div>
        <p className={`text-xs ${task.status === "todo" && task.due_date && task.due_date < data.today ? "text-red-700" : "text-brand-600"}`}>{task.due_date ? `${task.due_date} · ${task.status === "done" ? "原定复习日" : task.due_date < data.today ? "已逾期" : task.due_date === data.today ? "今日复习" : "已安排"}` : "尚未安排复习日期"}</p>
        <RevisionDateEditor taskId={task.id} theme={task.theme} value={task.due_date} disabled={busy} saving={scheduling === task.id} onSave={date => schedule(task, date)} />
        <p className="text-sm text-slate-600">来源主题均分 <span className="font-medium text-slate-900">{task.source_score.toFixed(1)} / 10</span><span className="ml-2 text-xs text-slate-500">加入时低于 {task.weak_score} 分</span></p>
        {task.focus_points.length ? <ul className="flex-1 list-disc space-y-2 pl-5 text-sm leading-6 text-slate-700">{task.focus_points.map(point => <li key={point}>{point}</li>)}</ul> : <p className="flex-1 text-sm leading-6 text-slate-500">本场未记录具体未覆盖要点，请结合来源报告复习该主题核心概念。</p>}
        <p className="text-xs text-slate-400">加入：{new Date(task.created_at).toLocaleString("zh-CN")}{task.completed_at && <><br />复习完成：{new Date(task.completed_at).toLocaleString("zh-CN")}</>}</p>
        <div className="flex flex-wrap items-center gap-3 text-sm">
          {task.latest_practice && ["created", "running"].includes(task.latest_practice.status)
            ? <Link href={`/interview/${task.latest_practice.interview_id}`} className="rounded-lg bg-brand-600 px-3 py-2 text-white">继续主题专项</Link>
            : <button type="button" disabled={busy} onClick={() => void practice(task)} className="rounded-lg bg-brand-600 px-3 py-2 text-white disabled:opacity-50">{practicing === task.id ? "正在创建…" : task.latest_practice ? "再次练习本主题" : "练习本主题"}</button>}
          {task.latest_practice && <Link href={`/report/${task.latest_practice.interview_id}`} className="text-xs text-brand-600 underline">{["created", "running"].includes(task.latest_practice.status) ? "查看练习进度" : task.latest_practice.status === "cancelled" ? "查看最近练习（已取消）" : "查看最近练习报告"}</Link>}
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-3 text-sm"><Link href={`/report/${task.interview_id}`} className="text-brand-600 underline">查看来源报告</Link><button type="button" disabled={busy} onClick={() => void change(task)} className="rounded-lg border border-slate-300 px-3 py-2 disabled:opacity-50">{changing === task.id ? "正在保存…" : task.status === "todo" ? "标记已复习" : "恢复待复习"}</button></div>
      </article>)}</div>}
      {data.total > 0 && <div className="flex items-center justify-center gap-4 text-sm"><button type="button" disabled={busy || data.offset === 0} onClick={() => void load(data.status ?? undefined, data.position ?? undefined, Math.max(0, data.offset - data.limit), data.due)} className="rounded-lg border px-4 py-2 disabled:opacity-50">上一页</button><span>第 {Math.floor(data.offset / data.limit) + 1} 页 · 共 {data.total} 项</span><button type="button" disabled={busy || !data.has_more} onClick={() => void load(data.status ?? undefined, data.position ?? undefined, data.offset + data.limit, data.due)} className="rounded-lg border px-4 py-2 disabled:opacity-50">下一页</button></div>}
    </>}
  </div>;
}
