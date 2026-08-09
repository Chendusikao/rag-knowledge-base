"use client";

import { FormEvent, useEffect, useState } from "react";
import { useCurrentUser } from "@/components/app-shell";
import { api, type Department } from "@/lib/api";

export default function DepartmentsPage() {
  const user = useCurrentUser();
  const [departments, setDepartments] = useState<Department[]>([]);
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function load() {
    try { setDepartments(await api.listDepartments()); setError(""); }
    catch (reason) { setError((reason as Error).message); }
    finally { setLoading(false); }
  }

  useEffect(() => { void load(); }, []);

  async function create(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError(""); setMessage("");
    try {
      await api.createDepartment({ name: name.trim(), code: code.trim().toLowerCase(), description: description.trim() });
      setName(""); setCode(""); setDescription("");
      setMessage("部门已创建，可以在创建知识库或用户时选择。" );
      await load();
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(false); }
  }

  async function toggle(department: Department) {
    if (!window.confirm(`确定${department.is_active ? "停用" : "启用"}部门“${department.name}”吗？`)) return;
    setError(""); setMessage("");
    try {
      await api.updateDepartment(department.id, { is_active: !department.is_active });
      setMessage(department.is_active ? "部门已停用，历史资料仍保留。" : "部门已重新启用。" );
      await load();
    } catch (reason) { setError((reason as Error).message); }
  }

  return (
    <div className="max-w-5xl space-y-5">
      <header>
        <h1 className="text-2xl font-semibold">部门管理</h1>
        <p className="mt-2 text-sm text-gray-400">知识库和成员归属部门，部门负责人只能管理本部门范围。</p>
      </header>

      {user?.system_role === "admin" && (
        <form className="card space-y-3" onSubmit={create}>
          <div className="text-sm font-medium">新建部门</div>
          <div className="grid gap-3 md:grid-cols-2">
            <input className="input" placeholder="部门名称，例如：销售部" value={name} onChange={(event) => setName(event.target.value)} required />
            <input className="input" placeholder="部门编码，例如：sales" pattern="[a-z0-9][a-z0-9_-]+" value={code} onChange={(event) => setCode(event.target.value)} required />
          </div>
          <input className="input w-full" placeholder="部门职责说明（可选）" value={description} onChange={(event) => setDescription(event.target.value)} />
          <button className="btn" disabled={busy}>{busy ? "正在创建…" : "创建部门"}</button>
        </form>
      )}

      {error && <div className="card text-sm text-red-400">{error}</div>}
      {message && <div className="card text-sm text-green-400">{message}</div>}
      {loading ? (
        <div className="card text-sm text-gray-400">正在读取部门…</div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {departments.map((department) => (
            <div key={department.id} className="card space-y-3">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="font-medium">{department.name}</div>
                  <div className="mt-1 text-xs text-gray-500">编码：{department.code}</div>
                </div>
                <span className={`rounded px-2 py-1 text-xs ${department.is_active ? "bg-green-500/10 text-green-400" : "bg-gray-500/10 text-gray-400"}`}>
                  {department.is_active ? "使用中" : "已停用"}
                </span>
              </div>
              <div className="text-sm text-gray-400">{department.description || "暂无说明"}</div>
              <div className="flex gap-6 text-xs text-gray-400">
                <span>{department.knowledge_base_count} 个知识库</span>
                <span>{department.user_count} 名有效成员</span>
              </div>
              {user?.system_role === "admin" && (
                <button className="text-xs text-accent hover:underline" onClick={() => toggle(department)}>
                  {department.is_active ? "停用部门" : "启用部门"}
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
