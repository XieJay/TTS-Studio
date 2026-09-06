"""ffmpeg 音频处理：整段合并（句间停顿）、SRT 字幕、ZIP 打包导出。"""
import asyncio
import zipfile
from pathlib import Path

from ..config import TASK_AUDIO_DIR, TMP_DIR, DEFAULT_LINE_GAP_MS, MAX_LINE_GAP_MS
from ..db import connect
from .audio import find_ffmpeg, probe_duration_ms


async def _run_ffmpeg(args: list[str], cwd: Path | None = None) -> None:
    ff = find_ffmpeg()
    if not ff:
        raise RuntimeError("未检测到 ffmpeg，无法执行音频处理")
    proc = await asyncio.create_subprocess_exec(
        ff, *args, cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg 失败：{stderr.decode(errors='replace')[:300]}")


async def _standardize(src: Path, dst: Path, cwd: Path) -> None:
    """统一重采样 44.1kHz 双声道 16bit wav，保证不同引擎产物可拼接。"""
    await _run_ffmpeg(
        ["-y", "-i", str(src), "-ar", "44100", "-ac", "2", "-sample_fmt", "s16", dst.name], cwd
    )


async def _silence_name(duration_ms: int, cwd: Path, cache: dict[int, str]) -> str:
    """生成（或复用）指定时长的静音 wav，返回 cwd 相对文件名；concat 列表可多处引用同一文件。"""
    ms = max(0, min(duration_ms, MAX_LINE_GAP_MS))
    if ms not in cache:
        name = f"sil_{ms}.wav"
        await _run_ffmpeg(
            ["-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
             "-t", f"{ms / 1000:.3f}", "-sample_fmt", "s16", name],
            cwd,
        )
        cache[ms] = name
    return cache[ms]


def _srt_time(ms: int) -> str:
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, msec = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{msec:03d}"


async def load_done_lines(task_id: str) -> list[dict]:
    async with connect() as conn:
        cur = await conn.execute(
            "SELECT id, idx, text, status, audio_path, duration_ms, gap_after_ms "
            "FROM lines WHERE task_id=? ORDER BY idx",
            (task_id,),
        )
        rows = [dict(r) for r in await cur.fetchall()]
    return [r for r in rows if r["status"] == "done" and r["audio_path"]]


async def build_srt(task_id: str) -> str:
    lines = await load_done_lines(task_id)
    blocks, start = [], 0
    for i, ln in enumerate(lines, 1):
        dur = ln["duration_ms"] or 0
        gap = ln["gap_after_ms"] if ln["gap_after_ms"] is not None else DEFAULT_LINE_GAP_MS
        blocks.append(f"{i}\n{_srt_time(start)} --> {_srt_time(start + dur)}\n{ln['text']}\n")
        start += dur + gap
    return "\n".join(blocks)


async def merge_task(task_id: str, fmt: str = "mp3") -> Path:
    """合并任务所有已合成句子为整段音频，返回输出文件路径。"""
    lines = await load_done_lines(task_id)
    if not lines:
        raise RuntimeError("没有已合成的句子，请先完成合成")

    work = TMP_DIR / f"merge_{task_id}_{fmt}"
    work.mkdir(parents=True, exist_ok=True)

    # 1) 标准化每个句子片段
    std_names: list[str] = []
    for i, ln in enumerate(lines):
        src = TASK_AUDIO_DIR / ln["audio_path"]
        std_name = f"std_{i:04d}.wav"
        await _standardize(src, work / std_name, work)
        std_names.append(std_name)

    # 2) 生成各句后静音段（按毫秒值缓存复用）
    silence_cache: dict[int, str] = {}
    entries: list[str] = []
    for i, ln in enumerate(lines):
        entries.append(f"file '{std_names[i]}'")
        gap = ln["gap_after_ms"] if ln["gap_after_ms"] is not None else DEFAULT_LINE_GAP_MS
        if i < len(lines) - 1 and gap > 0:
            entries.append(f"file '{await _silence_name(gap, work, silence_cache)}'")

    list_file = work / "list.txt"
    list_file.write_text("\n".join(entries), encoding="utf-8")

    # 3) 拼接并编码
    out_name = f"merged.{fmt}"
    if fmt == "mp3":
        encode = ["-b:a", "192k"]
    else:
        encode = ["-c:a", "pcm_s16le"]
    await _run_ffmpeg(["-y", "-f", "concat", "-safe", "0", "-i", "list.txt", *encode, out_name], work)

    out = TASK_AUDIO_DIR / task_id / "merged"
    out.mkdir(parents=True, exist_ok=True)
    result = out / out_name
    result.write_bytes((work / out_name).read_bytes())
    return result


async def export_zip(task_id: str, title: str) -> Path:
    """打包：合并音频 + 逐句编号音频 + 稿件文本 + SRT 字幕。"""
    lines = await load_done_lines(task_id)
    if not lines:
        raise RuntimeError("没有已合成的句子，请先完成合成")

    merged = await merge_task(task_id, "mp3")
    srt = await build_srt(task_id)
    script_text = "\n".join(ln["text"] for ln in lines)

    zip_path = TASK_AUDIO_DIR / task_id / "merged" / "export.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(merged, f"{title}_合并.mp3")
        zf.writestr(f"{title}.srt", srt)
        zf.writestr(f"{title}_稿件.txt", script_text)
        for i, ln in enumerate(lines, 1):
            src = TASK_AUDIO_DIR / ln["audio_path"]
            if src.exists():
                summary = ln["text"][:12].replace("/", " ").replace("\\", " ")
                zf.write(src, f"sentences/{i:02d}_{summary}{src.suffix}")
    return zip_path
