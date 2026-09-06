"""音色资产：参考音频存储、引擎目录映射、音色档案 → 各引擎 VoiceRef 解析、试听样本生成。"""
import shutil
import uuid
from pathlib import Path

from ..config import VOICE_AUDIO_DIR
from ..db import get_provider_config
from ..providers.base import ProviderError, SynthParams, VoiceRef
from ..providers.registry import get_provider

SAMPLE_TEXT = "你好，这是我的专属音色，很高兴用它为你朗读。"


def new_voice_id() -> str:
    return uuid.uuid4().hex[:12]


def save_ref_audio(voice_id: str, filename: str, content: bytes) -> str:
    """保存参考音频到 data/audio/voices/{voice_id}/，返回应用内相对路径。"""
    ext = Path(filename).suffix.lower().lstrip(".") or "wav"
    if ext not in ("wav", "mp3", "m4a", "ogg", "flac"):
        ext = "wav"
    voice_dir = VOICE_AUDIO_DIR / voice_id
    voice_dir.mkdir(parents=True, exist_ok=True)
    target = voice_dir / f"ref.{ext}"
    target.write_bytes(content)
    return str(target.relative_to(VOICE_AUDIO_DIR))


def read_ref_audio(ref_path: str) -> bytes:
    p = VOICE_AUDIO_DIR / ref_path
    if not p.exists():
        raise ProviderError("server", f"参考音频文件丢失：{ref_path}")
    return p.read_bytes()


async def mapped_ref_path_async(voice_id: str, ref_path: str, engine_id: str) -> str:
    src = VOICE_AUDIO_DIR / ref_path
    if not src.exists():
        raise ProviderError("server", f"参考音频文件丢失：{ref_path}")
    return await _mapped_ref_path_async(voice_id, src, engine_id)


async def _mapped_ref_path_async(voice_id: str, src: Path, engine_id: str) -> str:
    cfg = await get_provider_config(engine_id)
    ref_dir = (cfg.get("ref_dir") or "").strip()
    if not ref_dir:
        raise ProviderError(
            "not_configured",
            f"未配置「参考音频目录映射」：请在设置页为该引擎指定一个其服务进程可访问的目录",
        )
    dest_dir = Path(ref_dir)
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ProviderError("server", f"参考音频目录不可写（{ref_dir}）：{exc}") from exc
    dest = dest_dir / f"ttsstudio_{voice_id}_{src.name}"
    if not dest.exists() or dest.stat().st_size != src.stat().st_size:
        shutil.copy2(src, dest)
    return str(dest)


