# -*- coding: utf-8 -*-
"""
中文流式聊天小工具：像聊天一样，向你的本地知识库连续提问，答案逐字「流式」打印。

和 ask_kb.py（只返回检索片段）不同，这个工具会调用后端的 /chat/stream 接口，
由大模型基于知识库内容「生成」一段中文回答，并逐字打印出来，体验就像 ChatGPT。

能做什么：
  1. 列出你所有的知识库（中文名 + 编号）
  2. 选一个知识库
  3. 连续提问，答案逐字流式输出，并显示「参考来源」（文档/页码/章节）

重要前提：
  /chat/stream 需要后端配了一个「真实大模型」才能给出真回答。
  当前 backend/.env 里 RAG_DEFAULT_LLM_PROVIDER 默认是 mock（没配 key），
  那种情况下回答是「示例/假内容」。要得到真回答，请在 backend/.env 里：
      RAG_DEEPSEEK_API_KEY=sk-你的key
      RAG_DEFAULT_LLM_PROVIDER=deepseek
  本脚本会自动检测是否仍是 mock，若是会打印醒目提示。

用法（PowerShell）：
  E:/xaizai/wendaxitog/backend/.venv/Scripts/python.exe E:/xaizai/wendaxitog/backend/scripts/chat_kb.py
"""
from __future__ import annotations

import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

BASE = "http://127.0.0.1:8000"
API = f"{BASE}/api/v1"

# 知识库列表 / 聊天接口都与后端约定好的路径
KB_LIST_PATH = "/knowledge-bases"
CHAT_PATH = "/chat/stream"


def _http_json(method: str, path: str, payload: dict | None = None) -> dict:
    """普通的 JSON 请求（用于列知识库）。"""
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
    data = _http_json("GET", KB_LIST_PATH)
    if isinstance(data, dict):
        for k in ("items", "data", "knowledge_bases", "results"):
            if isinstance(data.get(k), list):
                return data[k]
        return [data]
    return data


def _detect_mock() -> tuple[bool, str]:
    """读取 backend/.env，判断是否仍是 mock 大模型。返回 (is_mock, 原因)。"""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    provider = "mock"
    key = ""
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip()
            if k == "RAG_DEFAULT_LLM_PROVIDER":
                provider = v
            elif k == "RAG_DEEPSEEK_API_KEY":
                key = v
    except FileNotFoundError:
        return True, "找不到 backend/.env，按 mock 处理"
    if provider in ("", "mock"):
        return True, "RAG_DEFAULT_LLM_PROVIDER 未设置或为 mock（默认）"
    if provider == "deepseek" and not key:
        return True, "RAG_DEFAULT_LLM_PROVIDER=deepseek 但 RAG_DEEPSEEK_API_KEY 为空"
    return False, ""


def stream_chat(kb_id: str, query: str, session_id: str | None, mode: str = "balanced"):
    """
    向 /chat/stream 发请求，逐行解析 SSE，yield 每个事件字典。
    SSE 格式：每行 `data: <json>\n\n`
    """
    url = API + CHAT_PATH
    payload = {"kb_id": kb_id, "query": query, "mode": mode, "backend": "local"}
    if session_id:
        payload["session_id"] = session_id
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            for raw in resp:  # 逐行流式读取
                line = raw.decode("utf-8", "replace")
                if not line.startswith("data:"):
                    continue
                payload_str = line[len("data:"):].strip()
                if not payload_str:
                    continue
                try:
                    yield json.loads(payload_str)
                except json.JSONDecodeError:
                    continue
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        yield {"phase": "error", "error": f"接口错误 {e.code}：{body[:300]}"}
    except urllib.error.URLError as e:
        yield {"phase": "error", "error": f"连不上后端：{e}。请确认后端已启动。"}


def _fmt_citation(c: dict) -> str:
    doc = c.get("doc_name") or c.get("source") or "(未知文档)"
    page = c.get("page_number") or c.get("page") or 0
    sec = c.get("section_path") or []
    sec_txt = " / ".join(str(s) for s in sec) if sec else "（无章节）"
    return f"  · {doc} ｜ 第 {page} 页 ｜ {sec_txt}"


