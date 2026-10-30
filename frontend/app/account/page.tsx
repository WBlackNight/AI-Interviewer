"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ApiError, authenticate, deleteAccount, getCurrentAccount, logoutAccount } from "@/lib/api";
import { clearAccountSession, getAccountSession, type AccountInfo } from "@/lib/account";

export default function AccountPage() {
  const [account, setAccount] = useState<AccountInfo | null>(null);
  const [checking, setChecking] = useState(true);
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  useEffect(() => {
    let active = true;
    if (!getAccountSession()) { setChecking(false); return; }
    getCurrentAccount().then(value => { if (active) setAccount(value); }).catch(error => {
      if (!active) return;
      if (error instanceof ApiError && error.status === 401) clearAccountSession();
      setError(error instanceof Error ? error.message : "账户读取失败，请刷新重试");
    }).finally(() => { if (active) setChecking(false); });
    return () => { active = false; };
  }, []);

  async function act(action: "authenticate" | "logout" | "delete") {
    if (pending.current) return;
    pending.current = true; setBusy(true); setError("");
    try {
      if (action === "authenticate") setAccount((await authenticate(mode, username, password)).account);
      else if (action === "logout") { await logoutAccount(); setAccount(null); }
      else { await deleteAccount(password); setAccount(null); setConfirmDelete(false); }
      setPassword("");
    } catch (error) { setError(error instanceof Error ? error.message : "请求失败，请重试"); }
    finally { pending.current = false; setBusy(false); }
  }

  if (checking) return <p className="py-16 text-center text-sm text-slate-500">正在检查登录状态…</p>;
  return <section className="mx-auto max-w-lg space-y-5 rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
    <div><span className="section-eyebrow">YOUR PERSONAL SPACE</span><h1 className="text-xl font-semibold">{account ? `账户：${account.username}` : "登录与注册"}</h1></div>
    <p className="text-sm leading-6 text-slate-500">登录后可找回账户中的练习记录。原标签页的匿名面试需在练习记录页主动认领。会话最长7天，关闭标签页后需重新登录。</p>
    {error && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
    {account ? <>
      <Link href="/history" className="inline-block rounded-lg bg-brand-600 px-4 py-2 text-sm text-white">查看账户练习</Link>
      <button type="button" disabled={busy} onClick={() => void act("logout")} className="ml-3 rounded-lg border px-4 py-2 text-sm disabled:opacity-50">退出当前会话</button>
      <p className="text-xs leading-5 text-slate-500">记录保留至主动删除。可在记录页删除已完成、已取消或尚未开始的面试；进行中需先完成或取消。目前不提供密码找回，请妥善保存密码。</p>
      <div className="border-t pt-4">
        {!confirmDelete ? <button type="button" disabled={busy} onClick={() => { setConfirmDelete(true); setPassword(""); }} className="text-sm text-red-700 underline">删除账户及所属内容</button> : <div className="space-y-3">
          <p className="text-sm text-red-700">这将永久删除账户、所属面试及简历。请输入密码确认；已有备份和外部供应商副本不在此处清理。</p>
          <input type="password" autoComplete="current-password" aria-label="确认删除的账户密码" value={password} disabled={busy} minLength={12} maxLength={128} onChange={event => setPassword(event.target.value)} className="w-full rounded-lg border px-3 py-2" />
          <button type="button" disabled={busy || password.length < 12} onClick={() => void act("delete")} className="rounded-lg bg-red-700 px-4 py-2 text-sm text-white disabled:opacity-50">确认永久删除</button>
          <button type="button" disabled={busy} onClick={() => { setConfirmDelete(false); setPassword(""); }} className="ml-3 text-sm underline">取消</button>
        </div>}
      </div>
    </> : <form className="space-y-4" onSubmit={event => { event.preventDefault(); void act("authenticate"); }}>
      <div role="group" aria-label="账户操作" className="flex gap-3">{(["login", "register"] as const).map(value => <button type="button" key={value} aria-pressed={mode === value} disabled={busy} onClick={() => { setMode(value); setError(""); setPassword(""); }} className={`rounded-lg border px-4 py-2 text-sm ${mode === value ? "border-brand-600 text-brand-600" : "text-slate-600"}`}>{value === "login" ? "登录" : "注册"}</button>)}</div>
      <label className="block space-y-1 text-sm"><span>用户名（3–32位字母、数字或下划线）</span><input autoComplete="username" required minLength={3} maxLength={32} pattern="[A-Za-z0-9_]+" value={username} disabled={busy} onChange={event => setUsername(event.target.value)} className="w-full rounded-lg border px-3 py-2" /></label>
      <label className="block space-y-1 text-sm"><span>密码（12–128字符）</span><input type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} required minLength={12} maxLength={128} value={password} disabled={busy} onChange={event => setPassword(event.target.value)} className="w-full rounded-lg border px-3 py-2" /></label>
      <p className="text-xs text-slate-500">目前不提供密码找回。未登录也可从首页匿名练习。</p>
      <button disabled={busy} className="w-full rounded-lg bg-brand-600 px-4 py-3 text-sm text-white disabled:opacity-50">{busy ? "处理中…" : mode === "login" ? "登录" : "注册并登录"}</button>
    </form>}
  </section>;
}
