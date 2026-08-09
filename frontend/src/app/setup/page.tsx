"use client";

import { FormEvent, useState } from "react";
import { api } from "@/lib/api";

export default function SetupPage() {
  const [organizationName, setOrganizationName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (password !== confirmPassword) { setError("两次输入的密码不一致"); return; }
    setBusy(true);
    setError("");
    try {
      await api.bootstrap({
        organization_name: organizationName.trim(),
        display_name: displayName.trim(),
        email: email.trim(),
        password,
      });
      window.location.href = "/";
    } catch (reason) {
      setError((reason as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <form className="card w-full max-w-md space-y-4" onSubmit={submit}>
        <div>
          <h1 className="text-xl font-semibold">初始化企业知识库</h1>
          <p className="mt-2 text-sm text-gray-400">创建组织和首位系统管理员。该入口完成后会自动关闭。</p>
        </div>
        <Field label="企业或组织名称" value={organizationName} setValue={setOrganizationName} required />
        <Field label="管理员姓名" value={displayName} setValue={setDisplayName} required />
        <Field label="管理员邮箱" type="email" value={email} setValue={setEmail} required />
        <Field label="管理员密码（至少 12 位）" type="password" value={password} setValue={setPassword} minLength={12} required />
        <Field label="确认密码" type="password" value={confirmPassword} setValue={setConfirmPassword} minLength={12} required />
        {error && <div className="text-sm text-red-400">{error}</div>}
        <button className="btn w-full" disabled={busy}>{busy ? "正在初始化…" : "创建企业管理员"}</button>
      </form>
    </div>
  );
}

function Field({ label, value, setValue, type = "text", ...props }: {
  label: string;
  value: string;
  setValue: (value: string) => void;
  type?: string;
  required?: boolean;
  minLength?: number;
}) {
  return (
    <label className="block space-y-2 text-sm">
      <span>{label}</span>
      <input className="input w-full" type={type} value={value} onChange={(event) => setValue(event.target.value)} {...props} />
    </label>
  );
}
