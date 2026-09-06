"""发音替换规则测试。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.pronunciation import apply


def test_apply_order_and_override():
    rules = [("长城", "cháng chéng"), ("长安", "cháng'ān"), ("小明", "Xiǎomíng")]
    text = "小明去长城看长安街。"
    assert apply(text, rules) == "Xiǎomíng去cháng chéng看cháng'ān街。"


def test_empty_find_skipped():
    assert apply("原文", [("", "x")]) == "原文"


def test_later_rule_wins():
    """任务级规则覆盖全局的同一原文（load_rules 内按 find 去重，保留最后一条）。"""
    from app.services.pronunciation import dedupe_rules

    rules = dedupe_rules([("小明", "Xiaoming"), ("小明", "Xiǎomíng")])
    assert apply("小明", rules) == "Xiǎomíng"
