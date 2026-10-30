import type { Metadata } from "next";
import WorkspaceShell from "@/components/WorkspaceShell";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI 模拟面试官",
  description: "面向 IT 求职者的多模态面试演练 Agent",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body>
        <a className="skip-link" href="#main-content">跳到主要内容</a>
        <WorkspaceShell>{children}</WorkspaceShell>
      </body>
    </html>
  );
}
