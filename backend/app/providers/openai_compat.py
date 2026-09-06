"""OpenAI 兼容 /audio/speech 通用适配器。

覆盖：OpenAI 官方、fish-speech、以及任何暴露该接口的本地/云服务。
SiliconFlow 语音合成同样走此协议（克隆接口由其子类补充）。

配置项（设置页）：
  base_url        必填，如 https://api.openai.com/v1 或 http://127.0.0.1:8080/v1
  api_key         鉴权令牌（可空）
  model           模型名，如 tts-1 / tts-1-hd / gpt-4o-mini-tts / fish-speech-1.5
  default_voice   默认音色名
  voices          逗号分隔的音色列表（前端下拉用）
  instruct_support  true 时把语气描述作为 instructions 传入
"""
import httpx

from ..config import DEFAULT_SYNTH_TIMEOUT
from .base import AudioResult, BuiltinVoice, Capabilities, ProviderError, ProviderMeta, SynthParams, TTSProvider, VoiceRef

_STATUS_KIND = {401: "auth", 403: "auth", 402: "quota", 429: "quota", 422: "param", 400: "param"}


class OpenAICompatProvider(TTSProvider):
    meta = ProviderMeta(
        id="openai_compat",
        name="OpenAI 兼容接口",
        type="local",
        description="通用 /v1/audio/speech 协议：OpenAI 官方、fish-speech、任意兼容服务",
        needs_config=True,
    )
    caps = Capabilities(instruct=True, builtin_voices=True)

    def _endpoint(self, base_url: str) -> str:
        base = base_url.rstrip("/")
        if base.endswith("/audio/speech"):
            return base
        if base.endswith("/v1"):
            return base + "/audio/speech"
        return base + "/v1/audio/speech"

    async def is_configured(self) -> bool:
        cfg = await self.get_config()
        return bool(cfg.get("base_url"))

    async def _do_synthesize(self, params: SynthParams, voice: VoiceRef) -> AudioResult:
        cfg = await self.get_config()
        base_url = (cfg.get("base_url") or "").strip()
        if not base_url:
            raise ProviderError("not_configured", "OpenAI 兼容接口尚未配置 base_url，请前往设置页")
        model = (cfg.get("model") or "tts-1").strip()
        voice_name = voice.voice_name or (cfg.get("default_voice") or "alloy").strip()
        fmt = (cfg.get("response_format") or "mp3").strip()
        body: dict = {
            "model": model,
            "input": params.text,
            "voice": voice_name,
            "response_format": fmt,
            "speed": max(0.25, min(4.0, params.speed)),
        }
        if params.instruct and (cfg.get("instruct_support") in (True, "true", "True", 1)):
            body["instructions"] = params.instruct
        headers = {}
        api_key = (cfg.get("api_key") or "").strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_SYNTH_TIMEOUT) as client:
                resp = await client.post(self._endpoint(base_url), json=body, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderError("network", "请求超时") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("network", f"连接失败：{exc.__class__.__name__}") from exc
        if resp.status_code >= 400:
            kind = _STATUS_KIND.get(resp.status_code, "server")
            raise ProviderError(kind, f"HTTP {resp.status_code}：{resp.text[:200]}")
        return AudioResult(data=resp.content, container=fmt)

    async def list_voices(self) -> list[BuiltinVoice]:
        cfg = await self.get_config()
        raw = (cfg.get("voices") or "alloy,echo,fable,onyx,nova,shimmer").strip()
        return [BuiltinVoice(name=v.strip(), display_name=v.strip()) for v in raw.split(",") if v.strip()]

    async def test_connection(self) -> tuple[bool, str]:
        if not await self.is_configured():
            return False, "尚未配置 base_url"
        cfg = await self.get_config()
        headers = {}
        if (cfg.get("api_key") or "").strip():
            headers["Authorization"] = f"Bearer {cfg['api_key'].strip()}"
        probe = self._endpoint(cfg["base_url"].strip()).rsplit("/", 1)[0]  # 去掉 /speech 级路径再探模型列表
        for path in ("/models", ""):
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(probe + path, headers=headers)
                if resp.status_code < 500:
                    if resp.status_code in (401, 403):
                        return False, "鉴权失败（检查 api_key）"
                    return True, "连接成功"
            except httpx.HTTPError:
                continue
        return False, "无法连接到 base_url"
