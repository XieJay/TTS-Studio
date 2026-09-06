"""ffmpeg / ffprobe 封装：探测、时长、（后续里程碑）合并与变速。

探测顺序：系统 PATH → winget 包目录 → 项目 tools/ 目录（便携版）。
"""
import asyncio
import json
import shutil
import sys
from pathlib import Path

from ..config import TOOLS_DIR

_ffmpeg: str | None = None
_ffprobe: str | None = None


def _winget_candidates() -> list[Path]:
    local = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
    if sys.platform != "win32" or not local.exists():
        return []
    return sorted(local.glob("Gyan.FFmpeg*/**/bin/ffmpeg.exe"))


def find_ffmpeg() -> str | None:
    global _ffmpeg
    if _ffmpeg:
        return _ffmpeg
    found = shutil.which("ffmpeg")
    if found:
        _ffmpeg = found
        return found
    for cand in _winget_candidates():
        if cand.exists():
            _ffmpeg = str(cand)
            return _ffmpeg
    tools = TOOLS_DIR.rglob("ffmpeg.exe") if TOOLS_DIR.exists() else []
    for cand in tools:
        _ffmpeg = str(cand)
        return _ffmpeg
    return None


def find_ffprobe() -> str | None:
    global _ffprobe
    if _ffprobe:
        return _ffprobe
    ff = find_ffmpeg()
    if not ff:
        return None
    probe = Path(ff).with_name(("ffprobe.exe" if sys.platform == "win32" else "ffprobe"))
    _ffprobe = str(probe) if probe.exists() else shutil.which("ffprobe") or ff.replace("ffmpeg", "ffprobe")
    return _ffprobe


def ffmpeg_available() -> bool:
    return find_ffmpeg() is not None


async def probe_duration_ms(path: str | Path) -> int | None:
    ffprobe = find_ffprobe()
    if not ffprobe:
        return None
    try:
        proc = await asyncio.create_subprocess_exec(
            ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", str(path),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            return None
        duration = float(json.loads(stdout)["format"]["duration"])
        return round(duration * 1000)
    except Exception:  # noqa: BLE001
        return None