def main() -> None:
    print("=" * 60)
    print("  本地知识库 · 中文流式聊天")
    print("=" * 60)

    # 0) 检测是否仍是 mock 大模型
    is_mock, reason = _detect_mock()
    if is_mock:
        print("\n⚠️ 警告：后端当前使用的是「示例模型(mock)」，回答可能是假内容！")
        print(f"   原因：{reason}")
        print("   要获得真实回答，请在 backend/.env 里填写：")
        print("     RAG_DEEPSEEK_API_KEY=sk-你的key")
        print("     RAG_DEFAULT_LLM_PROVIDER=deepseek")
        print("   然后重启后端即可。现在依然可以体验流式聊天界面（答案是示例）。\n")

    # 1) 列出知识库
    try:
        kbs = list_kbs()
    except RuntimeError as e:
        print(f"\n[错误] {e}")
        sys.exit(1)

    if not kbs:
        print("\n没有找到任何知识库。请先在前端或接口上传文档。")
        sys.exit(0)

    print("你有以下知识库：")
    for i, kb in enumerate(kbs, 1):
        name = kb.get("name") or kb.get("id") or "(未命名)"
        kid = kb.get("id")
        print(f"  [{i}] {name}   (id={kid})")

    # 2) 选择知识库
    while True:
        choice = input("\n请输入要聊天的知识库编号：").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(kbs):
            kb = kbs[int(choice) - 1]
            kb_id = kb.get("id")
            kb_name = kb.get("name") or kb_id
            break
        print("  输入无效，请重新输入编号。")

    print(f"\n已选择知识库：{kb_name}")
    print("直接输入问题即可（输入 q 退出）。支持连续多轮对话。\n")

    session_id = None  # 多轮对话的会话 ID，首轮后由后端返回
    while True:
        question = input("你> ").strip()
        if question.lower() in ("q", "quit", "exit", "退出"):
            print("再见。")
            break
        if not question:
            continue

        print("💭 ", end="", flush=True)
        generated = False
        citations = None
        confidence = None
        insufficient = None
        errored = None
        seen = 0

        for ev in stream_chat(kb_id, question, session_id):
            seen += 1
            phase = ev.get("phase")
            if phase == "retrieve":
                print("🔍 检索中…", end="", flush=True)
            elif phase == "rerank":
                print("📊 排序中…", end="", flush=True)
            elif phase == "generate":
                token = ev.get("token") or ""
                if token:
                    if not generated:
                        # 清掉前面的状态提示，开始输出正文
                        print("\r" + " " * 20 + "\r", end="", flush=True)
                        generated = True
                    sys.stdout.write(token)
                    sys.stdout.flush()
                if ev.get("session_id"):
                    session_id = ev["session_id"]
            elif phase == "citation":
                citations = ev.get("citations")
            elif phase == "done":
                confidence = ev.get("confidence")
                insufficient = ev.get("insufficient_evidence")
                if ev.get("session_id"):
                    session_id = ev["session_id"]
            elif phase == "error":
                errored = ev.get("error")

        if errored:
            print(f"\n[错误] {errored}\n")
            continue

        if seen == 0:
            # 后端连一个事件都没返回：通常是后端没带正确的环境变量启动，
            # 或进程已崩溃（中文 Windows 上 torch 嵌入会因 GBK 报错）。
            print("\r" + " " * 20 + "\r", end="", flush=True)
            print("\n[提示] 后端没有返回任何内容。最常见原因：后端启动方式不对。")
            print("   请在本机用正确的环境变量重启后端（会自动释放 8000 端口）：")
            print("     cd E:\\xaizai\\wendaxitog\\backend")
            print("     .\\scripts\\start_backend.ps1")
            print("   重启后重跑本脚本即可。若仍无内容，请查看 backend/backend.log。\n")
            continue

        print()  # 正文结束换行

        if insufficient:
            print("（注：知识库中未找到充分依据，以下为模型基于已有内容作答）")

        if citations:
            print("\n📚 参考来源：")
            for c in citations:
                print(_fmt_citation(c))

        if confidence is not None:
            print(f"\n  置信度：{confidence:.2f}")

        print()


if __name__ == "__main__":
    main()
