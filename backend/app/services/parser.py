"""文件解析与智能分句。

- 解析：txt（UTF-8/GBK 自动尝试）、md（去标记保留纯文本）、docx（python-docx 按段落）
- 分句：段落（空行）→ 句末标点切分（引号内不切）→ 长句按逗号/顿号二次切分
- 多角色剧本解析：`角色名: 台词` / `角色名(情绪): 台词`，无冒号行归旁白
"""
import re
from pathlib import Path

# 句末标点（含中英文）
_SENT_END = "。！？!?…；;"
_SUB_DELIMS = "，,、；;：:"

_MD_NOISE = re.compile(r"^#{1,6}\s+|^\s*[-*+]\s+|^\s*>\s?|\*\*|__|`|\[|\]\([^)]*\)")


def read_docx(content: bytes) -> list[str]:
    import io

    from docx import Document
    doc = Document(io.BytesIO(content))
    return [p.text.strip() for p in doc.paragraphs if p.text.strip()]


def read_text(content: bytes) -> str:
    for enc in ("utf-8", "gbk", "utf-16"):
        try:
            return content.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return content.decode("utf-8", errors="replace")


def parse_document(filename: str, content: bytes) -> list[str]:
    """解析上传文件为段落列表。"""
    suffix = Path(filename).suffix.lower()
    if suffix == ".docx":
        return read_docx(content)
    text = read_text(content)
    if suffix == ".md":
        text = "\n".join(_MD_NOISE.sub("", line) for line in text.splitlines())
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def split_paragraph(paragraph: str, max_len: int = 100) -> list[str]:
    """把一个段落切分为句子单元；引号内的句末标点不切分。"""
    sentences: list[str] = []
    buf = ""
    quote_chars = "「」『』\"\"''《》"
    open_quotes = "「『\"'《"
    depth = 0
    for ch in paragraph:
        buf += ch
        if ch in open_quotes:
            depth += 1
        elif ch in quote_chars:
            depth = max(0, depth - 1)
        elif depth == 0 and ch in _SENT_END:
            if buf.strip():
                sentences.append(buf.strip())
            buf = ""
    if buf.strip():
        sentences.append(buf.strip())

    # 长句按逗号/顿号二次切分
    result: list[str] = []
    for s in sentences:
        if len(s) <= max_len:
            result.append(s)
            continue
        piece = ""
        for ch in s:
            piece += ch
            if ch in _SUB_DELIMS and len(piece) >= max_len // 2:
                result.append(piece.strip())
                piece = ""
        if piece.strip():
            result.append(piece.strip())
    return result


def split_script(text: str) -> list[dict]:
    """多角色剧本解析：返回 [{role, emotion, text}]。无冒号行 role=旁白。"""
    lines: list[dict] = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        role, emotion, body = "旁白", "", raw
        m = re.match(r"^([^\s:：（()）]{1,12})(?:[（(]([^)）]{1,8})[）)])?\s*[:：]\s*(.+)$", raw)
        if m:
            role, emotion, body = m.group(1), (m.group(2) or "").strip(), m.group(3).strip()
        for s in split_paragraph(body):
            lines.append({"role": role, "emotion": emotion, "text": s})
    return lines


def split_for_task(mode: str, text: str) -> list[dict]:
    """任务内容 → 句子列表。

    - script（单音色）：[{text}]
    - dialogue（多角色）：[{role, emotion, text}]
    """
    if mode == "dialogue":
        return split_script(text)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out: list[dict] = []
    for para in paragraphs:
        for s in split_paragraph(para):
            out.append({"text": s})
    return out
