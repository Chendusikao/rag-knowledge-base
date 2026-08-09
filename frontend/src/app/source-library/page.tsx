"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useCurrentUser } from "@/components/app-shell";
import {
  api,
  type Department,
  type SourceBranch,
  type SourceBranchImportResult,
  type SourceLibrary,
} from "@/lib/api";

type AccessScope = "department" | "restricted";
type BranchChoice = { departmentId: string; accessScope: AccessScope };

export default function SourceLibraryPage() {
  const user = useCurrentUser();
  const [library, setLibrary] = useState<SourceLibrary | null>(null);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [choices, setChoices] = useState<Record<string, BranchChoice>>({});
  const [results, setResults] = useState<Record<string, SourceBranchImportResult>>({});
  const [busyBranch, setBusyBranch] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function load() {
    if (user?.system_role !== "admin") return;
    try {
      const [nextLibrary, departmentList] = await Promise.all([
        api.listSourceBranches(),
        api.listDepartments(),
      ]);
      const activeDepartments = departmentList.filter((item) => item.is_active);
      setLibrary(nextLibrary);
      setDepartments(activeDepartments);
      setChoices((current) => {
        const next = { ...current };
        for (const branch of nextLibrary.branches) {
          if (!next[branch.name]) {
            next[branch.name] = {
              departmentId: activeDepartments[0]?.id || "",
              accessScope: branch.recommended_access_scope,
            };
          }
        }
        return next;
      });
      setError("");
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, [user?.system_role]);

  function updateChoice(branchName: string, patch: Partial<BranchChoice>) {
    setChoices((current) => ({
      ...current,
      [branchName]: { ...current[branchName], ...patch },
    }));
  }

  async function importBranch(branch: SourceBranch) {
    const choice = choices[branch.name];
    if (!choice?.departmentId) {
      setError("请先选择所属部门。");
      return;
    }

    let confirmSensitiveDepartmentAccess = false;
    if (branch.sensitive && choice.accessScope === "department") {
      confirmSensitiveDepartmentAccess = window.confirm(
        `“${branch.name}”包含敏感资料。确定要让所选部门的全部成员默认可查看吗？`,
      );
      if (!confirmSensitiveDepartmentAccess) return;
    }

    setBusyBranch(branch.name);
    setError("");
    try {
      const result = await api.importSourceBranch({
        branch_name: branch.name,
        department_id: choice.departmentId,
        access_scope: choice.accessScope,
        confirm_sensitive_department_access: confirmSensitiveDepartmentAccess,
      });
      setResults((current) => ({ ...current, [branch.name]: result }));
      await load();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusyBranch("");
    }
  }

  if (user?.system_role !== "admin") {
    return <div className="card max-w-xl text-sm text-red-400">只有系统管理员可以查看和同步总资料库。</div>;
  }

  return (
    <div className="max-w-6xl space-y-5">
      <header>
        <h1 className="text-2xl font-semibold">企业总资料库</h1>
        <p className="mt-2 text-sm text-gray-400">
          一级目录作为资料分支展示。同步只会读取源文件并复制到受管知识库，不会修改或删除总资料库原件。
        </p>
      </header>

      {loading && <div className="card text-sm text-gray-400">正在扫描总资料库分支…</div>}
      {error && <div className="card text-sm text-red-400">{error}</div>}

      {!loading && library && (
        <div className="card flex flex-col gap-2 text-sm md:flex-row md:items-center md:justify-between">
          <div>
            <div className="text-xs text-gray-500">只读数据源</div>
            <div className="mt-1 break-all font-medium">{library.root}</div>
          </div>
          <div className={library.available ? "text-green-400" : "text-red-400"}>
            {library.available ? `已连接 · ${library.branches.length} 个分支` : "目录不存在或无法读取"}
          </div>
        </div>
      )}

      {!loading && library?.available && departments.length === 0 && (
        <div className="card text-sm text-amber-300">
          当前没有可用部门。请先前往 <Link className="text-accent hover:underline" href="/departments">部门管理</Link> 创建部门。
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        {library?.branches.map((branch) => {
          const choice = choices[branch.name];
          const result = results[branch.name];
          const canImport = branch.importable_file_count > 0
            && !branch.truncated
            && Boolean(choice?.departmentId)
            && !busyBranch;
          return (
            <section key={branch.name} className="card space-y-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="font-medium">{branch.name}</h2>
                    {branch.sensitive && <Badge tone="danger">敏感资料</Badge>}
                    {!branch.importable_file_count && <Badge>暂无可导入文件</Badge>}
                  </div>
                  <div className="mt-2 text-xs text-gray-500">
                    {branch.last_modified_at ? `最近更新 ${formatDate(branch.last_modified_at)}` : "空分支"}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-xl font-semibold">{branch.importable_file_count}</div>
                  <div className="text-xs text-gray-500">个可导入文件</div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 text-xs text-gray-400 md:grid-cols-4">
                <Stat label="全部文件" value={branch.total_file_count} />
                <Stat label="受支持" value={branch.supported_file_count} />
                <Stat label="不支持" value={branch.unsupported_file_count} />
                <Stat label="总大小" value={formatBytes(branch.total_size_bytes)} />
              </div>

              <div className="text-xs text-gray-500">
                类型：{formatExtensions(branch.extension_counts) || "暂无文件"}
                {branch.oversized_file_count > 0 && ` · ${branch.oversized_file_count} 个文件超过大小限制`}
                {branch.truncated && " · 扫描达到安全上限，暂不可导入"}
              </div>

              <div className="grid gap-3 md:grid-cols-2">
                <label className="space-y-2 text-sm">
                  <span className="text-gray-400">导入后所属部门</span>
                  <select
                    className="input w-full"
                    value={choice?.departmentId || ""}
                    onChange={(event) => updateChoice(branch.name, { departmentId: event.target.value })}
                  >
                    <option value="">请选择部门</option>
                    {departments.map((department) => (
                      <option key={department.id} value={department.id}>{department.name}</option>
                    ))}
                  </select>
                </label>
                <label className="space-y-2 text-sm">
                  <span className="text-gray-400">默认访问范围</span>
                  <select
                    className="input w-full"
                    value={choice?.accessScope || branch.recommended_access_scope}
                    onChange={(event) => updateChoice(branch.name, { accessScope: event.target.value as AccessScope })}
                  >
                    <option value="restricted">仅单独授权用户</option>
                    <option value="department">本部门成员可查看</option>
                  </select>
                </label>
              </div>

              {branch.sensitive && choice?.accessScope !== "department" && (
                <div className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
                  已按敏感资料使用受限模式。导入后请在“用户与权限”中单独授权。
                </div>
              )}

              <button className="btn" disabled={!canImport} onClick={() => importBranch(branch)}>
                {busyBranch === branch.name ? "正在安全复制并登记…" : "同步到同名知识库"}
              </button>

              {result && (
                <div className="rounded-md bg-panelb px-3 py-2 text-xs text-gray-300">
                  {result.created_knowledge_base ? "已创建知识库。" : "已同步现有知识库。"}
                  新增 {result.imported_count} 个，重复跳过 {result.skipped_duplicate_count} 个
                  {result.failed_count > 0 ? `，失败 ${result.failed_count} 个` : ""}。
                  {result.job_ids.length > 0 && "文件正在后台建立索引。"}
                </div>
              )}
            </section>
          );
        })}
      </div>

      {!loading && library?.available && library.branches.length === 0 && (
        <div className="card text-sm text-gray-400">总资料库下还没有一级分支。</div>
      )}
    </div>
  );
}

function Badge({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "danger" }) {
  const colors = tone === "danger" ? "bg-red-500/10 text-red-300" : "bg-panelb text-gray-400";
  return <span className={`rounded px-2 py-1 text-[11px] ${colors}`}>{children}</span>;
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return <div className="rounded bg-panelb px-3 py-2"><div>{value}</div><div className="mt-1 text-gray-500">{label}</div></div>;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function formatExtensions(counts: Record<string, number>): string {
  return Object.entries(counts).map(([extension, count]) => `${extension} × ${count}`).join("、");
}
