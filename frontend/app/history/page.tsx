"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { listInterviewIds } from "@/lib/access";
import { claimInterview, deleteAccountInterview, getAccountHistory, getInterviewSummary } from "@/lib/api";
import { getAccountSession, type AccountInfo } from "@/lib/account";
import { loadHistory, type HistoryEntry } from "@/lib/history";
import CancelInterviewButton from "@/components/CancelInterviewButton";
import { canCancelInterview, isInterviewTerminal } from "@/lib/interview-status";

const statuses: Record<string, string> = { created: "尚未开始", running: "进行中", finished: "已完成", cancelled: "已取消" };
const levels: Record<string, string> = { easy: "轻松", mid: "标准", hard: "地狱" };

function activityTime(value: string | null) {
  if (!value) return "尚未开始";
  const date = new Date(/Z$|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);
  return Number.isNaN(date.getTime()) ? "时间暂不可用" : date.toLocaleString("zh-CN");
}

export default function HistoryPage() {
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [account, setAccount] = useState<AccountInfo | null>(null);
  const [unclaimed, setUnclaimed] = useState<string[]>([]);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState("");
  const [confirmDelete, setConfirmDelete] = useState("");
  const [busyId, setBusyId] = useState("");
  const mutating = useRef(false);
  const requestVersion = useRef(0);
  const refresh = useCallback(async (pageOffset = 0) => {
    const version = ++requestVersion.current;
    setLoading(true); setError(""); setEntries([]); setConfirmDelete("");
    const session = getAccountSession();
    setAccount(session?.account ?? null);
    setUnclaimed(session ? listInterviewIds() : []);
    try {
      if (session) {
        const page = await getAccountHistory(pageOffset);
        if (version !== requestVersion.current) return;
        setEntries(page.items.map(summary => ({ id: summary.interview_id, summary })));
        setOffset(page.offset); setTotal(page.total); setHasMore(page.has_more);
      } else {
        const rows = await loadHistory(listInterviewIds(), getInterviewSummary);
        if (version !== requestVersion.current) return;
        setEntries(rows); setOffset(0); setTotal(rows.length); setHasMore(false);
      }
    } catch (error) { if (version === requestVersion.current) setError(error instanceof Error ? error.message : "读取失败，请重试"); }
    finally { if (version === requestVersion.current) setLoading(false); }
  }, []);
  useEffect(() => { void refresh(); return () => { requestVersion.current++; }; }, [refresh]);

  async function mutate(id: string, action: "claim" | "delete") {
    if (mutating.current) return;
    mutating.current = true; setBusyId(id); setError("");
    try {
      if (action === "claim") await claimInterview(id);
      else await deleteAccountInterview(id);
      await refresh(0);
    } catch (error) { setError(error instanceof Error ? error.message : "操作失败，请重试"); }
    finally { mutating.current = false; setBusyId(""); setConfirmDelete(""); }
  }

  return <div className="space-y-6">
    <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex items-center justify-between gap-4">
        <div><span className="section-eyebrow">YOUR PRACTICE JOURNAL</span><h1 className="text-xl font-semibold">练习记录</h1></div>
        <button type="button" disabled={loading || !!busyId} onClick={() => void refresh(offset)}
          className="rounded-lg border border-slate-200 px-4 py-2 text-sm disabled:opacity-50">{loading ? "读取中…" : "刷新记录"}</button>
      </div>
      <p className="mt-3 text-sm leading-6 text-slate-500">{account ? `${account.username} 的账户记录，保留至主动删除；重新登录可找回。共 ${total} 条。` : "这里最多显示当前标签页的50条记录；关闭标签页后匿名访问凭据不再保留。"}</p>
      <Link href="/account" className="mt-2 inline-block text-sm text-brand-600 underline">{account ? "管理账户与退出" : "登录或注册，保存长期历史"}</Link>
      {account && <Link href="/review" className="ml-4 inline-block text-sm text-brand-600 underline">同岗位跨场复盘</Link>}
    </section>
    {error && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
    {account && unclaimed.length > 0 && <section className="space-y-3 rounded-2xl border border-amber-200 bg-amber-50 p-6">
      <h2 className="font-medium">认领本标签页的匿名面试</h2>
      <p className="text-sm text-amber-900">认领后，这场面试仅可通过当前账户访问，原匿名凭据失效；不会同时认领原简历。</p>
      <ul className="space-y-2">{unclaimed.map(id => <li key={id} className="flex items-center justify-between gap-3 text-sm">
        <span>未认领面试 · {id.slice(0, 8)}</span>
        <button type="button" disabled={loading || !!busyId} onClick={() => void mutate(id, "claim")} className="rounded-lg border border-amber-300 bg-white px-3 py-2 disabled:opacity-50">{busyId === id ? "处理中…" : "认领到此账户"}</button>
      </li>)}</ul>
    </section>}
    <div aria-live="polite" aria-busy={loading}>
      {loading && <p className="py-5 text-center text-sm text-slate-500">正在读取练习记录…</p>}
      {!loading && !error && entries.length === 0 && <section className="rounded-2xl border border-dashed border-slate-300 p-10 text-center">
        <h2 className="font-medium">{account ? "账户中还没有练习记录" : "当前标签页还没有练习记录"}</h2>
        <p className="mt-2 text-sm text-slate-500">从首页开始一场面试，之后可以在这里继续练习和查看报告。</p>
        <Link href="/" className="mt-5 inline-block rounded-lg bg-brand-600 px-5 py-2 text-sm text-white">开始练习</Link>
      </section>}
      <div className="space-y-4">{entries.map(({ id, summary, error }) => <section key={id}
        className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        {summary ? <>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="font-semibold">{summary.position_display_name ?? summary.position} · {levels[summary.difficulty] ?? summary.difficulty}</h2>
            <span className={`rounded-full px-3 py-1 text-xs ${summary.status === "finished" ? "bg-emerald-50 text-emerald-700" : "bg-brand-50 text-brand-600"}`}>{statuses[summary.status] ?? "状态待确认"}</span>
          </div>
          <p className="mt-3 text-sm text-slate-500">{summary.theme_count} 个主题 · 已回答 {summary.answer_count} 轮</p>
          <p className="mt-1 text-xs text-slate-400">最近活动：{activityTime(summary.last_activity_at)}</p>
          <div className="mt-5 flex flex-wrap gap-3">
            {!isInterviewTerminal(summary.status) && <Link href={`/interview/${id}`} className="rounded-lg bg-brand-600 px-4 py-2 text-sm text-white">{summary.status === "created" ? "进入面试" : "继续面试"}</Link>}
            <Link href={`/report/${id}`} className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-700">{summary.status === "finished" ? "查看复盘报告" : summary.status === "cancelled" ? "查看取消前的部分报告" : "查看当前报告"}</Link>
            {canCancelInterview(summary.status) && <CancelInterviewButton interviewId={id} disabled={loading || !!busyId} onCancelled={() => refresh(offset)} />}
            {account && summary.status !== "running" && <button type="button" disabled={loading || !!busyId}
              onClick={() => confirmDelete === id ? void mutate(id, "delete") : setConfirmDelete(id)}
              className="rounded-lg border border-red-200 px-4 py-2 text-sm text-red-700 disabled:opacity-50">{busyId === id ? "删除中…" : confirmDelete === id ? "确认永久删除此记录" : "删除记录"}</button>}
            {confirmDelete === id && <button type="button" disabled={!!busyId} onClick={() => setConfirmDelete("")} className="text-sm underline">取消</button>}
          </div>
        </> : <><h2 className="font-medium">暂时无法读取这条练习</h2><p className="mt-2 text-sm text-red-700">{error}</p>
          <p className="mt-2 text-xs text-slate-500">可刷新重试；若服务端记录已失效，请从首页新建面试。</p></>}
      </section>)}</div>
      {account && !loading && !error && total > 0 && <div className="mt-5 flex items-center justify-center gap-4 text-sm">
        <button type="button" disabled={offset === 0 || !!busyId} onClick={() => void refresh(Math.max(0, offset - 20))} className="rounded-lg border px-4 py-2 disabled:opacity-50">上一页</button>
        <span>第 {Math.floor(offset / 20) + 1} 页</span>
        <button type="button" disabled={!hasMore || !!busyId} onClick={() => void refresh(offset + 20)} className="rounded-lg border px-4 py-2 disabled:opacity-50">下一页</button>
      </div>}
    </div>
  </div>;
}
