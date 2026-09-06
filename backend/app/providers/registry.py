"""引擎注册表：新增引擎 = 写一个 Provider 子类 + 在此注册。"""
from .base import TTSProvider
from .cosyvoice import CosyVoiceProvider
from .edge_tts_provider import EdgeTTSProvider
from .elevenlabs import ElevenLabsProvider
from .gpt_sovits import GptSovitsProvider
from .index_tts import IndexTTSProvider
from .minimax import MinimaxProvider
from .openai_compat import OpenAICompatProvider
from .siliconflow import SiliconFlowProvider

_PROVIDERS: dict[str, TTSProvider] = {}


def register(provider: TTSProvider) -> None:
    _PROVIDERS[provider.meta.id] = provider


def get_provider(provider_id: str) -> TTSProvider | None:
    return _PROVIDERS.get(provider_id)


def all_providers() -> list[TTSProvider]:
    return list(_PROVIDERS.values())


async def list_provider_info() -> list[dict]:
    """供前端展示：元信息 + 能力 + 配置状态。"""
    info = []
    for p in all_providers():
        info.append(
            {
                **p.meta.model_dump(),
                "capabilities": p.caps.model_dump(),
                "configured": await p.is_configured(),
            }
        )
    return info


register(EdgeTTSProvider())
register(OpenAICompatProvider())
register(SiliconFlowProvider())
register(GptSovitsProvider())
register(CosyVoiceProvider())
register(IndexTTSProvider())
register(MinimaxProvider())
register(ElevenLabsProvider())
