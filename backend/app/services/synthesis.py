"""合成管线：单句合成 + 批量任务（内存 Job + SSE 进度事件）。

- 句子状态落库（pending/synthesizing/done/failed），job 本身不落库；已 done 的句子断点续用。
- 每引擎并发默认 2（config.BATCH_CONCURRENCY）；云端失败不自动重试（防重复计费）。
"""
import asyncio
import json
import uuid
from dataclasses import dataclass, field

from ..config import TASK_AUDIO_DIR, BATCH_CONCURRENCY, DEFAULT_LINE_GAP_MS
from ..providers.base import AudioResult, ProviderError, SynthParams, VoiceRef
from ..providers.registry import get_provider
from ..db import connect
from . import pronunciation
from .voice_assets import resolve_voice_ref

# ---- 单句合成 ----

async def _load_line_task(line_id: str) -> dict | None:
    async with connect() as conn:
        cur = await conn.execute(
            "SELECT l.*, t.voice_id AS task_voice_id, t.mode, t.global_params "
            "FROM lines l JOIN tasks t ON t.id = l.task_id WHERE l.id=?",
            (line_id,),
        )
        row = await cur.fetchone()
    return dict(row) if row else None


async def _load_voice_row(voice_id: str) -> dict | None:
    if not voice_id:
        return None
    async with connect() as conn:
        cur = await conn.execute("SELECT * FROM voices WHERE id=?", (voice_id,))
        row = await cur.fetchone()
    if row is None:
        return None
    d = dict(row)
    for key in ("tags", "aux_refs", "provider_assets"):
        default = "{}" if key == "provider_assets" else "[]"
        d[key] = json.loads(d.get(key) or default)
    return d


async def synthesize_line(line_id: str) -> dict:
    """合成单句：返回 {status, duration_ms?, error?}。"""
    line = await _load_line_task(line_id)
    if line is None:
        raise ProviderError("param", f"句子不存在：{line_id}")
    task_id = line["task_id"]
    gparams: dict = json.loads(line["global_params"] or "{}")
    provider_id = gparams.get("provider_id") or "edge"
    provider = get_provider(provider_id)
    if provider is None:
        raise ProviderError("param", f"引擎不存在：{provider_id}")
    if not await provider.is_configured():
        raise ProviderError("not_configured", f"{provider.meta.name} 尚未配置，请前往设置页")

    voice_id = line["voice_override_id"] or line["task_voice_id"]
    if line["mode"] == "dialogue" and line["role_id"]:
        async with connect() as conn:
            cur = await conn.execute("SELECT voice_id, params FROM roles WHERE id=?", (line["role_id"],))
            role = await cur.fetchone()
        if role and role["voice_id"]:
            voice_id = role["voice_id"]
    voice_row = await _load_voice_row(voice_id)
    if voice_row is None:
        raise ProviderError("param", "该任务/角色尚未绑定有效音色，请到任务设置中选择")
    voice_ref = await resolve_voice_ref(voice_row, provider_id)

    rules = await pronunciation.load_rules(task_id)
    text = pronunciation.apply(line["text"], rules)
    params = SynthParams(
        text=text,
        speed=line["speed"] if line["speed"] is not None else gparams.get("speed", 1.0),
        pitch=line["pitch"],
        volume=line["volume"] if line["volume"] is not None else gparams.get("volume", 1.0),
        emotion=line["emotion"] or gparams.get("emotion") or None,
        instruct=line["instruct"] or None,
    )

    async with connect() as conn:
        await conn.execute("UPDATE lines SET status='synthesizing', error='' WHERE id=?", (line_id,))
    try:
        result: AudioResult = await provider.synthesize(params, voice_ref)
    except ProviderError as exc:
        async with connect() as conn:
            await conn.execute(
                "UPDATE lines SET status='failed', error=? WHERE id=?", (f"[{exc.kind}] {exc.message}", line_id)
            )
        return {"status": "failed", "error": f"[{exc.kind}] {exc.message}"}

    out_dir = TASK_AUDIO_DIR / task_id
    out_dir.mkdir(parents=True, exist_ok=True)
    audio_path = out_dir / f"{line_id}.{result.container}"
    audio_path.write_bytes(result.data)

    from .audio import probe_duration_ms
    duration = await probe_duration_ms(audio_path)

    async with connect() as conn:
        await conn.execute(
            "UPDATE lines SET status='done', audio_path=?, duration_ms=?, error='' WHERE id=?",
            (str(audio_path.relative_to(TASK_AUDIO_DIR)), duration, line_id),
        )
    return {"status": "done", "duration_ms": duration}


# ---- 批量任务 ----

@dataclass
class Job:
    id: str
    task_id: str
    line_ids: list[str]
    cancelled: bool = False
    subscribers: list = field(default_factory=list)
    finished: bool = False
    events: list = field(default_factory=list)  # 历史事件（供迟到的订阅者回放）


class JobManager:
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._semaphore = asyncio.Semaphore(BATCH_CONCURRENCY)

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def create(self, task_id: str, line_ids: list[str]) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], task_id=task_id, line_ids=list(line_ids))
        self._jobs[job.id] = job
        asyncio.get_running_loop().create_task(self._run(job))
        return job

    def _emit(self, job: Job, event: dict) -> None:
        job.events.append(event)
        for q in list(job.subscribers):
            q.put_nowait(event)

    async def _run_one(self, job: Job, line_id: str) -> None:
        if job.cancelled:
            return
        async with self._semaphore:
            if job.cancelled:
                return
            self._emit(job, {"type": "line_start", "line_id": line_id})
            try:
                r = await synthesize_line(line_id)
            except ProviderError as exc:
                r = {"status": "failed", "error": f"[{exc.kind}] {exc.message}"}
            except Exception as exc:  # noqa: BLE001 任何意外都转为失败事件，不让 job 崩掉
                r = {"status": "failed", "error": f"[server] {exc}"}
            if r["status"] == "done":
                self._emit(job, {"type": "line_done", "line_id": line_id, "duration_ms": r.get("duration_ms")})
            else:
                self._emit(job, {"type": "line_failed", "line_id": line_id, "error": r.get("error")})

    async def _run(self, job: Job) -> None:
        self._emit(job, {"type": "job_start", "total": len(job.line_ids)})
        try:
            await asyncio.gather(*(self._run_one(job, lid) for lid in job.line_ids))
        except Exception as exc:  # noqa: BLE001
            self._emit(job, {"type": "line_failed", "line_id": "", "error": f"[server] {exc}"})
        self._emit(job, {"type": "job_done", "cancelled": job.cancelled})
        job.finished = True

    def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job and not job.finished:
            job.cancelled = True
            return True
        return False

    async def subscribe(self, job_id: str):
        """SSE 事件流：先回放历史事件，再实时订阅，直到 job_done。"""
        job = self._jobs.get(job_id)
        if job is None:
            return
        for event in job.events:
            yield event
        if job.finished:
            return
        queue: asyncio.Queue = asyncio.Queue()
        job.subscribers.append(queue)
        try:
            while True:
                event = await queue.get()
                yield event
                if event["type"] in ("job_done",):
                    break
        finally:
            job.subscribers.remove(queue)


manager = JobManager()
