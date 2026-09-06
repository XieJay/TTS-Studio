"""IndexTTS-2.5（本地 Gradio WebUI）适配器：零样本复刻，参考音频经 HTTP 上传。

配置：base_url（默认 http://127.0.0.1:7860，即 Gradio WebUI 地址，无需参考音频目录映射——
参考音频直接经 /gradio_api/upload 上传到服务端临时目录）。

协议（Gradio queue API，实测于 IndexTTS-2.5 WebUI）：
  POST /gradio_api/upload（multipart，字段名 files）→ [服务端临时路径]
  POST /gradio_api/call/gen_single {"data": [...]}    → {"event_id"}
  GET  /gradio_api/call/gen_single/{event_id}（SSE）→ event: complete 后 data 为输出
  GET  /gradio_api/file=<urllib.parse.quote(path)>    → 音频字节（路径含 Windows 反斜杠，
        必须 URL 编码，否则 403）

已知怪癖：
- /gen_single 恰好 26 个参数且顺序固定（见 _build_call_data），多一项少一项都会被拒。
- 输出被包装成 [{"visible":…, "value": {"path","url"}}]，取 value.path；url 字段含原生
  反斜杠直接访问会 403，一律用 path 重新拼下载地址。
- duration_factor 即语速：>1 放慢、<1 加快，与 SynthParams.speed 相反（取倒数）。
- 情绪/语气描述走「使用情感向量控制」+ 情感描述文本（emo_text）。
"""
import json
import urllib.parse

import httpx

from ..config import DEFAULT_SYNTH_TIMEOUT
from .base import AudioResult, Capabilities, ProviderError, ProviderMeta, SynthParams, TTSProvider, VoiceRef

# SSE 读超时放宽：本地 GPU 合成长句可能远超默认请求超时
_SSE_READ_TIMEOUT_S = 300

# 与音色参考音频相同 → 使用情感向量控制（emo_text 生效的前提）
_EMO_SAME = "与音色参考音频相同"
_EMO_TEXT_MODE = "使用情感向量控制"

_LANG_MAP = {"zh": "ZH", "en": "EN", "ja": "JA"}


def _detect_lang(text: str) -> str:
    kana = sum(1 for ch in text if "\u3040" <= ch <= "\u30ff")
    if kana > 0:
        return "ja"
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    latin = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    if cjk > 0 and cjk >= latin:
        return "zh"
    if latin > 0:
        return "en"
    return "zh"


