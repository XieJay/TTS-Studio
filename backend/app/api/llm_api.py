"""LLM 能力：语境分析、剧本改编、连通性测试。"""
from fastapi import APIRouter, HTTPException

from .. import db
from ..services import llm

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.post("/test")
async def test():
    ok, message = await llm.test_connection()
    return {"ok": ok, "message": message}


@router.post("/adapt")
async def adapt(body: dict):
    """小说/文章 → 多角色对话剧本草稿（不入库，前端预览后经任务创建接口入库）。"""
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "文本不能为空")
    max_roles = int(body.get("max_roles") or 4)
    try:
        draft = await llm.adapt_script(text, max_roles)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    return draft


@router.post("/tasks/{task_id}/analyze")
async def analyze_task(task_id: str, body: dict | None = None):
    """对任务句子做语境分析，建议存入 ai_suggestion（不直接生效）。"""
    body = body or {}
    line_ids = body.get("line_ids") or []
    async with db.connect() as conn:
        if line_ids:
            placeholders = ",".join("?" for _ in line_ids)
            cur = await conn.execute(
                f"SELECT id, idx, text FROM lines WHERE task_id=? AND id IN ({placeholders}) ORDER BY idx",
                (task_id, *line_ids),
            )
        else:
            cur = await conn.execute(
                "SELECT id, idx, text FROM lines WHERE task_id=? ORDER BY idx", (task_id,)
            )
        rows = [dict(r) for r in await cur.fetchall()]
    if not rows:
        raise HTTPException(400, "任务没有句子")
    import json as _json

    numbered = [{"id": r["id"], "text": r["text"]} for r in rows]
    try:
        suggestions = await llm.analyze_lines(numbered)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    async with db.connect() as conn:
        for s in suggestions:
            await conn.execute(
                "UPDATE lines SET ai_suggestion=? WHERE id=? AND task_id=?",
                (_json.dumps(
                    {"emotion": s["emotion"], "speed": s["speed"], "gap_after_ms": s["gap_after_ms"]},
                    ensure_ascii=False,
                ), s["id"], task_id),
            )
    return {"suggestions": [
        {"line_id": s["id"], "emotion": s["emotion"], "speed": s["speed"], "gap_after_ms": s["gap_after_ms"]}
        for s in suggestions
    ]}


@router.post("/tasks/{task_id}/apply-analysis")
async def apply_analysis(task_id: str, body: dict):
    """把勾选的分析建议写入句子参数（句子重置为待合成）。"""
    items = body.get("items") or []
    if not items:
        raise HTTPException(400, "没有要应用的建议")
    async with db.connect() as conn:
        for it in items:
            await conn.execute(
                "UPDATE lines SET emotion=?, speed=?, gap_after_ms=?, status='pending' WHERE id=? AND task_id=?",
                (it.get("emotion") or "", it.get("speed"), it.get("gap_after_ms"), it.get("line_id"), task_id),
            )
    return {"ok": True, "applied": len(items)}
