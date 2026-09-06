"""音色库：创建（上传参考音频/内置音色）、编辑、删除、克隆到云端引擎、试听样本。"""
import json
import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from .. import db
from ..config import VOICE_MAX_UPLOAD_MB
from ..providers.base import ProviderError
from ..providers.registry import all_providers, get_provider
from ..services import voice_assets

router = APIRouter(prefix="/api/voices", tags=["voices"])


def _row_to_dict(row) -> dict:
    d = dict(row)
    d["tags"] = json.loads(d.get("tags") or "[]")
    d["aux_refs"] = json.loads(d.get("aux_refs") or "[]")
    d["provider_assets"] = json.loads(d.get("provider_assets") or "{}")
    if d.get("sample_audio_path"):
        d["sample_url"] = f"/audio/voices/{d['sample_audio_path']}"
    return d


async def _load_voice(voice_id: str) -> dict:
    async with db.connect() as conn:
        cur = await conn.execute("SELECT * FROM voices WHERE id=?", (voice_id,))
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(404, f"音色不存在：{voice_id}")
    return _row_to_dict(row)


@router.get("")
async def list_voices():
    async with db.connect() as conn:
        cur = await conn.execute("SELECT * FROM voices ORDER BY created_at DESC")
        rows = await cur.fetchall()
    voices = [_row_to_dict(r) for r in rows]
    # 计算每个音色在各引擎下的可用状态
    states: dict[str, dict[str, str]] = {}
    for v in voices:
        per: dict[str, str] = {}
        for p in all_providers():
            if p.meta.id == "edge":
                per[p.meta.id] = "ready" if v["provider_assets"].get("edge") else "unsupported"
            elif p.meta.id in ("gptsovits", "cosyvoice", "indextts"):
                per[p.meta.id] = "ready" if v["ref_audio_path"] else "unsupported"
            elif p.meta.id in ("siliconflow", "minimax", "elevenlabs", "custom_http"):
                # 克隆需要参考音频；内置音色（无参考音频）无法克隆
                if not v["ref_audio_path"]:
                    per[p.meta.id] = "unsupported"
                elif v["provider_assets"].get(p.meta.id):
                    per[p.meta.id] = "ready"
                else:
                    per[p.meta.id] = "needs_clone"
            else:  # openai_compat 等不支持复刻的引擎
                per[p.meta.id] = "ready" if v["provider_assets"].get(p.meta.id) else "unsupported"
        states[v["id"]] = per
    return {"voices": voices, "provider_states": states}


@router.post("")
async def create_voice(
    name: str = Form(...),
    description: str = Form(""),
    gender: str = Form(""),
    tags: str = Form("[]"),
    prompt_text: str = Form(""),
    prompt_lang: str = Form("zh"),
    ref_audio: UploadFile | None = File(None),
    aux_refs: list[UploadFile] = File(default=[]),
    provider_id: str = Form(""),
    builtin_voice_name: str = Form(""),
):
    content = b""
    if ref_audio is not None:
        content = await ref_audio.read()
        if len(content) > VOICE_MAX_UPLOAD_MB * 1024 * 1024:
            raise HTTPException(400, f"参考音频超过 {VOICE_MAX_UPLOAD_MB}MB 限制")
    voice_id = voice_assets.new_voice_id()
    ref_path = ""
    if content:
        ref_path = voice_assets.save_ref_audio(voice_id, ref_audio.filename or "ref.wav", content)
    aux_paths = []
    for f in (aux_refs or [])[:3]:
        c = await f.read()
        if c and len(c) <= VOICE_MAX_UPLOAD_MB * 1024 * 1024:
            aux_paths.append(voice_assets.save_ref_audio(voice_id, f.filename or "aux.wav", c))
    if content:
        vid, source = voice_id, "uploaded"
        provider_assets: dict = {}
    else:
        if not builtin_voice_name or not provider_id:
            raise HTTPException(400, "内置音色需要指定引擎与音色名")
        vid, source = f"builtin-{uuid.uuid4().hex[:8]}", "builtin"
        provider_assets = {provider_id: {"voice_name": builtin_voice_name}}
    async with db.connect() as conn:
        await conn.execute(
            "INSERT INTO voices (id, name, description, gender, tags, source, ref_audio_path, aux_refs, prompt_text, prompt_lang, provider_assets) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (vid, name, description, gender, tags, source,
             ref_path, json.dumps(aux_paths), prompt_text, prompt_lang, json.dumps(provider_assets)),
        )
        if ref_path:
            # 未指定引擎时，上传的参考音频直接作为初始试听样本；指定了引擎则会被合成样本替换
            await conn.execute("UPDATE voices SET sample_audio_path=? WHERE id=?", (ref_path, vid))
    voice = await _load_voice(vid)

    # 指定引擎时创建即出声：云端克隆引擎用参考音频立即克隆；随后统一合成试听样本（优先播参考文本）
    if provider_id and (content or builtin_voice_name):
        provider = get_provider(provider_id)
        clone_error = sample_error = None
        if provider is None or not await provider.is_configured():
            sample_error = f"引擎 {provider_id or '（未指定）'} 不可用，请到设置页配置"
        else:
            if content and provider_id in ("siliconflow", "minimax", "elevenlabs", "custom_http"):
                try:
                    cloud_id = await provider.clone(content, name, prompt_text or None)
                    assets = voice["provider_assets"]
                    assets.setdefault(provider_id, {})[
                        "voice_id" if provider_id != "siliconflow" else "voice_uri"
                    ] = cloud_id
                    async with db.connect() as conn:
                        await conn.execute("UPDATE voices SET provider_assets=? WHERE id=?", (json.dumps(assets, ensure_ascii=False), vid))
                    voice = await _load_voice(vid)
                except ProviderError as exc:
                    clone_error = f"[{exc.kind}] {exc.message}"
            try:
                sample = await voice_assets.generate_sample(vid, provider_id, voice)
                async with db.connect() as conn:
                    await conn.execute("UPDATE voices SET sample_audio_path=? WHERE id=?", (sample, vid))
                voice = await _load_voice(vid)
            except ProviderError as exc:
                sample_error = f"[{exc.kind}] {exc.message}"
        if clone_error:
            voice["clone_error"] = clone_error
        if sample_error:
            voice["sample_error"] = sample_error
    return voice


