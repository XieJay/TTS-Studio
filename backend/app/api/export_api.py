"""导出：合并音频、SRT、ZIP。"""
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..db import connect
from ..services import exporter

router = APIRouter(prefix="/api/tasks", tags=["export"])


def _safe_name(title: str) -> str:
    keep = "".join(c for c in title if c.isalnum() or c in "_-（）()· ")
    return keep.strip() or "导出"


@router.post("/{task_id}/merge")
async def merge(task_id: str, body: dict | None = None):
    body = body or {}
    fmt = body.get("format", "mp3")
    if fmt not in ("mp3", "wav"):
        raise HTTPException(400, "format 仅支持 mp3/wav")
    title = _safe_name((await _task_title(task_id)))
    try:
        out = await exporter.merge_task(task_id, fmt)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
    return FileResponse(out, media_type=_media(fmt), filename=f"{title}_合并.{fmt}")


@router.get("/{task_id}/export")
async def export_zip(task_id: str, format: str = "zip"):
    title = _safe_name((await _task_title(task_id)))
    if format == "srt":
        srt = await exporter.build_srt(task_id)
        from fastapi.responses import Response
        return Response(srt, media_type="text/plain; charset=utf-8", headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(f'{title}.srt')}"
        })
    try:
        out = await exporter.export_zip(task_id, title)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
    return FileResponse(out, media_type="application/zip", filename=f"{title}.zip")


@router.post("/{task_id}/remerge")
async def remerge(task_id: str):
    """句子参数变化后重新合并（先清理缓存产物）。"""
    await _task_title(task_id)
    try:
        out = await exporter.merge_task(task_id, "mp3")
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "path": str(out)}


async def _task_title(task_id: str) -> str:
    async with connect() as conn:
        cur = await conn.execute("SELECT title FROM tasks WHERE id=?", (task_id,))
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(404, "任务不存在")
    return row["title"]


def _media(fmt: str) -> str:
    return "audio/mpeg" if fmt == "mp3" else "audio/wav"
