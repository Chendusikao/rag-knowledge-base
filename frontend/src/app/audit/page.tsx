"use client";

import { useEffect, useState } from "react";
import { api, type AuditEvent, type SecurityStatus } from "@/lib/api";

const ACTION_LABELS: Record<string, string> = {
  "auth.bootstrap": "完成企业初始化",
  "auth.login": "用户登录",
  "auth.logout": "用户退出",
  "auth.password_changed": "修改密码",
  "department.created": "创建部门",
  "department.updated": "更新部门",
  "user.created": "创建用户",
  "user.updated": "更新用户",
  "user.password_reset": "重置用户密码",
  "knowledge_base.created": "创建知识库",
  "knowledge_base.updated": "更新知识库",
  "knowledge_base.deleted": "删除知识库",
  "permission.granted": "授予知识库权限",
  "permission.revoked": "撤销知识库权限",
  "permission.denied": "权限拒绝",
  "document.uploaded": "上传文档",
  "document.opened": "打开原文",
  "document.reindexed": "重新处理文档",
  "document.deleted": "删除文档",
  "document.source_imported": "从总资料库导入文档",
  "source_branch.imported": "同步总资料库分支",
  "chat.queried": "发起知识问答",
  "provider.updated": "更新模型配置",
};

export default function AuditPage() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [security, setSecurity] = useState<SecurityStatus | null>(null);
  const [action, setAction] = useState("");
  const [outcome, setOutcome] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    try {
      const [auditResult, securityResult] = await Promise.all([
        api.listAuditEvents({ action, outcome, limit: 100 }),
        api.securityStatus(),
      ]);
      setEvents(auditResult.items);
      setTotal(auditResult.total);
      setSecurity(securityResult);
      setError("");
    } catch (reason) { setError((reason as Error).message); }
    finally { setLoading(false); }
  }

  useEffect(() => { void load(); }, []);

  return (
    <div className="max-w-7xl space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">审计与数据安全</h1>
        <p className="mt-2 text-sm text-gray-400">审计记录只追加、不记录密码和问答正文；安全状态明确区分已启用能力与部署待办。</p>
      </header>
      {error && <div className="card text-sm text-red-400">{error}</div>}

      {security && (
        <section className="space-y-3">
          <h2 className="text-lg font-medium">安全基线</h2>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            <SecurityCard title="身份认证" value={security.authentication} ok />
            <SecurityCard title="密码存储" value={security.password_storage} ok />
            <SecurityCard title="会话 Cookie" value={security.session_cookie} ok={!security.session_cookie.includes("未启用")} />
            <SecurityCard title="跨站请求防护" value={security.csrf_protection} ok />
            <SecurityCard title="审计日志" value={security.audit_log} ok />
            <SecurityCard title="静态数据加密" value={security.storage_encryption} ok={security.storage_encryption_configured} />
          </div>
        </section>
      )}

      <section className="space-y-3">
        <div className="flex flex-col justify-between gap-3 md:flex-row md:items-end">
          <div><h2 className="text-lg font-medium">操作审计</h2><div className="mt-1 text-xs text-gray-500">共 {total} 条记录，当前显示最近 {events.length} 条</div></div>
          <div className="flex flex-wrap gap-2">
            <select aria-label="审计操作类型" className="input text-sm" value={action} onChange={(event) => setAction(event.target.value)}>
              <option value="">全部操作</option>
              {Object.entries(ACTION_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
            <select aria-label="审计结果" className="input text-sm" value={outcome} onChange={(event) => setOutcome(event.target.value)}>
              <option value="">全部结果</option>
              <option value="success">成功</option>
              <option value="failed">失败</option>
              <option value="denied">拒绝</option>
            </select>
            <button className="btn" onClick={load}>应用筛选</button>
          </div>
        </div>

        {loading ? <div className="card text-sm text-gray-400">正在读取审计记录…</div> : (
          <div className="overflow-x-auto rounded-lg border border-edge">
            <table className="w-full min-w-[900px] text-left text-sm">
              <thead className="bg-panelb text-xs text-gray-400"><tr><th className="p-3">时间</th><th className="p-3">操作者</th><th className="p-3">操作</th><th className="p-3">对象</th><th className="p-3">结果</th><th className="p-3">请求追踪</th></tr></thead>
              <tbody>
                {events.map((event) => (
                  <tr key={event.id} className="border-t border-edge align-top">
                    <td className="whitespace-nowrap p-3 text-gray-400">{formatTime(event.created_at)}</td>
                    <td className="p-3"><div>{event.actor_email || "未识别用户"}</div><div className="mt-1 text-xs text-gray-500">{event.ip_address || "未知地址"}</div></td>
                    <td className="p-3"><div>{ACTION_LABELS[event.action] || event.action}</div><Detail details={event.details} /></td>
                    <td className="p-3 text-gray-300"><div>{event.resource_type}</div><div className="mt-1 max-w-52 truncate text-xs text-gray-500" title={event.resource_id}>{event.resource_id || "-"}</div></td>
                    <td className="p-3"><Outcome value={event.outcome} /></td>
                    <td className="p-3"><span className="font-mono text-xs text-gray-500">{event.request_id.slice(0, 12) || "-"}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function SecurityCard({ title, value, ok }: { title: string; value: string; ok: boolean }) {
  return (
    <div className="card">
      <div className="flex items-center justify-between gap-3"><span className="text-sm font-medium">{title}</span><span className={ok ? "text-xs text-green-400" : "text-xs text-yellow-400"}>{ok ? "已启用" : "需要配置"}</span></div>
      <div className="mt-2 text-xs leading-5 text-gray-400">{value}</div>
    </div>
  );
}

function Outcome({ value }: { value: string }) {
  const style = value === "success" ? "text-green-400" : value === "denied" ? "text-yellow-400" : "text-red-400";
  const label = value === "success" ? "成功" : value === "denied" ? "拒绝" : "失败";
  return <span className={style}>{label}</span>;
}

function Detail({ details }: { details: Record<string, unknown> }) {
  const text = Object.entries(details).map(([key, value]) => `${key}: ${String(value)}`).join(" · ");
  return text ? <div className="mt-1 max-w-sm truncate text-xs text-gray-500" title={text}>{text}</div> : null;
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "short", timeStyle: "medium" }).format(new Date(value));
}
