"use client";

import { useEffect, useRef, useState } from "react";
import { api, type Citation } from "@/lib/api";

interface Turn {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  confidence?: number | null;
  insufficient?: boolean | null;
}

export default function ChatPage() {
  const [kbId, setKbId] = useState("");
  const [kbs, setKbs] = useState<{ id: string; name: string }[]>([]);
  const [query, setQuery] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.listKbs().then((l) => { setKbs(l); if (l.length) setKbId(l[0].id); }).catch(() => {});
  }, []);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [turns]);

  async function send() {
    if (!kbId || !query || busy) return;
    const q = query;
    setQuery("");
    setTurns((t) => [...t, { role: "user", content: q }]);
    setBusy(true);
    let acc = "";
    let cites: Citation[] = [];
    let conf: number | null = null;
    let insufficient: boolean | null = null;
    try {
      for await (const ev of api.chatStream({ kb_id: kbId, query: q, mode: "balanced", backend: "local" })) {
        if (ev.phase === "retrieve") setPhase("检索中…");
        else if (ev.phase === "rerank") setPhase("重排中…");
        else if (ev.phase === "generate" && ev.token) { acc += ev.token; setTurns((t) => syncAssistant(t, acc)); }
        else if (ev.phase === "citation") { cites = ev.citations ?? []; }
        else if (ev.phase === "done") { conf = ev.confidence ?? null; insufficient = ev.insufficient_evidence ?? null; setPhase(""); }
        else if (ev.phase === "error") setPhase("错误：" + ev.error);
      }
      setTurns((t) => replaceAssistant(t, { role: "assistant", content: acc, citations: cites, confidence: conf, insufficient }));
    } catch (e) {
      setPhase("错误：" + (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">聊天问答</h1>
      <select className="input" value={kbId} onChange={(e) => setKbId(e.target.value)}>
        {kbs.map((k) => <option key={k.id} value={k.id}>{k.name}</option>)}
      </select>
      <div className="card h-[55vh] overflow-auto space-y-3">
        {turns.map((t, i) => (
          <div key={i} className={t.role === "user" ? "text-right" : "text-left"}>
            <div className={"inline-block max-w-[80%] rounded-lg p-3 " + (t.role === "user" ? "bg-accent text-white" : "bg-panelb")}>
              <div className="whitespace-pre-wrap">{t.content}</div>
              {t.role === "assistant" && t.citations && t.citations.length > 0 && (
                <div className="mt-2 text-xs text-gray-400">
                  引用：
                  {t.citations.map((c, j) => (
                    <span key={c.id} className="mr-2">[来源 {j + 1}] {c.doc_name || c.doc_id} p{c.page_number}</span>
                  ))}
                </div>
              )}
              {t.role === "assistant" && t.insufficient && <div className="mt-1 text-xs text-yellow-400">资料不足</div>}
            </div>
          </div>
        ))}
        <div ref={endRef} />
      </div>
      <div className="flex gap-2">
        <input className="input flex-1" placeholder="输入问题…" value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()} />
        <button className="btn" onClick={send} disabled={busy}>{busy ? phase || "生成中…" : "发送"}</button>
      </div>
    </div>
  );
}

function syncAssistant(turns: Turn[], content: string): Turn[] {
  const copy = [...turns];
  const idx = copy.findIndex((t) => t.role === "assistant");
  if (idx >= 0) copy[idx] = { ...copy[idx], content };
  else copy.push({ role: "assistant", content });
  return copy;
}

function replaceAssistant(turns: Turn[], turn: Turn): Turn[] {
  const copy = [...turns];
  const idx = copy.findIndex((t) => t.role === "assistant");
  if (idx >= 0) copy[idx] = turn;
  else copy.push(turn);
  return copy;
}
