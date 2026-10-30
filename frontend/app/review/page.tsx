"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { getAccountReview } from "@/lib/api";
import { originLabel, originVersions } from "@/lib/score-origin";
import type { AccountReview } from "@/lib/types";

const levels: Record<string, string> = { easy: "轻松", mid: "标准", hard: "地狱", unknown: "未记录" };

export default function ReviewPage() {
  const [data, setData] = useState<AccountReview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const version = useRef(0);
  const load = useCallback(async (position?: string, theme?: string, offset = 0) => {
    const requestVersion = ++version.current;
    setLoading(true); setError("");
    try {
      const result = await getAccountReview(position, theme, offset);
      if (version.current === requestVersion) setData(result);
    } catch (error) {
      if (version.current === requestVersion) { setData(null); setError(error instanceof Error ? error.message : "读取失败，请重试"); }
    } finally { if (version.current === requestVersion) setLoading(false); }
  }, []);
  useEffect(() => { void load(); return () => { version.current++; }; }, [load]);
  const themes = data?.positions.find(p => p.id === data.position)?.themes ?? [];
  return <div className="space-y-6">
    <section className="space-y-3 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <div><span className="section-eyebrow">REFLECT & EXPLORE</span><h1 className="text-xl font-semibold">跨场复盘</h1></div>
      <p className="text-sm leading-6 text-slate-600">对照账户中已完成面试的同岗位、同主题记录。每行是一场面试的一个主题，追问不会增加主问题权重。</p>
      <div className="flex flex-wrap gap-4 text-sm"><Link href="/history" className="text-brand-600 underline">练习记录</Link><Link href="/account" className="text-brand-600 underline">登录与账户</Link></div>
      {data && data.positions.length > 0 && <div className="flex flex-wrap gap-4">
        <label className="text-sm">岗位<select aria-label="复盘岗位" disabled={loading} value={data.position ?? ""} onChange={event => void load(event.target.value)} className="ml-2 rounded-lg border px-3 py-2">
          {data.positions.map(p => <option key={p.id} value={p.id}>{p.display_name}</option>)}
        </select></label>
        <label className="text-sm">主题<select aria-label="复盘主题" disabled={loading} value={data.theme ?? ""} onChange={event => void load(data.position ?? undefined, event.target.value || undefined)} className="ml-2 rounded-lg border px-3 py-2">
          <option value="">全部主题</option>{themes.map(theme => <option key={theme} value={theme}>{theme}</option>)}
        </select></label>
        <button type="button" disabled={loading} onClick={() => void load(data.position ?? undefined, data.theme ?? undefined, data.offset)} className="rounded-lg border px-4 py-2 text-sm disabled:opacity-50">刷新</button>
      </div>}
    </section>
    {error && <div role="alert" className="space-y-3 rounded-xl bg-red-50 p-4 text-sm text-red-700"><p>{error}</p><button type="button" disabled={loading} onClick={() => void load()} className="underline">重试读取</button></div>}
    {loading && <p aria-live="polite" className="py-8 text-center text-sm text-slate-500">正在读取复盘记录…</p>}
    {data && !loading && <>
      <p className="rounded-xl bg-amber-50 p-4 text-sm leading-6 text-amber-900">{data.note}</p>
      {data.items.length === 0 ? <p className="rounded-xl border border-dashed p-8 text-center text-sm text-slate-500">暂无匹配的已完成面试。可先完成练习，或在练习记录页认领旧匿名面试。</p> : <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white">
        <table className="w-full min-w-[720px] text-left text-sm">
          <caption className="p-4 text-left text-xs leading-5 text-slate-500">本页{data.session_count}场 / 共{data.total}场 · {data.aggregation}</caption>
          <thead className="bg-slate-50 text-slate-600"><tr>{["面试 / 主题", "主题均分", "题目 / 轮数", "重复题", "评分来源"].map(label => <th key={label} scope="col" className="p-4 font-medium">{label}</th>)}</tr></thead>
          <tbody className="divide-y divide-slate-100">{data.items.map(row => <tr key={`${row.interview_id}:${row.theme}`}>
            <td className="p-4 align-top"><p className="font-medium">{row.theme}</p><p className="mt-1 text-xs text-slate-500">{row.position_display_name} · {levels[row.difficulty] ?? row.difficulty}</p><p className="mt-1 text-xs text-slate-500">{row.ended_at ? new Date(row.ended_at).toLocaleString("zh-CN") : "完成时间未记录"}</p><Link href={`/report/${row.interview_id}`} className="mt-2 inline-block text-xs text-brand-600 underline">逐轮报告</Link></td>
            <td className="p-4 align-top font-semibold text-brand-600">{row.score.toFixed(1)} / 10</td>
            <td className="p-4 align-top"><p>{row.question_count}题 / {row.answer_count}轮</p><p className="mt-1 text-xs leading-5 text-slate-500">实际主问题难度：{Object.entries(row.question_difficulties).map(([difficulty, count]) => `${difficulty === "unknown" ? "未记录" : difficulty} ${count}题`).join("、")}</p></td>
            <td className="p-4 align-top text-xs leading-5"><p>{row.repeat_question_count}题重复 / {row.known_question_version_count}题有版本</p>{row.unknown_question_version_count > 0 && <p className="mt-1 text-slate-500">另{row.unknown_question_version_count}题版本未记录</p>}</td>
            <td className="max-w-xs p-4 align-top text-xs leading-5">{row.scoring_profiles.map((profile, index) => <div key={index} className="mb-2">
              <p>{originLabel(profile)} · {profile.answer_count}轮{profile.cached_count > 0 ? `，其中缓存${profile.cached_count}轮` : ""}</p>
              <details className="mt-1 text-slate-500"><summary className="cursor-pointer">来源与版本</summary><p className="mt-1 break-all">{originVersions(profile)}</p></details>
            </div>)}</td>
          </tr>)}</tbody>
        </table>
      </div>}
      <p className="text-xs leading-5 text-slate-500">重复题口径：{data.repeat_definition}</p>
      {data.total > 0 && <div className="flex items-center justify-center gap-4 text-sm">
        <button type="button" disabled={data.offset === 0} onClick={() => void load(data.position ?? undefined, data.theme ?? undefined, Math.max(0, data.offset - data.limit))} className="rounded-lg border px-4 py-2 disabled:opacity-50">上一页</button>
        <span>第{Math.floor(data.offset / data.limit) + 1}页</span>
        <button type="button" disabled={!data.has_more} onClick={() => void load(data.position ?? undefined, data.theme ?? undefined, data.offset + data.limit)} className="rounded-lg border px-4 py-2 disabled:opacity-50">下一页</button>
      </div>}
    </>}
  </div>;
}
