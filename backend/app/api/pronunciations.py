"""发音词典：全局 / 任务级替换规则 CRUD。"""
import uuid

from fastapi import APIRouter, HTTPException

from .. import db

router = APIRouter(prefix="/api/pronunciations", tags=["pronunciations"])


@router.get("")
async def list_rules(task_id: str | None = None):
    async with db.connect() as conn:
        cur = await conn.execute("SELECT id, find, replace FROM pronunciations WHERE scope='global' ORDER BY rowid")
        global_rules = [dict(r) for r in await cur.fetchall()]
        task_rules: list[dict] = []
        if task_id:
            cur = await conn.execute(
                "SELECT id, find, replace FROM pronunciations WHERE scope='task' AND task_id=? ORDER BY rowid",
                (task_id,),
            )
            task_rules = [dict(r) for r in await cur.fetchall()]
    return {"global": global_rules, "task": task_rules}


@router.post("")
async def add_rule(body: dict):
    scope = body.get("scope", "global")
    if scope not in ("global", "task"):
        raise HTTPException(400, "scope 必须是 global/task")
    find = (body.get("find") or "").strip()
    replace = body.get("replace") or ""
    if not find:
        raise HTTPException(400, "替换前的文本不能为空")
    if scope == "task" and not body.get("task_id"):
        raise HTTPException(400, "任务级规则需要 task_id")
    rule_id = uuid.uuid4().hex[:12]
    async with db.connect() as conn:
        await conn.execute(
            "INSERT INTO pronunciations (id, scope, task_id, find, replace) VALUES (?,?,?,?,?)",
            (rule_id, scope, body.get("task_id") or "", find, replace),
        )
    return {"ok": True, "id": rule_id}


@router.delete("/{rule_id}")
async def delete_rule(rule_id: str):
    async with db.connect() as conn:
        await conn.execute("DELETE FROM pronunciations WHERE id=?", (rule_id,))
    return {"ok": True}