class IndexTTSProvider(TTSProvider):
    meta = ProviderMeta(
        id="indextts",
        name="IndexTTS-2.5（本地）",
        type="local",
        description="本地部署的 IndexTTS-2.5 Gradio WebUI，参考音频零样本复刻；只需填服务地址",
        needs_config=True,
        free=True,
    )
    caps = Capabilities(clone=True, emotion=True, instruct=True)

    async def is_configured(self) -> bool:
        cfg = await self.get_config()
        return bool((cfg.get("base_url") or "").strip())

    @staticmethod
    def _base(cfg: dict) -> str:
        return (cfg.get("base_url") or "").strip().rstrip("/")

    @staticmethod
    def _map_language(language: str | None, text: str) -> str:
        """映射到 lang_choice 枚举（ZH/EN/JA/AR/ES）；优先显式指定，否则按文本粗判。"""
        if language and language.lower() in _LANG_MAP:
            return _LANG_MAP[language.lower()]
        return _LANG_MAP.get(_detect_lang(text), "ZH")

    @staticmethod
    def _build_call_data(
        text: str, ref_remote_path: str, lang_choice: str, duration_factor: float, emo_text: str
    ) -> list:
        """按 /gen_single 的 26 个参数顺序组装 data（顺序不可变，见模块 docstring）。"""
        return [
            _EMO_TEXT_MODE if emo_text else _EMO_SAME,  # 1 emo_control_method
            {"path": ref_remote_path, "meta": {"_type": "gradio.FileData"}},  # 2 prompt 音色参考
            text,                                        # 3 text
            lang_choice,                                 # 4 lang_choice
            None,                                        # 5 emo_ref_path（不用情感参考音频）
            0.65,                                        # 6 emo_weight
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,      # 7-14 vec1..8（喜…平静）
            emo_text,                                    # 15 emo_text
            False,                                       # 16 emo_random
            120,                                         # 17 max_text_tokens_per_segment
            duration_factor,                             # 18 duration_factor（语速倒数）
            True,                                        # 19 do_sample
            0.8,                                         # 20 top_p
            30,                                          # 21 top_k
            0.8,                                         # 22 temperature
            0.0,                                         # 23 length_penalty
            3,                                           # 24 num_beams
            10.0,                                        # 25 repetition_penalty
            1500,                                        # 26 max_mel_tokens
        ]

    @staticmethod
    def _extract_output_path(final: list) -> str:
        """complete 事件 data → 输出文件服务端路径（兼容包装对象与裸路径两种形态）。"""
        first = final[0] if isinstance(final, list) and final else final
        value = first.get("value") if isinstance(first, dict) else first
        if isinstance(value, dict):
            value = value.get("path") or value.get("url")
        if not value or not isinstance(value, str):
            raise ProviderError("server", "IndexTTS 返回结果中缺少音频文件路径")
        return value

    async def _upload_ref(self, client: httpx.AsyncClient, base: str, ref_path: str) -> str:
        from pathlib import Path

        src = Path(ref_path)
        if not src.exists():
            raise ProviderError("server", f"参考音频文件丢失：{ref_path}")
        try:
            resp = await client.post(
                f"{base}/gradio_api/upload",
                files={"files": (src.name, src.read_bytes(), "application/octet-stream")},
            )
        except httpx.TimeoutException as exc:
            raise ProviderError("network", "上传参考音频到 IndexTTS 超时") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("network", f"无法连接 IndexTTS（{base}）：{exc.__class__.__name__}") from exc
        if resp.status_code >= 400:
            raise ProviderError("server", f"上传参考音频失败 HTTP {resp.status_code}：{resp.text[:200]}")
        try:
            remote = resp.json()[0]
        except Exception as exc:  # noqa: BLE001
            raise ProviderError("server", f"上传参考音频响应异常：{resp.text[:200]}") from exc
        if not remote:
            raise ProviderError("server", "上传参考音频失败：服务未返回文件路径")
        return remote

    async def _do_synthesize(self, params: SynthParams, voice: VoiceRef) -> AudioResult:
        cfg = await self.get_config()
        base = self._base(cfg)
        if not base:
            raise ProviderError("not_configured", "IndexTTS 尚未配置服务地址，请到设置页填写 Gradio WebUI 地址")
        if voice.kind != "ref_audio" or not voice.ref_audio_path:
            raise ProviderError(
                "param",
                "IndexTTS 零样本合成需要绑定带参考音频的音色（试炼场不支持，请在配音任务或音色库中使用）",
            )

        text = params.text.strip()
        if not text:
            raise ProviderError("param", "句子文本为空，无法合成")
        # 语速 → 时长系数（>1 放慢）；限 0.5~2.0
        duration_factor = max(0.5, min(2.0, 1.0 / (params.speed or 1.0)))
        emo_text = (params.instruct or params.emotion or "").strip()

        lang_choice = self._map_language(params.language, text)
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(DEFAULT_SYNTH_TIMEOUT, read=_SSE_READ_TIMEOUT_S)
        ) as client:
            remote = await self._upload_ref(client, base, voice.ref_audio_path)
            try:
                resp = await client.post(
                    f"{base}/gradio_api/call/gen_single",
                    json={"data": self._build_call_data(text, remote, lang_choice, duration_factor, emo_text)},
                )
            except httpx.TimeoutException as exc:
                raise ProviderError("network", "IndexTTS 请求超时") from exc
            except httpx.HTTPError as exc:
                raise ProviderError("network", f"无法连接 IndexTTS（{base}）：{exc.__class__.__name__}") from exc
            if resp.status_code >= 400:
                # Gradio 参数校验失败返回 422 + {"detail": "..."}，多为端点/参数不匹配
                raise ProviderError("param", f"IndexTTS 拒绝请求 HTTP {resp.status_code}：{resp.text[:200]}")
            try:
                event_id = resp.json()["event_id"]
            except Exception as exc:  # noqa: BLE001
                raise ProviderError("server", f"IndexTTS 响应缺少 event_id：{resp.text[:200]}") from exc

            final = await self._wait_result(client, base, event_id)
            out_path = self._extract_output_path(final)
            dl = await client.get(f"{base}/gradio_api/file={urllib.parse.quote(out_path, safe='')}")
        if dl.status_code >= 400:
            raise ProviderError("server", f"下载合成结果失败 HTTP {dl.status_code}")
        if not dl.content:
            raise ProviderError("server", "IndexTTS 返回了空音频")
        return AudioResult(data=dl.content, container="wav")

    async def _wait_result(self, client: httpx.AsyncClient, base: str, event_id: str) -> list:
        """订阅 SSE 直到 complete/error；返回 complete 事件的 data。"""
        try:
            async with client.stream("GET", f"{base}/gradio_api/call/gen_single/{event_id}") as resp:
                if resp.status_code >= 400:
                    raise ProviderError("server", f"订阅 IndexTTS 结果失败 HTTP {resp.status_code}")
                ev_type = ""
                data_lines: list[str] = []
                async for line in resp.aiter_lines():
                    if line.startswith("event:"):
                        ev_type = line.split(":", 1)[1].strip()
                        data_lines = []  # 新事件开始，丢弃上一事件的缓存
                    elif line.startswith("data:"):
                        data_lines.append(line.split(":", 1)[1].strip())
                    if ev_type == "complete" and data_lines:
                        return json.loads("\n".join(data_lines))
                    if ev_type == "error" and data_lines:
                        raise ProviderError("server", f"IndexTTS 合成失败：{' '.join(data_lines)[:300]}")
        except httpx.TimeoutException as exc:
            raise ProviderError("network", f"等待 IndexTTS 合成结果超时（>{_SSE_READ_TIMEOUT_S}s）") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("network", f"IndexTTS 连接中断：{exc.__class__.__name__}") from exc
        raise ProviderError("server", "IndexTTS 未返回合成结果（连接提前结束）")

    async def test_connection(self) -> tuple[bool, str]:
        cfg = await self.get_config()
        base = self._base(cfg)
        if not base:
            return False, "尚未配置服务地址"
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                resp = await client.get(f"{base}/gradio_api/info")
        except httpx.HTTPError as exc:
            return False, f"无法连接：{exc.__class__.__name__}"
        if resp.status_code >= 400:
            return False, f"服务异常 HTTP {resp.status_code}"
        if "/gen_single" not in json.dumps(resp.json().get("named_endpoints", {})):
            return False, "服务可达，但未找到 /gen_single 端点（确认是 IndexTTS WebUI）"
        return True, "IndexTTS 服务可达"
