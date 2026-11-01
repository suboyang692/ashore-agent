"""答疑结构化来源的纯函数测试，不调用真实模型。"""
from app.graph_agent import extract_sources


class ToolMessage:
    type = "tool"

    def __init__(self, content):
        self.content = content


def test_extract_sources_marks_explicit_fragment_citation():
    messages = [ToolMessage(
        "[片段1 | 出处: 讲义.md · 第9页 | 命中方式: vector]\n定积分换元要同步换上下限。\n\n"
        "[片段2 | 出处: 真题.md · 第3页 | 命中方式: bm25]\n另一个相关片段。"
    )]
    answer = "换元时上下限也要一起换。\n来源：片段1"

    sources = extract_sources(messages, answer)

    assert [s["cite"] for s in sources] == ["讲义.md · 第9页", "真题.md · 第3页"]
    assert [s["cited"] for s in sources] == [True, False]
    assert sources[0]["page"] == 9


def test_extract_sources_matches_full_citation_line():
    messages = [ToolMessage(
        "[片段1 | 出处: 2023解析.md · 第1页 | 命中方式: vector]\n斜渐近线先求 a 再求 b。"
    )]
    answer = "来源：2023解析.md · 第1页。"

    assert extract_sources(messages, answer)[0]["cited"] is True


def test_extract_sources_matches_page_range_citation():
    messages = [ToolMessage(
        "[片段1 | 出处: 讲义.md · 第8页 | 命中方式: vector]\n甲\n\n"
        "[片段2 | 出处: 讲义.md · 第9页 | 命中方式: vector]\n乙\n\n"
        "[片段3 | 出处: 讲义.md · 第11页 | 命中方式: vector]\n丙\n\n"
        "[片段4 | 出处: 讲义.md · 第12页 | 命中方式: vector]\n丁"
    )]
    answer = "来源：讲义.md · 第8-11页"

    sources = extract_sources(messages, answer)

    assert [s["cited"] for s in sources] == [True, True, True, False]


def test_extract_sources_does_not_guess_ambiguous_fragment_numbers():
    messages = [ToolMessage(
        "[片段1 | 出处: 甲.md · 第1页 | 命中方式: vector]\n甲\n\n"
        "[片段1 | 出处: 乙.md · 第2页 | 命中方式: bm25]\n乙"
    )]

    sources = extract_sources(messages, "来源：片段1")

    assert [s["cited"] for s in sources] == [False, False]


def test_extract_sources_empty_without_tool_results():
    assert extract_sources([], "来源：片段1") == []
