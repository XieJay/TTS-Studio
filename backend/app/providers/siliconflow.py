"""硅基流动 SiliconFlow：语音走 OpenAI 兼容协议（继承通用适配器），补充声音克隆接口。

克隆：POST /v1/uploads/audio/voice（multipart）→ 返回 voice_uri（speech:xxx）。
配置：api_key、model（默认 FunAudioLLM/CosyVoice2-0.5B）
"""
import httpx

from ..config import DEFAULT_SYNTH_TIMEOUT
from .base import AudioResult, BuiltinVoice, Capabilities, ProviderError, ProviderMeta, SynthParams, VoiceRef
from .openai_compat import OpenAICompatProvider

# 内置音色（挂在各模型下，请求时拼成 {model}:{name}）
_BUILTIN_VOICES = [
    "alex", "benjamin", "charles", "david", "dennis",
    "anna", "bella", "claire", "diana", "jenny",
]


class SiliconFlowProvider(OpenAICompatProvider):
    meta = ProviderMeta(
        id="siliconflow",
        name="硅基流动 SiliconFlow",
        type="cloud",
        description="国内聚合平台，托管 CosyVoice2 / Fish Speech；注册送额度，按量计费，支持即时克隆",
        needs_config=True,
    )
    caps = Capabilities(clone=True, builtin_voices=True)

    async def is_configured(self) -> bool:
        cfg = await self.get_config()
        return bool((cfg.get("api_key") or "").strip())

    async def get_config(self) -> dict:
        cfg = await super().get_config()
        cfg.setdefault("base_url", "https://api.siliconflow.cn/v1")
        cfg.setdefault("model", "FunAudioLLM/CosyVoice2-0.5B")
        return cfg

    async def _do_synthesize(self, params: SynthParams, voice: VoiceRef) -> AudioResult:
        cfg = await self.get_config()
        if voice.kind == "builtin" and voice.voice_name:
            # 内置音色需要 {model}:{name} 形式
            voice = voice.model_copy(update={"voice_name": f"{cfg['model']}:{voice.voice_name}"})
        return await super()._do_synthesize(params, voice)

    async def clone(self, audio: bytes, name: str, transcript: str | None) -> str:
        cfg = await self.get_config()
        api_key = (cfg.get("api_key") or "").strip()
        if not api_key:
            raise ProviderError("not_configured", "请先在设置中配置 SiliconFlow api_key")
        base = (cfg.get("base_url") or "https://api.siliconflow.cn/v1").rstrip("/")
        data = {
            "model": "FunAudioLLM/CosyVoice2-0.5B",
            "customName": name,
        }
        if transcript:
            data["text"] = transcript
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{base}/uploads/audio/voice",
                    headers={"Authorization": f"Bearer {api_key}"},
                    data=data,
                    files={"audio": (f"{name}.wav", audio)},
                )
        except httpx.HTTPError as exc:
            raise ProviderError("network", f"克隆请求失败：{exc.__class__.__name__}") from exc
        if resp.status_code >= 400:
            kind = {401: "auth", 403: "auth", 429: "quota"}.get(resp.status_code, "server")
            raise ProviderError(kind, f"克隆失败 HTTP {resp.status_code}：{resp.text[:200]}")
        voice_uri = resp.json().get("voice_uri")
        if not voice_uri:
            raise ProviderError("server", "克隆响应缺少 voice_uri")
        return voice_uri

    async def list_voices(self) -> list[BuiltinVoice]:
        return [BuiltinVoice(name=v, display_name=v, language="zh/en") for v in _BUILTIN_VOICES]
