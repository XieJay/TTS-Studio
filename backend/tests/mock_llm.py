"""模拟 OpenAI 兼容 LLM 服务（仅用于本地验证 LLM 链路）。

根据 system 提示词返回固定结构的 JSON：语境分析 或 剧本改编。
运行：python -m tests.mock_llm  （端口 8901）
"""
import json
import re

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()


def _lines_from_user(user: str) -> int:
    nums = re.findall(r"^(\d+)\. ", user, re.M)
    return len(nums)


@app.post("/v1/chat/completions")
async def chat(request: Request):
    body = await request.json()
    system = body["messages"][0]["content"]
    user = body["messages"][1]["content"]
    if "配音导演" in system:
        n = _lines_from_user(user)
        content = json.dumps({
            "lines": [
                {"idx": i + 1, "emotion": ["庄重", "开心", "惊讶", "平静"][i % 4],
                 "speed": 1.0 + (i % 3) * 0.05, "gap_after_ms": 300 + i * 100}
                for i in range(n)
            ]
        }, ensure_ascii=False)
    elif "编剧" in system:
        content = json.dumps({
            "title": "山谷里的约定",
            "cast": [
                {"name": "旁白", "gender": "女", "style": "温柔叙述"},
                {"name": "林晚", "gender": "女", "style": "倔强少女"},
                {"name": "陈默", "gender": "男", "style": "沉稳青年"},
            ],
            "lines": [
                {"role": "旁白", "text": "山谷的风吹了整整一夜。"},
                {"role": "林晚", "text": "你真的决定要走吗？"},
                {"role": "陈默", "text": "等我回来，这里的杜鹃就开了。"},
                {"role": "旁白", "text": "那是他们最后的对话。"},
            ],
        }, ensure_ascii=False)
    else:
        content = "正常"
    return JSONResponse({"choices": [{"message": {"role": "assistant", "content": content}}]})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8901)
