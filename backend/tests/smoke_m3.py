"""里程碑3 冒烟测试：建任务 → 分句 → 批量合成(SSE) → 合并 → 导出。

运行：python -m tests.smoke_m3   （需后端已启动且 edge 引擎可用）
"""
import asyncio
import json
import time

import httpx

B = "http://127.0.0.1:8000"


async def main() -> None:
    async with httpx.AsyncClient(timeout=180) as c:
        # 1. 准备音色（Edge 内置）
        voices = (await c.get(f"{B}/api/voices")).json()["voices"]
        voice = next((v for v in voices if v["provider_assets"].get("edge")), None)
        if voice is None:
            r = await c.post(f"{B}/api/voices", data={
                "name": "晓晓（Edge内置）", "gender": "女",
                "provider_id": "edge", "builtin_voice_name": "zh-CN-XiaoxiaoNeural",
            })
            voice = r.json()
        print("voice:", voice["id"], voice["name"])

        # 2. 创建任务（粘贴多句文本）
        text = (
            "各位来宾，大家好！欢迎来到年度技术盛会。\n\n"
            "今天的议程非常丰富，我们将一起见证三个重要时刻。首先，有请创始人致辞；"
            "随后是产品发布环节。最后，还有精彩的圆桌讨论等着大家。\n\n"
            "现在，让我们用热烈的掌声，正式开始今天的活动！"
        )
        r = await c.post(f"{B}/api/tasks", data={
            "title": "冒烟测试-年会主持", "mode": "script",
            "voice_id": voice["id"], "provider_id": "edge", "text": text,
        })
        assert r.status_code == 200, r.text
        data = r.json()
        task_id = data["task"]["id"]
        print("task:", task_id, "| 分句数:", len(data["lines"]))

        # 3. 启动批量合成并消费 SSE
        r = await c.post(f"{B}/api/jobs/synthesize", json={"task_id": task_id})
        print("synthesize:", r.json())
        job_id = r.json()["job_id"]
        done = failed = 0
        start = time.time()
        async with c.stream("GET", f"{B}/api/jobs/{job_id}/events") as resp:
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                ev = json.loads(line[6:])
                if ev["type"] == "line_done":
                    done += 1
                    print(f"  line_done {done} ({ev.get('duration_ms')}ms)")
                elif ev["type"] == "line_failed":
                    failed += 1
                    print("  line_failed:", ev.get("error"))
                elif ev["type"] == "job_done":
                    print(f"job_done: done={done} failed={failed} elapsed={time.time()-start:.1f}s")
                    break
        assert failed == 0, "存在失败句子"

        # 4. 合并 mp3
        r = await c.post(f"{B}/api/tasks/{task_id}/merge", json={"format": "mp3"})
        assert r.status_code == 200, r.text
        print("merge mp3:", r.headers.get("content-length"), "bytes")

        # 5. SRT 与 ZIP
        r = await c.get(f"{B}/api/tasks/{task_id}/export", params={"format": "srt"})
        print("srt preview:", r.text.splitlines()[1])
        r = await c.post(f"{B}/api/tasks/{task_id}/merge", json={"format": "mp3"})
        assert r.status_code == 200
        zip_url = f"{B}/api/tasks/{task_id}/export"
        r = await c.get(zip_url)
        assert r.status_code == 200 and len(r.content) > 10000, "zip 过小"
        print("zip:", len(r.content), "bytes")

        print("\nM3 冒烟测试全部通过 ✓  (task_id =", task_id, ")")


if __name__ == "__main__":
    asyncio.run(main())
