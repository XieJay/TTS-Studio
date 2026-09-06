"""分句与剧本解析单元测试。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.parser import split_for_task, split_paragraph, split_script


def test_basic_sentence_split():
    units = split_for_task("script", "第一句。第二句！第三句？")
    assert [u["text"] for u in units] == ["第一句。", "第二句！", "第三句？"]


def test_paragraph_gap_kept():
    text = "甲段落第一句。甲段落第二句。\n\n乙段落只有一句。"
    units = split_for_task("script", text)
    assert len(units) == 3


def test_quotes_protect_sentence_ends():
    """引号内的句末标点不切分；引号外正常切分。"""
    text = "「早上好。」他说。然后他走了。"
    units = split_paragraph(text)
    assert len(units) == 2
    assert units[0] == "「早上好。」他说。"
    # 引号内的 。 与 ！ 不切分
    inner = split_paragraph("他说：「今天真好。我们走吧！」然后就走了。")
    assert len(inner) == 1


def test_long_sentence_secondary_split():
    text = "这是一个非常长的句子，" * 15 + "最后一点。"
    units = split_paragraph(text, max_len=60)
    assert len(units) >= 2


def test_dialogue_script_parsing():
    script = "旁白: 夜幕降临。\n小明(兴奋): 我们到了！\n小红：嘘。"
    lines = split_script(script)
    assert lines[0]["role"] == "旁白" and lines[0]["emotion"] == ""
    assert lines[1]["role"] == "小明" and lines[1]["emotion"] == "兴奋"
    assert lines[2]["role"] == "小红"  # 中文冒号


def test_dialogue_no_colon_goes_narrator():
    lines = split_script("这是没有冒号的一行")
    assert lines[0]["role"] == "旁白"
    assert lines[0]["text"] == "这是没有冒号的一行"


def test_empty_lines_ignored():
    units = split_for_task("script", "\n\n  \n有内容。\n\n")
    assert len(units) == 1
