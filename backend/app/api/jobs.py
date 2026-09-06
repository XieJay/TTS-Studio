"""合成任务：批量合成（SSE 进度）、单句合成、取消。"""
import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..services.synthesis import manager, synthesize_line

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("/synthesize")
async def start_synthesis(body: dict):
    """启动批量合成：{task_id, line_ids?}；缺省=全部未完成句子。"""
    task_id = body.get("task_id")
    if not task_id:
        raise HTTPException(400, "缺少 task_id")
    line_ids = body.get("line_ids")
    if not line_ids:
        from ..db import connect
        async with connect() as conn:
            cur = await conn.execute(
                "SELECT id FROM lines WHERE task_id=? AND status!='done' ORDER BY idx", (task_id,)
            )
            line_ids = [r["id"] for r in await cur.fetchall()]
    if not line_ids:
        return {"job_id": None, "message": "所有句子都已合成"}
    job = manager.create(task_id, line_ids)
    return {"job_id": job.id, "total": len(line_ids)}


@router.post("/resynthesize")
async def start_resynthesis(body: dict):
    """强制重做：把句子重置为 pending 再合成。"""
    task_id = body.get("task_id")
    line_ids = body.get("line_ids") or []
    from ..db import connect
    async with connect() as conn:
        for lid in line_ids:
            await conn.execute(
                "UPDATE lines SET status='pending' WHERE id=? AND task_id=?", (lid, task_id)
            )
    if not line_ids:
        raise HTTPException(400, "缺少 line_ids")
    job = manager.create(task_id, line_ids)
    return {"job_id": job.id, "total": len(line_ids)}


@router.get("/{job_id}/events")
async def job_events(job_id: str):
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(404, "任务不存在或已结束")

    async def stream():
        try:
            async for event in manager.subscribe(job_id):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except asyncio.CancelledError:
            return

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str):
    return {"ok": manager.cancel(job_id)}


@router.post("/lines/{line_id}/synthesize")
async def synth_single(line_id: str):
    """单句同步合成（试听/重试）。"""
    try:
        result = await synthesize_line(line_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, str(exc)) from exc
    if result["status"] != "done":
        raise HTTPException(502, result.get("error", "合成失败"))
    return result
