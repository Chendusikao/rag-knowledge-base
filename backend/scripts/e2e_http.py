import asyncio
import tempfile
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8011"
MD = "# 测试文档\n\n## 检索\n\nRAG 系统结合 BM25 与稠密向量进行混合检索。\n\n## 引用\n\n回答会附带可点击的引用。\n"


async def main():
    async with httpx.AsyncClient(base_url=BASE, trust_env=True) as c:
        # create KB
        r = await c.post("/api/v1/knowledge-bases", json={"name": "e2e", "description": "x"})
        kb = r.json()
        print("KB:", kb["id"])

        # upload md
        p = Path(tempfile.gettempdir()) / "e2e.md"
        p.write_text(MD, encoding="utf-8")
        r = await c.post(
            f"/api/v1/knowledge-bases/{kb['id']}/documents",
            files={"file": ("e2e.md", p.read_bytes(), "text/markdown")},
        )
        up = r.json()
        print("upload:", up.get("job_id"))
        job_id = up["job_id"]

        # poll job
        for _ in range(20):
            r = await c.get(f"/api/v1/jobs/{job_id}")
            j = r.json()
            if j["status"] in ("succeeded", "failed"):
                print("job status:", j["status"])
                break
            await asyncio.sleep(0.5)

        # retrieval inspect
        r = await c.post("/api/v1/retrieval/inspect", json={
            "kb_id": kb["id"], "query": "混合检索怎么做？", "mode": "balanced",
        })
        data = r.json()
        print("retrieval results:", len(data["results"]), "latency_ms:", data["latency_ms"])

        # chat stream
        printed = []
        async with c.stream("POST", "/api/v1/chat/stream", json={
            "kb_id": kb["id"], "query": "引用是怎么来的？", "mode": "balanced", "backend": "local",
        }) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data:"):
                    printed.append(line[5:].strip()[:60])
        print("chat stream events:", len(printed))
        print("E2E_OK")


asyncio.run(main())
