"use client";

import { useEffect, useState } from "react";

export default function RevisionDateEditor({ taskId, theme, value, disabled, saving, onSave }: {
  taskId: string; theme: string; value: string | null; disabled: boolean; saving: boolean;
  onSave: (date: string | null) => Promise<void>;
}) {
  const [draft, setDraft] = useState(value ?? "");
  useEffect(() => { setDraft(value ?? ""); }, [value]);
  return <form className="revision-date-editor" onSubmit={event => {
    event.preventDefault(); void onSave(draft || null);
  }}>
    <label htmlFor={`due-${taskId}`} className="text-xs font-medium text-slate-600">复习日期 · 北京时间</label>
    <div className="mt-2 flex flex-wrap items-center gap-2">
      <input id={`due-${taskId}`} aria-label={`${theme}的复习日期`} type="date" min="2000-01-01" max="2100-12-31" value={draft} disabled={disabled} onChange={event => setDraft(event.target.value)} className="min-w-0 flex-1 rounded-lg border px-3 py-2 text-sm" />
      <button type="submit" aria-label={`保存${theme}的复习日期`} disabled={disabled || draft === (value ?? "")} className="rounded-lg bg-brand-600 px-3 py-2 text-sm text-white disabled:opacity-40">{saving ? "保存中…" : "保存日期"}</button>
      {value && <button type="button" aria-label={`清空${theme}的复习日期`} disabled={disabled} onClick={() => void onSave(null)} className="px-1 py-2 text-xs text-slate-500 underline disabled:opacity-40">清空</button>}
    </div>
  </form>;
}
