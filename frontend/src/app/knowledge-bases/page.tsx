"use client";

import { useEffect, useState } from "react";
import { api, type KnowledgeBase } from "@/lib/api";

export default function KnowledgeBasesPage() {
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [msg, setMsg] = useState("");

  async function load() {
    try {
      setKbs(await api.listKbs());
    } catch (e) {
      setMsg("加载失败：" + (e as Error).message);
    }
  }
  useEffect(() => { load(); }, []);

  async function create() {
    if (!name) return;
    try {
      await api.createKb({ name, description: desc });
      setName(""); setDesc(""); setMsg("已创建");
      load();
    } catch (e) {
      setMsg("创建失败：" + (e as Error).message);
    }
  }

  async function del(id: string) {
    await api.deleteKb(id);
    load();
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">知识库</h1>
      <div className="card space-y-2">
        <div className="flex gap-2">
          <input className="input flex-1" placeholder="知识库名称" value={name} onChange={(e) => setName(e.target.value)} />
          <input className="input flex-1" placeholder="描述（可选）" value={desc} onChange={(e) => setDesc(e.target.value)} />
          <button className="btn" onClick={create}>创建</button>
        </div>
        {msg && <div className="text-xs text-accent">{msg}</div>}
      </div>
      <div className="space-y-2">
        {kbs.map((kb) => (
          <div key={kb.id} className="card flex items-center justify-between">
            <div>
              <div className="font-medium">{kb.name}</div>
              <div className="text-xs text-gray-400">{kb.description} · 文档 {kb.document_count} · gen {kb.current_generation}</div>
            </div>
            <button className="text-xs text-red-400" onClick={() => del(kb.id)}>删除</button>
          </div>
        ))}
        {kbs.length === 0 && <div className="text-sm text-gray-500">暂无知识库</div>}
      </div>
    </div>
  );
}
