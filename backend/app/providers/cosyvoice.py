"""CosyVoice2 本地 API 适配器（社区常见 FastAPI server）。

不同实现请求体差异较大：支持 body_template 配置（{{text}} / {{ref_audio_path}} /
{{speaker}} 占位符），实在不匹配可用「自定义 HTTP」引擎兜底。
配置：base_url、api_path（默认 /api/tts）、ref_dir、body_template
"""
import json

import httpx

from ..config import DEFAULT_SYNTH_TIMEOUT
from .base import AudioResult, Capabilities, ProviderError, ProviderMeta, SynthParams, TTSProvider, VoiceRef

DEFAULT_BODY_TEMPLATE = '{"text": "{{text}}", "ref_audio_path": "{{ref_audio_path}}", "format": "wav"}'


class CosyVoiceProvider(TTSProvider):
    meta = ProviderMeta(
        id="cosyvoice",
        name="CosyVoice2（本地）",
        type="local",
        description="本地自部署 CosyVoice2 API，零样本复刻；支持自定义请求体模板适配不同实现",
        needs_config=True,
    )
    caps = Capabilities(clone=True)

    async def is_configured(self) -> bool:
        cfg = await self.get_config()
        return bool((cfg.get("base_url") or "").strip())

    def _build_body(self, cfg: dict, params: SynthParams, voice: VoiceRef) -> dict:
        template = (cfg.get("body_template") or DEFAULT_BODY_TEMPLATE).strip()
        speaker = (cfg.get("speaker") or "").strip()
        body_str = (
            template.replace("{{text}}", params.text.replace('"', '\\"'))
            .replace("{{ref_audio_path}}", (voice.ref_audio_path or "").replace('"', '\\"'))
            .replace("{{speaker}}", speaker)
        )
        try:
            return json.loads(body_str)
        except json.JSONDecodeError as exc:
            raise ProviderError("param", f"请求体模板不是合法 JSON：{exc}") from exc

    async def _do_synthesize(self, params: SynthParams, voice: VoiceRef) -> AudioResult:
        cfg = await self.get_config()
        base = (cfg.get("base_url") or "").rstrip("/")
        if not base:
            raise ProviderError("not_configured", "CosyVoice 尚未配置服务地址")
        if voice.kind != "ref_audio" or not voice.ref_audio_path:
            raise ProviderError("param", "CosyVoice 需要绑定带参考音频的音色（零样本复刻）")
        api_path = (cfg.get("api_path") or "/api/tts").strip()
        body = self._build_body(cfg, params, voice)
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_SYNTH_TIMEOUT) as client:
                resp = await client.post(f"{base}{api_path}", json=body)
        except httpx.TimeoutException as exc:
            raise ProviderError("network", "CosyVoice 请求超时") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("network", f"无法连接 CosyVoice（{base}）：{exc.__class__.__name__}") from exc
        if resp.status_code >= 400:
            raise ProviderError("server", f"CosyVoice HTTP {resp.status_code}：{resp.text[:200]}")
        content_type = resp.headers.get("content-type", "")
        container = "wav" if "wav" in content_type or "octet-stream" in content_type else "mp3"
        return AudioResult(data=resp.content, container=container)

    async def test_connection(self) -> tuple[bool, str]:
        cfg = await self.get_config()
        base = (cfg.get("base_url") or "").rstrip("/")
        if not base:
            return False, "尚未配置服务地址"
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                resp = await client.get(base)
            if resp.status_code < 500:
                return True, "服务可达（请确认 API 路径与请求体模板匹配）"
            return False, f"服务异常 HTTP {resp.status_code}"
        except httpx.HTTPError as exc:
            return False, f"无法连接：{exc.__class__.__name__}"
