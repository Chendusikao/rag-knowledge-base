"use client";

import { FormEvent, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ROLE_LABELS, useCurrentUser } from "@/components/app-shell";
import {
  api,
  type AccessLevel,
  type Department,
  type EnterpriseUser,
  type KnowledgeBase,
  type KnowledgePermission,
  type SystemRole,
} from "@/lib/api";

const ACCESS_LABELS: Record<AccessLevel, string> = { viewer: "查看", editor: "编辑与导入", manager: "管理" };

export default function AccessControlPage() {
  const currentUser = useCurrentUser();
  const searchParams = useSearchParams();
  const [users, setUsers] = useState<EnterpriseUser[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [selectedKbId, setSelectedKbId] = useState("");
  const [permissions, setPermissions] = useState<KnowledgePermission[]>([]);
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [role, setRole] = useState<SystemRole>("member");
  const [temporaryPassword, setTemporaryPassword] = useState("");
  const [grantUserId, setGrantUserId] = useState("");
  const [grantLevel, setGrantLevel] = useState<AccessLevel>("viewer");
  const [resetTarget, setResetTarget] = useState<EnterpriseUser | null>(null);
  const [resetPassword, setResetPassword] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function loadBase() {
    try {
      const [userList, departmentList, kbList] = await Promise.all([
        api.listUsers(), api.listDepartments(), api.listKbs(),
      ]);
      const manageableKbs = kbList.filter((kb) => kb.access_level === "manager");
      const requestedKb = searchParams.get("kb");
      setUsers(userList);
      setDepartments(departmentList);
      setKbs(manageableKbs);
      setDepartmentId((current) => current || currentUser?.department_id || departmentList.find((item) => item.is_active)?.id || "");
      setGrantUserId((current) => current || userList.find((item) => item.id !== currentUser?.id && item.is_active)?.id || "");
      setSelectedKbId((current) => {
        if (current && manageableKbs.some((kb) => kb.id === current)) return current;
        if (requestedKb && manageableKbs.some((kb) => kb.id === requestedKb)) return requestedKb;
        return manageableKbs[0]?.id || "";
      });
      setError("");
    } catch (reason) { setError((reason as Error).message); }
    finally { setLoading(false); }
  }

  useEffect(() => { void loadBase(); }, []);
  useEffect(() => {
    if (!selectedKbId) { setPermissions([]); return; }
    api.listKbPermissions(selectedKbId)
      .then(setPermissions)
      .catch((reason) => setError((reason as Error).message));
  }, [selectedKbId]);

  async function createUser(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError(""); setMessage("");
    try {
      await api.createUser({
        display_name: displayName.trim(),
        email: email.trim(),
        department_id: departmentId || null,
        system_role: currentUser?.system_role === "department_manager" ? "member" : role,
        temporary_password: temporaryPassword,
      });
      setDisplayName(""); setEmail(""); setTemporaryPassword("");
      setMessage("用户已创建。首次登录后必须更换临时密码。" );
      await loadBase();
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(false); }
  }

  async function toggleUser(user: EnterpriseUser) {
    if (!window.confirm(`确定${user.is_active ? "停用" : "启用"}账号“${user.display_name}”吗？`)) return;
    setError(""); setMessage("");
    try {
      await api.updateUser(user.id, { is_active: !user.is_active });
      setMessage(user.is_active ? "账号已停用，现有登录会话已撤销。" : "账号已启用。" );
      await loadBase();
    } catch (reason) { setError((reason as Error).message); }
  }

  async function updateUserField(user: EnterpriseUser, patch: Partial<EnterpriseUser>) {
    setError(""); setMessage("");
    try {
      await api.updateUser(user.id, patch);
      setMessage("用户角色或部门已更新，新的权限边界立即生效。" );
      await loadBase();
    } catch (reason) { setError((reason as Error).message); }
  }

  async function submitReset(event: FormEvent) {
    event.preventDefault();
    if (!resetTarget) return;
    setBusy(true); setError(""); setMessage("");
    try {
      await api.resetUserPassword(resetTarget.id, resetPassword);
      setMessage(`已为“${resetTarget.display_name}”设置临时密码，并撤销其现有会话。`);
      setResetTarget(null); setResetPassword("");
      await loadBase();
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(false); }
  }

  async function grant(event: FormEvent) {
    event.preventDefault();
    if (!selectedKbId || !grantUserId) return;
    setBusy(true); setError(""); setMessage("");
    try {
      await api.setKbPermission(selectedKbId, grantUserId, grantLevel);
      setMessage("知识库权限已生效并写入审计。" );
      setPermissions(await api.listKbPermissions(selectedKbId));
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(false); }
  }

  async function revoke(permission: KnowledgePermission) {
    if (!window.confirm(`确定撤销“${permission.user_display_name}”的单独授权吗？`)) return;
    setError(""); setMessage("");
    try {
      await api.revokeKbPermission(permission.kb_id, permission.user_id);
      setMessage("单独授权已撤销。用户仍可能通过本部门默认范围获得查看权限。" );
      setPermissions(await api.listKbPermissions(permission.kb_id));
    } catch (reason) { setError((reason as Error).message); }
  }

  const availableUsers = users.filter((user) => user.is_active && user.id !== currentUser?.id);
  return (
    <div className="max-w-6xl space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">用户与权限</h1>
        <p className="mt-2 text-sm text-gray-400">角色决定管理边界，知识库授权决定具体内容的查看、编辑或管理能力。</p>
      </header>
      {error && <div className="card text-sm text-red-400">{error}</div>}
      {message && <div className="card text-sm text-green-400">{message}</div>}

      <section className="space-y-3">
        <h2 className="text-lg font-medium">企业用户</h2>
        <form className="card space-y-3" onSubmit={createUser}>
          <div className="text-sm font-medium">创建用户</div>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            <input className="input" placeholder="姓名" value={displayName} onChange={(event) => setDisplayName(event.target.value)} required />
            <input className="input" type="email" placeholder="企业邮箱" value={email} onChange={(event) => setEmail(event.target.value)} required />
            <select aria-label="用户所属部门" className="input" value={departmentId} onChange={(event) => setDepartmentId(event.target.value)} disabled={currentUser?.system_role === "department_manager"} required>
              {departments.filter((item) => item.is_active).map((department) => <option key={department.id} value={department.id}>{department.name}</option>)}
            </select>
            {currentUser?.system_role === "admin" ? (
              <select aria-label="用户系统角色" className="input" value={role} onChange={(event) => setRole(event.target.value as SystemRole)}>
                {Object.entries(ROLE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            ) : <div className="input text-sm text-gray-400">角色：成员</div>}
            <input className="input" type="password" placeholder="临时密码（至少 12 位）" minLength={12} value={temporaryPassword} onChange={(event) => setTemporaryPassword(event.target.value)} required />
          </div>
          <button className="btn" disabled={busy}>{busy ? "正在创建…" : "创建用户"}</button>
        </form>

        {loading ? <div className="card text-sm text-gray-400">正在读取用户…</div> : (
          <div className="overflow-hidden rounded-lg border border-edge">
            <table className="w-full text-left text-sm">
              <thead className="bg-panelb text-xs text-gray-400"><tr><th className="p-3">用户</th><th className="p-3">部门</th><th className="p-3">角色</th><th className="p-3">状态</th><th className="p-3">操作</th></tr></thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.id} className="border-t border-edge">
                    <td className="p-3"><div>{user.display_name}</div><div className="text-xs text-gray-500">{user.email}</div></td>
                    <td className="p-3 text-gray-300">
                      {currentUser?.system_role === "admin" && user.id !== currentUser.id ? (
                        <select aria-label={`${user.display_name}所属部门`} className="input py-1 text-xs" value={user.department_id || ""} onChange={(event) => updateUserField(user, { department_id: event.target.value || null })}>
                          <option value="">未分配</option>
                          {departments.filter((item) => item.is_active).map((department) => <option key={department.id} value={department.id}>{department.name}</option>)}
                        </select>
                      ) : user.department_name || "未分配"}
                    </td>
                    <td className="p-3 text-gray-300">
                      {currentUser?.system_role === "admin" && user.id !== currentUser.id ? (
                        <select aria-label={`${user.display_name}系统角色`} className="input py-1 text-xs" value={user.system_role} onChange={(event) => updateUserField(user, { system_role: event.target.value as SystemRole })}>
                          {Object.entries(ROLE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                        </select>
                      ) : ROLE_LABELS[user.system_role]}
                    </td>
                    <td className="p-3"><span className={user.is_active ? "text-green-400" : "text-gray-500"}>{user.is_active ? (user.must_change_password ? "等待首次改密" : "有效") : "已停用"}</span></td>
                    <td className="p-3">
                      {user.id !== currentUser?.id && <div className="flex gap-3"><button className="text-xs text-accent hover:underline" onClick={() => { setResetTarget(user); setResetPassword(""); }}>重置密码</button><button className="text-xs text-accent hover:underline" onClick={() => toggleUser(user)}>{user.is_active ? "停用" : "启用"}</button></div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {resetTarget && (
          <form className="card flex flex-col gap-3 md:flex-row md:items-end" onSubmit={submitReset}>
            <label className="flex-1 space-y-2 text-sm"><span>为“{resetTarget.display_name}”设置临时密码</span><input className="input w-full" type="password" minLength={12} value={resetPassword} onChange={(event) => setResetPassword(event.target.value)} required /></label>
            <button className="btn" disabled={busy}>确认重置</button>
            <button type="button" className="px-3 py-2 text-sm text-gray-400" onClick={() => setResetTarget(null)}>取消</button>
          </form>
        )}
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-medium">知识库单独授权</h2>
        {kbs.length === 0 ? <div className="card text-sm text-gray-400">当前账号没有可管理的知识库。</div> : (
          <>
            <form className="card grid gap-3 md:grid-cols-[1.5fr_1.5fr_1fr_auto]" onSubmit={grant}>
              <select aria-label="授权知识库" className="input" value={selectedKbId} onChange={(event) => setSelectedKbId(event.target.value)}>
                {kbs.map((kb) => <option key={kb.id} value={kb.id}>{kb.department_name} · {kb.name}</option>)}
              </select>
              <select aria-label="授权用户" className="input" value={grantUserId} onChange={(event) => setGrantUserId(event.target.value)}>
                {availableUsers.map((user) => <option key={user.id} value={user.id}>{user.display_name} · {user.department_name || "未分配"}</option>)}
              </select>
              <select aria-label="授权级别" className="input" value={grantLevel} onChange={(event) => setGrantLevel(event.target.value as AccessLevel)}>
                {Object.entries(ACCESS_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
              <button className="btn" disabled={busy || !grantUserId}>保存授权</button>
            </form>
            <div className="space-y-2">
              {permissions.map((permission) => (
                <div key={permission.id} className="card flex items-center justify-between gap-4 text-sm">
                  <div><div>{permission.user_display_name}</div><div className="mt-1 text-xs text-gray-500">{permission.user_email}</div></div>
                  <div className="flex items-center gap-5"><span className="text-gray-300">{ACCESS_LABELS[permission.access_level]}</span><button className="text-xs text-red-400" onClick={() => revoke(permission)}>撤销</button></div>
                </div>
              ))}
              {permissions.length === 0 && <div className="card text-sm text-gray-400">暂无单独授权，系统将按知识库的部门范围判断。</div>}
            </div>
          </>
        )}
      </section>
    </div>
  );
}
