import { useId, useState } from "react";
import { ChevronDown, FileText } from "lucide-react";
import type { AnswerSource } from "./api";
import MathText from "./MathText";

function SourceGroup({ title, sources }: { title: string; sources: AnswerSource[] }) {
  return <section className="source-group">
    <h3>{title}</h3>
    {sources.map(source => <div className="source-excerpt" key={`${source.cite}-${source.fragment}`}>
      <div className="source-excerpt-head">
        <span>{source.source}</span>
        {source.page !== null ? <span>第 {source.page} 页</span> : null}
      </div>
      <MathText>{source.excerpt}</MathText>
    </div>)}
  </section>;
}

export default function AnswerSources({ sources }: { sources: AnswerSource[] }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  if (sources.length === 0) return null;

  const cited = sources.filter(source => source.cited);
  const others = sources.filter(source => !source.cited);
  const hasCitations = cited.length > 0;
  const visible = cited.length > 0 ? cited : others.slice(0, 2);
  const remaining = (cited.length > 0 ? others.length : Math.max(0, others.length - 2));

  return <div className="answer-sources">
    <div className="source-summary">
      <div className="source-summary-label"><FileText size={15} /><span>{hasCitations ? "出处" : "相关讲义"} · {cited.length || sources.length} 条</span></div>
      <button className="source-toggle" type="button" aria-expanded={open} aria-controls={id} onClick={() => setOpen(value => !value)}>
        {open ? "收起原文" : "查看原文"}<ChevronDown size={16} className={open ? "flipped" : ""} />
      </button>
    </div>
    <ul className="source-cites">
      {visible.map(source => <li key={`${source.cite}-${source.fragment}`}>
        <span className="source-name">{source.source}</span>
        {source.page !== null ? <span>第 {source.page} 页</span> : null}
      </li>)}
      {remaining > 0 ? <li className="source-more">另有 {remaining} 条参考资料</li> : null}
    </ul>
    {open ? <div className="source-drawer" id={id}>
      {!hasCitations ? <p className="source-note">回答未明确引用以下片段，可作为相关讲义参考。</p> : null}
      {cited.length > 0 ? <SourceGroup title="回答引用" sources={cited} /> : null}
      {others.length > 0 ? <SourceGroup title={cited.length > 0 ? "其他参考资料" : "本次检索"} sources={others} /> : null}
    </div> : null}
  </div>;
}
