"""配音任务：创建（粘贴/上传文件）、CRUD、句子增删改排。"""
import json
import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from .. import db
from ..config import DOC_MAX_UPLOAD_MB
from ..services import parser

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _task_dict(row) -> dict:
    d = dict(row)
    d["global_params"] = json.loads(d.get("global_params") or "{}")
    return d


async def _load_task(task_id: str) -> dict:
    async with db.connect() as conn:
        cur = await conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,))
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(404, f"任务不存在：{task_id}")
    return _task_dict(row)


@router.get("")
async def list_tasks():
    async with db.connect() as conn:
        cur = await conn.execute(
            "SELECT t.*, COUNT(l.id) AS line_count, "
            "SUM(CASE WHEN l.status='done' THEN 1 ELSE 0 END) AS done_count "
            "FROM tasks t LEFT JOIN lines l ON l.task_id = t.id "
            "GROUP BY t.id ORDER BY t.updated_at DESC"
        )
        rows = await cur.fetchall()
    return [_task_dict(r) | {"line_count": r["line_count"], "done_count": r["done_count"] or 0} for r in rows]


@router.get("/{task_id}")
async def get_task(task_id: str):
    task = await _load_task(task_id)
    async with db.connect() as conn:
        cur = await conn.execute("SELECT * FROM lines WHERE task_id=? ORDER BY idx", (task_id,))
        lines = [dict(r) for r in await cur.fetchall()]
    async with db.connect() as conn:
        cur = await conn.execute("SELECT * FROM roles WHERE task_id=? ORDER BY rowid", (task_id,))
        roles = [dict(r) for r in await cur.fetchall()]
    return {"task": task, "lines": lines, "roles": roles}


@router.post("/preview-split")
async def preview_split(
    text: str = Form(""),
    mode: str = Form("script"),
    file: UploadFile | None = File(None),
):
    """创建向导第三步：预览分句结果。"""
    if file is not None:
        content = await file.read()
        if len(content) > DOC_MAX_UPLOAD_MB * 1024 * 1024:
            raise HTTPException(400, f"文件超过 {DOC_MAX_UPLOAD_MB}MB 限制")
        paragraphs = parser.parse_document(file.filename or "input.txt", content)
        text = "\n\n".join(paragraphs)
    if not text.strip():
        raise HTTPException(400, "内容为空")
    units = parser.split_for_task(mode, text)
    return {"count": len(units), "units": units, "text": text}


_ROLE_COLORS = ["#6366f1", "#ec4899", "#14b8a6", "#f59e0b", "#8b5cf6", "#ef4444", "#10b981", "#3b82f6"]


@router.post("")
async def create_task(
    title: str = Form(...),
    mode: str = Form("script"),
    voice_id: str = Form(""),
    provider_id: str = Form("edge"),
    text: str = Form(""),
    cast: str = Form("[]"),  # AI 改编时传入角色信息 JSON [{name, gender, style}]
    file: UploadFile | None = File(None),
):
    """创建任务：文件或粘贴文本二选一，服务端分句后入库；多角色模式自动建角色。"""
    if file is not None:
        content = await file.read()
        if len(content) > DOC_MAX_UPLOAD_MB * 1024 * 1024:
            raise HTTPException(400, f"文件超过 {DOC_MAX_UPLOAD_MB}MB 限制")
        paragraphs = parser.parse_document(file.filename or "input.txt", content)
        text = "\n\n".join(paragraphs)
    if not text.strip():
        raise HTTPException(400, "内容为空：请上传文件或粘贴文本")
    units = parser.split_for_task(mode, text)
    task_id = uuid.uuid4().hex[:12]
    global_params = {"provider_id": provider_id, "speed": 1.0, "volume": 1.0}
    cast_info: dict[str, dict] = {}
    try:
        for c in json.loads(cast):
            cast_info[c.get("name", "")] = {"gender": c.get("gender", ""), "style": c.get("style", "")}
    except json.JSONDecodeError:
        pass
    async with db.connect() as conn:
        await conn.execute(
            "INSERT INTO tasks (id, title, mode, voice_id, global_params) VALUES (?,?,?,?,?)",
            (task_id, title, mode, voice_id, json.dumps(global_params)),
        )
        role_ids: dict[str, str] = {}
        if mode == "dialogue":
            seen: list[str] = []
            for u in units:
                role = u.get("role") or "旁白"
                if role not in seen:
                    seen.append(role)
            for i, role in enumerate(seen):
                rid = uuid.uuid4().hex[:12]
                role_ids[role] = rid
                info = cast_info.get(role, {})
                await conn.execute(
                    "INSERT INTO roles (id, task_id, name, color, params) VALUES (?,?,?,?,?)",
                    (rid, task_id, role, _ROLE_COLORS[i % len(_ROLE_COLORS)],
                     json.dumps({"gender": info.get("gender", ""), "style": info.get("style", "")}, ensure_ascii=False)),
                )
        for i, u in enumerate(units):
            await conn.execute(
                "INSERT INTO lines (id, task_id, idx, text, emotion, role_id) VALUES (?,?,?,?,?,?)",
                (uuid.uuid4().hex[:12], task_id, i, u["text"], u.get("emotion", ""),
                 role_ids.get(u.get("role") or "", "")),
            )
    return await get_task(task_id)


