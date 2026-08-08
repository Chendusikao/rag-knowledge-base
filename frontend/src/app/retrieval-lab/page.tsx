"use client";

import { useEffect, useState } from "react";
import { api, type RetrievedChunk } from "@/lib/api";

export default function RetrievalLabPage() {
  const [kbs, setKbs] = useState<{ id: string; name: string }[]>([]);
  const [kbId, setKbId] = useState("");
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState("balanced");
  const [results, setResults] = useState<RetrievedChunk[]>([]);
  const [latency, setLatency] = useState(0);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    api.listKbs().then((l) => { setKbs(l); if (l.length) setKbId(l[0].id); }).catch(() => {});
  }, []);

  async function inspect() {
    if (!kbId || !query) return;
    setMsg("");
    try {
      const r = await api.retrievalInspect({ kb_id: kbId, query, mode });
      setResults(r.results);
      setLatency(r.latency_ms);
    } catch (e) {
      setMsg("检索失败：" + (e as Error).message);
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">检索实验室</h1>
      <div className="card space-y-2">
        <select className="input" value={kbId} onChange={(e) => setKbId(e.target.value)}>
          {kbs.map((k) => <option key={k.id} value={k.id}>{k.name}</option>)}
        </select>
        <div className="flex gap-2">
          <input className="input flex-1" placeholder="检索问题" value={query} onChange={(e) => setQuery(e.target.value)} />
          <select className="input" value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="fast">fast</option>
            <option value="balanced">balanced</option>
            <option value="deep">deep</option>
          </select>
          <button className="btn" onClick={inspect}>检索</button>
        </div>
        {msg && <div className="text-xs text-red-400">{msg}</div>}
        {results.length > 0 && <div className="text-xs text-gray-400">延迟 {latency} ms · 命中 {results.length}</div>}
      </div>
      <div className="space-y-2">
        {results.map((r) => (
          <div key={r.chunk_id} className="card text-sm">
            <div className="flex justify-between text-xs text-gray-400">
              <span>Dense {r.dense_score.toFixed(3)} · BM25 {r.bm25_score.toFixed(3)} · RRF {r.rrf_score.toFixed(4)} · Rerank {r.rerank_score.toFixed(4)}</span>
              <span>{r.modality} · p{r.page_number}</span>
            </div>
            <div className="mt-1">{r.snippet}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
