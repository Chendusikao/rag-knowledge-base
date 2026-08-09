"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useCurrentUser } from "@/components/app-shell";
import { api, type KnowledgeBase } from "@/lib/api";

export default function HomePage() {
  const user = useCurrentUser();
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api.listKbs()
      .then(setKbs)
      .catch((reason) => setError((reason as Error).message))
      .finally(() => setLoading(false));
  }, []);

  const departmentCount = new Set(kbs.map((kb) => kb.department_id)).size;
  return (
    <div className="max-w-5xl space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">企业知识工作台</h1>
        <p className="mt-2 text-sm text-gray-400">
          {user ? `${user.display_name}，` : ""}这里仅展示当前账号有权访问的企业知识。
        </p>
      </header>
      {loading ? (
        <div className="card text-sm text-gray-400">正在读取授权范围…</div>
      ) : error ? (
        <div className="card text-sm text-red-400">暂时无法读取知识库：{error}</div>
      ) : (
        <>
          <div className="card flex flex-wrap gap-10">
            <Metric value={kbs.length} label="个可访问知识库" />
            <Metric value={kbs.reduce((total, kb) => total + kb.document_count, 0)} label="份授权资料" />
            <Metric value={departmentCount} label="个相关部门" />
          </div>
          <div className="grid gap-3 md:grid-cols-3">
            {user?.system_role !== "auditor" && <Link href="/chat" className="card hover:border-accent">
              <div className="font-medium">开始知识问答 →</div>
              <div className="mt-2 text-sm text-gray-400">在授权范围内获得带来源、可核查的回答。</div>
            </Link>}
            {user?.system_role !== "auditor" && <Link href="/documents" className="card hover:border-accent">
              <div className="font-medium">导入企业文件 →</div>
              <div className="mt-2 text-sm text-gray-400">编辑者可批量导入文件并跟踪处理进度。</div>
            </Link>}
            {user?.system_role === "admin" && <Link href="/source-library" className="card hover:border-accent">
              <div className="font-medium">同步总资料库 →</div>
              <div className="mt-2 text-sm text-gray-400">从只读总目录按分支导入，并先设置部门和访问范围。</div>
            </Link>}
            <Link href="/knowledge-bases" className="card hover:border-accent">
              <div className="font-medium">查看部门知识库 →</div>
              <div className="mt-2 text-sm text-gray-400">按部门、业务和访问范围管理知识资产。</div>
            </Link>
            {["admin", "auditor"].includes(user?.system_role || "") && <Link href="/audit" className="card hover:border-accent">
              <div className="font-medium">查看审计与安全 →</div>
              <div className="mt-2 text-sm text-gray-400">核对敏感操作记录和部署安全基线。</div>
            </Link>}
          </div>
        </>
      )}
    </div>
  );
}

function Metric({ value, label }: { value: number; label: string }) {
  return (
    <div>
      <div className="text-2xl font-semibold">{value}</div>
      <div className="mt-1 text-xs text-gray-400">{label}</div>
    </div>
  );
}
