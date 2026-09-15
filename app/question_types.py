"""研岸 D12：题型枚举的唯一来源。

背景（真实踩过的坑）：
    种子数据写「选择 / 填空 / 解答」，但模型出题时按提示词很容易输出
    「选择题 / 填空题 / 解答题」。而判分分流是按字符串精确匹配的——
    practice.judge 里 `== "选择"` 才走选项字母比对，api 的 /submit 里
    `== "解答"` 才转批改 Agent，grader_agent.pick_subjective 更是写死
    `WHERE question_type = '解答'`。多一个「题」字就会静默走到错误分支：
    不报错，只是判错，或者那道题永远抽不出来。

    更隐蔽的是同一个枚举在项目里有两套比对方式：quiz_agent 用
    `"选择" in qtype`（子串，能容忍「选择题」），判分用 `== "选择"`
    （不能容忍）。两处不一致，脏数据能过其中一道却卡在另一道。

所以收敛到这一处：
    - 入库统一过 normalize_question_type()，认不出来的直接拒绝，不让脏数据落库；
    - 分流统一用 is_choice / is_blank / is_subjective，不再手写字符串字面量；
    - 数据库层用 ENUM 兜底（见 db/schema.sql 与 db/migrate_question_type.py）。

注意：这里的判定是**严格**的——只认三种标准写法。这是刻意的：数据在写入时就
已经收敛过、数据库还有 ENUM 兜底，读取侧再去容错只会把数据问题藏起来。
"""
from __future__ import annotations

import re

CHOICE = "选择"
BLANK = "填空"
SOLUTION = "解答"

TYPES = (CHOICE, BLANK, SOLUTION)
OBJECTIVE_TYPES = (CHOICE, BLANK)          # 走精确判分的题型

# 「…题」写法与少量同义词都收敛到上面三种
_ALIASES = {
    "选择": CHOICE, "选择题": CHOICE, "单选题": CHOICE, "单选": CHOICE,
    "填空": BLANK, "填空题": BLANK,
    "解答": SOLUTION, "解答题": SOLUTION, "计算": SOLUTION, "计算题": SOLUTION,
    "证明": SOLUTION, "证明题": SOLUTION, "简答": SOLUTION, "简答题": SOLUTION,
}


def _type_of(q) -> str:
    """允许传整道题（dict）或单独的题型字符串。"""
    raw = q.get("question_type") if isinstance(q, dict) else q
    return str(raw or "")


def normalize_question_type(raw) -> str:
    """把各种写法收敛成三种标准题型；认不出来抛 ValueError。

    刻意不返回「未知题型」这种兜底值：入库口宁可拒绝这道题，
    也不要让一个判分时认不出的值悄悄进库。
    """
    text = re.sub(r"[\s\u3000]+", "", _type_of(raw))
    if text in _ALIASES:
        return _ALIASES[text]
    raise ValueError(f"未知题型 {raw!r}：只支持 {'/'.join(TYPES)}（或它们的「…题」写法）")


def is_choice(q) -> bool:
    return _type_of(q) == CHOICE


def is_blank(q) -> bool:
    return _type_of(q) == BLANK


def is_subjective(q) -> bool:
    return _type_of(q) == SOLUTION


def is_objective(q) -> bool:
    return _type_of(q) in OBJECTIVE_TYPES
