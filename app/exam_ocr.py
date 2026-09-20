"""真题 PDF -> Markdown（视觉模型逐页转录）。

为什么不用 pdfplumber：
这份真题解析的公式是矢量图形，PDF 文本层里只有中文和数字。直接抽会得到
「(1)曲线 的斜渐近线为 (A) (B)」这种到处是空洞的骨架 —— 入库只会污染检索，
检索到也没法回答。所以改成：每页渲染成 PNG -> 视觉模型逐字转录成 Markdown+LaTeX。

页码锚点：
转录结果里每页前面写一行 `<!-- page: N -->`，`app/ingest.py` 按页切片并把页码
写进切片元数据，检索结果的出处才能显示成「文件名 · 第N页」而不是只有文件名。

断点续跑：
每页的 PNG 与转录 md 都落盘在 data/ocr_cache/<pdf名>/ 下，已存在就跳过。
重复执行不会重复烧 token，中途断了重跑也只补没做完的页。

用法:
    python -m app.exam_ocr knowledge/raw/xxx.pdf
    python -m app.exam_ocr knowledge/raw/xxx.pdf --pages 1-3,7
    python -m app.exam_ocr knowledge/raw/xxx.pdf --out knowledge/xxx.md --force
"""
import argparse
import base64
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from openai import OpenAI

from app.config import BASE_DIR, DASHSCOPE_API_KEY, LLM_BASE_URL

VL_MODEL = "qwen-vl-max"
DPI = 150          # 150 够看清上下标；再高只是白烧 token
WORKERS = 3        # 视觉模型单页 30s 上下，3 路并发够用又不容易被限流

CACHE_DIR = BASE_DIR / "data" / "ocr_cache"

PROMPT = (
    "这是考研数学真题解析的一页。请把它逐字转录成 Markdown，要求：\n"
    "1. 所有数学公式转成 LaTeX：行内用 $...$，独立成行用 $$...$$；\n"
    "2. 保留原文题号（如 (1)、（11））、【答案】、【解析】标签和选项 A/B/C/D；\n"
    "3. 不要翻译、不要改写、不要总结、不要补充原文没有的内容；\n"
    "4. 忽略页眉、页脚和机构水印（如「正保考研」广告）；\n"
    "5. 只输出转录后的 Markdown 正文，不要任何解释性开场白或收尾语。"
)


MID = re.compile(r"\\mid(?![a-zA-Z])")


def normalize_latex(text: str) -> str:
    """转录后处理：把视觉模型写歪的 LaTeX 掰回来。

    只做一条：qwen-vl 会把绝对值 |x| 转录成 \\mid x \\mid。\\mid 在 LaTeX 里是
    关系符（整除、集合分隔），考研题面里基本不出现，而绝对值出现频率极高，
    所以统一还原成 | 的收益远大于风险。在**合并阶段**做，因此不需要重跑 API。
    """
    return MID.sub("|", text)


def _client() -> OpenAI:
    if not DASHSCOPE_API_KEY or DASHSCOPE_API_KEY.startswith("sk-在这里"):
        raise RuntimeError("请先在 .env 配置 DASHSCOPE_API_KEY")
    return OpenAI(api_key=DASHSCOPE_API_KEY, base_url=LLM_BASE_URL)


def parse_pages(spec: str, total: int):
    """'1-3,7' -> [1,2,3,7]；非法/越界的页码直接报错，不静默跳过。"""
    pages = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            pages.extend(range(int(a), int(b) + 1))
        else:
            pages.append(int(part))
    bad = [p for p in pages if p < 1 or p > total]
    if bad:
        raise ValueError(f"页码越界：{bad}（该 PDF 共 {total} 页）")
    return sorted(set(pages))


def render_pages(pdf_path: Path, page_nos, cache_dir: Path, dpi: int = DPI):
    """把指定页渲染成 PNG。已缓存的不重复渲染（渲染比调用便宜，但没必要重复做）。"""
    import pdfplumber

    cache_dir.mkdir(parents=True, exist_ok=True)
    out = []
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        if page_nos is None:
            page_nos = list(range(1, total + 1))
        for n in page_nos:
            png = cache_dir / f"p{n:02d}.png"
            if not png.exists():
                pdf.pages[n - 1].to_image(resolution=dpi).save(str(png))
            out.append((n, png))
    return out, total