async def resolve_voice_ref(voice: dict, provider_id: str) -> VoiceRef:
    """把音色档案解析为指定引擎可用的 VoiceRef。

    抛出 ProviderError(kind='param') 表示该音色在该引擎下需先克隆/不支持。
    """
    provider = get_provider(provider_id)
    if provider is None:
        raise ProviderError("param", f"引擎不存在：{provider_id}")
    assets: dict = voice.get("provider_assets") or {}

    if provider_id == "edge":
        voice_name = assets.get("edge", {}).get("voice_name")
        if not voice_name:
            raise ProviderError("param", "Edge TTS 不支持复刻：请直接使用其内置音色")
        return VoiceRef(kind="builtin", voice_name=voice_name)

    if provider_id == "gptsovits":
        ref = voice.get("ref_audio_path")
        if not ref:
            raise ProviderError("param", "该音色缺少参考音频，GPT-SoVITS 零样本复刻需要参考音频")
        mapped = await mapped_ref_path_async(voice["id"], ref, "gptsovits")
        return VoiceRef(
            kind="ref_audio", ref_audio_path=mapped,
            prompt_text=voice.get("prompt_text") or "",
            prompt_lang=voice.get("prompt_lang") or "zh",
        )

    if provider_id == "cosyvoice":
        ref = voice.get("ref_audio_path")
        if not ref:
            raise ProviderError("param", "该音色缺少参考音频，CosyVoice 零样本复刻需要参考音频")
        mapped = await mapped_ref_path_async(voice["id"], ref, "cosyvoice")
        return VoiceRef(kind="ref_audio", ref_audio_path=mapped)

    if provider_id == "indextts":
        # 走 Gradio HTTP 上传，无需 ref_dir 目录映射，直接把绝对路径交给适配器读取
        ref = voice.get("ref_audio_path")
        if not ref:
            raise ProviderError("param", "该音色缺少参考音频，IndexTTS 零样本复刻需要参考音频")
        src = VOICE_AUDIO_DIR / ref
        if not src.exists():
            raise ProviderError("server", f"参考音频文件丢失：{ref}")
        return VoiceRef(kind="ref_audio", ref_audio_path=str(src))

    if provider_id == "siliconflow":
        voice_uri = assets.get("siliconflow", {}).get("voice_uri")
        if voice_uri:
            return VoiceRef(kind="cloud_id", cloud_voice_id=voice_uri)
        builtin_name = assets.get("siliconflow", {}).get("voice_name")
        if builtin_name:
            return VoiceRef(kind="builtin", voice_name=builtin_name)
        if voice.get("ref_audio_path"):
            raise ProviderError("param", "该音色尚未克隆到 SiliconFlow，请先在音色库执行「克隆到此引擎」")
        raise ProviderError("param", "请选择 SiliconFlow 音色（内置或已克隆）")

    if provider_id == "minimax":
        voice_id_ = assets.get("minimax", {}).get("voice_id")
        if voice_id_:
            return VoiceRef(kind="cloud_id", cloud_voice_id=voice_id_)
        builtin_name = assets.get("minimax", {}).get("voice_name")
        if builtin_name:
            return VoiceRef(kind="builtin", voice_name=builtin_name)
        raise ProviderError("param", "该音色尚未克隆到 MiniMax，请先执行克隆")

    if provider_id == "elevenlabs":
        voice_id_ = assets.get("elevenlabs", {}).get("voice_id")
        if voice_id_:
            return VoiceRef(kind="cloud_id", cloud_voice_id=voice_id_)
        builtin_name = assets.get("elevenlabs", {}).get("voice_name")
        if builtin_name:
            return VoiceRef(kind="builtin", voice_name=builtin_name)
        raise ProviderError("param", "该音色尚未克隆到 ElevenLabs，请先执行克隆")

    if provider_id == "openai_compat":
        voice_name = assets.get("openai_compat", {}).get("voice_name")
        if voice_name:
            return VoiceRef(kind="builtin", voice_name=voice_name)
        raise ProviderError("param", "OpenAI 兼容接口不支持复刻：请使用其内置音色")

    # 自定义 HTTP：优先云端 id，其次参考音频路径（模板占位符自行使用）
    cloud = assets.get("custom_http", {}).get("voice_id")
    if cloud:
        return VoiceRef(kind="cloud_id", cloud_voice_id=cloud)
    if voice.get("ref_audio_path"):
        mapped = await mapped_ref_path_async(voice["id"], voice["ref_audio_path"], "custom_http")
        return VoiceRef(kind="ref_audio", ref_audio_path=mapped)
    builtin_name = assets.get("custom_http", {}).get("voice_name")
    if builtin_name:
        return VoiceRef(kind="builtin", voice_name=builtin_name)
    return VoiceRef(kind="builtin", voice_name=voice["name"])


async def generate_sample(voice_id: str, provider_id: str, voice_row: dict, text: str = "") -> str:
    """用指定引擎合成试听样本，返回样本文件相对路径。

    样本文本优先级：显式传入 > 音色的参考文本 > 默认问候语——参考音频的音色最直观的演示
    就是让它读参考文本（用户要求试听样本播参考文本的合成音频）。
    """
    provider = get_provider(provider_id)
    if provider is None:
        raise ProviderError("param", f"引擎不存在：{provider_id}")
    voice_ref = await resolve_voice_ref(voice_row, provider_id)
    sample_text = (text or "").strip() or (voice_row.get("prompt_text") or "").strip() or SAMPLE_TEXT
    result = await provider.synthesize(SynthParams(text=sample_text), voice_ref)
    sample_rel = f"{voice_id}/sample.{result.container}"
    target = VOICE_AUDIO_DIR / sample_rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(result.data)
    return sample_rel


def delete_voice_files(voice_id: str) -> None:
    shutil.rmtree(VOICE_AUDIO_DIR / voice_id, ignore_errors=True)