@router.put("/{voice_id}")
async def update_voice(voice_id: str, patch: dict):
    await _load_voice(voice_id)
    fields, params = [], []
    for key in ("name", "description", "gender", "prompt_text", "prompt_lang"):
        if key in patch:
            fields.append(f"{key}=?")
            params.append(patch[key])
    if "tags" in patch:
        fields.append("tags=?")
        params.append(json.dumps(patch["tags"], ensure_ascii=False))
    if not fields:
        return {"ok": True}
    params.append(voice_id)
    async with db.connect() as conn:
        await conn.execute(f"UPDATE voices SET {', '.join(fields)}, updated_at=datetime('now','localtime') WHERE id=?", params)
    return {"ok": True}


@router.delete("/{voice_id}")
async def delete_voice(voice_id: str):
    await _load_voice(voice_id)
    async with db.connect() as conn:
        await conn.execute("DELETE FROM voices WHERE id=?", (voice_id,))
    voice_assets.delete_voice_files(voice_id)
    return {"ok": True}


@router.post("/{voice_id}/clone/{provider_id}")
async def clone_voice(voice_id: str, provider_id: str):
    voice = await _load_voice(voice_id)
    provider = get_provider(provider_id)
    if provider is None:
        raise HTTPException(404, f"引擎不存在：{provider_id}")
    if not provider.caps.clone:
        raise HTTPException(400, f"{provider.meta.name} 不支持声音复刻")
    if not await provider.is_configured():
        raise HTTPException(400, f"{provider.meta.name} 尚未配置，请先到设置页配置")
    if not voice["ref_audio_path"]:
        raise HTTPException(400, "该音色没有参考音频，无法克隆（内置音色可直接选用）")
    try:
        content = voice_assets.read_ref_audio(voice["ref_audio_path"])
        cloud_id = await provider.clone(content, voice["name"], voice.get("prompt_text") or None)
        assets = voice["provider_assets"]
        assets.setdefault(provider_id, {})["voice_id" if provider_id != "siliconflow" else "voice_uri"] = cloud_id
        async with db.connect() as conn:
            await conn.execute(
                "UPDATE voices SET provider_assets=?, updated_at=datetime('now','localtime') WHERE id=?",
                (json.dumps(assets, ensure_ascii=False), voice_id),
            )
    except ProviderError as exc:
        raise HTTPException(502, f"[{exc.kind}] {exc.message}") from exc
    updated = await _load_voice(voice_id)
    try:
        sample = await voice_assets.generate_sample(voice_id, provider_id, updated)
        async with db.connect() as conn:
            await conn.execute("UPDATE voices SET sample_audio_path=? WHERE id=?", (sample, voice_id))
    except ProviderError as exc:
        # 样本生成失败不阻塞克隆结果，但要把原因带回给前端展示（可手动重试）
        updated = {**updated, "sample_error": f"[{exc.kind}] {exc.message}"}
    return updated


async def _pick_sample_provider(voice: dict) -> str:
    """为试听样本挑引擎：音色已绑定资产的引擎优先，其余已配置且能解析该音色的引擎按注册顺序兜底。"""
    candidates: list[str] = []
    for p in all_providers():
        if not await p.is_configured():
            continue
        try:
            await voice_assets.resolve_voice_ref(voice, p.meta.id)
        except ProviderError:
            continue
        candidates.append(p.meta.id)
    assets = voice.get("provider_assets") or {}
    candidates.sort(key=lambda pid: 0 if assets.get(pid) else 1)
    return candidates[0] if candidates else ""


@router.post("/{voice_id}/sample")
async def make_sample_auto(voice_id: str):
    """自动选引擎生成/重生成试听样本（不指定引擎时前端调用）。"""
    voice = await _load_voice(voice_id)
    provider_id = await _pick_sample_provider(voice)
    if not provider_id:
        raise HTTPException(
            400,
            "没有可用引擎生成试听样本：复刻音色需要先配置支持零样本合成的引擎（如 IndexTTS / GPT-SoVITS），"
            "内置音色需要配置对应引擎",
        )
    try:
        sample = await voice_assets.generate_sample(voice_id, provider_id, voice)
    except ProviderError as exc:
        status = {"param": 400, "not_configured": 400}.get(exc.kind, 502)
        raise HTTPException(status, f"[{exc.kind}] {exc.message}") from exc
    async with db.connect() as conn:
        await conn.execute("UPDATE voices SET sample_audio_path=? WHERE id=?", (sample, voice_id))


@router.post("/{voice_id}/sample/{provider_id}")
async def make_sample(voice_id: str, provider_id: str):
    voice = await _load_voice(voice_id)
    try:
        sample = await voice_assets.generate_sample(voice_id, provider_id, voice)
    except ProviderError as exc:
        status = {"param": 400, "not_configured": 400}.get(exc.kind, 502)
        raise HTTPException(status, f"[{exc.kind}] {exc.message}") from exc
    async with db.connect() as conn:
        await conn.execute("UPDATE voices SET sample_audio_path=? WHERE id=?", (sample, voice_id))
    return await _load_voice(voice_id)
