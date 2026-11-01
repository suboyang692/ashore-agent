import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowRight, CheckCircle2, PencilLine, RotateCcw, XCircle } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError, getNextQuestion, submitAnswer, type ObjectiveResult, type Question, type Session, type SubmitResult, type SubjectiveResult } from "./api";
import MathText from "./MathText";
import PageHeader from "./PageHeader";
import QuestionContent, { splitChoiceOptions } from "./QuestionContent";

const filters = ["全部", "选择", "填空", "解答"] as const;
type Filter = (typeof filters)[number];

type PracticeState = {
  point: string;
  question: Question | null;
  answer: string;
  result: SubmitResult | null;
  loading: boolean;
  empty: boolean;
  submitting: boolean;
  error: string;
};

function blankPracticeState(point = ""): PracticeState {
  return {
    point, question: null, answer: "", result: null,
    loading: true, empty: false, submitting: false, error: "",
  };
}

function ResultPanel({ result }: { result: SubmitResult }) {
  const objective = result as ObjectiveResult;
  const subjective = result as SubjectiveResult;
  return <section className={`result-panel ${result.type === "objective" && !objective.correct ? "wrong" : "correct"}`} aria-live="polite">
    <div className="result-heading">
      {result.type === "objective"
        ? objective.correct ? <><CheckCircle2 size={21} /><strong>回答正确</strong></> : <><XCircle size={21} /><strong>回答有误</strong></>
        : <><PencilLine size={21} /><strong>{subjective.score} 分</strong><span>{subjective.mistake_type}</span></>}
    </div>
    {result.type === "subjective" ? <>
      <p>{subjective.comment}</p>
      <p className="muted">{subjective.suggestion}</p>
    </> : null}
    {result.type === "objective" && objective.mastery ? <p className="muted">该知识点掌握度 {Math.round(Number(objective.mastery.mastery) * 100)}% · 已练 {objective.mastery.total_count} 次 / 错 {objective.mastery.wrong_count} 次</p> : null}
    <div className="answer-block"><span>标准答案</span><MathText>{result.standard_answer || "暂无"}</MathText></div>
    <div className="answer-block"><span>解析</span><MathText>{result.analysis || "暂无解析"}</MathText></div>
  </section>;
}

