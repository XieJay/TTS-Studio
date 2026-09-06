"""路径与全局常量。"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # TTS 根目录
BACKEND_DIR = BASE_DIR / "backend"

DATA_DIR = BASE_DIR / "data"
AUDIO_DIR = DATA_DIR / "audio"
VOICE_AUDIO_DIR = AUDIO_DIR / "voices"      # 音色参考音频/试听样本
TASK_AUDIO_DIR = AUDIO_DIR / "tasks"        # 任务句子音频与合并产物
TMP_DIR = DATA_DIR / "tmp"
DB_PATH = DATA_DIR / "tts.db"
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
TOOLS_DIR = BASE_DIR / "tools"              # 可选：便携版 ffmpeg 存放处

VOICE_MAX_UPLOAD_MB = 20
DOC_MAX_UPLOAD_MB = 5
DEFAULT_SYNTH_TIMEOUT = 120.0
DEFAULT_LINE_GAP_MS = 300
MAX_LINE_GAP_MS = 2000
BATCH_CONCURRENCY = 2

DEFAULT_LLM_CONFIG = {
    "base_url": "",
    "api_key": "",
    "model": "",
}


def ensure_dirs() -> None:
    for d in (DATA_DIR, AUDIO_DIR, VOICE_AUDIO_DIR, TASK_AUDIO_DIR, TMP_DIR):
        d.mkdir(parents=True, exist_ok=True)