def transcribe_page(png_path: Path, model: str = VL_MODEL) -> str:
    """一页 PNG -> Markdown。视觉模型有时会抖，失败交给上层重试。"""
    b64 = base64.b64encode(png_path.read_bytes()).decode()
    resp = _client().chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            {"type": "text", "text": PROMPT},
        ]}],
    )
    return (resp.choices[0].message.content or "").strip()


def build(pdf_path: Path, out_path: Path, pages=None, force=False,
          workers: int = WORKERS, model: str = VL_MODEL) -> int:
    cache_dir = CACHE_DIR / pdf_path.stem
    rendered, total = render_pages(pdf_path, pages, cache_dir)
    print(f"[render] {pdf_path.name}：共 {total} 页，本次处理 {len(rendered)} 页（PNG 缓存 {cache_dir}）")

    todo = []
    for n, png in rendered:
        md = cache_dir / f"p{n:02d}.md"
        if md.exists() and not force:
            print(f"  [cache] 第 {n} 页已有转录结果，跳过（--force 可强制重做）")
        else:
            todo.append((n, png, md))

    if todo:
        print(f"[ocr] {len(todo)} 页待转录，模型 {model}，并发 {workers}")
        t0 = time.time()
        done = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(transcribe_page, png, model): (n, md) for n, png, md in todo}
            for fut in as_completed(futs):
                n, md = futs[fut]
                try:
                    text = fut.result()
                except Exception as e:          # 单页失败不拖垮整批，重跑即可补齐
                    print(f"  [fail] 第 {n} 页：{type(e).__name__}: {e}")
                    continue
                md.write_text(text, encoding="utf-8")
                done += 1
                print(f"  [ok] 第 {n} 页 {len(text)} 字（{done}/{len(todo)}，耗时 {time.time() - t0:.0f}s）")
        if done < len(todo):
            print(f"[warn] {len(todo) - done} 页失败，重新执行同一条命令即可续跑")

    parts = [f"<!-- source: {pdf_path.name} | 由 app/exam_ocr.py 用 {model} 逐页转录 -->"]
    got = 0
    for n, _png in rendered:
        md = cache_dir / f"p{n:02d}.md"
        if not md.exists():
            print(f"[warn] 第 {n} 页没有转录结果，已从合并结果中剔除")
            continue
        parts.append(f"<!-- page: {n} -->\n" + normalize_latex(md.read_text(encoding="utf-8")).strip())
        got += 1
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n\n".join(parts) + "\n", encoding="utf-8")
    print(f"[out] {out_path}（{got} 页）")
    return got


def main():
    ap = argparse.ArgumentParser(description="真题 PDF -> Markdown（视觉模型转录）")
    ap.add_argument("pdf", help="PDF 路径")
    ap.add_argument("--out", default=None, help="输出 md 路径，默认 knowledge/<pdf名>.md")
    ap.add_argument("--pages", default=None, help="只处理这些页，如 1-3,7；默认全部")
    ap.add_argument("--force", action="store_true", help="忽略缓存，重新转录")
    ap.add_argument("--workers", type=int, default=WORKERS)
    ap.add_argument("--model", default=VL_MODEL)
    args = ap.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"文件不存在：{pdf_path}")
        sys.exit(1)
    out_path = Path(args.out) if args.out else BASE_DIR / "knowledge" / f"{pdf_path.stem}.md"

    # 需要先知道总页数才能校验 --pages
    import pdfplumber
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
    pages = parse_pages(args.pages, total) if args.pages else None

    got = build(pdf_path, out_path, pages=pages, force=args.force,
                workers=args.workers, model=args.model)
    if got:
        print(f"\n下一步：python -m app.ingest {out_path.relative_to(BASE_DIR).as_posix()}")


if __name__ == "__main__":
    main()
