import { useCallback, useEffect, useState } from "react";
import { RefreshCw, RotateCcw } from "lucide-react";
import { getAdminJobs, retryAdminJob, type JobItem, type Session } from "./api";
import { formatTime } from "./format";

const PAGE_SIZE = 20;
const statusLabels: Record<string, string> = {
  pending: "等待中",
  running: "执行中",
  success: "成功",
  failed: "失败",
  cancelled: "已取消",
};

export default function AdminJobs({ session }: { session: Session }) {
  const [jobs, setJobs] = useState<JobItem[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [retrying, setRetrying] = useState<string | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const page = await getAdminJobs(offset, PAGE_SIZE, session.token);
      setJobs(page.items);
      setTotal(page.total);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "任务列表加载失败");
    } finally {
      setLoading(false);
    }
  }, [offset, session.token]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!jobs.some(item => item.status === "pending" || item.status === "running")) return;
    const timer = window.setInterval(() => { void load(); }, 3000);
    return () => window.clearInterval(timer);
  }, [jobs, load]);

  async function retry(job: JobItem) {
    if (retrying) return;
    if (!window.confirm("确定重新执行这个任务吗？")) return;
    setRetrying(job.id);
    setError("");
    try {
      await retryAdminJob(job.id, session.token);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "任务重试失败");
    } finally {
      setRetrying(null);
    }
  }

  return <>
    <div className="admin-list-toolbar">
      <span>共 {total} 个任务</span>
      <button className="secondary-button" type="button" onClick={() => void load()} disabled={loading}><RefreshCw size={15} />刷新</button>
    </div>
    {error ? <div className="notice error-notice" role="alert">{error}</div> : null}
    {loading && !jobs.length ? <div className="state-message">正在加载任务…</div> : jobs.length ? <div className="admin-job-list">
      {jobs.map(job => {
        const source = typeof job.payload?.source_name === "string" ? job.payload.source_name : job.job_type;
        return <article className="admin-job-row" key={job.id}>
          <div className="admin-job-copy">
            <strong>{source}</strong>
            <span>{job.id}</span>
            {job.error_message ? <small>{job.error_message}</small> : null}
          </div>
          <span className={`admin-doc-status ${job.status}`}>{statusLabels[job.status] ?? job.status}</span>
          <div className="admin-job-progress">
            <span>{job.progress}%</span>
            <div><i style={{ width: `${job.progress}%` }} /></div>
          </div>
          <time>{formatTime(job.created_at)}</time>
          <button className="admin-action-button" type="button"
            disabled={job.status !== "failed" || retrying !== null}
            onClick={() => void retry(job)}>
            <RotateCcw size={14} />{retrying === job.id ? "提交中…" : "重试"}
          </button>
        </article>;
      })}
    </div> : <p className="admin-empty">还没有异步任务</p>}

    <div className="admin-pagination">
      <button className="secondary-button" type="button" disabled={offset === 0 || loading} onClick={() => setOffset(value => Math.max(0, value - PAGE_SIZE))}>上一页</button>
      <span className="admin-page-number">第 {Math.floor(offset / PAGE_SIZE) + 1} 页</span>
      <button className="secondary-button" type="button" disabled={offset + PAGE_SIZE >= total || loading} onClick={() => setOffset(value => value + PAGE_SIZE)}>下一页</button>
    </div>
  </>;
}