@router.put("/{task_id}")
async def update_task(task_id: str, patch: dict):
    task = await _load_task(task_id)
    fields, params = [], []
    reset_lines = False
    for key in ("title", "voice_id"):
        if key in patch:
            if key == "voice_id" and patch[key] != task["voice_id"]:
                reset_lines = True
            fields.append(f"{key}=?")
            params.append(patch[key])
    if "global_params" in patch:
        merged = {**task["global_params"], **patch["global_params"]}
        # 合成引擎变化会使现有音频失效
        if merged.get("provider_id") != task["global_params"].get("provider_id"):
            reset_lines = True
        fields.append("global_params=?")
        params.append(json.dumps(merged, ensure_ascii=False))
    if not fields:
        return {"ok": True}
    params.append(task_id)
    async with db.connect() as conn:
        await conn.execute(f"UPDATE tasks SET {', '.join(fields)}, updated_at=datetime('now','localtime') WHERE id=?", params)
        if reset_lines:
            await conn.execute("UPDATE lines SET status='pending' WHERE task_id=?", (task_id,))
    return {"ok": True}


@router.delete("/{task_id}")
async def delete_task(task_id: str):
    await _load_task(task_id)
    async with db.connect() as conn:
        await conn.execute("DELETE FROM lines WHERE task_id=?", (task_id,))
        await conn.execute("DELETE FROM roles WHERE task_id=?", (task_id,))
        await conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    return {"ok": True}


# ---- 句子操作 ----

@router.post("/{task_id}/lines")
async def add_line(task_id: str, body: dict):
    task = await _load_task(task_id)
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "句子内容不能为空")
    async with db.connect() as conn:
        cur = await conn.execute("SELECT COALESCE(MAX(idx), -1) FROM lines WHERE task_id=?", (task_id,))
        idx = (await cur.fetchone())[0] + 1
        await conn.execute(
            "INSERT INTO lines (id, task_id, idx, text, role_id) VALUES (?,?,?,?,?)",
            (uuid.uuid4().hex[:12], task_id, idx, text, body.get("role_id", "")),
        )
    return await get_task(task_id)


@router.put("/{task_id}/lines/{line_id}")
async def update_line(task_id: str, line_id: str, patch: dict):
    fields, params = [], []
    for key in ("text", "emotion", "instruct", "role_id", "voice_override_id"):
        if key in patch:
            fields.append(f"{key}=?")
            params.append(patch[key])
    for key in ("speed", "pitch", "volume", "gap_after_ms"):
        if key in patch:
            fields.append(f"{key}=?")
            params.append(patch[key])
            # 参数变化后需要重新合成
            fields.append("status='pending'")
    if "reset" in patch and patch["reset"]:
        fields.append("status='pending'")
    if not fields:
        return {"ok": True}
    params.append(line_id)
    async with db.connect() as conn:
        cur = await conn.execute(
            f"UPDATE lines SET {', '.join(fields)}, updated_at=datetime('now','localtime') WHERE id=? AND task_id=?",
            (*params, task_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "句子不存在")
        await conn.execute("UPDATE tasks SET updated_at=datetime('now','localtime') WHERE id=?", (task_id,))
    return {"ok": True}


@router.delete("/{task_id}/lines/{line_id}")
async def delete_line(task_id: str, line_id: str):
    async with db.connect() as conn:
        cur = await conn.execute("SELECT idx FROM lines WHERE id=? AND task_id=?", (line_id, task_id))
        row = await cur.fetchone()
        if row is None:
            raise HTTPException(404, "句子不存在")
        await conn.execute("DELETE FROM lines WHERE id=?", (line_id,))
        # 重排序号
        cur = await conn.execute(
            "SELECT id FROM lines WHERE task_id=? AND idx>? ORDER BY idx", (task_id, row["idx"])
        )
        later = [r["id"] for r in await cur.fetchall()]
        for offset, lid in enumerate(later):
            await conn.execute("UPDATE lines SET idx=? WHERE id=?", (row["idx"] + offset, lid))
    return {"ok": True}


@router.put("/{task_id}/roles/{role_id}")
async def update_role(task_id: str, role_id: str, patch: dict):
    fields, params = [], []
    for key in ("name", "color", "voice_id"):
        if key in patch:
            fields.append(f"{key}=?")
            params.append(patch[key])
    if "params" in patch:
        fields.append("params=?")
        params.append(json.dumps(patch["params"], ensure_ascii=False))
    if not fields:
        return {"ok": True}
    params.extend([role_id, task_id])
    async with db.connect() as conn:
        cur = await conn.execute(
            f"UPDATE roles SET {', '.join(fields)} WHERE id=? AND task_id=?", params
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "角色不存在")
    return {"ok": True}


@router.post("/{task_id}/lines/{line_id}/move")
async def move_line(task_id: str, line_id: str, body: dict):
    direction = body.get("direction")
    if direction not in ("up", "down"):
        raise HTTPException(400, "direction 必须是 up/down")
    async with db.connect() as conn:
        cur = await conn.execute("SELECT id, idx FROM lines WHERE task_id=? ORDER BY idx", (task_id,))
        rows = [dict(r) for r in await cur.fetchall()]
        pos = next((i for i, r in enumerate(rows) if r["id"] == line_id), -1)
        if pos < 0:
            raise HTTPException(404, "句子不存在")
        swap = pos - 1 if direction == "up" else pos + 1
        if 0 <= swap < len(rows):
            await conn.execute("UPDATE lines SET idx=? WHERE id=?", (rows[swap]["idx"], rows[pos]["id"]))
            await conn.execute("UPDATE lines SET idx=? WHERE id=?", (rows[pos]["idx"], rows[swap]["id"]))
    return {"ok": True}
