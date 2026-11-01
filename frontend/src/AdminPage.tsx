import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  Activity, Ban, CheckCircle2, ChevronLeft, ChevronRight,
  RefreshCw, Search, ShieldCheck, Users,
} from "lucide-react";
import {
  getAdminAuditLogs, getAdminOverview, getAdminUsers,
  setAdminUserRole, setAdminUserStatus,
  type AdminOverview, type AdminUser, type AuditLog, type Session,
} from "./api";
import { formatTime } from "./format";
import PageHeader from "./PageHeader";

const PAGE_SIZE = 20;
const actionLabels: Record<string, string> = {
  "auth.login": "登录",
  "auth.login_failed": "登录失败",
  "auth.register": "注册",
  "admin.user_status": "修改用户状态",
  "admin.user_role": "修改用户角色",
};

function AdminSkeleton() {
  return <div className="skeleton-stack" aria-label="正在加载管理数据">
    <div className="skeleton-row skeleton-short" />
    <div className="skeleton-row" />
    <div className="skeleton-row" />
    <div className="skeleton-row" />
  </div>;
}

function actionText(action: string) {
  return actionLabels[action] ?? action;
}

export default function AdminPage({ session }: { session: Session }) {
  const [tab, setTab] = useState<"overview" | "users">("overview");
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [audits, setAudits] = useState<AuditLog[]>([]);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [query, setQuery] = useState("");
  const [draftQuery, setDraftQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [usersLoading, setUsersLoading] = useState(false);
  const [mutatingId, setMutatingId] = useState<string | null>(null);
  const [error, setError] = useState("");

  const loadOverview = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [summary, auditPage] = await Promise.all([
        getAdminOverview(session.token),
        getAdminAuditLogs(0, 8, session.token),
      ]);
      setOverview(summary);
      setAudits(auditPage.items);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "管理数据加载失败");
    } finally {
      setLoading(false);
    }
  }, [session.token]);

  const loadUsers = useCallback(async () => {
    setUsersLoading(true);
    setError("");
    try {
      const page = await getAdminUsers(query, offset, PAGE_SIZE, session.token);
      setUsers(page.items);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "用户列表加载失败");
    } finally {
      setUsersLoading(false);
    }
  }, [offset, query, session.token]);

  useEffect(() => { void loadOverview(); }, [loadOverview]);
  useEffect(() => {
    if (tab === "users") void loadUsers();
  }, [loadUsers, tab]);

  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setOffset(0);
    setQuery(draftQuery.trim());
  }

  async function toggleStatus(user: AdminUser) {
    if (mutatingId) return;
    const next = user.status === "active" ? "disabled" : "active";
    if (!window.confirm(`确定${next === "disabled" ? "禁用" : "启用"}用户“${user.username}”吗？`)) return;
    setMutatingId(user.id);
    setError("");
    try {
      await setAdminUserStatus(user.id, next, session.token);
      setUsers(current => current.map(item => item.id === user.id ? { ...item, status: next } : item));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "用户状态修改失败");
    } finally {
      setMutatingId(null);
    }
  }

  async function toggleRole(user: AdminUser) {
    if (mutatingId) return;
    const next = user.role === "admin" ? "student" : "admin";
    if (!window.confirm(`确定将“${user.username}”设为${next === "admin" ? "管理员" : "学生"}吗？`)) return;
    setMutatingId(user.id);
    setError("");
    try {
      await setAdminUserRole(user.id, next, session.token);
      setUsers(current => current.map(item => item.id === user.id ? { ...item, role: next } : item));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "用户角色修改失败");
    } finally {
      setMutatingId(null);
    }
  }

  return <section className="workspace-page">
    <PageHeader title="管理" description="查看运行状态、用户权限与最近操作。" action={
      <button className="secondary-button" type="button"
        onClick={() => void (tab === "overview" ? loadOverview() : loadUsers())}
        disabled={loading || usersLoading}>
        <RefreshCw size={16} />刷新
      </button>
    } />
    <div className="page-scroll">
      <div className="segmented" role="group" aria-label="管理视图">
        <button type="button" className={tab === "overview" ? "active" : ""} onClick={() => setTab("overview")}>概览</button>
        <button type="button" className={tab === "users" ? "active" : ""} onClick={() => { setTab("users"); setError(""); }}>用户</button>
      </div>

      {error ? <div className="notice error-notice" role="alert">{error}</div> : null}

      {tab === "overview" ? loading ? <AdminSkeleton /> : overview ? <>
        <section className="admin-metrics" aria-label="运行数据">
          <div><span>用户</span><strong>{overview.users}</strong></div>
          <div><span>题目</span><strong>{overview.questions}</strong></div>
          <div><span>会话</span><strong>{overview.conversations}</strong></div>
          <div><span>答题</span><strong>{overview.attempts}</strong></div>
        </section>

        <section className="admin-system">
          <div className="section-row-head"><div><Activity size={17} /><h2>运行状态</h2></div></div>
          <dl>
            <div><dt>缓存后端</dt><dd>{overview.cache.backend === "redis" ? "Redis" : "进程内降级"}</dd></div>
            <div><dt>缓存命中率</dt><dd>{Math.round(overview.cache.hit_rate * 100)}%</dd></div>
            <div><dt>知识库版本</dt><dd>{overview.cache.kb_version}</dd></div>
            <div><dt>缓存键</dt><dd>{overview.cache.keys}</dd></div>
          </dl>
        </section>

        <section className="admin-audit">
          <div className="section-row-head"><div><ShieldCheck size={17} /><h2>最近操作</h2></div><span>{audits.length} 条</span></div>
          {audits.length ? <div className="admin-audit-list">
            {audits.map(item => <article key={item.id} className="admin-audit-row">
              <span className={`admin-action${item.action.includes("failed") ? " failed" : ""}`}>{actionText(item.action)}</span>
              <div><strong>{item.actor_name || item.actor_id || "系统"}</strong><span>{item.target_id ? `目标 ${item.target_id}` : "安全事件"}</span></div>
              <time>{formatTime(item.created_at)}</time>
            </article>)}
          </div> : <p className="admin-empty">暂无审计记录</p>}
        </section>
      </> : null : <>
        <form className="admin-search" onSubmit={search}>
          <label htmlFor="admin-user-search">搜索用户</label>
          <div>
            <input id="admin-user-search" value={draftQuery} onChange={event => setDraftQuery(event.target.value)} placeholder="用户名或用户 ID" />
            <button className="secondary-button" type="submit"><Search size={16} />搜索</button>
          </div>
        </form>

        {usersLoading ? <AdminSkeleton /> : users.length ? <div className="admin-user-table" role="table" aria-label="用户列表">
          <div className="admin-user-head" role="row">
            <span role="columnheader">用户</span><span role="columnheader">角色</span>
            <span role="columnheader">状态</span><span role="columnheader">最近登录</span>
            <span role="columnheader">操作</span>
          </div>
          {users.map(user => {
            const self = user.id === session.user.id;
            const busy = mutatingId === user.id;
            return <div className="admin-user-row" role="row" key={user.id}>
              <div className="admin-user-identity" role="cell">
                <span className="avatar">{user.username.slice(0, 1).toUpperCase()}</span>
                <span><strong>{user.username}</strong><small>{user.id}</small></span>
              </div>
              <span role="cell" className={`admin-role ${user.role}`}>{user.role === "admin" ? "管理员" : "学生"}</span>
              <span role="cell" className={`admin-status ${user.status}`}>{user.status === "active" ? "启用" : "禁用"}</span>
              <time role="cell">{formatTime(user.last_login_at)}</time>
              <div className="admin-user-actions" role="cell">
                {self ? <span className="admin-self">当前账号</span> : <>
                  <button type="button" className="admin-action-button" disabled={busy} onClick={() => void toggleRole(user)}>
                    {user.role === "admin" ? <Users size={15} /> : <ShieldCheck size={15} />}
                    {user.role === "admin" ? "设为学生" : "设为管理员"}
                  </button>
                  <button type="button" className={`admin-action-button${user.status === "active" ? " danger" : ""}`} disabled={busy} onClick={() => void toggleStatus(user)}>
                    {user.status === "active" ? <Ban size={15} /> : <CheckCircle2 size={15} />}
                    {user.status === "active" ? "禁用" : "启用"}
                  </button>
                </>}
              </div>
            </div>;
          })}
        </div> : <p className="admin-empty">没有匹配的用户</p>}

        <div className="admin-pagination">
          <button className="secondary-button" type="button" disabled={offset === 0 || usersLoading} onClick={() => setOffset(value => Math.max(0, value - PAGE_SIZE))}><ChevronLeft size={16} />上一页</button>
          <span className="admin-page-number">第 {Math.floor(offset / PAGE_SIZE) + 1} 页</span>
          <button className="secondary-button" type="button" disabled={users.length < PAGE_SIZE || usersLoading} onClick={() => setOffset(value => value + PAGE_SIZE)}>下一页<ChevronRight size={16} /></button>
        </div>
      </>}
    </div>
  </section>;
}
