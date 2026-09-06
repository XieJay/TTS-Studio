"""GPT-SoVITS api_v2 适配器（本地自部署，零样本复刻）。

要求参考音频位于 GPT-SoVITS 服务端本地：通过设置的 ref_dir（参考音频目录映射）
把上传的参考音频复制过去后按映射路径调用。
配置：base_url（如 http://127.0.0.1:9880）、ref_dir、text_lang、prompt_lang
"""
import httpx

from ..config import DEFAULT_SYNTH_TIMEOUT
from .base import AudioResult, Capabilities, ProviderError, ProviderMeta, SynthParams, TTSProvider, VoiceRef


class GptSovitsProvider(TTSProvider):
    meta = ProviderMeta(
        id="gptsovits",
        name="GPT-SoVITS（本地）",
        type="local",
        description="本地自部署 api_v2，参考音频零样本复刻；需在设置中配置服务地址与参考音频目录映射",
        needs_config=True,
    )
    caps = Capabilities(clone=True)

    async def is_configured(self) -> bool:
        cfg = await self.get_config()
        return bool((cfg.get("base_url") or "").strip())

    async def _do_synthesize(self, params: SynthParams, voice: VoiceRef) -> AudioResult:
        cfg = await self.get_config()
        base = (cfg.get("base_url") or "").rstrip("/")
        if not base:
            raise ProviderError("not_configured", "GPT-SoVITS 尚未配置服务地址")
        if voice.kind != "ref_audio" or not voice.ref_audio_path:
            raise ProviderError("param", "GPT-SoVITS 需要绑定带参考音频的音色（零样本复刻）")
        body = {
            "text": params.text,
            "text_lang": params.language or (cfg.get("text_lang") or "zh"),
            "ref_audio_path": voice.ref_audio_path,
            "prompt_text": voice.prompt_text or "",
            "prompt_language": voice.prompt_lang or (cfg.get("prompt_lang") or "zh"),
            "speed_factor": max(0.6, min(1.65, params.speed)),
        }
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_SYNTH_TIMEOUT) as client:
                resp = await client.post(f"{base}/tts", json=body)
        except httpx.TimeoutException as exc:
            raise ProviderError("network", "GPT-SoVITS 请求超时") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("network", f"无法连接 GPT-SoVITS（{base}）：{exc.__class__.__name__}") from exc
        if resp.status_code >= 400:
            raise ProviderError("server", f"GPT-SoVITS HTTP {resp.status_code}：{resp.text[:200]}")
        return AudioResult(data=resp.content, container="wav")

    async def test_connection(self) -> tuple[bool, str]:
        cfg = await self.get_config()
        base = (cfg.get("base_url") or "").rstrip("/")
        if not base:
            return False, "尚未配置服务地址"
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                resp = await client.get(base)
            if resp.status_code < 500:
                return True, "服务可达（请确认已以 api_v2 模式启动）"
            return False, f"服务异常 HTTP {resp.status_code}"
        except httpx.HTTPError as exc:
            return False, f"无法连接：{exc.__class__.__name__}"
