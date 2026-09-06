"""LLM 客户端：OpenAI 兼容 /chat/completions。

- 语境分析：逐句输出情绪/语速/停顿建议（temperature 0.3）
- 剧本改编：小说/文章 → 多角色对话剧本（temperature 0.8）
- JSON 输出校验，失败带错误信息重试一次
"""
import json

import httpx
from pydantic import BaseModel, Field, ValidationError

from ..db import get_setting

ANALYZE_SYSTEM = """你是资深配音导演。用户会给出一篇稿件的分句列表。
请逐句分析语境，为每句给出配音建议：
- emotion：情绪标签，从【平静、庄重、开心、悲伤、愤怒、惊讶、恐惧】中选最合适的一个
- speed：语速倍率，0.8~1.3（紧张/激动略快，庄重/深沉略慢，一般 1.0）
- gap_after_ms：该句之后的停顿毫秒数（0~2000；段落末尾/转折处更长，一般 300）
只输出 JSON：{"lines": [{"idx": 句子序号从1开始, "emotion": "...", "speed": 1.0, "gap_after_ms": 300}]}"""

ADAPT_SYSTEM = """你是资深编剧。把用户提供的小说/文章改写为适合配音的多角色对话剧本：
- 提取 2~6 个角色（含旁白），cast 里给出 name/gender(男|女)/style（一句风格描述）
- lines 里每句 {"role": "角色名或旁白", "text": "台词"}，台词口语化、每句不超过 60 字
- 旁白负责叙述衔接
只输出 JSON：{"title": "剧本标题", "cast": [{"name": "...", "gender": "女", "style": "..."}], "lines": [{"role": "旁白", "text": "..."}]}"""


class AnalyzeResult(BaseModel):
    lines: list[dict] = Field(default_factory=list)


class AdaptResult(BaseModel):
    title: str = "改编剧本"
    cast: list[dict] = Field(default_factory=list)
    lines: list[dict] = Field(default_factory=list)


async def _chat(system: str, user: str, temperature: float) -> str:
    cfg = await get_setting("llm", {}) or {}
    base = (cfg.get("base_url") or "").rstrip("/")
    if not base:
        raise RuntimeError("LLM 尚未配置，请到设置页配置 OpenAI 兼容接口")
    model = (cfg.get("model") or "").strip()
    if not model:
        raise RuntimeError("LLM 尚未配置模型名")
    headers = {"Content-Type": "application/json"}
    if (cfg.get("api_key") or "").strip():
        headers["Authorization"] = f"Bearer {cfg['api_key'].strip()}"
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": temperature,
    }
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(f"{base}/chat/completions", headers=headers, json=body)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"LLM 连接失败：{exc.__class__.__name__}") from exc
    if resp.status_code >= 400:
        raise RuntimeError(f"LLM HTTP {resp.status_code}：{resp.text[:200]}")
    content = resp.json()["choices"][0]["message"]["content"]
    return _strip_fences(content)


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    return t.strip()


def _parse_json(content: str, schema: type[BaseModel]) -> BaseModel:
    data = json.loads(content)
    return schema.model_validate(data)


async def _chat_json(system: str, user: str, temperature: float, schema: type[BaseModel]) -> BaseModel:
    last_error = ""
    for attempt in range(2):
        content = await _chat(system, user if attempt == 0 else user + f"\n\n注意：上一次输出不是合法 JSON（{last_error}），请只输出 JSON。", temperature)
        try:
            return _parse_json(content, schema)
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = str(exc)[:120]
    raise RuntimeError(f"LLM 两次输出均无法解析为 JSON：{last_error}")


async def analyze_lines(lines: list[dict]) -> list[dict]:
    """lines: [{id, idx(1-based), text}] → 返回 [{id, emotion, speed, gap_after_ms}]"""
    user = "\n".join(f"{i + 1}. {l['text']}" for i, l in enumerate(lines))
    result = await _chat_json(ANALYZE_SYSTEM, f"共 {len(lines)} 句：\n{user}", 0.3, AnalyzeResult)
    by_idx = {int(item.get("idx", 0)): item for item in result.lines}
    out = []
    for i, l in enumerate(lines, 1):
        s = by_idx.get(i, {})
        speed = s.get("speed", 1.0)
        gap = s.get("gap_after_ms", 300)
        out.append({
            "id": l["id"],
            "emotion": str(s.get("emotion") or "平静")[:8],
            "speed": max(0.5, min(2.0, float(speed) if speed else 1.0)),
            "gap_after_ms": max(0, min(2000, int(gap) if gap is not None else 300)),
        })
    return out


async def adapt_script(text: str, max_roles: int = 4) -> dict:
    if len(text) > 8000:
        raise RuntimeError("文本超过 8000 字，请分段改编")
    user = f"（角色数不超过 {max_roles} 个，含旁白）\n\n{text}"
    result = await _chat_json(ADAPT_SYSTEM, user, 0.8, AdaptResult)
    return result.model_dump()


async def test_connection() -> tuple[bool, str]:
    try:
        reply = await _chat("你是一个回声机。用户说什么你就只回复两个字：正常。", "测试", 0.0)
        return True, f"连接正常（回复：{reply[:20]}）"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:200]
