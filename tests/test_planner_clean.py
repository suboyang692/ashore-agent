"""规划 Agent 的排期依据清理（D7 发现的思维链外泄）。"""
from app.planner_agent import clean_reason

REAL_LEAK = (
    "函数极值距Day1已隔2天（满足间隔\u22652天要求），且仍有1题未做（共2题\u2192已做2题？"
    "校验：学情显示\u2018练1次\u2019，题库共2题\u2192实为1题未做，Day1已覆盖2题？不\u2014\u2014Day1任务为"
    "\u2018重做错题1道 + 新题1道\u2019，即2题全部完成；故Day4无新极值题，转为错题深度复盘。"
)


def test_clean_reason_removes_self_verification():
    out = clean_reason(REAL_LEAK)
    assert "校验" not in out
    assert "不\u2014\u2014" not in out
    assert out.startswith("函数极值距Day1已隔2天")


def test_clean_reason_keeps_normal_reason():
    ok = "泰勒展开掌握度0.00（错1/练1），题库仅1题但已做完，需结合公式推导强化。"
    assert clean_reason(ok) == ok


def test_clean_reason_handles_empty():
    assert clean_reason("") == ""
    assert clean_reason(None) == ""
