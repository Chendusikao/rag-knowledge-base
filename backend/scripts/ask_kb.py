# -*- coding: utf-8 -*-
"""
中文问答小工具：直接用浏览器之外的命令行，向你的本地知识库提问。

能做什么：
  1. 列出你所有的知识库（中文名 + 编号）
  2. 你选一个知识库，输入一个问题（中文）
  3. 脚本把问题发给后端，打印「检索到的真实内容片段」以及
     它来自「第几页 / 哪个章节 / 文字还是表格」

好处：不用看 Swagger 的英文，也不用配大模型。
     只要后端在跑（http://127.0.0.1:8000），就能用。

用法（在 PowerShell 里）：
  E:/xaizai/wendaxitog/backend/.venv/Scripts/python.exe E:/xaizai/wendaxitog/backend/scripts/ask_kb.py
"""
from __future__ import annotations

import json
import sys
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8000"
API = f"{BASE}/api/v1"


def _http(method: str, path: str, payload: dict | None = None) -> dict:
    url = API + path
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"接口返回错误 {e.code}：{body[:300]}")
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"连不上后端（{BASE}）。请确认后端已启动：\n"
            f"  cd E:\\xaizai\\wendaxitog\\backend\n"
            f"  .\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
        )


def list_kbs() -> list[dict]:
    data = _http("GET", "/knowledge-bases")
    # 返回结构可能是 list，也可能包了一层；做个兼容
    if isinstance(data, dict):
        for k in ("items", "data", "knowledge_bases", "results"):
            if isinstance(data.get(k), list):
                return data[k]
        # 只剩单对象时当成单个
        return [data]
    return data


def ask(kb_id: str, question: str, top_k: int = 5) -> dict:
    return _http(
        "POST",
        "/retrieval/inspect",
        {"kb_id": kb_id, "query": question, "mode": "balanced"},
    )


def main() -> None:
    print("=" * 60)
    print("  本地知识库 · 中文问答工具")
    print("=" * 60)

    # 1) 列出知识库
    try:
        kbs = list_kbs()
    except RuntimeError as e:
        print(f"\n[错误] {e}")
        sys.exit(1)

    if not kbs:
        print("\n没有找到任何知识库。请先在前端或接口上传文档。")
        sys.exit(0)

    print("\n你有以下知识库：")
    for i, kb in enumerate(kbs, 1):
        name = kb.get("name") or kb.get("id") or "(未命名)"
        kid = kb.get("id")
        print(f"  [{i}] {name}   (id={kid})")

    # 2) 选择知识库
    while True:
        choice = input("\n请输入要提问的知识库编号：").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(kbs):
            kb = kbs[int(choice) - 1]
            kb_id = kb.get("id")
            kb_name = kb.get("name") or kb_id
            break
        print("  输入无效，请重新输入编号。")

    # 3) 输入问题（可连续问）
    print(f"\n已选择知识库：{kb_name}")
    print("直接输入问题即可（输入 q 退出）。\n")
    while True:
        question = input("你的问题> ").strip()
        if question.lower() in ("q", "quit", "exit", "退出"):
            print("再见。")
            break
        if not question:
            continue
        try:
            resp = ask(kb_id, question)
        except RuntimeError as e:
            print(f"[错误] {e}\n")
            continue

        results = resp.get("results") or []
        if not results:
            print("  （没检索到相关内容。换个问法，或确认该文档已索引。）\n")
            continue

        print(f"\n  检索到 {len(results)} 段相关内容：")
        for rank, r in enumerate(results[:5], 1):
            page = r.get("page_number") or 0
            sec = r.get("section_path") or []
            sec_txt = " / ".join(str(s) for s in sec) if sec else "（无章节）"
            modality = r.get("modality") or "text"
            modality_cn = {"text": "文字", "table": "表格", "image": "图片"}.get(modality, modality)
            snippet = (r.get("snippet") or "").replace("\n", " ").strip()
            if len(snippet) > 200:
                snippet = snippet[:200] + "…"
            print(f"\n  —— 第 {rank} 段 ——")
            print(f"  文档：{r.get('doc_name') or '(未知)'}")
            print(f"  位置：第 {page} 页 | 章节：{sec_txt} | 类型：{modality_cn}")
            print(f"  内容：{snippet}")
        print()


if __name__ == "__main__":
    main()
