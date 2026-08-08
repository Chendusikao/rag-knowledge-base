import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "RAG 知识库",
  description: "个人多模态 RAG 知识库问答系统",
};

const NAV = [
  { href: "/", label: "概览" },
  { href: "/knowledge-bases", label: "知识库" },
  { href: "/documents", label: "文档" },
  { href: "/chat", label: "聊天" },
  { href: "/retrieval-lab", label: "检索实验室" },
  { href: "/evaluation", label: "评测" },
  { href: "/settings", label: "设置" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh">
      <body>
        <div className="flex min-h-screen">
          <aside className="w-48 border-r border-edge bg-panel p-3">
            <div className="mb-4 px-2 text-sm font-semibold text-accent">RAG 控制台</div>
            <nav className="flex flex-col gap-1 text-sm">
              {NAV.map((n) => (
                <Link key={n.href} href={n.href} className="px-2 py-1.5 rounded hover:bg-panelb">
                  {n.label}
                </Link>
              ))}
            </nav>
          </aside>
          <main className="flex-1 p-6 overflow-auto">{children}</main>
        </div>
      </body>
    </html>
  );
}
