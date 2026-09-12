"""出题 Agent 的答案规范化（D6 修的两个判分隐患）。"""
from app.quiz_agent import (
    clean_analysis,
    clean_answer,
    coerce_choice_answer,
    final_answer,
    strip_blank_prefix,
)

OPTIONS = "A. f(1) > 2 | B. f(1) > e | C. f(1) > 2e | D. f(1) > 4e"
BLANK_STEM = "设 f(x) 在 [1,2] 上连续，则存在 \u03be \u2208 (1,2)，使得 f\u2032(\u03be) = ________。"


def test_clean_answer_strips_model_prefix():
    assert clean_answer("math:1") == "1"
    assert clean_answer("Math: 0") == "0"


def test_clean_answer_unwraps_latex_wrappers():
    assert clean_answer("$1/2$") == "1/2"
    assert clean_answer(r"\text{1/2}") == "1/2"


def test_coerce_choice_maps_option_text_to_letter():
    """模型直接写选项内容会导致选择题判分失效，必须反查成字母。"""
    assert coerce_choice_answer("f(1) > 2e", OPTIONS) == "C"


def test_coerce_choice_passes_through_letter():
    assert coerce_choice_answer("b", OPTIONS) == "B"


def test_coerce_choice_keeps_raw_when_unmatched():
    assert coerce_choice_answer("完全对不上", OPTIONS) == "完全对不上"


def test_strip_blank_prefix_removes_repeated_lhs():
    """题干已给出等号左边时，答案只该保留空处的值。"""
    assert strip_blank_prefix("f\u2032(\u03be) = \u03be\u00b2 - 1/3", BLANK_STEM) == "\u03be\u00b2 - 1/3"


def test_strip_blank_prefix_keeps_answer_without_blank():
    stem = "证明：存在 \u03be \u2208 (0,2)，使得 f\u2032(\u03be) = 2\u03be。"
    assert strip_blank_prefix("f\u2032(\u03be) = 2\u03be", stem) == "f\u2032(\u03be) = 2\u03be"


def test_final_answer_routes_by_question_type():
    assert final_answer({"question_type": "选择", "options": OPTIONS,
                         "stem": "x", "answer": "f(1) > 2e"}) == "C"
    assert final_answer({"question_type": "填空", "options": "",
                         "stem": BLANK_STEM, "answer": "f\u2032(\u03be) = \u03be\u00b2 - 1/3"}) == "\u03be\u00b2 - 1/3"
    assert final_answer({"question_type": "解答", "options": "",
                         "stem": "证明", "answer": "存在 \u03be"}) == "存在 \u03be"


def test_clean_analysis_drops_self_correction_trace():
    out = clean_analysis("先按错的思路算了一遍。此前分析有误，正确路径是泰勒展开。")
    assert "此前分析有误" not in out
    assert out == "正确路径是泰勒展开。"


def test_clean_analysis_leaves_normal_text_touched():
    text = "由罗尔定理得 f\u2032(\u03be) = 0，代入即得结论。"
    assert clean_analysis(text) == text
