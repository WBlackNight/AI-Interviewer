"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { getAccountSession } from "@/lib/account";
import { addRevisionTasks } from "@/lib/api";

export default function AddRevisionTasks({ interviewId }: { interviewId: string }) {
  const [signedIn, setSignedIn] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const working = useRef(false);
  useEffect(() => { setSignedIn(!!getAccountSession()); }, []);
  async function add() {
    if (working.current) return;
    working.current = true; setBusy(true); setError(""); setMessage("");
    try {
      const result = await addRevisionTasks(interviewId);
      setMessage(`已加入 ${result.added} 个复习任务，另有 ${result.existing} 个已在清单中。已有完成状态保持不变。`);
    } catch (error) { setError(error instanceof Error ? error.message : "加入失败，请重试"); }
    finally { working.current = false; setBusy(false); }
  }
  return <section className="space-y-3 rounded-2xl border border-slate-200 bg-white p-6">
    <h2 className="text-sm font-medium">把薄弱主题加入复习任务</h2>
    <p className="text-sm leading-6 text-slate-600">保存本场的待补强主题与未覆盖要点，复习后自行标记完成。同一报告重复加入不会重置进度。</p>
    {signedIn ? <div className="flex flex-wrap items-center gap-4 text-sm">
      <button type="button" disabled={busy} onClick={() => void add()} className="rounded-lg bg-slate-800 px-4 py-2 text-white disabled:opacity-50">{busy ? "正在加入…" : "加入复习任务"}</button>
      <Link href="/revision" className="text-brand-600 underline">查看复习任务板</Link>
    </div> : <p className="text-sm text-slate-600"><Link href="/account" className="text-brand-600 underline">登录账户</Link>后，在<Link href="/history" className="text-brand-600 underline">练习记录</Link>认领本场，即可保存复习任务。</p>}
    {message && <p role="status" className="text-sm text-emerald-700">{message}</p>}
    {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
  </section>;
}
