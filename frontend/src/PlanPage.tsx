import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowRight, CalendarDays, Check, CheckCircle2, LoaderCircle, RefreshCw,
} from "lucide-react";
import {
  ApiError, completePlanItem, createPlan, getLatestPlan,
  type PlanItem, type ReviewPlan, type Session,
} from "./api";
import { formatTime } from "./format";
import PageHeader from "./PageHeader";

const dayOptions = [7, 14, 21] as const;

function PlanSkeleton() {
  return <div className="skeleton-stack" aria-label="正在加载复习计划">
    <div className="skeleton-row skeleton-short" />
    <div className="skeleton-row" />
    <div className="skeleton-row" />
    <div className="skeleton-row skeleton-short" />
  </div>;
}

function groupItems(items: PlanItem[]) {
  const grouped = new Map<number, PlanItem[]>();
  for (const item of items) {
    const current = grouped.get(item.day_no) ?? [];
    current.push(item);
    grouped.set(item.day_no, current);
  }
  return [...grouped.entries()].sort(([left], [right]) => left - right);
}

export default function PlanPage({ session }: { session: Session }) {
  const [plan, setPlan] = useState<ReviewPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [completingId, setCompletingId] = useState<number | null>(null);
  const [days, setDays] = useState<number>(7);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setPlan(await getLatestPlan(session.user.id, session.token));
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 404) {
        setPlan(null);
      } else {
        setError(cause instanceof Error ? cause.message : "复习计划加载失败");
      }
    } finally {
      setLoading(false);
    }
  }, [session.token, session.user.id]);

  useEffect(() => { void load(); }, [load]);

  const groups = useMemo(() => groupItems(plan?.items ?? []), [plan]);
  const items = plan?.items ?? [];
  const completed = items.filter(item => item.status === "completed").length;
  const percent = items.length ? Math.round(completed / items.length * 100) : 0;

  async function generate() {
    if (creating) return;
    setCreating(true);
    setError("");
    try {
      await createPlan(session.user.id, days, session.token);
      setPlan(await getLatestPlan(session.user.id, session.token));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "计划生成失败，请稍后重试");
    } finally {
      setCreating(false);
    }
  }

  async function markComplete(item: PlanItem) {
    if (item.status === "completed" || completingId !== null) return;
    setCompletingId(item.id);
    setError("");
    try {
      const updated = await completePlanItem(item.id, session.user.id, session.token);
      setPlan(current => current ? {
        ...current,
        items: current.items?.map(value => value.id === updated.id ? { ...value, ...updated } : value),
      } : current);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "计划项更新失败");
    } finally {
      setCompletingId(null);
    }
  }

  return <section className="workspace-page">
    <PageHeader title="规划" description="按学情诊断安排复习节奏，逐项完成计划。" action={
      <button className="secondary-button" type="button" onClick={() => void load()} disabled={loading}>
        <RefreshCw size={16} />刷新
      </button>
    } />
    <div className="page-scroll">
      {error ? <div className="notice error-notice" role="alert">{error}</div> : null}
      {loading ? <PlanSkeleton /> : plan ? <>
        <section className="plan-overview">
          <div>
            <span className="plan-overview-label">当前计划</span>
            <strong>{plan.days} 天</strong>
            <span>生成于 {formatTime(plan.created_at)}</span>
          </div>
          <div className="plan-progress">
            <div className="plan-progress-copy"><span>任务完成</span><strong>{completed} / {items.length || "—"}</strong></div>
            <div className="plan-progress-track" role="progressbar" aria-label="计划完成度" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}>
              <span style={{ width: `${percent}%` }} />
            </div>
          </div>
        </section>

        <section className="plan-summary"><h2>学情诊断</h2><p>{plan.summary}</p></section>

        <div className="plan-toolbar">
          <div><span className="field-label">计划周期</span>
            <div className="segmented" role="group" aria-label="选择计划周期">
              {dayOptions.map(value => <button key={value} type="button" className={days === value ? "active" : ""} onClick={() => setDays(value)}>{value} 天</button>)}
            </div>
          </div>
          <button className="primary" type="button" onClick={() => void generate()} disabled={creating}>
            {creating ? <><LoaderCircle className="spin" size={17} />正在生成…</> : <>生成新计划<ArrowRight size={17} /></>}
          </button>
        </div>

        <div className="plan-days">
          {groups.length ? groups.map(([day, dayItems]) => <section className="plan-day" key={day}>
            <div className="plan-day-head"><CalendarDays size={17} /><h2>第 {day} 天</h2><span>{dayItems.filter(item => item.status === "completed").length} / {dayItems.length} 已完成</span></div>
            <div className="plan-task-list">
              {dayItems.map(item => {
                const done = item.status === "completed";
                const busy = completingId === item.id;
                return <article className={`plan-task${done ? " done" : ""}`} key={item.id}>
                  <button className={`plan-check${done ? " done" : ""}`} type="button" title={done ? "已完成" : "标记完成"} aria-label={done ? `${item.knowledge_point}已完成` : `标记${item.knowledge_point}完成`} aria-pressed={done} disabled={done || busy} onClick={() => void markComplete(item)}>
                    {busy ? <LoaderCircle className="spin" size={16} /> : done ? <CheckCircle2 size={18} /> : <Check size={17} />}
                  </button>
                  <div className="plan-task-copy">
                    <strong>{item.knowledge_point}</strong>
                    <span>{item.task_type} · 目标 {item.target_count} 道</span>
                  </div>
                  <span className="plan-task-type">{done ? "已完成" : item.status === "overdue" ? "已逾期" : "待完成"}</span>
                </article>;
              })}
            </div>
          </section>) : plan.schedule.length ? <section className="plan-schedule">
            <h2>计划安排</h2>
            {plan.schedule.map(day => <article className="plan-schedule-day" key={day.day}>
              <div className="plan-day-head"><CalendarDays size={17} /><h3>第 {day.day} 天</h3><span>{day.focus}</span></div>
              <p>{day.tasks}</p>
              <small>{day.reason}</small>
            </article>)}
          </section> : null}
        </div>
      </> : <div className="empty-state plan-empty">
        <CalendarDays size={28} className="empty-inline-icon" />
        <h2>还没有复习计划</h2>
        <p>从学情诊断开始，把薄弱知识点拆成每天能完成的小任务。</p>
        <div className="empty-actions">
          <div className="segmented" role="group" aria-label="选择计划周期">
            {dayOptions.map(value => <button key={value} type="button" className={days === value ? "active" : ""} onClick={() => setDays(value)}>{value} 天</button>)}
          </div>
          <button className="primary" type="button" onClick={() => void generate()} disabled={creating}>
            {creating ? "正在生成…" : "生成复习计划"}<ArrowRight size={17} />
          </button>
        </div>
      </div>}
    </div>
  </section>;
}
