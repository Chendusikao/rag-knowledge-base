import { api, type KnowledgeBase } from "@/lib/api";
import Link from "next/link";

export default async function HomePage() {
  let kbs: KnowledgeBase[] = [];
  let error = "";
  try {
    kbs = await api.listKbs();
  } catch (e) {
    error = (e as Error).message;
  }
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">概览</h1>
      {error ? (
        <div className="card text-red-400">后端连接失败：{error}</div>
      ) : (
        <>
          <div className="card">
            知识库数量：<b>{kbs.length}</b>　文档总数：
            <b>{kbs.reduce((a, k) => a + k.document_count, 0)}</b>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Link href="/knowledge-bases" className="card hover:border-accent">管理知识库 →</Link>
            <Link href="/chat" className="card hover:border-accent">开始问答 →</Link>
            <Link href="/retrieval-lab" className="card hover:border-accent">检索调试 →</Link>
            <Link href="/evaluation" className="card hover:border-accent">评测面板 →</Link>
          </div>
        </>
      )}
    </div>
  );
}
