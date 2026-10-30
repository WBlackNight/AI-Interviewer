"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const destinations = [
  { href: "/", label: "开始练习", caption: "练习工作台", icon: "home" },
  { href: "/history", label: "练习记录", caption: "记录每一次尝试", icon: "history" },
  { href: "/revision", label: "复习任务", caption: "把复盘变成行动", icon: "tasks" },
  { href: "/review", label: "跨场复盘", caption: "回看不同场次的表现", icon: "chart" },
  { href: "/account", label: "我的账户", caption: "你的个人练习空间", icon: "user" },
];

export function WorkspaceIcon({ name, className = "" }: { name: string; className?: string }) {
  const paths: Record<string, ReactNode> = {
    home: <><path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1Z" /><path d="M9 21v-8h6v8" /></>,
    history: <><path d="M4 5h14a2 2 0 0 1 2 2v13H6a2 2 0 0 1-2-2V5Zm0 0V3h12v2M8 10h8M8 14h5" /></>,
    tasks: <><rect x="4" y="4" width="16" height="17" rx="3" /><path d="M9 4V2h6v2M8 10l2 2 4-4M8 17h8" /></>,
    chart: <><path d="M4 3v17h17M8 15l4-5 4 2 5-7" /><path d="M18 5h3v3" /></>,
    user: <><circle cx="12" cy="8" r="4" /><path d="M4 21v-2a8 8 0 0 1 16 0v2" /></>,
    arrow: <><path d="M4 12h16m-6-6 6 6-6 6" /></>,
    sparkle: <><path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5ZM20 2v4m-2-2h4" /></>,
    check: <path d="m5 12 4 4L19 6" />,
  };
  return <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] ?? paths.sparkle}</svg>;
}

export default function WorkspaceShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const active = destinations.find(item => item.href === pathname);
  const detail = pathname.startsWith("/interview/") ? { label: "面试进行中", caption: "专注当下，慢慢展开你的思路" }
    : pathname.startsWith("/report/") ? { label: "面试复盘", caption: "回看回答，找到下一步方向" } : null;
  const current = active ?? detail ?? destinations[0];
  return <div className="workspace-root">
    <aside className="workspace-sidebar">
      <Link href="/" className="workspace-brand" aria-label="AI 模拟面试官首页">
        <span className="brand-symbol"><WorkspaceIcon name="sparkle" /></span>
        <span><strong>面试练习室<span className="brand-dot">.</span></strong><small>INTERVIEW STUDIO</small></span>
      </Link>
      <p className="nav-caption">我的工作空间</p>
      <nav aria-label="主导航" className="workspace-nav">{destinations.map(item => <Link key={item.href} href={item.href}
        aria-current={active?.href === item.href ? "page" : undefined} className={`workspace-nav-link ${active?.href === item.href ? "is-active" : ""}`}>
        <WorkspaceIcon name={item.icon} /><span>{item.label}</span>{active?.href === item.href && <span className="nav-active-dot" />}
      </Link>)}</nav>
      <div className="sidebar-note"><span className="sidebar-note-icon"><WorkspaceIcon name="sparkle" /></span><p>每一点准备，<br />都在让你更从容。</p><Link href="/" className="sidebar-note-link">开始今天的练习 <span aria-hidden="true">↗</span></Link></div>
      <div className="sidebar-footer"><span className="status-dot" /> 练习 · 复盘 · 再出发</div>
    </aside>
    <div className="workspace-stage">
      <header className="workspace-topbar"><div className="workspace-breadcrumb"><span>个人工作台</span><span aria-hidden="true">/</span><strong>{current.label}</strong></div>
        <Link href="/account" className="workspace-account"><span className="account-avatar"><WorkspaceIcon name="user" /></span><span>账户中心</span></Link>
      </header>
      <main className="app-content" id="main-content">{children}</main>
      <footer className="workspace-footer"><span>INTERVIEW STUDIO</span><span>为下一次面试，做好这一次准备。</span></footer>
    </div>
  </div>;
}
