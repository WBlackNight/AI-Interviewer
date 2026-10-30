"use client";

import { useRef, useState } from "react";
import { cancelInterview } from "@/lib/api";

export default function CancelInterviewButton({ interviewId, disabled = false, onCancelled }: {
  interviewId: string; disabled?: boolean; onCancelled?: () => void | Promise<void>;
}) {
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submitting = useRef(false);
  async function cancel() {
    if (submitting.current) return;
    submitting.current = true; setBusy(true); setError("");
    try { await cancelInterview(interviewId); setConfirm(false); await onCancelled?.(); }
    catch (error) { setError(error instanceof Error ? error.message : "取消失败，请重试"); }
    finally { submitting.current = false; setBusy(false); }
  }
  return <div className="space-y-2 text-sm">
    {!confirm ? <button type="button" disabled={disabled || busy} onClick={() => { setConfirm(true); setError(""); }}
      className="rounded-lg border border-amber-300 px-4 py-2 text-amber-800 disabled:opacity-50">取消面试</button> : <div className="space-y-2 rounded-lg border border-amber-200 bg-amber-50 p-3">
      <p className="text-xs leading-5 text-amber-900">确认取消这场面试？已提交回答和部分报告会保留，当前未提交的回答不会保存；取消后不能继续本场。</p>
      <div className="flex flex-wrap gap-3">
        <button type="button" disabled={disabled || busy} onClick={() => void cancel()} className="rounded-lg bg-amber-700 px-3 py-2 text-xs text-white disabled:opacity-50">{busy ? "正在取消…" : "确认取消并保留报告"}</button>
        <button type="button" disabled={busy} onClick={() => { setConfirm(false); setError(""); }} className="text-xs underline">返回继续练习</button>
      </div>
    </div>}
    {error && <p role="alert" className="text-xs text-red-700">{error}</p>}
  </div>;
}
