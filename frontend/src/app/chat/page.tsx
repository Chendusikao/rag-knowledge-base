"use client";

import Link from "next/link";
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
  const [loading, setLoading] = useState(true);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.listKbs()
      .then((list) => {
        const requestedKbId = new URLSearchParams(window.location.search).get("kb");
        setKbs(list);
        if (requestedKbId && list.some((kb) => kb.id === requestedKbId)) setKbId(requestedKbId);
        else if (list.length) setKbId(list[0].id);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
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
        if (ev.phase === "retrieve" || ev.phase === "rerank") setPhase("正在查找相关资料…");
        else if (ev.phase === "generate" && ev.token) {
          setPhase("正在整理回答…");
          acc += ev.token;
          setTurns((t) => syncAssistant(t, acc));
        }
        else if (ev.phase === "citation") { cites = ev.citations ?? []; }
        else if (ev.phase === "done") { conf = ev.confidence ?? null; insufficient = ev.insufficient_evidence ?? null; setPhase(""); }
        else if (ev.phase === "error") setPhase("暂时无法回答：" + ev.error);
      }
      setTurns((t) => replaceAssistant(t, { role: "assistant", content: acc, citations: cites, confidence: conf, insufficient }));
    } catch (e) {
      setPhase("暂时无法回答：" + (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-5xl space-y-4">
      <header>
        <h1 className="text-2xl font-semibold">问答</h1>
        <p className="mt-2 text-sm text-gray-400">回答会依据所选企业知识库，并标出可核查的引用来源。</p>
      </header>

      {loading ? (
        <div className="card text-sm text-gray-400">正在读取知识库…</div>
      ) : kbs.length === 0 ? (
        <div className="card text-sm text-gray-300">
          还没有可用的知识库。请先<Link href="/knowledge-bases" className="mx-1 text-accent hover:underline">创建知识库</Link>并添加资料。
        </div>
      ) : (
        <label className="block space-y-2">
          <span className="text-sm font-medium">回答所依据的知识库</span>
          <select className="input w-full md:w-80" value={kbId} onChange={(e) => setKbId(e.target.value)}>
            {kbs.map((k) => <option key={k.id} value={k.id}>{k.name}</option>)}
          </select>
        </label>
      )}

      <div className="card h-[55vh] overflow-auto space-y-3">
        {turns.length === 0 && (
          <div className="flex h-full items-center justify-center text-sm text-gray-500">
            {loading ? "正在准备问答…" : "输入一个与资料有关的问题，开始问答。"}
          </div>
        )}
        {turns.map((t, i) => (
          <div key={i} className={t.role === "user" ? "text-right" : "text-left"}>
            <div className={"inline-block max-w-[80%] rounded-lg p-3 " + (t.role === "user" ? "bg-accent text-white" : "bg-panelb")}>
              <div className="whitespace-pre-wrap">{t.content}</div>
              {t.role === "assistant" && t.citations && t.citations.length > 0 && (
                <div className="mt-3 border-t border-edge pt-2 text-xs text-gray-400">
                  <div className="mb-1">参考来源</div>
                  {t.citations.map((c, j) => (
                    <a
                      key={c.id}
                      href={`${api.base}/api/v1/documents/${c.doc_id}/file`}
                      target="_blank"
                      rel="noreferrer"
                      className="mr-3 text-accent hover:underline"
                    >
                      [{j + 1}] {c.doc_name || c.doc_id}{c.page_number > 0 ? ` · 第 ${c.page_number} 页` : ""}
                    </a>
                  ))}
                </div>
              )}
              {t.role === "assistant" && t.insufficient && <div className="mt-2 text-xs text-yellow-400">现有资料不足以可靠回答这个问题。</div>}
            </div>
          </div>
        ))}
        <div ref={endRef} />
      </div>
      <div className="flex gap-2">
        <input
          className="input flex-1"
          placeholder={loading ? "正在读取知识库…" : kbs.length ? "输入需要查询的业务问题…" : "请先创建知识库并添加资料"}
          value={query}
          disabled={!kbId || busy}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
        />
        <button className="btn" onClick={send} disabled={!kbId || !query.trim() || busy}>
          {busy ? phase || "正在回答…" : "发送"}
        </button>
      </div>
      {!busy && phase && <div className="text-sm text-red-400">{phase}</div>}
    </div>
  );
}

function syncAssistant(turns: Turn[], content: string): Turn[] {
  const copy = [...turns];
  const idx = findAssistantAfterLatestQuestion(copy);
  if (idx >= 0) copy[idx] = { ...copy[idx], content };
  else copy.push({ role: "assistant", content });
  return copy;
}

function replaceAssistant(turns: Turn[], turn: Turn): Turn[] {
  const copy = [...turns];
  const idx = findAssistantAfterLatestQuestion(copy);
  if (idx >= 0) copy[idx] = turn;
  else copy.push(turn);
  return copy;
}

function findAssistantAfterLatestQuestion(turns: Turn[]): number {
  const latestQuestion = turns.findLastIndex((turn) => turn.role === "user");
  return turns.findIndex((turn, index) => index > latestQuestion && turn.role === "assistant");
}
