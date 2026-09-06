"""TTS 引擎适配层抽象。

所有引擎（本地/云端）都实现 TTSProvider；上层只见 synthesize(voice_ref, params) -> 音频字节。
pitch 语义：相对基频的赫兹偏移（-100~+100，0 为不变），各引擎自行换算。
"""
import time
from abc import ABC, abstractmethod
from typing import ClassVar, Literal, Optional

from pydantic import BaseModel

from .. import db


class ProviderError(Exception):
    """统一引擎错误。kind: not_configured|network|auth|quota|param|content|server"""

    def __init__(self, kind: str, message: str):
        self.kind = kind
        self.message = message
        super().__init__(message)


class BuiltinVoice(BaseModel):
    name: str
    display_name: str = ""
    gender: str = ""
    language: str = ""


class VoiceRef(BaseModel):
    kind: Literal["builtin", "ref_audio", "cloud_id"] = "builtin"
    voice_name: Optional[str] = None
    ref_audio_path: Optional[str] = None
    prompt_text: Optional[str] = None
    prompt_lang: Optional[str] = None
    cloud_voice_id: Optional[str] = None


class SynthParams(BaseModel):
    text: str
    speed: float = 1.0            # 0.5 ~ 2.0
    pitch: Optional[float] = None  # Hz 偏移，None/0 不变
    volume: float = 1.0            # 0 ~ 2.0
    emotion: Optional[str] = None
    instruct: Optional[str] = None
    language: Optional[str] = None
    extra: dict = {}


class AudioResult(BaseModel):
    data: bytes
    container: str                 # mp3 | wav
    duration_ms: Optional[int] = None


class Capabilities(BaseModel):
    clone: bool = False            # 支持声音复刻
    pitch: bool = False            # 原生支持音调
    emotion: bool = False          # 支持情绪预设
    instruct: bool = False         # 支持自由语气描述
    builtin_voices: bool = False   # 有内置音色列表


class ProviderMeta(BaseModel):
    id: str
    name: str
    type: Literal["builtin", "local", "cloud"]
    description: str = ""
    needs_config: bool = False     # 需要配置后才可用
    free: bool = False


class TTSProvider(ABC):
    meta: ClassVar[ProviderMeta]
    caps: ClassVar[Capabilities] = Capabilities()
    _voices_cache: Optional[tuple[float, list[BuiltinVoice]]] = None
    _VOICES_TTL = 3600

    # ---- 合成 ----
    @abstractmethod
    async def _do_synthesize(self, params: SynthParams, voice: VoiceRef) -> AudioResult: ...

    async def synthesize(self, params: SynthParams, voice: VoiceRef) -> AudioResult:
        started = time.monotonic()
        try:
            result = await self._do_synthesize(params, voice)
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001 统一归为服务端错误
            raise ProviderError("server", f"{self.meta.name} 调用失败：{exc}") from exc
        result.duration_ms = int((time.monotonic() - started) * 1000)
        return result

    # ---- 能力 ----
    async def list_voices(self) -> list[BuiltinVoice]:
        return []

    async def clone(self, audio: bytes, name: str, transcript: Optional[str]) -> str:
        raise ProviderError("param", f"{self.meta.name} 不支持声音复刻")

    async def is_configured(self) -> bool:
        return not self.meta.needs_config

    async def test_connection(self) -> tuple[bool, str]:
        if not await self.is_configured():
            return False, "尚未配置"
        return True, "可用"

    # ---- 配置 ----
    async def get_config(self) -> dict:
        return await db.get_provider_config(self.meta.id)

    @staticmethod
    def _voices_cache_valid() -> bool:
        return (
            TTSProvider._voices_cache is not None
            and time.monotonic() - TTSProvider._voices_cache[0] < TTSProvider._VOICES_TTL
        )
