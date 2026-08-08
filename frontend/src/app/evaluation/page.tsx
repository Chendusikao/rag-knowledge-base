"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function EvaluationPage() {
  const [kbs, setKbs] = useState<{ id: string; name: string }[]>([]);
  const [kbId, setKbId] = useState("");
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    api.listKbs().then((l) => { setKbs(l); if (l.length) setKbId(l[0].id); }).catch(() => {});
  }, []);

  async function runEval() {
    if (!kbId) return;
    setMsg("评测任务已创建，等待完成后刷新…");
    try {
      await api.createRun({ kb_id: kbId, mode: "balanced" });
      setMsg("已创建评测运行（结果需后端执行 eval 任务；当前为脚手架，指标口径见 PLAN 第 5 节）。");
    } catch (e) {
      setMsg("创建失败：" + (e as Error).message);
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">评测面板</h1>
      <div className="card space-y-2">
        <select className="input" value={kbId} onChange={(e) => setKbId(e.target.value)}>
          {kbs.map((k) => <option key={k.id} value={k.id}>{k.name}</option>)}
        </select>
        <button className="btn" onClick={runEval}>运行评测</button>
        {msg && <div className="text-xs text-accent">{msg}</div>}
      </div>
      <div className="card text-sm text-gray-400">
        验收口径（PLAN 5）：Recall@10 ≥ 0.85，MRR@10 ≥ 0.70，引用准确率 ≥ 95%，
        Faithfulness ≥ 0.85，不可回答拒答率 ≥ 90%，10 万 Chunk 下本地 Balanced p95 ≤ 2s。
        当前为脚手架，评测 Job 已接入真实检索指标计算（MRR/Hit/Recall/nDCG），
        RAGAS 与引用准确率在后续阶段补齐。
      </div>
    </div>
  );
}
