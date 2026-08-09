"use client";

import { FormEvent, useState } from "react";
import { api } from "@/lib/api";

export default function ChangePasswordPage() {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (newPassword !== confirmPassword) { setError("两次输入的新密码不一致"); return; }
    setBusy(true);
    setError("");
    try {
      await api.changePassword({ current_password: currentPassword, new_password: newPassword });
      window.location.href = "/";
    } catch (reason) {
      setError((reason as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <form className="card w-full max-w-sm space-y-4" onSubmit={submit}>
        <div>
          <h1 className="text-xl font-semibold">设置新密码</h1>
          <p className="mt-2 text-sm text-gray-400">临时密码仅用于首次登录。新密码至少 12 位。</p>
        </div>
        <PasswordField label="当前密码" value={currentPassword} setValue={setCurrentPassword} />
        <PasswordField label="新密码" value={newPassword} setValue={setNewPassword} minLength={12} />
        <PasswordField label="确认新密码" value={confirmPassword} setValue={setConfirmPassword} minLength={12} />
        {error && <div className="text-sm text-red-400">{error}</div>}
        <button className="btn w-full" disabled={busy}>{busy ? "正在保存…" : "保存新密码"}</button>
      </form>
    </div>
  );
}

function PasswordField({ label, value, setValue, minLength }: { label: string; value: string; setValue: (value: string) => void; minLength?: number }) {
  return (
    <label className="block space-y-2 text-sm">
      <span>{label}</span>
      <input className="input w-full" type="password" value={value} onChange={(event) => setValue(event.target.value)} minLength={minLength} required />
    </label>
  );
}
