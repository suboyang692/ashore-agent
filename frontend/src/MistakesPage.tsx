import { useCallback, useEffect, useState } from "react";
import { RefreshCw, Search } from "lucide-react";
import { getMistakes, type Mistake, type Session } from "./api";
import { formatTime } from "./format";
import PageHeader from "./PageHeader";
import QuestionContent from "./QuestionContent";

export default function MistakesPage({ session }: { session: Session }) {
  const [knowledgePoint, setKnowledgePoint] = useState("");
  const [mistakeType, setMistakeType] = useState("");
  const [items, setItems] = useState<Mistake[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await getMistakes(session.user.id, knowledgePoint, mistakeType, session.token);
      setItems(result.items);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "错题加载失败");
    } finally {
      setLoading(false);
    }
  }, [knowledgePoint, mistakeType, session.token, session.user.id]);

  useEffect(() => { void load(); }, [load]);

  return <section className="workspace-page">
    <PageHeader title="错题" description="按知识点和错因回看已经暴露的问题。" action={
      <button className="secondary-button" type="button" onClick={() => void load()} disabled={loading}><RefreshCw size={16} />刷新</button>
    } />
    <div className="page-scroll">
      <form className="filter-bar" onSubmit={event => { event.preventDefault(); void load(); }}>
        <label><span>知识点</span><input value={knowledgePoint} onChange={event => setKnowledgePoint(event.target.value)} placeholder="全部知识点" /></label>
        <label><span>错因</span><input value={mistakeType} onChange={event => setMistakeType(event.target.value)} placeholder="全部错因" /></label>
        <button className="primary" type="submit" disabled={loading}><Search size={17} />筛选</button>
      </form>
      {error ? <div className="notice error-notice" role="alert">{error}</div> : null}
      {loading ? <div className="state-message">正在加载错题…</div> : items.length === 0 ? <div className="empty-state"><h2>还没有符合条件的错题</h2><p>完成练习后，错因会记录在这里。</p></div> : <div className="record-list">
        {items.map(item => <article className="record" key={item.id}>
          <div className="record-top"><span className="record-kp">{item.knowledge_point || "未标注知识点"}</span><span className="record-type">{item.mistake_type}</span><time dateTime={item.submitted_at}>{formatTime(item.submitted_at)}</time></div>
          <QuestionContent stem={item.stem} choice={item.question_type === "选择"} />
          <details className="record-details"><summary>查看错因与订正</summary>
            <dl><div><dt>你的作答</dt><dd>{item.original_text || "—"}</dd></div><div><dt>原因</dt><dd>{item.reason || "—"}</dd></div><div><dt>订正方向</dt><dd>{item.correct_method || "—"}</dd></div></dl>
          </details>
        </article>)}
      </div>}
    </div>
  </section>;
}
