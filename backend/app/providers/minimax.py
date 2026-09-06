"""MiniMax 海螺 TTS：T2A v2 接口 + voice_clone 克隆。

注意：返回的 data.audio 是 hex 编码字符串，需要 bytes.fromhex 解码。
配置：api_key、group_id、model（speech-02-hd / speech-02-turbo）
"""
import uuid

import httpx

from ..config import DEFAULT_SYNTH_TIMEOUT
from .base import AudioResult, BuiltinVoice, Capabilities, ProviderError, ProviderMeta, SynthParams, TTSProvider, VoiceRef

_BASE = "https://api.minimax.chat"

_EMOTION_MAP = {
    "平静": "neutral", "开心": "happy", "悲伤": "sad", "愤怒": "angry",
    "惊讶": "surprised", "恐惧": "fearful", "厌恶": "disgusted",
}

_SYSTEM_VOICES = [
    ("male-qn-qingse", "青年男声·清涩", "男"), ("male-qn-jingying", "青年男声·精英", "男"),
    ("male-qn-badao", "青年男声·霸道", "男"), ("female-shaonv", "少女音色", "女"),
    ("female-yujie", "御姐音色", "女"), ("female-chengshu", "成熟女声", "女"),
    ("female-tianmei", "甜美女声", "女"), ("presenter_female", "主持人·女", "女"),
    ("presenter_male", "主持人·男", "男"),
]


class MinimaxProvider(TTSProvider):
    meta = ProviderMeta(
        id="minimax",
        name="MiniMax 海螺",
        type="cloud",
        description="国内大厂 TTS，情感表现力强，支持即时克隆与情绪参数；按量计费",
        needs_config=True,
    )
    caps = Capabilities(clone=True, emotion=True, pitch=True, builtin_voices=True)

    async def is_configured(self) -> bool:
        cfg = await self.get_config()
        return bool((cfg.get("api_key") or "").strip() and (cfg.get("group_id") or "").strip())

    def _headers(self, cfg: dict) -> dict:
        return {"Authorization": f"Bearer {(cfg.get('api_key') or '').strip()}", "Content-Type": "application/json"}

    async def _do_synthesize(self, params: SynthParams, voice: VoiceRef) -> AudioResult:
        cfg = await self.get_config()
        if not await self.is_configured():
            raise ProviderError("not_configured", "MiniMax 尚未配置 api_key / group_id")
        voice_id = voice.cloud_voice_id or voice.voice_name or "female-shaonv"
        if voice.kind == "builtin" and voice.voice_name:
            voice_id = voice.voice_name
        voice_setting: dict = {
            "voice_id": voice_id,
            "speed": max(0.5, min(2.0, params.speed)),
            "vol": max(1.0, min(10.0, params.volume * 5)),
        }
        if params.pitch:
            voice_setting["pitch"] = max(-12, min(12, round(params.pitch / 8)))
        if params.emotion:
            voice_setting["emotion"] = _EMOTION_MAP.get(params.emotion, "neutral")
        body = {
            "model": (cfg.get("model") or "speech-02-hd").strip(),
            "text": params.text,
            "stream": False,
            "voice_setting": voice_setting,
            "audio_setting": {"sample_rate": 32000, "bitrate": 128000, "format": "mp3", "channel": 1},
        }
        group_id = (cfg.get("group_id") or "").strip()
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_SYNTH_TIMEOUT) as client:
                resp = await client.post(
                    f"{_BASE}/v1/t2a_v2", params={"GroupId": group_id},
                    headers=self._headers(cfg), json=body,
                )
        except httpx.HTTPError as exc:
            raise ProviderError("network", f"MiniMax 连接失败：{exc.__class__.__name__}") from exc
        if resp.status_code >= 400:
            kind = {401: "auth", 403: "auth", 429: "quota"}.get(resp.status_code, "server")
            raise ProviderError(kind, f"MiniMax HTTP {resp.status_code}：{resp.text[:200]}")
        payload = resp.json()
        base_resp = payload.get("base_resp", {})
        if base_resp.get("status_code", 0) != 0:
            kind = {1004: "auth", 1008: "quota", 1027: "quota", 1039: "quota"}.get(base_resp.get("status_code"), "server")
            raise ProviderError(kind, f"MiniMax 错误 {base_resp.get('status_code')}：{base_resp.get('status_msg')}")
        audio_hex = (payload.get("data") or {}).get("audio")
        if not audio_hex:
            raise ProviderError("server", "MiniMax 未返回音频数据")
        return AudioResult(data=bytes.fromhex(audio_hex), container="mp3")

    async def clone(self, audio: bytes, name: str, transcript: str | None) -> str:
        cfg = await self.get_config()
        if not await self.is_configured():
            raise ProviderError("not_configured", "MiniMax 尚未配置 api_key / group_id")
        group_id = (cfg.get("group_id") or "").strip()
        voice_id = f"ttsstudio-{name}-{uuid.uuid4().hex[:6]}"
        files = {"file": (f"{name}.mp3", audio), "voice_id": (None, voice_id)}
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{_BASE}/v1/voice_clone", params={"GroupId": group_id},
                    headers={"Authorization": f"Bearer {(cfg.get('api_key') or '').strip()}"},
                    files=files,
                )
        except httpx.HTTPError as exc:
            raise ProviderError("network", f"克隆请求失败：{exc.__class__.__name__}") from exc
        payload = resp.json() if resp.status_code < 500 else {}
        base_resp = payload.get("base_resp", {})
        if resp.status_code >= 400 or base_resp.get("status_code", 0) != 0:
            raise ProviderError("server", f"克隆失败：{base_resp.get('status_msg') or resp.text[:200]}")
        return voice_id

    async def list_voices(self) -> list[BuiltinVoice]:
        return [BuiltinVoice(name=n, display_name=d, gender=g) for n, d, g in _SYSTEM_VOICES]
