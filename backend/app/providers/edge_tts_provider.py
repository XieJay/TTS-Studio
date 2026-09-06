"""edge-tts：微软免费音色，无需配置、需联网；不支持复刻。"""
import time

import edge_tts

from .base import AudioResult, BuiltinVoice, Capabilities, ProviderError, ProviderMeta, SynthParams, TTSProvider, VoiceRef

_LANG_PREFIX = {
    "zh": "中文", "en": "英语", "ja": "日语",
}


def _text_lang(text: str) -> str:
    """粗判文本主语言：ja（含假名）> zh（汉字为主）> en（拉丁字母为主）> 空串。"""
    kana = sum(1 for ch in text if "\u3040" <= ch <= "\u30ff")
    if kana > 0:
        return "ja"
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    latin = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    if cjk > 0 and cjk >= latin:
        return "zh"
    if latin > 0:
        return "en"
    return ""


def _voice_locale(voice_name: str) -> str:
    """从 ShortName 取区域前缀，如 af-ZA-WillemNeural → af-ZA。"""
    parts = voice_name.split("-")
    return "-".join(parts[:2]) if len(parts) >= 3 else ""


# 只暴露中英文音色（zh-* 含普通话/粤语/繁体，en-* 含各英语地区，Multilingual 变体因前缀相同自然保留）。
# 产品场景为中英文稿件；其他语言音色读中文文本会直接失败（见 _do_synthesize 的语言预检），
# 从源头过滤掉可避免误选（2026-09 实际发生过误选 af-ZA 音色导致合成报错）。
_ALLOWED_LOCALE_PREFIXES = ("zh-", "en-")


class EdgeTTSProvider(TTSProvider):
    meta = ProviderMeta(
        id="edge",
        name="Edge TTS（免费）",
        type="builtin",
        description="微软 Edge 朗读音色，免费、无需配置，需联网；不支持声音复刻",
        free=True,
    )
    caps = Capabilities(pitch=True, builtin_voices=True)
    _voices_cache: tuple[float, list[BuiltinVoice]] | None = None

    async def _do_synthesize(self, params: SynthParams, voice: VoiceRef) -> AudioResult:
        voice_name = voice.voice_name or "zh-CN-XiaoxiaoNeural"
        text = params.text.strip()
        if not text:
            raise ProviderError("param", "句子文本为空，无法合成")
        # 非中文/日语音色读中文（或日语）文本时，微软服务会直接返回空音频（NoAudioReceived），
        # 且重试也无济于事——提前拦截并给出可操作的提示，避免用户面对无意义的报错。
        lang = _text_lang(text)
        locale = _voice_locale(voice_name)
        if lang in ("zh", "ja") and locale and not locale.startswith(lang) and "Multilingual" not in voice_name:
            raise ProviderError(
                "param",
                f"所选音色 {voice_name}（{locale}）不支持朗读{'中文' if lang == 'zh' else '日语'}文本，"
                "请在任务设置中换用对应语言的音色（或选 Multilingual 多语言音色）",
            )
        rate = f"{round((params.speed - 1) * 100):+d}%"
        volume = f"{round((params.volume - 1) * 100):+d}%"
        pitch = f"{round(params.pitch or 0):+d}Hz"
        last_error: Exception | None = None
        # 微软免费接口偶发返回空音频，免费引擎自动重试一次（无计费风险）
        for attempt in range(2):
            try:
                com = edge_tts.Communicate(params.text, voice_name, rate=rate, volume=volume, pitch=pitch)
                buf = bytearray()
                async for chunk in com.stream():
                    if chunk["type"] == "audio":
                        buf.extend(chunk["data"])
                if buf:
                    return AudioResult(data=bytes(buf), container="mp3")
                last_error = ProviderError("server", "Edge TTS 未返回音频数据")
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt == 1:
                    break
        msg = str(last_error)
        # edge-tts 的 NoAudioReceived 异常 str() 只有 "No audio was received..."，不含类名
        if "No audio was received" in msg or "NoAudioReceived" in msg:
            raise ProviderError(
                "server",
                "Edge TTS 未返回音频（已自动重试仍失败）。常见原因：音色语言与文本语言不匹配、"
                "文本为空或微软接口偶发故障，可稍后重试或更换音色",
            ) from last_error
        if "timeout" in msg.lower() or "connect" in msg.lower():
            raise ProviderError("network", "Edge TTS 连接失败（该引擎需要联网）") from last_error
        raise ProviderError("server", f"Edge TTS 调用失败：{msg}") from last_error

    async def list_voices(self) -> list[BuiltinVoice]:
        if EdgeTTSProvider._voices_cache and time.monotonic() - EdgeTTSProvider._voices_cache[0] < self._VOICES_TTL:
            return EdgeTTSProvider._voices_cache[1]
        try:
            raw = await edge_tts.list_voices()
        except Exception as exc:  # noqa: BLE001
            raise ProviderError("network", "获取 Edge 音色列表失败（需要联网）") from exc
        voices = [
            BuiltinVoice(
                name=v["ShortName"],
                display_name=v.get("FriendlyName", v["ShortName"]),
                gender={"Female": "女", "Male": "男"}.get(v.get("Gender", ""), ""),
                language=v.get("Locale", ""),
            )
            for v in raw
            if v.get("ShortName", "").startswith(_ALLOWED_LOCALE_PREFIXES)
        ]
        EdgeTTSProvider._voices_cache = (time.monotonic(), voices)
        return voices
