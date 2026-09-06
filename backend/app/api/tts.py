"""快速合成（试炼场预览）。"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from ..providers.base import ProviderError, SynthParams, VoiceRef
from ..providers.registry import get_provider

router = APIRouter(prefix="/api/tts", tags=["tts"])


class PreviewRequest(SynthParams):
    provider_id: str
    voice: VoiceRef = VoiceRef()


@router.post("/preview")
async def preview(req: PreviewRequest):
    provider = get_provider(req.provider_id)
    if not provider:
        raise HTTPException(404, f"引擎不存在：{req.provider_id}")
    if not req.text.strip():
        raise HTTPException(400, "文本不能为空")
    if not await provider.is_configured():
        raise HTTPException(400, f"{provider.meta.name} 尚未配置，请前往设置页")
    voice = req.voice
    if voice.kind == "builtin" and not voice.voice_name:
        voice.voice_name = (await provider.get_config()).get("default_voice") or None
    params = SynthParams(
        text=req.text, speed=req.speed, pitch=req.pitch, volume=req.volume,
        emotion=req.emotion, instruct=req.instruct, language=req.language, extra=req.extra,
    )
    try:
        result = await provider.synthesize(params, voice)
    except ProviderError as exc:
        status = {"not_configured": 400, "param": 400, "network": 502,
                  "auth": 502, "quota": 502, "content": 400}.get(exc.kind, 500)
        raise HTTPException(status, f"[{exc.kind}] {exc.message}") from exc
    media = "audio/mpeg" if result.container == "mp3" else "audio/wav"
    return Response(
        content=result.data,
        media_type=media,
        headers={"X-Audio-Format": result.container, "X-Synth-Ms": str(result.duration_ms or 0)},
    )
