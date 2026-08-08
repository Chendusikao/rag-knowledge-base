"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const ROLES = ["llm", "embedding", "vision", "agent"];

export default function SettingsPage() {
  const [profiles, setProfiles] = useState<Record<string, any>>({});
  const [msg, setMsg] = useState("");

  async function load() {
    try {
      const list = (await api.listProviders()) as any[];
      const map: Record<string, any> = {};
      for (const p of list) map[p.role] = p;
      setProfiles(map);
    } catch (e) {
      setMsg("加载失败：" + (e as Error).message);
    }
  }
  useEffect(() => { load(); }, []);

  function set(role: string, key: string, value: string) {
    setProfiles((p) => ({ ...p, [role]: { ...(p[role] ?? { role }), [key]: value } }));
  }

  async function save(role: string) {
    const p = profiles[role] ?? { role };
    try {
      await api.upsertProvider(role, p);
      setMsg(`已保存 ${role}`);
      load();
    } catch (e) {
      setMsg("保存失败：" + (e as Error).message);
    }
  }

  async function test(role: string) {
    const p = profiles[role] ?? { role };
    try {
      const r = await api.testProvider({ role, kind: p.kind ?? "mock", base_url: p.base_url ?? "", model: p.model ?? "" });
      setMsg(`测试 ${role}：${r.ok ? "通过" : "失败"} ${r.detail} (${r.latency_ms}ms)`);
    } catch (e) {
      setMsg("测试失败：" + (e as Error).message);
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">设置 · Provider</h1>
      {msg && <div className="text-xs text-accent">{msg}</div>}
      {ROLES.map((role) => {
        const p = profiles[role] ?? { role, kind: "mock" };
        return (
          <div key={role} className="card space-y-2">
            <div className="font-medium">{role}</div>
            <div className="grid grid-cols-3 gap-2">
              <select className="input" value={p.kind ?? "mock"} onChange={(e) => set(role, "kind", e.target.value)}>
                <option value="mock">mock</option>
                <option value="openai_compatible">openai_compatible</option>
                <option value="dify">dify</option>
              </select>
              <input className="input" placeholder="base_url" value={p.base_url ?? ""} onChange={(e) => set(role, "base_url", e.target.value)} />
              <input className="input" placeholder="model" value={p.model ?? ""} onChange={(e) => set(role, "model", e.target.value)} />
            </div>
            <div className="flex gap-2">
              <button className="btn" onClick={() => save(role)}>保存</button>
              <button className="btn bg-panelb" onClick={() => test(role)}>测试连接</button>
            </div>
          </div>
        );
      })}
      <div className="card text-xs text-gray-500">
        密钥仅以引用（credential_ref）存入 SQLite，真实值计划存放于 Windows 凭据管理器
        （secret_store 当前为占位实现，可通过环境变量 RAG_SECRET_&lt;ref&gt; 注入）。默认全部为 mock，
        系统无需 GPU / 云端 Key 即可运行。
      </div>
    </div>
  );
}
