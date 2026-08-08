"use client";

import { useEffect, useState } from "react";
import { api, type DocumentOut, type KnowledgeBase } from "@/lib/api";

export default function DocumentsPage() {
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [kbId, setKbId] = useState("");
  const [docs, setDocs] = useState<DocumentOut[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [job, setJob] = useState("");
  const [msg, setMsg] = useState("");

  async function loadKbs() {
    const list = await api.listKbs();
    setKbs(list);
    if (list.length && !kbId) setKbId(list[0].id);
  }
  useEffect(() => { loadKbs(); }, []);

  // Documents are listed via the backend; for the scaffold we surface upload +
  // polling the returned job. Listing all docs across KBs is a follow-up route.
  async function upload() {
    if (!kbId || !file) return;
    try {
      const r = await api.uploadDoc(kbId, file);
      setJob(r.job_id);
      setMsg("已上传，索引任务：" + r.job_id);
      setFile(null);
    } catch (e) {
      setMsg("上传失败：" + (e as Error).message);
    }
  }

  async function pollJob() {
    if (!job) return;
    const j = await api.getJob(job);
    setMsg(`任务状态：${j.status} 进度 ${(j.progress * 100).toFixed(0)}%`);
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">文档</h1>
      <div className="card space-y-2">
        <select className="input" value={kbId} onChange={(e) => setKbId(e.target.value)}>
          {kbs.map((k) => <option key={k.id} value={k.id}>{k.name}</option>)}
        </select>
        <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <div className="flex gap-2">
          <button className="btn" onClick={upload} disabled={!file}>上传并索引</button>
          <button className="btn bg-panelb" onClick={pollJob} disabled={!job}>查询任务</button>
        </div>
        {msg && <div className="text-xs text-accent">{msg}</div>}
      </div>
      <div className="text-xs text-gray-500">
        说明：V1 脚手架支持 PDF / Markdown / PNG / JPG 上传；Markdown 会做标题感知的
        结构化切分并写入 Chunk，PDF/图片当前为占位解析（待接入 Docling）。
      </div>
    </div>
  );
}
