"""ElevenLabs：TTS + 即时声音克隆。

配置：api_key、model（eleven_multilingual_v2）
端点：POST /v1/text-to-speech/{voice_id}（xi-api-key 头）、POST /v1/voices/add（克隆）、GET /v1/voices
已知怪癖：
- 错误响应为 {"detail": {type, code, message, status}} 结构；免费订阅克隆会返回
  payment_required/can_not_use_instant_voice_cloning —— 统一经 _explain_error 映射为中文提示。
- voice_settings.speed 支持 0.7~1.2，越界由本适配器截断。
"""
import httpx

from ..config import DEFAULT_SYNTH_TIMEOUT
from .base import AudioResult, BuiltinVoice, Capabilities, ProviderError, ProviderMeta, SynthParams, TTSProvider, VoiceRef

_BASE = "https://api.elevenlabs.io"

# detail.status/type/code → (kind, 中文可操作提示)；未命中的错误保留服务端原文便于排查。
# 免费订阅不支持即时克隆是最高频的踩坑点（HTTP 400 + payment_required），必须给明确指引。
_DETAIL_HINTS = {
    "can_not_use_instant_voice_cloning": (
        "quota",
        "当前订阅（免费版）不支持即时声音克隆，需升级付费套餐（Starter 及以上）；"
        "或改用 SiliconFlow / MiniMax 等支持即时克隆的引擎",
    ),
    "paid_plan_required": ("quota", "该功能需要付费订阅（Starter 及以上）才能使用"),
    "payment_required": ("quota", "该功能需要付费订阅（Starter 及以上）才能使用"),
    "voice_limit_exceeded": ("quota", "自定义音色数量已达套餐上限，请删除不需要的音色或升级套餐"),
    "quota_exceeded": ("quota", "额度已用尽，请等待额度刷新或升级套餐"),
    "character_limit_exceeded": ("quota", "字符额度已用尽，请等待额度刷新或升级套餐"),
    "invalid_api_key": ("auth", "api_key 无效"),
    "missing_permissions": ("auth", "api_key 权限不足，请检查密钥对应账号的权限"),
}


def _classify_status(status: int) -> str:
    return {401: "auth", 403: "auth", 422: "param", 429: "quota"}.get(status, "server")


def _explain_error(resp: httpx.Response, action: str) -> ProviderError:
    """把 ElevenLabs 错误响应归一为 ProviderError：结构化 detail 映射为中文提示，否则保留原文。"""
    try:
        detail = resp.json().get("detail")
    except Exception:  # noqa: BLE001 非 JSON 响应
        detail = None
    server_msg = ""
    hint = None
    if isinstance(detail, dict):
        server_msg = str(detail.get("message") or "")
        key = detail.get("status") or detail.get("type") or detail.get("code")
        hint = _DETAIL_HINTS.get(str(key) if key else "")
    elif isinstance(detail, str):
        server_msg = detail
    if hint:
        kind, zh = hint
        return ProviderError(kind, f"ElevenLabs {action}失败：{zh}")
    msg = server_msg or resp.text[:300]
    return ProviderError(_classify_status(resp.status_code), f"ElevenLabs {action}失败 HTTP {resp.status_code}：{msg}")


class ElevenLabsProvider(TTSProvider):
    meta = ProviderMeta(
        id="elevenlabs",
        name="ElevenLabs",
        type="cloud",
        description="国际主流 TTS，克隆效果天花板；按量计费（有免费额度）",
        needs_config=True,
    )
    caps = Capabilities(clone=True, builtin_voices=True)

    async def is_configured(self) -> bool:
        cfg = await self.get_config()
        return bool((cfg.get("api_key") or "").strip())

    async def _do_synthesize(self, params: SynthParams, voice: VoiceRef) -> AudioResult:
        cfg = await self.get_config()
        if not await self.is_configured():
            raise ProviderError("not_configured", "ElevenLabs 尚未配置 api_key")
        voice_id = voice.cloud_voice_id or voice.voice_name or (cfg.get("default_voice_id") or "")
        if not voice_id:
            # 试炼场等场景未指定音色：默认用账号第一个音色（零配置可用；任务管线始终显式绑定音色）
            voices = await self.list_voices()
            if not voices:
                raise ProviderError("param", "ElevenLabs 账号下没有可用音色，请到官网创建后重试")
            voice_id = voices[0].name
        body: dict = {
            "text": params.text,
            "model_id": (cfg.get("model") or "eleven_multilingual_v2").strip(),
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }
        if params.speed and params.speed != 1.0:
            body["voice_settings"]["speed"] = max(0.7, min(1.2, params.speed))
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_SYNTH_TIMEOUT) as client:
                resp = await client.post(
                    f"{_BASE}/v1/text-to-speech/{voice_id}",
                    params={"output_format": "mp3_44100_128"},
                    headers={"xi-api-key": (cfg.get("api_key") or "").strip()},
                    json=body,
                )
        except httpx.HTTPError as exc:
            raise ProviderError("network", f"ElevenLabs 连接失败：{exc.__class__.__name__}") from exc
        if resp.status_code >= 400:
            raise _explain_error(resp, "合成")
        return AudioResult(data=resp.content, container="mp3")

    async def list_voices(self) -> list[BuiltinVoice]:
        cfg = await self.get_config()
        if not await self.is_configured():
            raise ProviderError("not_configured", "ElevenLabs 尚未配置 api_key")
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(f"{_BASE}/v1/voices", headers={"xi-api-key": (cfg.get("api_key") or "").strip()})
        except httpx.HTTPError as exc:
            raise ProviderError("network", f"获取音色列表失败：{exc.__class__.__name__}") from exc
        if resp.status_code >= 400:
            raise _explain_error(resp, "获取音色列表")
        return [
            BuiltinVoice(name=v["voice_id"], display_name=v["name"], gender=v.get("labels", {}).get("gender", ""))
            for v in resp.json().get("voices", [])
        ]

    async def clone(self, audio: bytes, name: str, transcript: str | None) -> str:
        cfg = await self.get_config()
        if not await self.is_configured():
            raise ProviderError("not_configured", "ElevenLabs 尚未配置 api_key")
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{_BASE}/v1/voices/add",
                    headers={"xi-api-key": (cfg.get("api_key") or "").strip()},
                    data={"name": name},
                    files={"files": (f"{name}.mp3", audio)},
                )
        except httpx.HTTPError as exc:
            raise ProviderError("network", f"克隆请求失败：{exc.__class__.__name__}") from exc
        if resp.status_code >= 400:
            raise _explain_error(resp, "克隆")
        voice_id = resp.json().get("voice_id")
        if not voice_id:
            raise ProviderError("server", "克隆响应缺少 voice_id")
        return voice_id
