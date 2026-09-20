"""把真题解析的 Markdown 导入题库。

输入是 app/exam_ocr.py 的转录产物（knowledge/*.md，带 `<!-- page: N -->` 页码锚点），
本脚本负责把它拆成一道一道的题：题号、题干、选项、答案、解析、页码。

知识点不猜：只导入 db/exam_2023_math2.py 里人工标过的题号。没标注的题打印一行提示
跳过，宁可少入库也不让线代题被标成高数知识点 —— 学情画像和规划 Agent 全靠这个字段。

用法:
    python db/import_exam.py --dry-run        # 只打印解析结果，不写库
    python db/import_exam.py                  # 解析并写库
    python db/import_exam.py --md knowledge/xxx.md
幂等: 每次先删掉 source='2023年数学二真题' 的旧题及其答题记录，再重新插入。
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import BASE_DIR
from app.db import execute, query_all, query_one
from db.exam_2023_math2 import ANSWERS, EXAM_SOURCE, SUBJECT, TAGS

DEFAULT_MD = BASE_DIR / "knowledge" / "2023年考研数学二参考答案及解析.md"

COMMENT = re.compile(r"<!--.*?-->", re.S)
PAGE_MARK = re.compile(r"<!--\s*page:\s*(\d+)\s*-->")
QNUM = re.compile(r"(?m)^\((\d{1,2})\)\s*")
OPTION = re.compile(r"(?m)^\(([ABCD])\)\s*")
ANSWER_LINE = re.compile(r"【答案】\s*(.+)")
ANALYSIS_MARK = re.compile(r"【解析】")
BLANK_MARK = ("____", "\\underline", "＿", "\\qquad")


def squash(text: str) -> str:
    """把多行压成一行（选项里的 cases 环境会有换行，不压平会撑爆 stem）。"""
    return re.sub(r"\s+", " ", text).strip()


def parse(md_path: Path):
    raw = md_path.read_text(encoding="utf-8")
    anchors = [(m.start(), int(m.group(1))) for m in PAGE_MARK.finditer(raw)]
    # 等长替换成空格：注释清掉了，但字符位置不变，题号坐标仍然能对上页码
    clean = COMMENT.sub(lambda m: " " * len(m.group(0)), raw)

    def page_of(pos: int) -> int:
        page = 0
        for start, no in anchors:
            if start <= pos:
                page = no
            else:
                break
        return page

    marks = list(QNUM.finditer(clean))
    items = []
    for i, mark in enumerate(marks):
        no = int(mark.group(1))
        start = mark.end()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(clean)
        seg = clean[start:end].strip()
        if not seg:
            continue

        cut = ANALYSIS_MARK.search(seg)
        head = seg[:cut.start()] if cut else seg
        analysis = seg[cut.end():].strip() if cut else ""

        ans_match = ANSWER_LINE.search(head)
        answer = ans_match.group(1).strip() if ans_match else ""
        if ans_match:
            head = head[:ans_match.start()]

        opts = list(OPTION.finditer(head))
        if opts:
            stem = head[:opts[0].start()].strip()
            options = []
            for j, o in enumerate(opts):
                stop = opts[j + 1].start() if j + 1 < len(opts) else len(head)
                options.append(f"({o.group(1)}) " + squash(head[o.end():stop]))
            qtype = "选择"
        else:
            stem, options = head.strip(), []
            qtype = "填空" if any(b in seg for b in BLANK_MARK) else "解答"

        if no in ANSWERS:                       # 解答题的标准答案转录里没有，人工补
            answer = ANSWERS[no]
        elif qtype == "选择":
            letters = re.findall(r"[A-D]", answer)
            answer = letters[0] if letters else answer
        if qtype == "填空":
            answer = answer.strip().strip("。.；;，,")

        # 卷面排版信息（本题满分 N 分）不是题干，剥掉
        stem = re.sub(r"^（本题满分\s*\d+\s*分）\s*", "", stem.strip()).strip()
        if options:
            stem = stem + "\n" + " | ".join(options)
        if analysis:
            analysis = f"{analysis}\n\n（转录自 2023年考研数学二参考答案及解析.pdf 第 {page_of(mark.start())} 页）"

        items.append({
            "no": no, "page": page_of(mark.start()), "qtype": qtype,
            "stem": stem, "answer": answer, "analysis": analysis, "options": options,
        })
    return items


def report(items):
    print(f"解析出 {len(items)} 道题：")
    print(f"  {'题号':<4}{'页':<4}{'题型':<6}{'标注':<6}{'答案':<26}题干")
    for it in items:
        tagged = "有" if it["no"] in TAGS else "缺"
        stem = it["stem"].split("\n")[0]
        print(f"  ({it['no']:<2}) {it['page']:<4}{it['qtype']:<6}{tagged:<6}"
              f"{squash(it['answer'])[:24]:<26}{stem[:46]}")
    missing = [it["no"] for it in items if it["no"] not in TAGS]
    empty = [it["no"] for it in items if not it["stem"] or not it["answer"]]
    print()
    if missing:
        print(f"[warn] 这些题没有人工标注，将跳过：{missing}")
    if empty:
        print(f"[warn] 这些题题干或答案为空，将跳过：{empty}")
    return [it for it in items if it["no"] in TAGS and it["stem"] and it["answer"]]


def save(items):
    ids = [r["id"] for r in query_all("SELECT id FROM questions WHERE source=%s", (EXAM_SOURCE,))]
    if ids:
        marks = ",".join(["%s"] * len(ids))
        n = execute(f"DELETE FROM answer_records WHERE question_id IN ({marks})", ids)
        m = execute("DELETE FROM questions WHERE source=%s", (EXAM_SOURCE,))
        print(f"[clean] 清掉旧真题 {m} 道、关联答题记录 {n} 条")

    for it in items:
        chapter, kp, diff = TAGS[it["no"]]
        execute(
            """INSERT INTO questions
               (subject, chapter, knowledge_point, question_type, stem, answer, analysis, difficulty, source)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (SUBJECT, chapter, kp, it["qtype"], it["stem"], it["answer"],
             it["analysis"], diff, EXAM_SOURCE),
        )
    total = query_one("SELECT COUNT(*) AS c FROM questions")["c"]
    print(f"[ok] 导入 {len(items)} 道真题（source={EXAM_SOURCE}），题库共 {total} 道")
    rows = query_all(
        "SELECT knowledge_point AS kp, COUNT(*) AS c FROM questions WHERE source=%s GROUP BY knowledge_point ORDER BY c DESC",
        (EXAM_SOURCE,),
    )
    print("  按知识点分布：" + "、".join(f"{r['kp']}({r['c']})" for r in rows))


def main():
    args = sys.argv[1:]
    dry = "--dry-run" in args
    md_path = DEFAULT_MD
    if "--md" in args:
        md_path = Path(args[args.index("--md") + 1])
    if not md_path.exists():
        print(f"找不到转录结果：{md_path}\n先跑：python -m app.exam_ocr knowledge/raw/<真题>.pdf")
        sys.exit(1)

    items = parse(md_path)
    ready = report(items)
    if dry:
        print("\n（--dry-run：没有写库）")
        return
    save(ready)


if __name__ == "__main__":
    main()
