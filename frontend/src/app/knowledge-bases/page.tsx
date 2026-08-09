"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useCurrentUser } from "@/components/app-shell";
import { api, type Department, type KnowledgeBase } from "@/lib/api";

const ACCESS_LABELS = { viewer: "可查看", editor: "可编辑", manager: "可管理", none: "无权限" };

export default function KnowledgeBasesPage() {
  const user = useCurrentUser();
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [accessScope, setAccessScope] = useState<"department" | "restricted">("department");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const canCreate = user && ["admin", "department_manager"].includes(user.system_role);

  async function load() {
    try {
      const [knowledgeBases, departmentList] = await Promise.all([api.listKbs(), api.listDepartments()]);
      setKbs(knowledgeBases);
      setDepartments(departmentList);
      setDepartmentId((current) => {
        if (current && departmentList.some((item) => item.id === current)) return current;
        if (user?.system_role === "department_manager" && user.department_id) return user.department_id;
        return departmentList.find((item) => item.is_active)?.id || "";
      });
      setError("");
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  async function create() {
    if (!name.trim() || !departmentId) return;
    setMessage(""); setError("");
    try {
      await api.createKb({
        name: name.trim(),
        description: description.trim(),
        department_id: departmentId,
        access_scope: accessScope,
      });
      setName(""); setDescription("");
      setMessage("知识库已创建，访问范围已经生效。" );
      await load();
    } catch (reason) { setError((reason as Error).message); }
  }

  async function remove(id: string, kbName: string) {
    if (!window.confirm(`确定删除知识库“${kbName}”吗？数据库记录和对应原文件都会删除，审计记录将保留。`)) return;
    setMessage(""); setError("");
    try {
      await api.deleteKb(id);
      setMessage("知识库及其原文件已删除，操作已写入审计。" );
      await load();
    } catch (reason) { setError((reason as Error).message); }
  }

  return (
    <div className="max-w-5xl space-y-5">
      <header>
        <h1 className="text-2xl font-semibold">部门知识库</h1>
        <p className="mt-2 text-sm text-gray-400">当前列表只包含账号有权访问的知识库，权限由部门范围和单独授权共同决定。</p>
      </header>

      {canCreate && (
        <div className="card space-y-3">
          <div className="text-sm font-medium">新建部门知识库</div>
          <div className="grid gap-3 md:grid-cols-2">
            <input className="input" placeholder="知识库名称" value={name} onChange={(event) => setName(event.target.value)} />
            <input className="input" placeholder="用途或内容说明（可选）" value={description} onChange={(event) => setDescription(event.target.value)} />
            <label className="space-y-2 text-sm">
              <span className="text-gray-400">所属部门</span>
              <select className="input w-full" value={departmentId} onChange={(event) => setDepartmentId(event.target.value)} disabled={user?.system_role === "department_manager"}>
                {departments.filter((item) => item.is_active).map((department) => (
                  <option key={department.id} value={department.id}>{department.name}</option>
                ))}
              </select>
            </label>
            <label className="space-y-2 text-sm">
              <span className="text-gray-400">默认访问范围</span>
              <select className="input w-full" value={accessScope} onChange={(event) => setAccessScope(event.target.value as "department" | "restricted")}>
                <option value="department">本部门成员可查看</option>
                <option value="restricted">仅单独授权用户</option>
              </select>
            </label>
          </div>
          <button className="btn" onClick={create} disabled={!name.trim() || !departmentId}>创建知识库</button>
        </div>
      )}

      {error && <div className="card text-sm text-red-400">{error}</div>}
      {message && <div className="card text-sm text-green-400">{message}</div>}
      <div className="space-y-2">
        {loading && <div className="card text-sm text-gray-400">正在读取授权知识库…</div>}
        {!loading && kbs.map((kb) => (
          <div key={kb.id} className="card flex flex-col justify-between gap-4 md:flex-row md:items-center">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{kb.name}</span>
                <Badge>{kb.department_name}</Badge>
                <Badge>{kb.access_scope === "department" ? "部门可读" : "指定用户"}</Badge>
                <Badge>{ACCESS_LABELS[kb.access_level]}</Badge>
              </div>
              <div className="mt-2 text-xs text-gray-400">{kb.description || "暂无说明"} · {kb.document_count} 份资料</div>
            </div>
            <div className="flex flex-wrap items-center gap-4">
              <Link href={`/chat?kb=${encodeURIComponent(kb.id)}`} className="text-xs text-accent hover:underline">发起问答</Link>
              {["editor", "manager"].includes(kb.access_level) && (
                <Link href={`/documents?kb=${encodeURIComponent(kb.id)}`} className="text-xs text-accent hover:underline">导入文件</Link>
              )}
              {kb.access_level === "manager" && (
                <Link href={`/access-control?kb=${encodeURIComponent(kb.id)}`} className="text-xs text-accent hover:underline">管理权限</Link>
              )}
              {kb.access_level === "manager" && (
                <button className="text-xs text-red-400" onClick={() => remove(kb.id, kb.name)}>删除</button>
              )}
            </div>
          </div>
        ))}
        {!loading && kbs.length === 0 && <div className="card text-sm text-gray-400">当前账号还没有可访问的知识库。</div>}
      </div>
    </div>
  );
}

function Badge({ children }: { children: React.ReactNode }) {
  return <span className="rounded bg-panelb px-2 py-1 text-[11px] text-gray-400">{children}</span>;
}
