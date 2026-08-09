// Typed API client for the RAG backend. Generated types can be produced with
// `npm run generate-client` (scripts/generate-client.ts) from the backend's
// /openapi.json. The hand-written types below mirror the Pydantic schemas.

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    headers.set("X-Requested-With", "EnterpriseKnowledgeBase");
  }
  return fetch(`${API_BASE}${path}`, {
    ...init,
    method,
    headers,
    credentials: "include",
    cache: "no-store",
  });
}

async function json<T>(response: Promise<Response>): Promise<T> {
  const res = await response;
  if (!res.ok) {
    const raw = await res.text().catch(() => "");
    let detail = raw;
    try {
      const parsed = JSON.parse(raw) as { detail?: string | Array<{ msg?: string }> };
      detail = typeof parsed.detail === "string"
        ? parsed.detail
        : Array.isArray(parsed.detail)
          ? parsed.detail.map((item) => item.msg).filter(Boolean).join("；")
          : raw;
    } catch {}
    throw new Error(detail || `${res.status} ${res.statusText}`);
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
  department_id: string;
  department_name: string;
  access_scope: "department" | "restricted";
  access_level: "none" | "viewer" | "editor" | "manager";
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
  created_at: string;
  updated_at: string;
}

export type SystemRole = "admin" | "department_manager" | "member" | "auditor";
export type AccessLevel = "viewer" | "editor" | "manager";

export interface EnterpriseUser {
  id: string;
  email: string;
  display_name: string;
  department_id: string | null;
  department_name: string | null;
  system_role: SystemRole;
  is_active: boolean;
  must_change_password: boolean;
  last_login_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AuthStatus {
  setup_required: boolean;
  authenticated: boolean;
  user: EnterpriseUser | null;
}

export interface Department {
  id: string;
  name: string;
  code: string;
  description: string;
  is_active: boolean;
  user_count: number;
  knowledge_base_count: number;
  created_at: string;
  updated_at: string;
}

export interface KnowledgePermission {
  id: string;
  kb_id: string;
  user_id: string;
  user_email: string;
  user_display_name: string;
  access_level: AccessLevel;
  granted_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface AuditEvent {
  id: string;
  actor_user_id: string | null;
  actor_email: string;
  action: string;
  resource_type: string;
  resource_id: string;
  department_id: string | null;
  outcome: string;
  request_id: string;
  ip_address: string;
  user_agent: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface AuditEventList {
  items: AuditEvent[];
  total: number;
  limit: number;
  offset: number;
}

export interface SecurityStatus {
  authentication: string;
  password_storage: string;
  session_cookie: string;
  csrf_protection: string;
  audit_log: string;
  storage_encryption: string;
  storage_encryption_configured: boolean;
}

export interface SourceBranch {
  name: string;
  total_file_count: number;
  supported_file_count: number;
  importable_file_count: number;
  unsupported_file_count: number;
  oversized_file_count: number;
  total_size_bytes: number;
  extension_counts: Record<string, number>;
  last_modified_at: string | null;
  sensitive: boolean;
  recommended_access_scope: "department" | "restricted";
  truncated: boolean;
}

export interface SourceLibrary {
  root: string;
  available: boolean;
  read_only: boolean;
  branches: SourceBranch[];
}

export interface SourceBranchImportResult {
  branch_name: string;
  knowledge_base_id: string;
  knowledge_base_name: string;
  created_knowledge_base: boolean;
  imported_count: number;
  skipped_duplicate_count: number;
  unsupported_count: number;
  oversized_count: number;
  failed_count: number;
  job_ids: string[];
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

// ---- Client ----
export const api = {
  base: API_BASE,

  // Authentication
  authStatus: () => json<AuthStatus>(request("/api/v1/auth/status")),
  bootstrap: (body: { organization_name: string; display_name: string; email: string; password: string }) =>
    json<EnterpriseUser>(request("/api/v1/auth/bootstrap", post(body))),
  login: (body: { email: string; password: string }) =>
    json<EnterpriseUser>(request("/api/v1/auth/login", post(body))),
  logout: () => request("/api/v1/auth/logout", { method: "POST" }).then(assert),
  me: () => json<EnterpriseUser>(request("/api/v1/auth/me")),
  changePassword: (body: { current_password: string; new_password: string }) =>
    request("/api/v1/auth/change-password", post(body)).then(assert),

  // Departments and users
  listDepartments: () => json<Department[]>(request("/api/v1/departments")),
  createDepartment: (body: { name: string; code: string; description?: string }) =>
    json<Department>(request("/api/v1/departments", post(body))),
  updateDepartment: (id: string, body: Partial<Department>) =>
    json<Department>(request(`/api/v1/departments/${id}`, put(body))),
  listUsers: () => json<EnterpriseUser[]>(request("/api/v1/users")),
  createUser: (body: {
    email: string;
    display_name: string;
    department_id: string | null;
    system_role: SystemRole;
    temporary_password: string;
  }) => json<EnterpriseUser>(request("/api/v1/users", post(body))),
  updateUser: (id: string, body: Partial<EnterpriseUser>) =>
    json<EnterpriseUser>(request(`/api/v1/users/${id}`, put(body))),
  resetUserPassword: (id: string, temporaryPassword: string) =>
    request(`/api/v1/users/${id}/reset-password`, post({ temporary_password: temporaryPassword })).then(assert),

  // Knowledge bases
  listKbs: () => json<KnowledgeBase[]>(request("/api/v1/knowledge-bases")),
  createKb: (body: Partial<KnowledgeBase>) =>
    json<KnowledgeBase>(request("/api/v1/knowledge-bases", post(body))),
  getKb: (id: string) => json<KnowledgeBase>(request(`/api/v1/knowledge-bases/${id}`)),
  updateKb: (id: string, body: Partial<KnowledgeBase>) =>
    json<KnowledgeBase>(request(`/api/v1/knowledge-bases/${id}`, put(body))),
  deleteKb: (id: string) => request(`/api/v1/knowledge-bases/${id}`, { method: "DELETE" }).then(assert),
  listKbPermissions: (id: string) =>
    json<KnowledgePermission[]>(request(`/api/v1/knowledge-bases/${id}/permissions`)),
  setKbPermission: (id: string, userId: string, accessLevel: AccessLevel) =>
    json<KnowledgePermission>(request(`/api/v1/knowledge-bases/${id}/permissions`, put({ user_id: userId, access_level: accessLevel }))),
  revokeKbPermission: (id: string, userId: string) =>
    request(`/api/v1/knowledge-bases/${id}/permissions/${userId}`, { method: "DELETE" }).then(assert),

  // Documents
  uploadDoc: (kbId: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return json<{ document: DocumentOut; job_id: string; message: string }>(
      request(`/api/v1/knowledge-bases/${kbId}/documents`, {
        method: "POST",
        body: fd,
      })
    );
  },
  reindexDoc: (docId: string) => json<DocumentOut>(request(`/api/v1/documents/${docId}/reindex`, { method: "POST" })),
  deleteDoc: (docId: string) => request(`/api/v1/documents/${docId}`, { method: "DELETE" }).then(assert),

  // Jobs
  getJob: (id: string) => json<JobRun>(request(`/api/v1/jobs/${id}`)),

  // Audit and security
  listAuditEvents: (params: Record<string, string | number | undefined> = {}) => {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== "") search.set(key, String(value));
    });
    const suffix = search.size ? `?${search.toString()}` : "";
    return json<AuditEventList>(request(`/api/v1/audit-events${suffix}`));
  },
  securityStatus: () => json<SecurityStatus>(request("/api/v1/security/status")),

  // Read-only enterprise source library (admin only)
  listSourceBranches: () => json<SourceLibrary>(request("/api/v1/source-library/branches")),
  importSourceBranch: (body: {
    branch_name: string;
    department_id: string;
    access_scope: "department" | "restricted";
    confirm_sensitive_department_access?: boolean;
  }) => json<SourceBranchImportResult>(request("/api/v1/source-library/imports", post(body))),

  // Chat stream (SSE)
  async *chatStream(body: {
    kb_id: string;
    query: string;
    mode?: string;
    filters?: Record<string, unknown>;
    backend?: string;
    session_id?: string | null;
  }): AsyncGenerator<ChatStreamEvent> {
    const res = await request("/api/v1/chat/stream", post(body));
    if (!res.ok || !res.body) throw new Error(`问答服务暂时不可用（${res.status}）`);
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
};

function post(body: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

function put(body: unknown): RequestInit {
  return {
    method: "PUT",
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
