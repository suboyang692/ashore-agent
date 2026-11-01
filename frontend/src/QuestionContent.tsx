import MathText from "./MathText";

type ChoiceOption = { key: string; text: string };

const OPTION_MARKER = /(?:^|[\s|])(?:[（(]\s*([A-D])\s*[)）]|([A-D])\s*[.．、:：])\s*/g;
const EXISTING_MATH = /(\$\$[\s\S]*?\$\$|\$[^$\n]*\$)/g;
const NON_CJK_RUN = /([^\u3400-\u9fff，。；：？！、（）【】《》]+)/g;
const MATH_SIGNAL = /[\\^_=+\-*/·×÷∫∑≤≥≠≈∞→←²³¹⁰₀₁₂₃₄₅₆₇₈₉ₑ₋₊]/;
const SUBSCRIPTS: Record<string, string> = {
  "₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4",
  "₅": "5", "₆": "6", "₇": "7", "₈": "8", "₉": "9",
  "₊": "+", "₋": "-", "ₑ": "e",
};
const SUPERSCRIPTS: Record<string, string> = {
  "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4",
  "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
  "⁺": "+", "⁻": "-",
};

function normalizeRawMath(text: string): string {
  let value = text;
  value = value.replace(/[₀-₉₊₋ₑ]+/g, run => `_{${[...run].map(char => SUBSCRIPTS[char] ?? char).join("")}}`);
  value = value.replace(/[⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]+/g, run => `^{${[...run].map(char => SUPERSCRIPTS[char] ?? char).join("")}}`);
  return value
    .replace(/∫/g, "\\int{}")
    .replace(/∑/g, "\\sum{}")
    .replace(/∞/g, "\\infty{}")
    .replace(/→/g, "\\to{}")
    .replace(/·/g, "\\cdot{}")
    .replace(/×/g, "\\times{}")
    .replace(/≤/g, "\\le{}")
    .replace(/≥/g, "\\ge{}")
    .replace(/(^|[^\\A-Za-z])(lim|sin|cos|tan|ln|log|exp)\b/g, "$1\\$2");
}

function wrapRawMath(part: string): string {
  const outer = part.match(/^(\s*)([\s\S]*?)(\s*)$/);
  if (!outer || !/[A-Za-z0-9]/.test(outer[2]) || !MATH_SIGNAL.test(outer[2])) return part;

  return outer[1] + outer[2].split(/(_{3,})/g).map(piece => {
    if (/^_{3,}$/.test(piece)) return piece;
    const inner = piece.match(/^(\s*)([\s\S]*?)(\s*)$/);
    if (!inner || !inner[2] || !MATH_SIGNAL.test(inner[2])) return piece;
    return inner[1] + `$${normalizeRawMath(inner[2])}$` + inner[3];
  }).join("") + outer[3];
}

export function normalizeQuestionMath(text: string): string {
  return text.split(EXISTING_MATH).map((part, index) => {
    if (index % 2 === 1) return part;
    return part.split(NON_CJK_RUN).map((piece, pieceIndex) => (
      pieceIndex % 2 === 1 ? wrapRawMath(piece) : piece
    )).join("");
  }).join("");
}

function formatOptionText(text: string): string {
  const source = text.trim().replace(/^\$|\$$/g, "").trim();
  const fraction = source.match(/^(-?\d+)\s*\/\s*(-?\d+)$/);
  return normalizeQuestionMath(fraction ? `$\\frac{${fraction[1]}}{${fraction[2]}}$` : text);
}

export function splitChoiceOptions(stem: string): { body: string; options: ChoiceOption[] } {
  const markers = [...stem.matchAll(OPTION_MARKER)];
  if (markers.length < 2) return { body: stem, options: [] };

  const options = markers.map((match, index) => {
    const next = markers[index + 1];
    return {
      key: match[1] ?? match[2],
      text: formatOptionText(stem.slice(match.index + match[0].length, next?.index ?? stem.length)
        .replace(/\s*\|\s*$/, "")
        .trim()),
    };
  });
  const keys = options.map(option => option.key).join("");
  if (keys !== "ABCD".slice(0, options.length) || new Set(keys).size !== options.length) {
    return { body: stem, options: [] };
  }

  return {
    body: stem.slice(0, markers[0].index).trim(),
    options,
  };
}

export default function QuestionContent({ stem, choice = false, selected, disabled = false, onSelect }: {
  stem: string; choice?: boolean; selected?: string | null;
  disabled?: boolean; onSelect?: (key: string) => void;
}) {
  const parsed = choice ? splitChoiceOptions(stem) : { body: stem, options: [] };

  return <div className="question-content">
    <MathText>{normalizeQuestionMath(parsed.body)}</MathText>
    {parsed.options.length ? <div className="choice-options" role="group" aria-label="选择题选项">
      {parsed.options.map(option => {
        const active = selected === option.key;
        const content = <>
          <span className="choice-key" aria-hidden="true">{option.key}</span>
          <div className="choice-text"><MathText>{option.text}</MathText></div>
        </>;
        return onSelect
          ? <button className={`choice-option interactive${active ? " selected" : ""}`} type="button" aria-pressed={active} disabled={disabled} key={option.key} onClick={() => onSelect(option.key)}>{content}</button>
          : <div className={`choice-option${active ? " selected" : ""}`} key={option.key}>{content}</div>;
      })}
    </div> : null}
  </div>;
}
