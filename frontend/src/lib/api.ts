// Typed API client for the RAG backend. Generated types can be produced with
// `npm run generate-client` (scripts/generate-client.ts) from the backend's
// /openapi.json. The hand-written types below mirror the Pydantic schemas.

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText} ${detail}`);
  }
  return res.json() as Promise<T>;
}

// ---- Types ----
export interface KnowledgeBase {
  id: string;
  name: string;
  description: string;
  embedding_model: string;
  reranker_model: string;
  vision_enabled: boolean;
  current_generation: number;
  settings: Record<string, unknown>;
  document_count: number;
  created_at: string;
  updated_at: string;
}

export interface DocumentOut {
  id: string;
  kb_id: string;
  filename: string;
  mime_type: string;
  ext: string;
  content_hash: string;
  size_bytes: number;
  num_pages: number;
  status: string;
  current_version: number;
  storage_path: string;
  created_at: string;
  updated_at: string;
}

export interface JobRun {
  id: string;
  job_type: string;
  kb_id: string;
  doc_id: string | null;
  status: string;
  progress: number;
  retries: number;
  max_retries: number;
  error: string | null;
  checkpoint: Record<string, unknown>;
  lease_owner: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Citation {
  id: string;
  chunk_id: string | null;
  kb_id: string;
  doc_id: string;
  doc_name: string;
  citation_type: string;
  page_number: number;
  section_path: string[];
  region: Record<string, unknown> | null;
  snippet: string;
}

export type StreamPhase =
  | "retrieve" | "rerank" | "generate" | "citation" | "done" | "error";

export interface ChatStreamEvent {
  phase: StreamPhase;
  session_id?: string | null;
  message_id?: string | null;
  token?: string | null;
  citations?: Citation[] | null;
  confidence?: number | null;
  insufficient_evidence?: boolean | null;
  data?: Record<string, unknown> | null;
  error?: string | null;
}

export interface RetrievedChunk {
  chunk_id: string;
  doc_id: string;
  doc_name: string;
  page_number: number;
  section_path: string[];
  modality: string;
  snippet: string;
  dense_score: number;
  bm25_score: number;
  rrf_score: number;
  rerank_score: number;
}

// ---- Client ----
export const api = {
  base: API_BASE,

  // Knowledge bases
  listKbs: () => json<KnowledgeBase[]>(fetch(`${API_BASE}/api/v1/knowledge-bases`).then(assert)),
  createKb: (body: Partial<KnowledgeBase>) =>
    json<KnowledgeBase>(fetch(`${API_BASE}/api/v1/knowledge-bases`, post(body)).then(assert)),
  getKb: (id: string) => json<KnowledgeBase>(fetch(`${API_BASE}/api/v1/knowledge-bases/${id}`).then(assert)),
  deleteKb: (id: string) => fetch(`${API_BASE}/api/v1/knowledge-bases/${id}`, { method: "DELETE" }).then(assert),

  // Documents
  uploadDoc: (kbId: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return json<{ document: DocumentOut; job_id: string; message: string }>(
      fetch(`${API_BASE}/api/v1/knowledge-bases/${kbId}/documents`, {
        method: "POST",
        body: fd,
      }).then(assert)
    );
  },
  reindexDoc: (docId: string) => json<DocumentOut>(fetch(`${API_BASE}/api/v1/documents/${docId}/reindex`, { method: "POST" }).then(assert)),
  deleteDoc: (docId: string) => fetch(`${API_BASE}/api/v1/documents/${docId}`, { method: "DELETE" }).then(assert),

  // Jobs
  getJob: (id: string) => json<JobRun>(fetch(`${API_BASE}/api/v1/jobs/${id}`).then(assert)),

  // Retrieval inspect
  retrievalInspect: (body: { kb_id: string; query: string; mode?: string; filters?: Record<string, unknown> }) =>
    json<{ query: string; mode: string; results: RetrievedChunk[]; latency_ms: number; rrf_scores: unknown[] }>(
      fetch(`${API_BASE}/api/v1/retrieval/inspect`, post(body)).then(assert)
    ),

  // Chat stream (SSE)
  async *chatStream(body: {
    kb_id: string;
    query: string;
    mode?: string;
    filters?: Record<string, unknown>;
    backend?: string;
    session_id?: string | null;
  }): AsyncGenerator<ChatStreamEvent> {
    const res = await fetch(`${API_BASE}/api/v1/chat/stream`, post(body));
    if (!res.ok || !res.body) throw new Error(`chat stream failed: ${res.status}`);
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const frames = buf.split("\n\n");
      buf = frames.pop() ?? "";
      for (const frame of frames) {
        const line = frame.split("\n").find((l) => l.startsWith("data:"));
        if (!line) continue;
        const payload = line.slice(5).trim();
        if (!payload) continue;
        yield JSON.parse(payload) as ChatStreamEvent;
      }
    }
  },

  // Evaluation
  createCase: (body: Record<string, unknown>) =>
    json<unknown>(fetch(`${API_BASE}/api/v1/evaluation-cases`, post(body)).then(assert)),
  listCases: (kbId: string) =>
    json<unknown[]>(fetch(`${API_BASE}/api/v1/evaluation-cases?kb_id=${kbId}`).then(assert)),
  createRun: (body: { kb_id: string; mode?: string; case_ids?: string[] }) =>
    json<unknown>(fetch(`${API_BASE}/api/v1/evaluation-runs`, post(body)).then(assert)),

  // Providers
  listProviders: () => json<unknown[]>(fetch(`${API_BASE}/api/v1/provider-profiles`).then(assert)),
  upsertProvider: (role: string, body: Record<string, unknown>) =>
    json<unknown>(fetch(`${API_BASE}/api/v1/provider-profiles/${role}`, { method: "PUT", ...post(body) }).then(assert)),
  testProvider: (body: Record<string, unknown>) =>
    json<{ ok: boolean; latency_ms: number; detail: string }>(
      fetch(`${API_BASE}/api/v1/provider-profiles/test`, post(body)).then(assert)
    ),
};

function post(body: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

async function assert(res: Response): Promise<Response> {
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText} ${detail}`);
  }
  return res;
}