export default function PracticePage({ session }: { session: Session }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const knowledgePoint = searchParams.get("knowledge_point")?.trim() ?? "";
  const [filter, setFilter] = useState<Filter>("全部");
  const [states, setStates] = useState<Partial<Record<Filter, PracticeState>>>({});
  const loadToken = useRef<Partial<Record<Filter, number>>>({});
  const resultRef = useRef<HTMLDivElement>(null);

  const loadQuestion = useCallback(async (targetFilter: Filter, point: string) => {
    const sequence = (loadToken.current[targetFilter] ?? 0) + 1;
    loadToken.current[targetFilter] = sequence;
    setStates(current => ({
      ...current,
      [targetFilter]: { ...blankPracticeState(point), loading: true },
    }));
    try {
      const question = await getNextQuestion(
        session.user.id, targetFilter === "全部" ? "" : targetFilter, point, session.token,
      );
      if (loadToken.current[targetFilter] !== sequence) return;
      setStates(current => ({
        ...current,
        [targetFilter]: { ...blankPracticeState(point), question, loading: false },
      }));
    } catch (cause) {
      if (loadToken.current[targetFilter] !== sequence) return;
      const empty = cause instanceof ApiError && cause.status === 404;
      setStates(current => ({
        ...current,
        [targetFilter]: {
          ...blankPracticeState(point),
          loading: false,
          empty,
          error: empty ? "" : cause instanceof Error ? cause.message : "取题失败，请稍后重试",
        },
      }));
    }
  }, [session.token, session.user.id]);

  const initialLoad = useRef(false);
  useEffect(() => {
    if (!initialLoad.current) {
      initialLoad.current = true;
      void loadQuestion("全部", knowledgePoint);
    }
  }, [knowledgePoint, loadQuestion]);
  const previousPoint = useRef(knowledgePoint);
  useEffect(() => {
    if (previousPoint.current !== knowledgePoint) {
      previousPoint.current = knowledgePoint;
      setStates({});
      void loadQuestion(filter, knowledgePoint);
    }
  }, [filter, knowledgePoint, loadQuestion]);

  const active = states[filter] ?? blankPracticeState(knowledgePoint);
  useEffect(() => {
    if (active.result) resultRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [active.result]);

  function updateState(target: Filter, patch: Partial<PracticeState>) {
    setStates(current => ({
      ...current,
      [target]: { ...(current[target] ?? blankPracticeState(knowledgePoint)), ...patch },
    }));
  }

  function chooseFilter(next: Filter) {
    if (next === filter) return;
    setFilter(next);
    const saved = states[next];
    if (!saved || saved.point !== knowledgePoint) void loadQuestion(next, knowledgePoint);
  }

  function clearKnowledgePoint() {
    const next = new URLSearchParams(searchParams);
    next.delete("knowledge_point");
    setSearchParams(next);
  }

  const choiceOptions = active.question?.question_type === "选择"
    ? splitChoiceOptions(active.question.stem).options
    : [];
  const hasChoiceOptions = choiceOptions.length >= 2;

  async function submit(chosen?: string) {
    const targetFilter = filter;
    const current = states[targetFilter];
    const question = current?.question;
    const response = chosen ?? current?.answer ?? "";
    if (!question || !response.trim() || current.submitting || current.result) return;
    updateState(targetFilter, { submitting: true, error: "" });
    try {
      const result = await submitAnswer(session.user.id, question.id, response, session.token);
      setStates(latest => {
        const saved = latest[targetFilter];
        if (!saved?.question || saved.question.id !== question.id) return latest;
        return { ...latest, [targetFilter]: { ...saved, result, submitting: false, error: "" } };
      });
    } catch (cause) {
      setStates(latest => {
        const saved = latest[targetFilter];
        if (!saved?.question || saved.question.id !== question.id) return latest;
        return {
          ...latest,
          [targetFilter]: {
            ...saved,
            submitting: false,
            error: cause instanceof Error ? cause.message : "提交失败，请稍后重试",
          },
        };
      });
    }
  }

  return <section className="workspace-page">
    <PageHeader title="练习" description="从题库取一道未做过的题，提交后查看结果。" action={
      <button className="secondary-button" type="button" onClick={() => void loadQuestion(filter, knowledgePoint)} disabled={active.loading || active.submitting}><RotateCcw size={16} />换一题</button>
    } />
    <div className="page-scroll">
      {knowledgePoint ? <div className="focus-filter">
        <span>当前知识点：<strong>{knowledgePoint}</strong></span>
        <button type="button" onClick={clearKnowledgePoint}>清除筛选</button>
      </div> : null}
      <div className="segmented" role="group" aria-label="筛选题型">
        {filters.map(value => <button key={value} type="button" className={filter === value ? "active" : ""} onClick={() => chooseFilter(value)}>{value}</button>)}
      </div>
      {active.error ? <div className="notice error-notice" role="alert">{active.error}{!active.question ? <button type="button" onClick={() => void loadQuestion(filter, knowledgePoint)}>重新取题</button> : null}</div> : null}
      {active.loading ? <div className="state-message">正在取题…</div> : active.question ? <article className="question-panel">
        <div className="question-meta"><span>{active.question.question_type}</span><span>{active.question.knowledge_point}</span><span>难度 {active.question.difficulty ?? "—"}</span></div>
        <QuestionContent stem={active.question.stem} choice={active.question.question_type === "选择"} selected={hasChoiceOptions ? active.answer : null} disabled={Boolean(active.result) || active.submitting} onSelect={hasChoiceOptions ? key => { updateState(filter, { answer: key }); void submit(key); } : undefined} />
        {hasChoiceOptions ? (active.submitting || active.result) ? <div className="answer-form choice-answer">
          {active.submitting ? <p className="choice-hint">正在判分…</p> : null}
          {active.result ? <button className="primary" type="button" onClick={() => void loadQuestion(filter, knowledgePoint)}><ArrowRight size={17} />下一题</button> : null}
        </div> : null : <form className="answer-form" onSubmit={event => { event.preventDefault(); void submit(); }}>
          <label htmlFor="practice-answer">{active.question.question_type === "解答" ? "写下完整解答过程" : "输入你的答案"}</label>
          <textarea id="practice-answer" value={active.answer} onChange={event => updateState(filter, { answer: event.target.value })} placeholder={active.question.question_type === "解答" ? "写出关键步骤和结论" : "请输入你的答案"} disabled={Boolean(active.result)} />
          {active.result ? <button className="primary" type="button" onClick={() => void loadQuestion(filter, knowledgePoint)}><ArrowRight size={17} />下一题</button>
            : <button className="primary" type="submit" disabled={!active.answer.trim() || active.submitting}>{active.submitting ? "正在批改…" : "提交作答"}<ArrowRight size={17} /></button>}
        </form>}
      </article> : active.empty ? <div className="empty-state">
        <h2>{knowledgePoint ? `「${knowledgePoint}」暂时没有未做过的题` : "暂时没有可取的新题"}</h2>
        <p>{knowledgePoint ? "可以清除知识点筛选查看全部题目，或回到答疑继续提问。" : "题库可能已经做完，稍后再试或换一种题型。"}</p>
        <div className="empty-actions">
          {knowledgePoint
            ? <button className="primary" type="button" onClick={clearKnowledgePoint}>查看全部题目</button>
            : <button className="primary" type="button" onClick={() => void loadQuestion(filter, knowledgePoint)}>重新取题</button>}
          <Link className="secondary-button" to="/chat">回到答疑</Link>
        </div>
      </div> : null}
      {active.result ? <div ref={resultRef}><ResultPanel result={active.result} /></div> : null}
    </div>
  </section>;
}
