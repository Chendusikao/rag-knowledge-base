"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";
import { api, type AuthStatus, type EnterpriseUser, type SystemRole } from "@/lib/api";

const PUBLIC_PATHS = new Set(["/login", "/setup"]);
const ROLE_LABELS: Record<SystemRole, string> = {
  admin: "系统管理员",
  department_manager: "部门负责人",
  member: "成员",
  auditor: "审计员",
};

const AuthContext = createContext<EnterpriseUser | null>(null);

export function useCurrentUser() {
  return useContext(AuthContext);
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    api.authStatus()
      .then((next) => { if (active) setStatus(next); })
      .catch((reason) => { if (active) setError((reason as Error).message); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!status) return;
    if (status.setup_required && pathname !== "/setup") router.replace("/setup");
    else if (!status.setup_required && !status.authenticated && pathname !== "/login") router.replace("/login");
    else if (status.user?.must_change_password && pathname !== "/change-password") router.replace("/change-password");
    else if (status.authenticated && PUBLIC_PATHS.has(pathname)) router.replace("/");
  }, [pathname, router, status]);

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center p-6">
        <div className="card max-w-lg text-sm text-red-400">无法连接企业知识库服务：{error}</div>
      </div>
    );
  }
  if (!status) return <LoadingScreen label="正在验证访问权限…" />;

  const publicPage = PUBLIC_PATHS.has(pathname);
  const waitingForRedirect =
    (status.setup_required && pathname !== "/setup")
    || (!status.setup_required && !status.authenticated && pathname !== "/login")
    || Boolean(status.user?.must_change_password && pathname !== "/change-password")
    || Boolean(status.authenticated && publicPage);
  if (waitingForRedirect) return <LoadingScreen label="正在进入正确页面…" />;
  if (publicPage || pathname === "/change-password") {
    return <AuthContext.Provider value={status.user}>{children}</AuthContext.Provider>;
  }

  const user = status.user;
  if (!user) return <LoadingScreen label="正在进入登录页面…" />;

  const navigation = [
    { href: "/", label: "首页", show: true },
    { href: "/knowledge-bases", label: "部门知识库", show: true },
    { href: "/documents", label: "导入文件", show: user.system_role !== "auditor" },
    { href: "/source-library", label: "总资料库", show: user.system_role === "admin" },
    { href: "/chat", label: "知识问答", show: user.system_role !== "auditor" },
    { href: "/departments", label: "部门管理", show: user.system_role !== "member" },
    { href: "/access-control", label: "用户与权限", show: ["admin", "department_manager"].includes(user.system_role) },
    { href: "/audit", label: "审计与安全", show: ["admin", "auditor"].includes(user.system_role) },
  ];

  async function logout() {
    try { await api.logout(); } finally { window.location.href = "/login"; }
  }

  return (
    <AuthContext.Provider value={user}>
      <div className="flex min-h-screen">
        <aside className="flex w-56 shrink-0 flex-col border-r border-edge bg-panel p-3">
          <div className="mb-4 px-2">
            <div className="text-sm font-semibold text-accent">企业知识库</div>
            <div className="mt-1 text-xs text-gray-500">让内部知识可管、可查、可审计</div>
          </div>
          <nav className="flex flex-1 flex-col gap-1 text-sm">
            {navigation.filter((item) => item.show).map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`rounded px-2 py-1.5 hover:bg-panelb ${pathname === item.href ? "bg-panelb text-accent" : ""}`}
              >
                {item.label}
              </Link>
            ))}
          </nav>
          <div className="border-t border-edge px-2 pt-3 text-xs">
            <div className="font-medium text-gray-200">{user.display_name}</div>
            <div className="mt-1 text-gray-500">{ROLE_LABELS[user.system_role]} · {user.department_name || "未分配部门"}</div>
            <button className="mt-3 text-gray-400 hover:text-white" onClick={logout}>退出登录</button>
          </div>
        </aside>
        <main className="flex-1 overflow-auto p-6">{children}</main>
      </div>
    </AuthContext.Provider>
  );
}

function LoadingScreen({ label }: { label: string }) {
  return <div className="flex min-h-screen items-center justify-center text-sm text-gray-400">{label}</div>;
}

export { ROLE_LABELS };
