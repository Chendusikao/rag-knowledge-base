"use client";

import { FormEvent, useState } from "react";
import { api } from "@/lib/api";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const user = await api.login({ email: email.trim(), password });
      window.location.href = user.must_change_password ? "/change-password" : "/";
    } catch (reason) {
      setError((reason as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <form className="card w-full max-w-sm space-y-4" onSubmit={submit}>
        <div>
          <h1 className="text-xl font-semibold">登录企业知识库</h1>
          <p className="mt-2 text-sm text-gray-400">使用企业管理员分配的账号访问内部知识。</p>
        </div>
        <label className="block space-y-2 text-sm">
          <span>企业邮箱</span>
          <input className="input w-full" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
        </label>
        <label className="block space-y-2 text-sm">
          <span>密码</span>
          <input className="input w-full" type="password" value={password} onChange={(event) => setPassword(event.target.value)} required />
        </label>
        {error && <div className="text-sm text-red-400">{error}</div>}
        <button className="btn w-full" disabled={busy}>{busy ? "正在登录…" : "登录"}</button>
      </form>
    </div>
  );
}
