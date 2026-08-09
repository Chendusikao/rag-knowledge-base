"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, type KnowledgeBase } from "@/lib/api";

type ImportStatus = "queued" | "uploading" | "processing" | "done" | "error";

interface ImportItem {
  id: string;
  filename: string;
  status: ImportStatus;
  progress: number;
  detail: string;
}

type UpdateImportItem = (id: string, patch: Partial<ImportItem>) => void;

const STATUS_LABELS: Record<ImportStatus, string> = {
  queued: "等待上传",
  uploading: "正在上传",
  processing: "正在处理",
  done: "已导入",
  error: "导入失败",
};

export default function DocumentsPage() {
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [kbId, setKbId] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [imports, setImports] = useState<ImportItem[]>([]);
  const [loadMessage, setLoadMessage] = useState("");
  const [loadError, setLoadError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function loadKbs() {
    try {
      const list = await api.listKbs();
      const editableList = list.filter((kb) => kb.access_level === "editor" || kb.access_level === "manager");
      const requestedKbId = new URLSearchParams(window.location.search).get("kb");
      setKbs(editableList);
      setKbId((current) => {
        if (current && editableList.some((kb) => kb.id === current)) return current;
        if (requestedKbId && editableList.some((kb) => kb.id === requestedKbId)) return requestedKbId;
        return editableList[0]?.id || "";
      });
      setLoadError(false);
      setLoadMessage("");
    } catch (e) {
      setLoadError(true);
      setLoadMessage("暂时无法读取知识库：" + (e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void loadKbs(); }, []);

  function selectFiles(selected: FileList | null) {
    const nextFiles = Array.from(selected ?? []);
    setFiles(nextFiles);
    setImports([]);
  }

  function removeFile(index: number) {
    setFiles((current) => current.filter((_, currentIndex) => currentIndex !== index));
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function updateImportItem(id: string, patch: Partial<ImportItem>) {
    setImports((current) => current.map((item) => item.id === id ? { ...item, ...patch } : item));
  }

  async function importFiles() {
    if (!kbId || files.length === 0 || busy) return;

    const selectedFiles = [...files];
    const batch = selectedFiles.map((file, index): ImportItem => ({
      id: `${file.name}-${file.size}-${file.lastModified}-${index}`,
      filename: file.name,
      status: "queued",
      progress: 0,
      detail: "等待上传",
    }));

    setImports(batch);
    setBusy(true);

    const jobs: Array<{ itemId: string; jobId: string; filename: string }> = [];
    for (let index = 0; index < selectedFiles.length; index += 1) {
      const file = selectedFiles[index];
      const item = batch[index];
      updateImportItem(item.id, { status: "uploading", progress: 5, detail: "正在上传文件…" });

      try {
        const result = await api.uploadDoc(kbId, file);
        jobs.push({ itemId: item.id, jobId: result.job_id, filename: file.name });
        updateImportItem(item.id, { status: "processing", progress: 10, detail: "文件已上传，正在处理内容…" });
      } catch (e) {
        updateImportItem(item.id, {
          status: "error",
          progress: 100,
          detail: "上传失败：" + (e as Error).message,
        });
      }
    }

    setFiles([]);
    if (fileInputRef.current) fileInputRef.current.value = "";

    await Promise.all(jobs.map(async ({ itemId, jobId, filename }) => {
      try {
        await followImportJob(jobId, itemId, filename, updateImportItem);
      } catch {
        updateImportItem(itemId, {
          status: "error",
          progress: 100,
          detail: "文件已上传，但暂时无法获取处理进度。",
        });
      }
    }));

    await loadKbs();
    setBusy(false);
  }

  const finishedCount = imports.filter((item) => item.status === "done" || item.status === "error").length;

  return (
    <div className="max-w-3xl space-y-5">
      <header>
        <h1 className="text-2xl font-semibold">导入知识库文件</h1>
        <p className="mt-2 text-sm text-gray-400">
          一次选择一个或多个文件。系统处理完成后，即可围绕这些内容提问。
        </p>
      </header>

      {loading ? (
        <div className="card text-sm text-gray-400">正在读取知识库…</div>
      ) : kbs.length === 0 ? (
        <div className={`card text-sm ${loadError ? "text-red-400" : "text-gray-300"}`}>
          {loadMessage || (
            <>
              当前账号没有可编辑的知识库。请联系知识库管理员授予编辑权限，或前往<Link href="/knowledge-bases" className="mx-1 text-accent hover:underline">部门知识库</Link>查看访问范围。
            </>
          )}
        </div>
      ) : (
        <div className="card space-y-5">
          <label className="block space-y-2">
            <span className="text-sm font-medium">导入到知识库</span>
            <select className="input w-full" value={kbId} onChange={(e) => setKbId(e.target.value)} disabled={busy}>
              {kbs.map((kb) => <option key={kb.id} value={kb.id}>{kb.name}</option>)}
            </select>
          </label>

          <label className="block space-y-2">
            <span className="text-sm font-medium">选择文件</span>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".pdf,.md,.markdown,.png,.jpg,.jpeg"
              disabled={!kbId || busy}
              onChange={(e) => selectFiles(e.target.files)}
              className="block w-full text-sm text-gray-300"
            />
            <span className="block text-xs text-gray-500">支持一次选择多个 PDF、Markdown、PNG 或 JPG 文件。</span>
          </label>

          {files.length > 0 && (
            <div className="space-y-2">
              <div className="text-sm font-medium">已选择 {files.length} 个文件</div>
              {files.map((file, index) => (
                <div key={`${file.name}-${file.size}-${file.lastModified}-${index}`} className="flex items-center justify-between rounded-md bg-panelb px-3 py-2 text-sm">
                  <div className="min-w-0">
                    <div className="truncate">{file.name}</div>
                    <div className="text-xs text-gray-500">{formatBytes(file.size)}</div>
                  </div>
                  <button className="ml-4 text-xs text-red-400" onClick={() => removeFile(index)}>移除</button>
                </div>
              ))}
            </div>
          )}

          <button className="btn" onClick={importFiles} disabled={files.length === 0 || !kbId || busy}>
            {busy ? `正在导入 ${finishedCount}/${imports.length}` : files.length > 0 ? `导入 ${files.length} 个文件` : "选择文件后导入"}
          </button>
        </div>
      )}

      {imports.length > 0 && (
        <div className="card space-y-3">
          <div className="text-sm font-medium">导入进度</div>
          {imports.map((item) => (
            <div key={item.id} className="space-y-1 rounded-md bg-panelb px-3 py-2">
              <div className="flex items-center justify-between gap-4 text-sm">
                <span className="truncate">{item.filename}</span>
                <span className={item.status === "error" ? "text-red-400" : item.status === "done" ? "text-green-400" : "text-accent"}>
                  {STATUS_LABELS[item.status]}
                </span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-edge">
                <div
                  className={`h-full transition-all ${item.status === "error" ? "bg-red-500" : item.status === "done" ? "bg-green-500" : "bg-accent"}`}
                  style={{ width: `${item.progress}%` }}
                />
              </div>
              <div className="text-xs text-gray-500">{item.detail}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

async function followImportJob(
  jobId: string,
  itemId: string,
  filename: string,
  updateItem: UpdateImportItem,
) {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    const job = await api.getJob(jobId);
    if (job.status === "succeeded") {
      updateItem(itemId, { status: "done", progress: 100, detail: `“${filename}”可以用于问答了。` });
      return;
    }
    if (job.status === "failed" || job.status === "canceled") {
      updateItem(itemId, { status: "error", progress: 100, detail: "处理失败，请重新导入这个文件。" });
      return;
    }

    const progress = Math.max(10, Math.min(95, Math.round(job.progress * 100)));
    updateItem(itemId, { status: "processing", progress, detail: `正在处理“${filename}”… ${progress}%` });
    await new Promise((resolve) => window.setTimeout(resolve, 1500));
  }

  updateItem(itemId, { status: "processing", progress: 95, detail: "仍在后台处理，可以稍后回来查看。" });
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
