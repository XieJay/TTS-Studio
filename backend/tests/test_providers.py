"""引擎适配器单元测试（不发起真实网络请求）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.providers.elevenlabs import ElevenLabsProvider
from app.providers.minimax import MinimaxProvider
from app.providers.openai_compat import OpenAICompatProvider
from app.providers.siliconflow import SiliconFlowProvider


def test_openai_endpoint_normalization():
    p = OpenAICompatProvider()
    assert p._endpoint("https://api.openai.com/v1") == "https://api.openai.com/v1/audio/speech"
    assert p._endpoint("http://127.0.0.1:8080") == "http://127.0.0.1:8080/v1/audio/speech"
    assert p._endpoint("http://127.0.0.1:8080/") == "http://127.0.0.1:8080/v1/audio/speech"
    assert p._endpoint("http://h/x/audio/speech") == "http://h/x/audio/speech"


def test_siliconflow_builtin_voice_prefix():
    """内置音色应拼成 {model}:{name} 形式（通过 VoiceRef 替换逻辑验证）。"""
    from app.providers.base import SynthParams, VoiceRef

    voice = VoiceRef(kind="builtin", voice_name="alex")
    params = SynthParams(text="hi")
    # SiliconFlow._do_synthesize 需要网络；仅验证 voice_name 组装分支
    provider = SiliconFlowProvider()

    async def fake_super_synth(self, params, voice):
        return voice

    # 直接检查组装逻辑：monkeypatch 父类
    import app.providers.openai_compat as oc

    captured = {}

    async def fake_do(self, params, voice):
        captured["voice"] = voice.voice_name
        raise TimeoutError("stop")

    orig = oc.OpenAICompatProvider._do_synthesize
    oc.OpenAICompatProvider._do_synthesize = fake_do
    try:
        import asyncio
        try:
            asyncio.run(provider._do_synthesize(params, voice))
        except TimeoutError:
            pass
    finally:
        oc.OpenAICompatProvider._do_synthesize = orig
    assert captured["voice"] == "FunAudioLLM/CosyVoice2-0.5B:alex"


def _mock_httpx(payload: dict, monkeypatch):
    """把 httpx.AsyncClient.post 替换为返回固定 payload 的桩。"""
    import httpx
    from app.providers import minimax as mm

    class MockResp:
        status_code = 200
        content = b""
        text = ""
        headers: dict = {}

        def json(self):
            return payload

    class MockClient:
        def __init__(self, *a, **kw): ...

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **kw):
            return MockResp()

    monkeypatch.setattr(httpx, "AsyncClient", MockClient)
    monkeypatch.setattr(mm.MinimaxProvider, "is_configured", async_lambda(True))
    monkeypatch.setattr(
        mm.MinimaxProvider, "get_config",
        async_lambda({"api_key": "k", "group_id": "g", "model": "speech-02-hd"}),
    )


class async_lambda:
    def __init__(self, value):
        self.value = value

    async def __call__(self, self_=None):
        return self.value


def test_minimax_hex_decode(monkeypatch):
    import asyncio

    from app.providers.base import SynthParams, VoiceRef

    provider = MinimaxProvider()
    audio_hex = b"fake-mp3".hex()
    _mock_httpx({"data": {"audio": audio_hex}, "base_resp": {"status_code": 0}}, monkeypatch)
    result = asyncio.run(
        provider._do_synthesize(SynthParams(text="你好"), VoiceRef(kind="builtin", voice_name="female-shaonv"))
    )
    assert result.data == b"fake-mp3"
    assert result.container == "mp3"


def test_edge_builtin_voices_zh_en_only(monkeypatch):
    """Edge 内置音色列表只保留中英文音色（试炼场下拉与加入内置音色共用此接口）。"""
    import asyncio

    import app.providers.edge_tts_provider as ep

    async def fake_list_voices():
        return [
            {"ShortName": "af-ZA-WillemNeural", "Gender": "Male", "Locale": "af-ZA", "FriendlyName": "Willem"},
            {"ShortName": "ja-JP-NanamiNeural", "Gender": "Female", "Locale": "ja-JP", "FriendlyName": "Nanami"},
            {"ShortName": "zh-CN-XiaoxiaoNeural", "Gender": "Female", "Locale": "zh-CN", "FriendlyName": "Xiaoxiao"},
            {"ShortName": "zh-HK-HiuMaanNeural", "Gender": "Female", "Locale": "zh-HK", "FriendlyName": "HiuMaan"},
            {"ShortName": "en-US-AriaNeural", "Gender": "Female", "Locale": "en-US", "FriendlyName": "Aria"},
            {"ShortName": "en-GB-soniaMultilingualNeural", "Gender": "Female", "Locale": "en-GB", "FriendlyName": "Sonia"},
        ]

    monkeypatch.setattr(ep.edge_tts, "list_voices", fake_list_voices)
    monkeypatch.setattr(ep.EdgeTTSProvider, "_voices_cache", None)
    voices = asyncio.run(ep.EdgeTTSProvider().list_voices())
    names = [v.name for v in voices]
    assert names == ["zh-CN-XiaoxiaoNeural", "zh-HK-HiuMaanNeural", "en-US-AriaNeural", "en-GB-soniaMultilingualNeural"]


def _mock_elevenlabs(payload: dict, status_code: int, monkeypatch, capture: dict | None = None):
    """把 httpx.AsyncClient.post 替换为返回固定 ElevenLabs 响应的桩；capture 记录请求 URL。"""
    import json as _json

    import httpx
    from app.providers import elevenlabs as el

    code = status_code  # 类体内不能写 status_code = status_code（类名空间自引用会 NameError）

    class MockResp:
        status_code = code
        content = b"fake-mp3"
        text = _json.dumps(payload, ensure_ascii=False)

        def json(self):
            return payload

    class MockClient:
        def __init__(self, *a, **kw): ...

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, *a, **kw):
            if capture is not None:
                capture["url"] = url
            return MockResp()

    monkeypatch.setattr(httpx, "AsyncClient", MockClient)
    monkeypatch.setattr(el.ElevenLabsProvider, "is_configured", async_lambda(True))
    monkeypatch.setattr(el.ElevenLabsProvider, "get_config", async_lambda({"api_key": "k"}))


def test_elevenlabs_default_voice_fallback(monkeypatch):
    """未指定音色（试炼场默认值）时应回退到账号第一个音色，而不是报 param 错误。"""
    import asyncio

    from app.providers.base import BuiltinVoice, SynthParams, VoiceRef

    provider = ElevenLabsProvider()
    captured: dict = {}
    _mock_elevenlabs({"ok": True}, 200, monkeypatch, capture=captured)
    monkeypatch.setattr(
        ElevenLabsProvider,
        "list_voices",
        async_lambda([BuiltinVoice(name="voice-rachel", display_name="Rachel")]),
    )
    result = asyncio.run(provider._do_synthesize(SynthParams(text="你好"), VoiceRef()))
    assert result.data == b"fake-mp3"
    assert captured["url"].endswith("/v1/text-to-speech/voice-rachel")


def test_elevenlabs_clone_paid_plan_error(monkeypatch):
    """免费订阅克隆：payment_required 应归为 quota 并给出中文升级指引。"""
    import asyncio

    from app.providers.base import ProviderError

    provider = ElevenLabsProvider()
    payload = {
        "detail": {
            "type": "payment_required",
            "code": "paid_plan_required",
            "message": "Your subscription does not include instant voice cloning. Please upgrade your plan.",
            "status": "can_not_use_instant_voice_cloning",
        }
    }
    _mock_elevenlabs(payload, 400, monkeypatch)
    try:
        asyncio.run(provider.clone(b"audio-bytes", "测试音色", None))
        assert False, "应当抛出 ProviderError"
    except ProviderError as exc:
        assert exc.kind == "quota"
        assert "不支持即时声音克隆" in exc.message
        assert "SiliconFlow" in exc.message


def test_elevenlabs_unknown_error_keeps_server_message(monkeypatch):
    """未识别的错误保留服务端原文，状态码正确归类。"""
    import asyncio

    from app.providers.base import ProviderError

    provider = ElevenLabsProvider()
    _mock_elevenlabs({"detail": {"message": "weird internal failure", "status": "something_new"}}, 401, monkeypatch)
    try:
        asyncio.run(provider.clone(b"audio-bytes", "测试音色", None))
        assert False, "应当抛出 ProviderError"
    except ProviderError as exc:
        assert exc.kind == "auth"
        assert "weird internal failure" in exc.message


def test_indextts_call_data_and_language():
    """IndexTTS：26 参数顺序组装、语言映射、语速→时长系数取倒数、情绪模式切换。"""
    from app.providers.index_tts import IndexTTSProvider

    p = IndexTTSProvider()
    assert p._map_language(None, "你好世界") == "ZH"
    assert p._map_language(None, "hello world") == "EN"
    assert p._map_language(None, "こんにちは") == "JA"
    assert p._map_language("en", "你好世界") == "EN"  # 显式指定优先
    assert p._map_language(None, "……") == "ZH"  # 无法判断时兜底中文

    data = p._build_call_data("你好。", r"C:\tmp\ref.mp3", "ZH", 0.5, "")
    assert len(data) == 26
    assert data[0] == "与音色参考音频相同"  # 无情绪描述 → 与参考音频相同
    assert data[1] == {"path": r"C:\tmp\ref.mp3", "meta": {"_type": "gradio.FileData"}}
    assert data[2] == "你好。"
    assert data[3] == "ZH"
    assert data[17] == 0.5  # duration_factor 原样传入（由调用方取倒数）

    data_emo = p._build_call_data("你好。", "ref", "EN", 1.0, "疲惫地低声说")
    assert data_emo[0] == "使用情感向量控制"  # 有语气描述 → 情感向量控制模式
    assert data_emo[14] == "疲惫地低声说"


def test_indextts_output_path_extraction():
    from app.providers.base import ProviderError
    from app.providers.index_tts import IndexTTSProvider

    p = IndexTTSProvider()
    # IndexTTS WebUI 实际返回：gr.Audio 更新对象包装
    wrapped = [{"visible": True, "value": {"path": r"C:\tmp\out.wav", "url": "http://x"}}]
    assert p._extract_output_path(wrapped) == r"C:\tmp\out.wav"
    assert p._extract_output_path([r"C:\tmp\out.wav"]) == r"C:\tmp\out.wav"
    try:
        p._extract_output_path([])
        assert False, "应当抛出 ProviderError"
    except ProviderError:
        pass


def test_minimax_error_mapping(monkeypatch):
    import asyncio

    from app.providers.base import ProviderError, SynthParams, VoiceRef

    provider = MinimaxProvider()
    _mock_httpx({"base_resp": {"status_code": 1004, "status_msg": "invalid api key"}}, monkeypatch)
    try:
        asyncio.run(provider._do_synthesize(SynthParams(text="x"), VoiceRef()))
        assert False, "应当抛出 ProviderError"
    except ProviderError as exc:
        assert exc.kind == "auth"


def test_edge_language_mismatch_preflight():
    """非中文音色读中文文本应提前拦截并给出可操作提示（不发起网络请求）。"""
    import asyncio

    from app.providers.base import ProviderError, SynthParams, VoiceRef
    from app.providers.edge_tts_provider import EdgeTTSProvider, _text_lang, _voice_locale

    assert _text_lang("你好世界") == "zh"
    assert _text_lang("こんにちは") == "ja"
    assert _text_lang("hello world") == "en"
    assert _text_lang("你好世界，hi") == "zh"
    assert _voice_locale("af-ZA-WillemNeural") == "af-ZA"
    assert _voice_locale("zh-CN-XiaoxiaoNeural") == "zh-CN"

    provider = EdgeTTSProvider()
    try:
        asyncio.run(
            provider._do_synthesize(
                SynthParams(text="理赔快了，跑腿少了"),
                VoiceRef(kind="builtin", voice_name="af-ZA-WillemNeural"),
            )
        )
        assert False, "应当抛出 ProviderError"
    except ProviderError as exc:
        assert exc.kind == "param"
        assert "不支持朗读中文" in exc.message

    # 多语言音色不拦截语言预检（后续可能因网络失败，但报错不应是语言不匹配）
    try:
        asyncio.run(
            provider._do_synthesize(
                SynthParams(text="你好世界"),
                VoiceRef(kind="builtin", voice_name="en-US-AvaMultilingualNeural"),
            )
        )
    except ProviderError as exc:
        assert "不支持朗读中文" not in exc.message

    try:
        asyncio.run(provider._do_synthesize(SynthParams(text="  "), VoiceRef(kind="builtin", voice_name="zh-CN-XiaoxiaoNeural")))
        assert False, "空文本应当抛出 ProviderError"
    except ProviderError as exc:
        assert exc.kind == "param" and "文本为空" in exc.message
