"""发音替换：先应用全局规则，再应用任务级规则（任务级可覆盖全局的同一替换）。

只影响送入引擎的文本，不改动原稿。
"""
from ..db import connect


async def load_rules(task_id: str | None) -> list[tuple[str, str]]:
    """全局规则在前、任务级在后；同一 find 后者覆盖前者（任务级优先）。"""
    ordered: list[tuple[str, str]] = []
    async with connect() as conn:
        cur = await conn.execute("SELECT find, replace FROM pronunciations WHERE scope='global' ORDER BY created_at")
        ordered.extend([(r[0], r[1]) for r in await cur.fetchall()])
        if task_id:
            cur = await conn.execute(
                "SELECT find, replace FROM pronunciations WHERE scope='task' AND task_id=? ORDER BY created_at",
                (task_id,),
            )
            ordered.extend([(r[0], r[1]) for r in await cur.fetchall()])
    deduped = dedupe_rules(ordered)
    return deduped


def dedupe_rules(ordered: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """同一 find 保留最后一条（任务级覆盖全局）。返回元组列表，可直接传给 apply。"""
    deduped: dict[str, str] = {}
    for find, replace in ordered:
        if find:
            deduped[find] = replace
    return list(deduped.items())


def apply(text: str, rules: list[tuple[str, str]]) -> str:
    for find, replace in rules:
        if find:
            text = text.replace(find, replace)
    return text
