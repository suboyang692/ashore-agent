/**
 * 前端渲染逻辑测试（答案里的 Markdown + LaTeX 混合内容）。
 *
 * 运行: node tests/js/test_render.js       （需 Node 18+，与 pytest 互不影响）
 *
 * 为什么单独测：公式渲染和换行处理是两套逻辑，容易互相打架。
 * 曾出现过的 bug：auto-render 只在单个文本节点里找公式，而换行被切成 <br> 后
 * 跨行的 $$ 块直接匹配不到——肉眼看不出，只能靠断言。
 */
const fs = require('fs');
const path = require('path');

const INDEX = path.join(__dirname, '..', '..', 'web', 'index.html');
const html = fs.readFileSync(INDEX, 'utf8');
const start = html.indexOf('/* --- mathify:start');
const end = html.indexOf('/* --- mathify:end --- */');
if (start === -1 || end === -1) {
  console.error('未在 web/index.html 找到 mathify 抽取标记');
  process.exit(1);
}
const source = html.slice(html.indexOf('\n', start) + 1, end);

/* ---------- 最小假 DOM ---------- */
function makeEl(tag) {
  return {
    tag: tag || 'div',
    className: '',
    children: [],
    _text: '',
    appendChild(c) { this.children.push(c); return c; },
    set textContent(v) { this._text = v; this.children = []; },
    get textContent() { return this._text; }
  };
}
global.document = {
  createElement: (tag) => makeEl(tag),
  createTextNode: (t) => ({ nodeText: t })
};
global.window = {
  katex: { render: (tex, span, opt) => { span.__tex = tex; span.__display = !!opt.display; } }
};

eval(source);

function walk(node, out) {
  out = out || [];
  for (const c of node.children || []) {
    if (c.__tex !== undefined) out.push({kind: 'math', tex: c.__tex, display: !!c.__display});
    else if (c.nodeText !== undefined) out.push({kind: 'text', value: c.nodeText});
    else if (c.tag === 'br') out.push({kind: 'br'});
    else {
      out.push({kind: 'el', tag: c.tag, cls: c.className});
      if (c._text) out.push({kind: 'text', value: c._text});
      walk(c, out);
    }
  }
  return out;
}
const allText = (el) => walk(el).filter(x => x.kind === 'text').map(x => x.value).join('');

/* ---------- 用例 ---------- */
let pass = 0, fail = 0;
function check(name, input, pred) {
  const el = makeEl();
  setRichText(el, input);
  const flat = walk(el);
  let ok = false;
  try { ok = pred(flat, el); } catch (e) { ok = false; }
  if (ok) { pass++; console.log('  PASS ' + name); }
  else { fail++; console.log('  FAIL ' + name + '\n        ' + JSON.stringify(flat)); }
}

check('多行 $$ 块 -> display 公式', '前文\n$$\n\\int_a^b f(x)\\,dx = F(b)-F(a)\n$$\n后文',
  f => f.some(x => x.kind === 'math' && x.display && x.tex.includes('int_a^b')));
check('行内 $...$ -> inline 公式', '设 $f(x)=x^2$ 则导数为 $2x$',
  f => f.filter(x => x.kind === 'math' && !x.display).length === 2);
check('\\[...\\] -> display 公式', '\\[ E = mc^2 \\]',
  f => f.some(x => x.kind === 'math' && x.display && x.tex === 'E = mc^2'));
check('\\(...\\) -> inline 公式', '结果是 \\(x=1\\)。',
  f => f.some(x => x.kind === 'math' && !x.display && x.tex === 'x=1'));
check('多行块里的 cases 环境', '$$\n\\begin{cases} 1 & n\\text{ 偶} \\\\ 2 & n\\text{ 奇} \\end{cases}\n$$',
  f => f.some(x => x.kind === 'math' && x.tex.includes('begin{cases}')));
check('未闭合的 $ 当普通文本（货币符号不误判）', '单价 5$ 一共 10$ 元',
  f => f.some(x => x.kind === 'text' && x.value.includes('单价 5$')));
check('**加粗** -> strong', '这是 **牛顿-莱布尼茨公式** 方法',
  f => f.some(x => x.kind === 'el' && x.tag === 'strong'));
check('`行内代码` -> code', '公式 `f(x)=x^2` 的写法',
  f => f.some(x => x.kind === 'el' && x.tag === 'code'));
check('### 标题 -> md-h 块', '### 定积分',
  f => f.some(x => x.kind === 'el' && x.cls === 'md-h'));
check('来源行 -> src 块', '正文\n来源：片段1、片段4',
  f => f.some(x => x.kind === 'el' && x.cls === 'src'));
check('加粗跨公式片段时不露星号', '设 **$F(x)$ 是原函数** 则',
  (f, el) => !allText(el).includes('**'));
check('正常加粗内容保留', '**分部积分法**：适用于乘积',
  (f, el) => allText(el).includes('分部积分法') && !allText(el).includes('**'));
check('换行转 <br>', 'a\nb\nc', f => f.filter(x => x.kind === 'br').length === 2);
check('KaTeX 不可用时降级显示原文', '有公式 $x^2$ 和块 $$\ny=1\n$$',
  (f, el) => { window.__noKatex = 1; const e2 = makeEl(); setRichText(e2, '有公式 $x^2$ 和块 $$\ny=1\n$$'); const t = allText(e2); window.__noKatex = 0; return t.includes('$x^2$') && t.includes('$$'); });

console.log('\n合计: ' + pass + ' passed, ' + fail + ' failed');
process.exit(fail ? 1 : 0);
